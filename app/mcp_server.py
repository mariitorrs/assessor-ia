import sys
from pathlib import Path
from typing import Annotated, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from app.tools.financeiro import (
    add_transaction as _add_transaction,
    daily_balance as _daily_balance,
    query_transactions as _query_transactions,
    total_balance as _total_balance,
    update_transaction as _update_transaction,
)
from app.tools.agenda import (
    add_event as _add_event,
    query_events as _query_events,
)

mcp = MCPServer(
    name="assessor-financeiro",
    version="1.0.0",
    instructions="Ferramentas financeiras e de agenda do Assessor.AI.",
)

LEITURA = ToolAnnotations(readOnlyHint=True)
ESCRITA = ToolAnnotations(readOnlyHint=False, destructiveHint=False)


@mcp.tool(
    name="add_event",
    title="Registrar evento",
    description="Registra um evento na tabela events do Postgres.",
    annotations=ESCRITA,
)
def add_event(
    title: Annotated[str, Field(description="Título do evento.")],
    source_text: Annotated[str, Field(description="Texto original do usuário.")],
    start_time: Annotated[str, Field(description="Início em ISO 8601 com fuso.")],
    end_time: Annotated[Optional[str], Field(description="Fim em ISO 8601.")] = None,
    location: Annotated[Optional[str], Field(description="Local do evento.")] = None,
    notes: Annotated[Optional[str], Field(description="Observações adicionais.")] = None,
) -> dict[str, Any]:
    return _add_event.invoke({
        "title": title,
        "source_text": source_text,
        "start_time": start_time,
        "end_time": end_time,
        "location": location,
        "notes": notes,
    })


@mcp.tool(
    name="query_events",
    title="Consultar agenda",
    description="Consulta eventos por texto e intervalo de datas locais.",
    annotations=LEITURA,
)
def query_events(
    text: Annotated[Optional[str], Field(description="Busca em título, local, notas ou texto original.")] = None,
    date_local: Annotated[Optional[str], Field(description="Dia no formato YYYY-MM-DD.")] = None,
    date_from_local: Annotated[Optional[str], Field(description="Data inicial inclusiva.")] = None,
    date_to_local: Annotated[Optional[str], Field(description="Data final inclusiva.")] = None,
    limit: Annotated[int, Field(description="Máximo de resultados entre 1 e 200.")] = 20,
) -> dict[str, Any]:
    return _query_events.invoke({
        "text": text,
        "date_local": date_local,
        "date_from_local": date_from_local,
        "date_to_local": date_to_local,
        "limit": limit,
    })


@mcp.tool(
    name="total_balance",
    title="Saldo total",
    description="Saldo de todo o histórico: receitas menos despesas. Transferências são ignoradas.",
    annotations=LEITURA,
)
def total_balance() -> dict[str, Any]:
    """Retorna o saldo acumulado de todo o histórico financeiro."""
    return _total_balance.invoke({})


@mcp.tool(
    name="add_transaction",
    title="Registrar transação",
    description="Registra uma transação na tabela transactions.",
    annotations=ESCRITA,
)
def add_transaction(
    amount: Annotated[float, Field(description="Valor da transação (sempre positivo).")],
    source_text: Annotated[str, Field(description="Texto original informado pelo usuário.")],
    occurred_at: Annotated[
        Optional[str],
        Field(description="Timestamp ISO 8601 opcional; se ausente, usa a data/hora atual.")
    ] = None,
    type_name: Annotated[
        Optional[str],
        Field(description="Tipo: INCOME, EXPENSES ou TRANSFER.")
    ] = None,
    description: Annotated[
        Optional[str],
        Field(description="Descrição da transação, opcional.")
    ] = None,
    payment_method: Annotated[
        Optional[str],
        Field(description="Forma de pagamento, opcional.")
    ] = None,
    category_name: Annotated[
        Optional[str],
        Field(description="Nome da categoria em pt-BR, opcional.")
    ] = None,
) -> dict[str, Any]:
    """Registra uma nova transação financeira."""
    return _add_transaction.invoke({
        "amount": amount,
        "source_text": source_text,
        "occurred_at": occurred_at,
        "type_name": type_name,
        "description": description,
        "payment_method": payment_method,
        "category_name": category_name,
    })


@mcp.tool(
    name="query_transactions",
    title="Consultar transações",
    description="Consulta transações por texto, tipo e intervalo de datas locais.",
    annotations=LEITURA,
)
def query_transactions(
    text: Annotated[Optional[str], Field(description="Texto para buscar na origem ou descrição.")] = None,
    type_name: Annotated[Optional[str], Field(description="Tipo: INCOME, EXPENSES ou TRANSFER.")] = None,
    date_from_local: Annotated[
        Optional[str], Field(description="Data inicial local no formato YYYY-MM-DD.")
    ] = None,
    date_to_local: Annotated[
        Optional[str], Field(description="Data final local no formato YYYY-MM-DD.")
    ] = None,
    limit: Annotated[
        Optional[int], Field(description="Quantidade máxima de resultados. Padrão: 50.")
    ] = 50,
) -> dict[str, Any]:
    """Consulta o histórico de transações financeiras."""
    return _query_transactions.invoke({
        "text": text,
        "type_name": type_name,
        "date_from_local": date_from_local,
        "date_to_local": date_to_local,
        "limit": limit,
    })


@mcp.tool(
    name="daily_balance",
    title="Saldo diário",
    description="Retorna o saldo de um dia: receitas menos despesas.",
    annotations=LEITURA,
)
def daily_balance(
    date_local: Annotated[str, Field(description="Data local no formato YYYY-MM-DD.")],
) -> dict[str, Any]:
    """Retorna o saldo financeiro do dia informado."""
    return _daily_balance.invoke({"date_local": date_local})


@mcp.tool(
    name="update_transaction",
    title="Atualizar transação",
    description="Atualiza uma transação existente por ID ou por texto e data.",
    annotations=ESCRITA,
)
def update_transaction(
    id: Annotated[Optional[int], Field(description="ID da transação a atualizar.")] = None,
    match_text: Annotated[
        Optional[str], Field(description="Texto para localizar a transação quando não houver ID.")
    ] = None,
    date_local: Annotated[
        Optional[str], Field(description="Data local YYYY-MM-DD usada com match_text.")
    ] = None,
    amount: Annotated[Optional[float], Field(description="Novo valor da transação.")] = None,
    type_name: Annotated[
        Optional[str], Field(description="Novo tipo: INCOME, EXPENSES ou TRANSFER.")
    ] = None,
    category_name: Annotated[Optional[str], Field(description="Novo nome da categoria.")] = None,
    description: Annotated[Optional[str], Field(description="Nova descrição.")] = None,
    payment_method: Annotated[Optional[str], Field(description="Nova forma de pagamento.")] = None,
    occurred_at: Annotated[
        Optional[str], Field(description="Novo timestamp ISO 8601.")
    ] = None,
) -> dict[str, Any]:
    """Atualiza uma transação existente."""
    return _update_transaction.invoke({
        "id": id,
        "match_text": match_text,
        "date_local": date_local,
        "amount": amount,
        "type_name": type_name,
        "category_name": category_name,
        "description": description,
        "payment_method": payment_method,
        "occurred_at": occurred_at,
    })

if __name__ == "__main__":
    from app.config import DATABASE_URL

    if not DATABASE_URL:
        print("[assessor-financeiro] DATABASE_URL ausente no .env", file=sys.stderr)

    mcp.run(transport="stdio")
