"""Registro temporário de latência, tokens e custo por chamada e por turno."""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

_FUSO = ZoneInfo("America/Sao_Paulo")

# USD por milhão de tokens (entrada, saída), conforme preços publicados pelos provedores.
# Gemini: https://ai.google.dev/gemini-api/docs/pricing
# Groq: https://console.groq.com/docs/model/openai/gpt-oss-120b
PRECO_POR_MILHAO: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash": (0.30, 2.50),
    "openai/gpt-oss-120b": (0.15, 0.60),
}

_NOS_ESPECIALISTA = {"financeiro", "agenda"}
_MODELO_ESPECIALISTA = "gemini-2.5-flash"

LIMITE_TURNOS = 50
LIMITE_P95_MS = 8_000
LIMITE_TAXA_ERRO = 0.05

_lock = threading.Lock()
_inicio_processo = time.time()
_em_andamento = 0
_turnos: list[dict[str, Any]] = []
_chamadas: list[dict[str, Any]] = []
_abertos: dict[str, float] = {}
_runs: dict[str, dict[str, Any]] = {}
_ligado = False
_turno_por_thread = threading.local()


def _agora_local() -> str:
    return datetime.now(_FUSO).strftime("%H:%M:%S")


def _nome_modelo(
    serialized: dict | None,
    invocation_params: dict | None,
    resposta_meta: dict | None,
) -> str:
    candidatos = []
    fontes = (resposta_meta or {}, invocation_params or {}, (serialized or {}).get("kwargs") or {})
    for fonte in fontes:
        for chave in ("model_name", "model"):
            valor = fonte.get(chave)
            if valor:
                candidatos.append(str(valor))
    for nome in candidatos:
        if nome.startswith("models/"):
            nome = nome.split("/", 1)[1]
        return nome
    return "desconhecido"


def _no_do_grafo(metadata: dict | None) -> str:
    """Retorna o nó do grafo, não um nó interno do create_agent."""
    metadata = metadata or {}
    namespace = str(metadata.get("langgraph_checkpoint_ns") or "")
    candidatos: list[str] = []
    if namespace:
        candidatos.extend(parte.split(":", 1)[0] for parte in namespace.split("|"))
    no = metadata.get("langgraph_node")
    if no:
        candidatos.append(str(no))
    for nome in candidatos:
        if nome in _NOS_ESPECIALISTA:
            return nome
    return candidatos[0] if candidatos else ""


def _tokens(message: Any) -> tuple[int, int]:
    usage = getattr(message, "usage_metadata", None) or {}
    if not isinstance(usage, dict):
        usage = {
            "input_tokens": getattr(usage, "input_tokens", 0),
            "output_tokens": getattr(usage, "output_tokens", 0),
        }
    entrada = int(usage.get("input_tokens") or 0)
    saida = int(usage.get("output_tokens") or 0)
    if entrada or saida:
        return entrada, saida

    meta = getattr(message, "response_metadata", None) or {}
    bruto = meta.get("token_usage") or meta.get("usage") or {}
    entrada = int(bruto.get("prompt_tokens") or bruto.get("input_tokens") or 0)
    saida = int(bruto.get("completion_tokens") or bruto.get("output_tokens") or 0)
    return entrada, saida


def custo_usd(modelo: str, entrada: int, saida: int) -> float:
    precos = PRECO_POR_MILHAO.get(modelo)
    if precos is None:
        precos = next((valor for chave, valor in PRECO_POR_MILHAO.items() if chave in modelo), None)
    if precos is None:
        return 0.0
    preco_entrada, preco_saida = precos
    return (entrada * preco_entrada + saida * preco_saida) / 1_000_000


def _eh_fallback(no: str, modelo: str) -> bool:
    return no in _NOS_ESPECIALISTA and _MODELO_ESPECIALISTA not in modelo


def _turno_da_thread() -> str | None:
    return getattr(_turno_por_thread, "turno_id", None)


class ColetorChamadas(BaseCallbackHandler):
    """Anota chamadas de modelo sem reter o texto dos prompts."""

    raise_error = False

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: Any,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        invocation = kwargs.get("invocation_params") or {}
        with _lock:
            _runs[str(run_id)] = {
                "t0": time.perf_counter(),
                "modelo": _nome_modelo(serialized, invocation, None),
                "no": _no_do_grafo(metadata),
                "turno_id": _turno_da_thread(),
            }

    def on_llm_end(self, response: LLMResult, *, run_id: Any, **kwargs: Any) -> None:
        with _lock:
            abertura = _runs.pop(str(run_id), None)
        if abertura is None or not abertura.get("turno_id"):
            return

        try:
            message = response.generations[0][0].message
        except (IndexError, AttributeError):
            message = None
        entrada, saida = _tokens(message) if message is not None else (0, 0)
        meta = getattr(message, "response_metadata", None) if message is not None else None
        modelo = _nome_modelo(None, None, meta)
        if modelo == "desconhecido":
            modelo = abertura["modelo"]

        registro = {
            "turno_id": abertura["turno_id"],
            "modelo": modelo,
            "no": abertura["no"],
            "tokens_entrada": entrada,
            "tokens_saida": saida,
            "custo_usd": custo_usd(modelo, entrada, saida),
            "latencia_ms": int((time.perf_counter() - abertura["t0"]) * 1000),
            "fallback": _eh_fallback(abertura["no"], modelo),
        }
        with _lock:
            _chamadas.append(registro)

    def on_llm_error(self, error: BaseException, *, run_id: Any, **kwargs: Any) -> None:
        with _lock:
            _runs.pop(str(run_id), None)


coletor = ColetorChamadas()


def ligar_coleta() -> None:
    """Anexa o callback aos modelos configurados, uma vez por processo."""
    global _ligado
    with _lock:
        if _ligado:
            return
        from app.llms import llm_gemini, llm_groq, llm_rapido

        for modelo in (llm_gemini, llm_groq, llm_rapido):
            atuais = list(modelo.callbacks or [])
            if not any(isinstance(item, ColetorChamadas) for item in atuais):
                modelo.callbacks = [*atuais, coletor]
        _ligado = True


def abrir_turno() -> str:
    ligar_coleta()
    turno_id = uuid.uuid4().hex
    _turno_por_thread.turno_id = turno_id
    global _em_andamento
    with _lock:
        _em_andamento += 1
        _abertos[turno_id] = time.perf_counter()
    return turno_id


def fechar_turno(turno_id: str, session_id: str, rota: str, status: str) -> None:
    _turno_por_thread.turno_id = None
    global _em_andamento
    with _lock:
        inicio = _abertos.pop(turno_id, None)
        if inicio is None:
            return
        _em_andamento = max(0, _em_andamento - 1)
        chamadas_turno = [c for c in _chamadas if c["turno_id"] == turno_id]
        _turnos.append({
            "id": turno_id,
            "hora": _agora_local(),
            "session_id": session_id,
            "latencia_ms": int((time.perf_counter() - inicio) * 1000),
            "rota": rota or "—",
            "status": status,
            "tokens_total": sum(c["tokens_entrada"] + c["tokens_saida"] for c in chamadas_turno),
            "custo_usd": sum(c["custo_usd"] for c in chamadas_turno),
        })
        while len(_turnos) > LIMITE_TURNOS:
            antigo = _turnos.pop(0)
            _chamadas[:] = [c for c in _chamadas if c["turno_id"] != antigo["id"]]


def status_do_estado(estado: dict) -> str:
    """Bloqueio de entrada é comportamento esperado; exceções são erros."""
    status_turno = estado.get("turno_status")
    if status_turno in {"ok", "bloqueado"}:
        return status_turno
    for nome in estado.get("agentes_chamados") or []:
        if (
            isinstance(nome, str)
            and nome.startswith("guardrail_entrada:")
            and nome != "guardrail_entrada:aprovado"
        ):
            return "bloqueado"
    return "ok"


def listar_turnos() -> list[dict[str, Any]]:
    with _lock:
        return [{chave: valor for chave, valor in turno.items() if chave != "id"} for turno in _turnos]


def listar_chamadas() -> list[dict[str, Any]]:
    with _lock:
        return [
            {chave: valor for chave, valor in chamada.items() if chave != "turno_id"}
            for chamada in _chamadas
        ]


def situacao() -> dict[str, int]:
    with _lock:
        return {
            "em_andamento": _em_andamento,
            "no_ar_segundos": int(time.time() - _inicio_processo),
        }
