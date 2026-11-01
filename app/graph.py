import operator
import re
import unicodedata
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, MessagesState, START, END
from typing import Annotated

from app.guardrail import guardrail_entrada, guardrail_saida, anonimizar_entrada
from app.juiz import no_juiz
from langchain_core.messages import RemoveMessage
from langchain_core.runnables import RunnableConfig

from app.agents import (
    agenda_app,
    faq_app,
    financeiro_app,
    orquestrador_app,
    router_app,
)

from app.memory import salvar_mensagem
from app.observabilidade import abrir_turno, fechar_turno, status_do_estado

# ==============================================================================
# ESTADO
# ==============================================================================
class Estado(MessagesState):
    mapa_pii: dict #valores originais gerados na anonimização
    agentes_chamados: Annotated[list[str], operator.add]
    rota: str
    turno_status: str


# ==============================================================================
# NÓ ROTEADOR
# ==============================================================================
def _mensagens_limpas_para_roteador(estado: Estado) -> list:
    """
    O MemorySaver mantém também mensagens internas dos agentes e resultados de tools.
    O roteador não deve enxergar essas chamadas internas, senão pode tentar repetir
    tools que pertencem aos especialistas (ex.: criar_evento).
    """
    limpas = []

    for mensagem in list(estado.get("messages", [])):
        tipo = getattr(mensagem, "type", None)

        # Resultado de tool nunca vai para o roteador.
        if tipo == "tool":
            continue

        # Mensagem de IA que contém tool_calls também é interna do especialista.
        if getattr(mensagem, "tool_calls", None):
            continue

        conteudo = getattr(mensagem, "content", "")
        if not conteudo:
            continue

        if tipo in ("human", "ai"):
            limpas.append(mensagem)

    # Contexto recente é suficiente para entender respostas como "17h" depois
    # de uma pergunta de clarificação da agenda.
    return limpas[-8:]


def _rota_fallback(mensagens: list) -> str:
    """Fallback simples para impedir erro 500 caso o LLM tente tool indevida."""
    texto = _texto_ultima_mensagem_humana(mensagens)

    palavras_agenda = (
        "agenda", "evento", "reunião", "reuniao", "compromisso", "horário",
        "horario", "calendário", "calendario", "marcar", "agendar", "termina",
        "término", "termino", "disponibilidade", "conflito"
    )
    palavras_financeiro = (
        "gastei", "gasto", "gastos", "receita", "saldo", "dinheiro", "reais",
        "r$", "transação", "transacao", "despesa", "pagamento", "extrato",
        "financeiro", "orçamento", "orcamento", "renda", "guardar",
        "investimento", "investir", "risco", "objetivo", "perfil"
    )
    palavras_faq = (
        "assessor.ai", "assessor ia", "como funciona", "faq", "regra",
        "politica", "termo de uso", "responsabilidade", "restricao",
        "limitacao", "privacidade", "lgpd", "dado pessoal", "suporte",
        "atendimento", "e-mail", "email", "telefone", "arquivo", "pdf",
        "planilha", "senha", "codigo de verificacao", "excluir", "apagar",
        "pagamento", "transferencia", "integracao externa",
    )

    if any(p in texto for p in palavras_agenda):
        return "agenda"
    if any(p in texto for p in palavras_financeiro):
        return "financeiro"
    if any(p in texto for p in palavras_faq):
        return "faq"
    return "fim"


def _normalizar_texto(valor: str) -> str:
    sem_acentos = "".join(
        caractere
        for caractere in unicodedata.normalize("NFD", valor)
        if unicodedata.category(caractere) != "Mn"
    )
    return sem_acentos.lower().strip()


def _texto_ultima_mensagem_humana(mensagens: list) -> str:
    for mensagem in reversed(mensagens):
        if getattr(mensagem, "type", None) != "human":
            continue
        conteudo = getattr(mensagem, "content", "")
        if isinstance(conteudo, list):
            conteudo = " ".join(
                parte.get("text", "") if isinstance(parte, dict) else str(parte)
                for parte in conteudo
            )
        return _normalizar_texto(str(conteudo))
    return ""


def _parece_pergunta_de_faq(mensagens: list) -> bool:
    texto = _texto_ultima_mensagem_humana(mensagens)
    sinais = (
        "faq", "assessor.ai", "assessor ia", "suporte", "atendimento",
        "privacidade", "lgpd", "termos de uso", "politica", "regra",
        "limitacao", "restricao", "responsabilidade", "e-mail", "email",
        "telefone", "dados pessoais", "codigo de verificacao",
    )
    return any(sinal in texto for sinal in sinais)


def no_roteador(estado: Estado, config: RunnableConfig) -> dict:
    mensagens_roteador = _mensagens_limpas_para_roteador(estado)

    # Perguntas institucionais claras não dependem do LLM para chegar ao FAQ.
    # Isso cobre inclusive o teste oficial da Etapa 4: e-mail do suporte.
    if _parece_pergunta_de_faq(mensagens_roteador):
        return {
            "agentes_chamados": ["roteador:faq_direto"],
            "rota": "faq",
        }

    try:
        saida = router_app.invoke(
            {"messages": mensagens_roteador},
            config=config,
        )
        texto = saida["messages"][-1].content
    except Exception as erro:
        # O Groq pode rejeitar a resposta antes mesmo de devolvê-la quando o
        # modelo tenta chamar uma tool que não foi fornecida ao roteador.
        # Em vez de derrubar o POST /chat com 500, preservamos o fluxo e
        # encaminhamos pelo contexto recente.
        print(f"[roteador] fallback por erro do modelo: {erro}")
        rota = _rota_fallback(mensagens_roteador)
        return {
            "agentes_chamados": ["roteador:fallback"],
            "rota": rota,
        }

    if "ROUTE=" not in texto:
        return {
            "agentes_chamados": ["roteador"],
            "rota":             "fim",
            "messages":         [{"role": "assistant", "content": texto}],
        }

    rota = "fim"
    match = re.search(
        r"ROUTE\s*=\s*(financeiro|agenda|faq|fora_escopo|fim)",
        texto,
        flags=re.IGNORECASE,
    )
    if match:
        rota = match.group(1).lower()
        if rota == "fora_escopo":
            rota = "fim"

    return {
        "agentes_chamados": ["roteador"],
        "rota":             rota,
        # Não adiciona nada ao messages — especialista lê histórico limpo
    }

def no_guardrail_saida(estado: Estado) -> dict:
    ultima = ""
    for msg in reversed(estado["messages"]):
        if msg.type == "ai" and msg.content:
            ultima = msg.content
            break
    # percorre o histórico de trás para frente para pegar
    # a última mensagem do modelo (ignora tool calls e mensagens humanas)

    resultado = guardrail_saida(ultima, estado.get("mapa_pii", {}))

    return {
        "messages":         [{"role": "assistant", "content": resultado["conteudo"]}],
        "agentes_chamados": ["guardrail_saida"],
    }
# ==============================================================================
# NÓS 
# ==============================================================================
def no_orquestrador(estado: Estado, config: RunnableConfig) -> dict:
    ultima_especialista = ""

    for mensagem in reversed(estado["messages"]):
        if mensagem.type == "ai" and mensagem.content:
            ultima_especialista = mensagem.content
            break

    saida = orquestrador_app.invoke(
        {"messages": [{"role": "human", "content": ultima_especialista}]},
        config=config,
    )

    return {
        "agentes_chamados": [estado["rota"], "orquestrador"],
        "messages": [
            {
                "role": "assistant",
                "content": saida["messages"][-1].content,
            }
        ],
    }

def decidir_pos_guardrail_entrada(estado: Estado) -> str:
    if estado.get("rota") == "fim":
        return "fim"

    mensagens = list(estado.get("messages", []))
    humanas = [
        mensagem for mensagem in mensagens
        if getattr(mensagem, "type", None) == "human"
        or (isinstance(mensagem, dict) and mensagem.get("role") == "human")
    ]
    ultima = humanas[-1] if humanas else None
    if ultima is None:
        return "fim"
    texto = ultima.content if hasattr(ultima, "content") else ultima.get("content", "")
    if isinstance(texto, list):
        texto = "".join(
            parte.get("text", "") if isinstance(parte, dict) else str(parte)
            for parte in texto
        )
    if str(texto).strip().lower() in ("sair", "end", "fim", "tchau", "bye"):
        return "fim"
    return "roteador"

def no_guardrail_entrada(estado: Estado) -> dict:
    # list() materializa a lista real com HumanMessage — tem .text e .id
    # estado["messages"][-1] retorna TextAccessor — só tem .content, sem .id
    human_message = list(estado["messages"])[-1]

    # 1. Anonimiza — o LLM nunca vê CPF, email, etc.
    texto = human_message.content if hasattr(human_message, "content") else human_message.get("content", "")
    texto_anonimizado, mapa = anonimizar_entrada(str(texto))

    # 2. Roda as verificações de segurança na mensagem já anonimizada
    resultado = guardrail_entrada(texto_anonimizado)

    if resultado["bloqueado"]:
        return {
            "messages":         [{"role": "assistant", "content": resultado["mensagem"]}],
            "rota":             "fim",
            "turno_status":     "bloqueado",
            "mapa_pii":         {},
            "agentes_chamados": [f"guardrail_entrada:{resultado['motivo']}"],
        }

    return {
        "messages": [
            RemoveMessage(id=human_message.id),          # remove a original pelo id
            {"role": "human", "content": texto_anonimizado}, # adiciona a anonimizada
        ],
        "mapa_pii":         mapa,
        "agentes_chamados": ["guardrail_entrada:aprovado"],
        "rota":             "",
        "turno_status":     "ok",
    }
# ==============================================================================
# FUNÇÃO DE DECISÃO
# ==============================================================================
def decidir_especialista(estado: Estado) -> str:
    rota = estado.get("rota", "fim")

    if rota in ("financeiro", "agenda", "faq"):
        return rota

    return "fim"


# ==============================================================================
# CONSTRUÇÃO DO GRAFO
# ==============================================================================
grafo = StateGraph(Estado)

grafo.add_node("guardrail_entrada", no_guardrail_entrada)
grafo.add_node("roteador", no_roteador)
grafo.add_node("financeiro", financeiro_app)
grafo.add_node("agenda", agenda_app)
grafo.add_node("faq", faq_app)
grafo.add_node("orquestrador", no_orquestrador)
grafo.add_node("guardrail_saida", no_guardrail_saida)
grafo.add_node("juiz", no_juiz)

grafo.set_entry_point("guardrail_entrada")
grafo.add_conditional_edges(
    "guardrail_entrada",
    decidir_pos_guardrail_entrada,
    {
        "roteador": "roteador",
        "fim": END,
    },
    
)

grafo.add_conditional_edges(
    "roteador",
    decidir_especialista,
    {
        "financeiro": "financeiro",
        "agenda": "agenda",
        "faq": "faq",
        "fim": END,
    },
)

grafo.add_edge("financeiro", "orquestrador")
grafo.add_edge("agenda", "orquestrador")
grafo.add_edge("orquestrador", "guardrail_saida")
grafo.add_edge("guardrail_saida", "juiz")
grafo.add_edge("faq", "juiz")
grafo.add_edge("juiz", END)

memory = MemorySaver()

fluxo_agentes = grafo.compile(checkpointer=memory)


# ==============================================================================
# FLUXO PRINCIPAL
# ==============================================================================
def executar_fluxo_assessor(
    pergunta_usuario: str,
    session_id: str,
    user_id: str = "usuario_teste",
) -> str:
    pergunta_usuario_anonimizada, _ = anonimizar_entrada(pergunta_usuario)
    estado_inicial = {
        "messages": [
            {
                "role": "human",
                "content": pergunta_usuario,
            }
        ],
        "session_id": session_id,
        "agentes_chamados": [],
        "rota": "",
        "turno_status": "ok",
        "mapa_pii": {},
    }

    turno_id = abrir_turno()
    status = "erro"
    rota = ""
    try:
        estado_final = fluxo_agentes.invoke(
            estado_inicial,
            config={"configurable": {"thread_id": session_id, "user_id": user_id}},
        )

        resposta = estado_final["messages"][-1].content
        salvar_mensagem(session_id, "human", pergunta_usuario_anonimizada, user_id=user_id)
        salvar_mensagem(session_id, "assistant", resposta, user_id=user_id)

        status = status_do_estado(estado_final)
        rota = estado_final.get("rota") or ""
        return resposta
    finally:
        fechar_turno(turno_id, session_id=session_id, rota=rota, status=status)
