"""Verifica a base atual sem criar, alterar ou apagar dados.

Uso, a partir da raiz do projeto:

    py scripts/verificar_prerequisitos.py

O script não executa nenhuma prática futura. Ele só confirma que as
dependências e os serviços já usados pelo Assessor.AI estão acessíveis.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


DEPENDENCIAS = (
    "fastapi",
    "langchain",
    "langgraph",
    "pymongo",
    "psycopg2",
    "qdrant_client",
)


def registrar(nome: str, acao) -> bool:
    try:
        detalhe = acao()
        sufixo = f" — {detalhe}" if detalhe else ""
        print(f"[OK] {nome}{sufixo}")
        return True
    except Exception as erro:
        print(f"[FALHOU] {nome} — {erro}")
        return False


def verificar_dependencias() -> str:
    ausentes = []
    for pacote in DEPENDENCIAS:
        try:
            importlib.import_module(pacote)
        except ImportError:
            ausentes.append(pacote)
    if ausentes:
        raise RuntimeError(
            "dependências ausentes: " + ", ".join(ausentes)
            + ". Rode: py -m pip install -r requirements.txt"
        )
    return "dependências principais instaladas"


def verificar_configuracao() -> str:
    from app.config import validar_config

    problemas = validar_config()
    if problemas:
        raise RuntimeError("; ".join(problemas))
    return ".env e PDF do FAQ encontrados"


def verificar_postgres() -> str:
    from app.tools.db import get_conn

    conexao = get_conn()
    try:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    finally:
        conexao.close()
    return "conexão e SELECT 1 concluídos"


def verificar_mongodb() -> str:
    from pymongo import MongoClient

    from app.config import MONGODB_URI

    cliente = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    try:
        cliente.admin.command("ping")
    finally:
        cliente.close()
    return "ping concluído"


def verificar_qdrant() -> str:
    from app.vectorstore import COLLECTION_FAQ, COLLECTION_MEMORIA, qdrant

    existentes = {
        item.name for item in qdrant.get_collections().collections
    }
    esperadas = {COLLECTION_FAQ, COLLECTION_MEMORIA}
    ausentes = sorted(esperadas - existentes)
    if ausentes:
        raise RuntimeError("collections ausentes: " + ", ".join(ausentes))
    return "collections atuais encontradas"


def main() -> int:
    print("Verificação da base do Assessor.AI\n")
    testes = (
        ("Dependências Python", verificar_dependencias),
        ("Configuração", verificar_configuracao),
        ("PostgreSQL", verificar_postgres),
        ("MongoDB", verificar_mongodb),
        ("Qdrant", verificar_qdrant),
    )
    resultados = [registrar(nome, acao) for nome, acao in testes]
    print()
    if all(resultados):
        print("Base pronta. Nenhuma prática futura foi executada.")
        return 0
    print("Há pré-requisitos pendentes. Corrija os itens marcados como FALHOU.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
