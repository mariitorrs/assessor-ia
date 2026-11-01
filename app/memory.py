"""
=================
Modelagem
---------

Um documento por acesso (sessão = uma conversa completa).

O _id é um UUID gerado internamente — a API conhece o session_id e o user_id.

O session_id identifica a conversa; o user_id identifica o usuário.

Documento
---------

{
  "_id":           "uuid-gerado-internamente",
  "session_id":    "id_usuario",
  "iniciada_em":   datetime,
  "atualizada_em": datetime,
  "resumo":        "Usuário registrou Pix de R$50...",
  "mensagens":     [
    {"role": "usuario",    "content": "oi"},
    {"role": "assistente", "content": "Olá!"}
  ]
}

Funções
----------------

iniciar_sessao(session_id)                 → cria documento no MongoDB
salvar_mensagem(session_id, role, content) → adiciona mensagem na sessão ativa
encerrar_sessao(session_id)                → gera resumo e salva no documento
"""

import uuid
from datetime import datetime, timezone

import certifi
import httpx

from langchain_groq import ChatGroq
from pymongo import MongoClient
from qdrant_client import models

from app.config import GROQ_API_KEY, MONGODB_URI
from app.vectorstore import (
    COLLECTION_MEMORIA,
    garantir_collection,
    gerar_embedding,
    qdrant,
)


_mongo = MongoClient(
    MONGODB_URI,
    tls=True,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=10000,
)

db = _mongo["assessor"]
col_sessoes = db["sessoes"]


_llm_resumo = ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0.0,
    api_key=GROQ_API_KEY,
    http_client=httpx.Client(trust_env=False),
    http_async_client=httpx.AsyncClient(trust_env=False),
)


_PROMPT_RESUMO = """\
Você é um assistente que resume conversas de assessoria financeira e agenda.

Gere um resumo conciso em 2-4 frases capturando:

- O que o usuário fez (transações registradas, eventos agendados)
- O que o usuário perguntou
- Informações relevantes mencionadas (valores, datas, categorias)

Responda APENAS com o resumo, sem introdução ou explicação.

Conversa:
{conversa}
"""


_sessoes_ativas: dict = {}


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _formatar_conversa(mensagens: list[dict]) -> str:
    """Formata o array de mensagens em texto para o prompt de resumo."""

    linhas = []

    for msg in mensagens:
        linhas.append(f"{msg['role']}: {msg['content']}")

    return "\n".join(linhas)


def _gerar_resumo(mensagens: list[dict]) -> str:
    """Chama o LLM para gerar o resumo da sessão."""

    conversa = _formatar_conversa(mensagens)

    return _llm_resumo.invoke(
        _PROMPT_RESUMO.format(conversa=conversa)
    ).content.strip()


def _doc_id_da_sessao(session_id: str) -> str | None:
    """
    Descobre o documento da sessão EM ANDAMENTO deste usuário, ou None.

    Olha primeiro o cache em memória (_sessoes_ativas). Se não achar, procura
    no MongoDB a sessão mais recente que ainda não foi encerrada — isto é, com
    resumo vazio.

    Essa segunda tentativa existe porque _sessoes_ativas vive na RAM do
    processo: um --reload do uvicorn no meio da conversa esvazia o dicionário.

    Sem ela, iniciar_sessao() criaria um documento novo para a mesma conversa a
    cada reinício, e encerrar_sessao() não acharia nada para resumir — sem erro
    nenhum, apenas silêncio.
    """

    doc_id = _sessoes_ativas.get(session_id)

    if doc_id:
        return doc_id

    doc = col_sessoes.find_one(
        {
            "session_id": session_id,
            "resumo": {"$in": ["", None]},
        },
        {
            "_id": 1,
        },
        sort=[("iniciada_em", -1)],
    )

    if not doc:
        return None

    _sessoes_ativas[session_id] = doc["_id"]

    return doc["_id"]


def iniciar_sessao(
    session_id: str,
    user_id: str = "usuario_teste",
) -> None:
    """
    Garante que existe um documento de sessão aberto para este session_id.

    Se já houver um (em memória ou no Mongo), não faz nada.
    """

    if _doc_id_da_sessao(session_id):
        return

    doc_id = str(uuid.uuid4())

    agora = _agora()

    col_sessoes.insert_one(
        {
            "_id": doc_id,
            "session_id": session_id,
            "user_id": user_id,
            "iniciada_em": agora,
            "atualizada_em": agora,
            "resumo": "",
            "mensagens": [],
        }
    )

    _sessoes_ativas[session_id] = doc_id


def salvar_mensagem(
    session_id: str,
    role: str,
    content: str,
    user_id: str = "usuario_teste",
) -> None:
    """
    Adiciona uma mensagem ao array de mensagens da sessão ativa.
    """

    iniciar_sessao(session_id, user_id=user_id)

    doc_id = _doc_id_da_sessao(session_id)

    col_sessoes.update_one(
        {
            "_id": doc_id,
        },
        {
            "$push": {
                "mensagens": {
                    "role": role,
                    "content": content,
                }
            },
            "$set": {
                "atualizada_em": _agora(),
            },
        },
    )


def recuperar_historico(
    user_id: str,
    busca: str = "",
    limite: int = 3,
) -> list[dict]:
    """
    Recupera resumos de sessões ANTERIORES (já encerradas) de um usuário.

    Estratégia: olha primeiro os resumos.

    Se houver termo de busca, filtra por ele;
    senão, traz as sessões mais recentes.

    As mensagens completas NÃO vêm aqui —
    para isso use recuperar_mensagens(doc_id).

    user_id    : identifica o usuário de forma estável entre sessões
    busca      : termo opcional para filtrar resumos relevantes
    limite     : máximo de sessões retornadas
    """

    if busca:
        garantir_collection(COLLECTION_MEMORIA)
        vetor = gerar_embedding(busca)
        resultados = qdrant.query_points(
            collection_name=COLLECTION_MEMORIA,
            query=vetor,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="user_id",
                        match=models.MatchValue(value=user_id),
                    )
                ]
            ),
            limit=limite,
        )

        if resultados.points:
            return [
                {
                    "doc_id": ponto.id,
                    "iniciada_em": ponto.payload.get("iniciada_em", ""),
                    "resumo": ponto.payload["resumo"],
                }
                for ponto in resultados.points
            ]

    filtro = {
        "user_id": user_id,
        "resumo": {"$nin": ["", None]},
    }
    docs = (
        col_sessoes
        .find(filtro, {"resumo": 1, "iniciada_em": 1})
        .sort("iniciada_em", -1)
        .limit(limite)
    )

    return [
        {
            "doc_id": d["_id"],
            "iniciada_em": d["iniciada_em"],
            "resumo": d["resumo"],
        }
        for d in docs
    ]


def recuperar_mensagens(doc_id: str) -> list[dict]:
    """
    Busca o array completo de mensagens de um documento específico, pelo _id.

    Usada no passo 2 — só quando o resumo deu match e você precisa do detalhe
    literal da conversa.

    O doc_id pode vir do Qdrant ou diretamente do MongoDB.
    """

    doc = col_sessoes.find_one(
        {
            "_id": doc_id,
        },
        {
            "mensagens": 1,
        },
    )

    return doc["mensagens"] if doc else []


def encerrar_sessao(session_id: str) -> str:
    """
    Encerra a sessão ativa:

    1. Carrega mensagens do MongoDB
    2. Gera resumo via LLM
    3. Atualiza documento com resumo e atualizada_em
    4. Remove sessão do estado interno

    Retorna o resumo gerado ou string vazia se não houver mensagens.
    """

    doc_id = _doc_id_da_sessao(session_id)

    if not doc_id:
        return ""

    doc = col_sessoes.find_one(
        {
            "_id": doc_id,
        }
    )

    if not doc or not doc.get("mensagens"):
        _sessoes_ativas.pop(session_id, None)
        return ""

    resumo = _gerar_resumo(
        doc["mensagens"]
    )

    col_sessoes.update_one(
        {
            "_id": doc_id,
        },
        {
            "$set": {
                "resumo": resumo,
                "atualizada_em": _agora(),
            }
        },
    )

    user_id = doc.get("user_id", "usuario_teste")
    garantir_collection(COLLECTION_MEMORIA)
    qdrant.upsert(
        collection_name=COLLECTION_MEMORIA,
        points=[
            models.PointStruct(
                id=doc_id,
                vector=gerar_embedding(resumo),
                payload={
                    "user_id": user_id,
                    "session_id": session_id,
                    "resumo": resumo,
                    "iniciada_em": doc["iniciada_em"].isoformat(),
                },
            )
        ],
    )

    _sessoes_ativas.pop(
        session_id,
        None,
    )

    return resumo
