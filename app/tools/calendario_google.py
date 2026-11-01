"""Cliente Python do Google Calendar MCP e fallback para Calendar API."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from langchain.tools import tool
from pydantic import BaseModel, Field

from app.config import (
    BASE_DIR,
    GOOGLE_CALENDAR_ACCESS_TOKEN,
    GOOGLE_CALENDAR_MCP_URL,
    GOOGLE_OAUTH_CREDENTIALS,
)

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_PATH = BASE_DIR / "google-calendar.token.json"


def _credentials_path() -> Optional[Path]:
    if not GOOGLE_OAUTH_CREDENTIALS:
        return None
    path = Path(GOOGLE_OAUTH_CREDENTIALS)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path if path.is_file() else None


def _save_token(credentials) -> None:
    TOKEN_PATH.write_text(credentials.to_json(), encoding="utf-8")


def _load_token():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    if not TOKEN_PATH.is_file():
        return None
    credentials = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        _save_token(credentials)
    return credentials if credentials.valid else None


def autenticar() -> dict:
    """Executa o OAuth Desktop e salva o token da conta autenticada."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    keys = _credentials_path()
    if not keys:
        return {"status": "error", "message": "Falta gcp-oauth.keys.json na raiz do projeto."}
    flow = InstalledAppFlow.from_client_secrets_file(str(keys), SCOPES)
    credentials = flow.run_local_server(port=0, prompt="consent")
    _save_token(credentials)
    return {"status": "ok", "arquivo": str(TOKEN_PATH)}


def _access_token() -> Optional[str]:
    if GOOGLE_CALENDAR_ACCESS_TOKEN:
        return GOOGLE_CALENDAR_ACCESS_TOKEN
    credentials = _load_token()
    return credentials.token if credentials else None


def _decode_result(result: Any) -> dict:
    structured = getattr(result, "structured_content", None)
    if structured:
        return structured if isinstance(structured, dict) else {"status": "ok", "result": structured}
    texts = [getattr(block, "text", None) for block in getattr(result, "content", []) or []]
    text = next((item for item in texts if item), None)
    if not text:
        return {"status": "error", "message": "O servidor MCP não devolveu conteúdo."}
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {"status": "ok", "result": value}
    except json.JSONDecodeError:
        return {"status": "ok", "result": text}


async def _call_http(tool_name: str, arguments: dict) -> dict:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from mcp.shared._httpx_utils import create_mcp_http_client

    token = _access_token()
    if not token:
        return {"status": "error", "message": "Sem token. Execute autenticar() primeiro."}

    client = create_mcp_http_client()
    client.headers["Authorization"] = f"Bearer {token}"
    async with client:
        async with streamable_http_client(GOOGLE_CALENDAR_MCP_URL, http_client=client) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                if getattr(result, "is_error", False):
                    decoded = _decode_result(result)
                    return {"status": "error", "message": decoded.get("message", str(decoded))}
                return _decode_result(result)


def _run(coro_factory) -> dict:
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro_factory())).result()


def _calendar_api_create(payload: dict) -> dict:
    import httpx

    token = _access_token()
    if not token:
        return {"status": "error", "message": "Sem token do Google Calendar."}
    timezone = payload.get("timeZone", "America/Sao_Paulo")
    body = {
        "summary": payload["summary"],
        "start": {"dateTime": payload["startTime"], "timeZone": timezone},
        "end": {"dateTime": payload["endTime"], "timeZone": timezone},
    }
    if payload.get("location"):
        body["location"] = payload["location"]
    if payload.get("description"):
        body["description"] = payload["description"]
    response = httpx.post(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        headers={"Authorization": f"Bearer {token}"}, json=body, timeout=30,
    )
    data = response.json()
    if response.is_error:
        return {"status": "error", "message": data.get("error", {}).get("message", str(data))}
    return {"status": "ok", "id": data.get("id"), "titulo": data.get("summary"),
            "inicio": (data.get("start") or {}).get("dateTime"), "link": data.get("htmlLink")}


def chamar_google_calendar(tool_name: str, arguments: dict) -> dict:
    try:
        result = _run(lambda: _call_http(tool_name, arguments))
    except Exception as exc:
        result = {"status": "error", "message": f"{type(exc).__name__}: {exc}"}
    message = str(result.get("message", ""))
    if result.get("status") == "error" and (
        "calendarmcp.googleapis.com" in message
        or "Calendar MCP API has not been used" in message
        or "Server returned an error" in message
    ):
        return _calendar_api_create(arguments)
    return result


def listar_tools_google() -> dict:
    """Lista o catálogo público de tools do servidor MCP do Google."""
    import httpx

    response = httpx.post(
        GOOGLE_CALENDAR_MCP_URL,
        headers={"content-type": "application/json", "accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, timeout=30,
    )
    return response.json()


def _default_end(start_time: str) -> str:
    try:
        return (datetime.fromisoformat(start_time) + timedelta(hours=1)).isoformat()
    except ValueError:
        return start_time


class AddGoogleEventArgs(BaseModel):
    title: str = Field(..., description="Título do evento no Google Calendar.")
    start_time: str = Field(..., description="Início em ISO 8601 com fuso.")
    end_time: Optional[str] = Field(None, description="Fim; padrão: uma hora após o início.")
    location: Optional[str] = Field(None, description="Local.")
    description: Optional[str] = Field(None, description="Descrição ou notas.")


@tool("add_google_event", args_schema=AddGoogleEventArgs)
def add_google_event(title: str, start_time: str, end_time: Optional[str] = None,
                     location: Optional[str] = None, description: Optional[str] = None) -> dict:
    """Cria um evento no Google Calendar da conta autenticada."""
    end = end_time or _default_end(start_time)
    payload = {"summary": title, "startTime": start_time, "endTime": end,
               "timeZone": "America/Sao_Paulo"}
    if location:
        payload["location"] = location
    if description:
        payload["description"] = description
    result = chamar_google_calendar("create_event", payload)
    if result.get("status") == "ok" and result.get("id"):
        return {"status": "ok", "id": result["id"], "titulo": result.get("titulo", title),
                "inicio": result.get("inicio", start_time), "link": result.get("link")}
    return result


TOOLS_GOOGLE = [add_google_event]
