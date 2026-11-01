"""Evidence fidelity judge: only the fixed Python message is used on rejection."""

import json
import math
import urllib.error
import urllib.request

from app.config import TYPESAFE_API_KEY

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"
THRESHOLD = 0.70
SAFE_MESSAGE = "N\u00e3o tenho evid\u00eancia para afirmar isso."

RULES = (
    "A pergunta do usuario e evidencia do que ele diz que fez, mas nao de fatos "
    "sobre o mundo. Somatorios, contagens, datas convertidas para o horario de "
    "Brasilia e reformatações feitas somente com dados da evidencia contam como "
    "apoiadas. Saudacoes, esclarecimentos, ofertas de ajuda e ausencia de registro "
    "podem ser apoiadas. Opinioes podem ser citadas como fala do usuario, nao como "
    "fato do sistema. A moeda de cada valor e a que aparece no source_text ou na "
    "fala do usuario. Trocar moedas, somar moedas diferentes num total, ou afirmar "
    "numero, data, telefone ou regra ausente da evidencia conta como sem_apoio."
)


def _text(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
        return "\n".join(part for part in parts if part)
    return str(content or "")


def _collect(state: dict) -> tuple[str, str, str]:
    question = ""
    answer = ""
    evidence = []

    for message in state.get("messages", []):
        kind = getattr(message, "type", "")
        content = _text(message).strip()

        if kind == "human":
            # Keep only messages and evidence from the current user turn.
            question = content
            answer = ""
            evidence = []
        elif kind == "tool" and content:
            name = getattr(message, "name", "") or "tool"
            evidence.append(f"[{name}]\n{content}")
        elif kind == "ai":
            for call in getattr(message, "tool_calls", None) or []:
                args = json.dumps(call.get("args", {}), ensure_ascii=False, default=str)
                evidence.append(f"[chamada {call.get('name')}]\n{args}")
            if content:
                answer = content

    if not evidence:
        evidence_text = "(nenhuma tool devolveu conteudo neste turno)"
    else:
        evidence_text = "\n\n".join(evidence)
    return question, answer, evidence_text[-6000:]


def _publish(text: str, label: str, original: str) -> dict:
    print(f"[juiz] {label}")
    if text.strip() == (original or "").strip():
        return {"agentes_chamados": [f"juiz:{label}"]}
    return {
        "messages": [{"role": "assistant", "content": text.strip()}],
        "agentes_chamados": [f"juiz:{label}"],
    }


def _judge(question: str, answer: str, evidence: str) -> dict:
    if not TYPESAFE_API_KEY:
        return _publish(SAFE_MESSAGE, "sem_chave", answer)

    body = json.dumps(
        {
            "model": JEV_MODEL,
            "state": {
                "pergunta": question,
                "resposta": answer,
                "evidencia": evidence,
                "regras": RULES,
            },
            "questions": {
                "veredito": {
                    "type": "choice",
                    "instructions": (
                        "A resposta afirma somente o que a evidencia sustenta, "
                        "seguindo as regras?"
                    ),
                    "criteria": {
                        "apoiada": "Toda afirmacao factual aparece na evidencia.",
                        "parcial": "Parte aparece e parte nao aparece na evidencia.",
                        "sem_apoio": "Ha fato ou numero sem apoio na evidencia.",
                    },
                },
                "apoiada": {
                    "type": "noul",
                    "instructions": (
                        "A resposta e fiel a evidencia: cada valor, moeda, data e fato "
                        "vem da evidencia, da fala do usuario ou de contas sobre elas?"
                    ),
                },
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        JEV_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {TYPESAFE_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return _publish(SAFE_MESSAGE, f"erro http {error.code}", answer)

    answers = result["answers"]
    choice = answers["veredito"]["choice"]
    confidence = float(answers["apoiada"]["noul"])
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise ValueError("JEV returned an invalid noul probability")

    if choice == "apoiada" and confidence >= THRESHOLD:
        return _publish(answer, f"apoiada noul={confidence:.2f}", answer)

    label = "apoiada:abaixo_do_limiar" if choice == "apoiada" else str(choice)
    return _publish(SAFE_MESSAGE, f"{label} noul={confidence:.2f}", answer)


def no_juiz(state: dict) -> dict:
    """Verify the final answer against evidence collected during this turn."""
    question, answer, evidence = _collect(state)
    if not answer:
        return {"agentes_chamados": ["juiz:sem_resposta"]}
    try:
        return _judge(question, answer, evidence)
    except Exception as error:
        print(f"[juiz] erro {error}")
        return _publish(SAFE_MESSAGE, "erro", answer)
