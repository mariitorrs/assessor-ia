"""Persistência do perfil e tool de consulta do especialista financeiro."""

import uuid
from datetime import datetime, timezone

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from qdrant_client import models

from app.memory import db
from app.schemas import PerfilRequest
from app.vectorstore import (
    COLLECTION_PERFIL,
    garantir_collection,
    gerar_embedding,
    qdrant,
)


col_perfis = db["perfis"]


def _point_id(user_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"assessor.ai/perfil/{user_id}"))


def _garantir_indice_user_id() -> None:
    """Garante o índice exigido pelo Qdrant para filtrar por usuário."""
    garantir_collection(COLLECTION_PERFIL)
    informacoes = qdrant.get_collection(COLLECTION_PERFIL)
    if "user_id" not in (informacoes.payload_schema or {}):
        qdrant.create_payload_index(
            collection_name=COLLECTION_PERFIL,
            field_name="user_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
            wait=True,
        )


def salvar_perfil(perfil: PerfilRequest) -> dict:
    """Atualiza o MongoDB e o Qdrant a partir do mesmo POST."""
    col_perfis.create_index("user_id", unique=True)

    vetor = gerar_embedding(perfil.preferencias)
    _garantir_indice_user_id()

    anterior = col_perfis.find_one({"user_id": perfil.user_id})
    agora = datetime.now(timezone.utc)

    col_perfis.update_one(
        {"user_id": perfil.user_id},
        {
            "$set": {
                "user_id": perfil.user_id,
                "renda_mensal": perfil.renda_mensal,
                "objetivo": perfil.objetivo,
                "tolerancia_risco": perfil.tolerancia_risco,
                "atualizado_em": agora,
            },
            "$setOnInsert": {"criado_em": agora},
        },
        upsert=True,
    )

    try:
        qdrant.upsert(
            collection_name=COLLECTION_PERFIL,
            wait=True,
            points=[
                models.PointStruct(
                    id=_point_id(perfil.user_id),
                    vector=vetor,
                    payload={
                        "user_id": perfil.user_id,
                        "preferencias": perfil.preferencias,
                    },
                )
            ],
        )
    except Exception:
        if anterior is None:
            col_perfis.delete_one({"user_id": perfil.user_id})
        else:
            col_perfis.replace_one({"_id": anterior["_id"]}, anterior)
        raise

    return perfil.model_dump()


@tool
def consultar_perfil_financeiro(
    pergunta: str,
    config: RunnableConfig,
) -> str:
    """Consulta o perfil ao preparar um conselho financeiro personalizado.

    Args:
        pergunta: pergunta financeira usada para buscar preferências por
            similaridade semântica.
    """
    configuravel = (config or {}).get("configurable", {})
    user_id = configuravel.get("user_id") or configuravel.get("thread_id")
    if not user_id:
        return "Não foi possível identificar o usuário atual."

    perfil = col_perfis.find_one(
        {"user_id": user_id},
        {
            "_id": 0,
            "renda_mensal": 1,
            "objetivo": 1,
            "tolerancia_risco": 1,
        },
    )
    if not perfil:
        return (
            "PERFIL_NAO_CADASTRADO. Oriente o usuário a preencher "
            "http://localhost:8000/perfil.html."
        )

    _garantir_indice_user_id()
    resultados = qdrant.query_points(
        collection_name=COLLECTION_PERFIL,
        query=gerar_embedding(pergunta),
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="user_id",
                    match=models.MatchValue(value=user_id),
                )
            ]
        ),
        limit=1,
        with_payload=True,
    )
    preferencias = ""
    if resultados.points:
        preferencias = str(
            (resultados.points[0].payload or {}).get("preferencias", "")
        ).strip()

    return (
        f"Renda mensal: R$ {float(perfil['renda_mensal']):.2f}\n"
        f"Objetivo: {perfil['objetivo']}\n"
        f"Tolerância a risco: {perfil['tolerancia_risco']}\n"
        f"Preferências: {preferencias or 'nenhuma encontrada'}"
    )
