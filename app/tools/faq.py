from langchain.tools import tool

from app.vectorstore import (
    COLLECTION_FAQ,
    garantir_collection,
    gerar_embedding,
    qdrant,
)


def _consultar_qdrant(question: str):
    vetor = gerar_embedding(question)
    return qdrant.query_points(
        collection_name=COLLECTION_FAQ,
        query=vetor,
        limit=6,
        with_payload=True,
    )


@tool
def faq_retriever(question: str) -> str:
    """Busca no FAQ oficial os trechos mais relevantes para responder a pergunta."""
    pergunta = question.strip()
    if not pergunta:
        return "Nenhuma pergunta foi informada para consultar o FAQ."

    try:
        garantir_collection(COLLECTION_FAQ)
        info = qdrant.get_collection(COLLECTION_FAQ)

        # Evita o silêncio quando o script de ingestão ainda não foi executado.
        # A primeira pergunta popula a collection; as seguintes apenas consultam.
        if not info.points_count:
            from app.ingest_faq import ingerir_faq

            ingerir_faq(limpar=False)

        resultados = _consultar_qdrant(pergunta)
    except Exception as erro:
        print(f"[faq] falha ao consultar/indexar o FAQ: {erro}")
        return (
            "Não foi possível consultar o FAQ agora. Verifique a conexão com "
            "o Qdrant e as variáveis QDRANT_URL, QDRANT_API_KEY e GEMINI_API_KEY."
        )

    if not resultados.points:
        return "Nenhum trecho relevante encontrado no FAQ."

    trechos = [
        str((ponto.payload or {}).get("page_content", "")).strip()
        for ponto in resultados.points
    ]
    trechos = [trecho for trecho in trechos if trecho]
    if not trechos:
        return "Nenhum trecho relevante encontrado no FAQ."

    return "\n\n".join(trechos)


TOOLS_FAQ = [faq_retriever]
