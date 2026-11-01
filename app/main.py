from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import FRONTEND_DIR, validar_config
from app.routes import chat, monitor, perfil, sessions


for _problema in validar_config():
    print(f"[config] ATENÇÃO: {_problema}")


app = FastAPI(
    title="Assessor IA",
    description="Assessor financeiro e de agenda com LangChain e LangGraph.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    """
    Responde 'ok' se o servidor subiu.
    """
    problemas = validar_config()
    return {
        "status": "ok" if not problemas else "atencao",
        "problemas_de_configuracao": problemas,
    }


app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(perfil.router)
app.include_router(monitor.router)
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
