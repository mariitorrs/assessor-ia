const API_BASE = window.location.origin;
const CHAT_ENDPOINT = `${API_BASE}/chat`;

const thread = document.getElementById("thread");
const threadEmpty = document.getElementById("thread-empty");
const composer = document.getElementById("composer");
const inputPergunta = document.getElementById("pergunta");
const botaoEnviar = document.getElementById("enviar");
const sessionIdEl = document.getElementById("session-id");
const resetButton = document.getElementById("reset-session");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const hint = document.getElementById("hint");
const quickActionButtons = document.querySelectorAll("[data-prompt]");

const SESSION_STORAGE_KEY = "assistente_session_id";

function gerarSessionId() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return "sess-" + Math.random().toString(36).slice(2, 10);
}

function obterOuCriarSessionId() {
  let id = localStorage.getItem(SESSION_STORAGE_KEY);
  if (!id) {
    id = gerarSessionId();
    localStorage.setItem(SESSION_STORAGE_KEY, id);
  }
  return id;
}

function exibirSessionId(id) {
  sessionIdEl.textContent = id.length > 18 ? id.slice(0, 13) + "…" : id;
  sessionIdEl.title = id;
}

async function encerrarSessaoAtual(id) {
  try {
    const resposta = await fetch(`${API_BASE}/sessions/${encodeURIComponent(id)}/encerrar`, {
      method: "POST",
    });
    if (!resposta.ok) return null;
    const dados = await resposta.json();
    return dados.resumo;
  } catch (erro) {
    console.warn("Não foi possível encerrar a sessão anterior:", erro);
    return null;
  }
}

async function iniciarNovaSessao() {
  const anterior = sessionId;
  resetButton.disabled = true;
  setHint("guardando a conversa anterior... ♡");

  const resumo = await encerrarSessaoAtual(anterior);
  sessionId = gerarSessionId();
  localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  exibirSessionId(sessionId);

  thread.innerHTML = "";
  thread.appendChild(threadEmpty);
  threadEmpty.style.display = "grid";

  setHint(resumo ? "conversa anterior guardadinha ✿" : "nova conversa prontinha ✿");
  resetButton.disabled = false;
  inputPergunta.focus();
}

let sessionId = obterOuCriarSessionId();
exibirSessionId(sessionId);
resetButton.addEventListener("click", iniciarNovaSessao);

function setHint(texto, comoErro = false) {
  hint.textContent = texto || "";
  hint.classList.toggle("is-error", comoErro);
}

function marcarStatus(online) {
  statusDot.classList.toggle("is-offline", !online);
  statusText.textContent = online ? "prontinho" : "ops, desconectou";
}

function escaparHtml(texto) {
  const div = document.createElement("div");
  div.textContent = texto;
  return div.innerHTML;
}

function rolarParaFinal() {
  requestAnimationFrame(() => {
    thread.scrollTop = thread.scrollHeight;
  });
}

function esconderBoasVindas() {
  if (threadEmpty) threadEmpty.style.display = "none";
}

function adicionarMensagem({ tipo, texto, agentes }) {
  esconderBoasVindas();

  const wrapper = document.createElement("article");
  wrapper.className = `message message--${tipo}`;

  const label = document.createElement("div");
  label.className = "message__label";
  label.textContent = tipo === "user" ? "Você" : tipo === "error" ? "assessor" : "Assessor";
  wrapper.appendChild(label);

  const bubble = document.createElement("div");
  bubble.className = "message__bubble";
  bubble.innerHTML = escaparHtml(texto);
  wrapper.appendChild(bubble);

  if (agentes && agentes.length > 0) {
    const agentesEl = document.createElement("div");
    agentesEl.className = "message__agents";

    agentes.forEach((nome) => {
      const tag = document.createElement("span");
      tag.className = "agent-tag";
      tag.textContent = nome;
      agentesEl.appendChild(tag);
    });

    wrapper.appendChild(agentesEl);
  }

  thread.appendChild(wrapper);
  rolarParaFinal();
  return wrapper;
}

function adicionarIndicadorDigitando() {
  esconderBoasVindas();

  const wrapper = document.createElement("article");
  wrapper.className = "message message--assistant";
  wrapper.id = "typing-indicator";

  const label = document.createElement("div");
  label.className = "message__label";
  label.textContent = "assessor";
  wrapper.appendChild(label);

  const bubble = document.createElement("div");
  bubble.className = "message__bubble";
  bubble.innerHTML = `<span class="typing" aria-label="Digitando"><span></span><span></span><span></span></span>`;
  wrapper.appendChild(bubble);

  thread.appendChild(wrapper);
  rolarParaFinal();
}

function removerIndicadorDigitando() {
  document.getElementById("typing-indicator")?.remove();
}

inputPergunta.addEventListener("input", () => {
  inputPergunta.style.height = "auto";
  inputPergunta.style.height = Math.min(inputPergunta.scrollHeight, 130) + "px";
});

inputPergunta.addEventListener("keydown", (evento) => {
  if (evento.key === "Enter" && !evento.shiftKey) {
    evento.preventDefault();
    composer.requestSubmit();
  }
});

quickActionButtons.forEach((button) => {
  button.addEventListener("click", () => {
    inputPergunta.value = button.dataset.prompt || "";
    inputPergunta.dispatchEvent(new Event("input"));
    inputPergunta.focus();
  });
});

composer.addEventListener("submit", async (evento) => {
  evento.preventDefault();

  const pergunta = inputPergunta.value.trim();
  if (!pergunta) return;

  adicionarMensagem({ tipo: "user", texto: pergunta });
  inputPergunta.value = "";
  inputPergunta.style.height = "auto";
  setHint("");

  botaoEnviar.disabled = true;
  inputPergunta.disabled = true;
  adicionarIndicadorDigitando();

  try {
    const resposta = await fetch(CHAT_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pergunta,
        session_id: sessionId,
      }),
    });

    if (!resposta.ok) {
      const detalhe = await resposta.text();
      throw new Error(`A API respondeu com status ${resposta.status}. ${detalhe || "Sem detalhe no corpo da resposta."}`);
    }

    const dados = await resposta.json();
    marcarStatus(true);
    removerIndicadorDigitando();

    adicionarMensagem({
      tipo: "assistant",
      texto: dados.resposta ?? "(resposta vazia)",
      agentes: dados.agentes_chamados,
    });
  } catch (erro) {
    marcarStatus(false);
    removerIndicadorDigitando();

    adicionarMensagem({
      tipo: "error",
      texto: erro.message.includes("Failed to fetch")
        ? "Não consegui conversar com a API agora. Confere se o FastAPI está rodando e tenta de novo ♡"
        : erro.message,
    });

    setHint("deu um errinho na conexão :(", true);
    console.error(erro);
  } finally {
    botaoEnviar.disabled = false;
    inputPergunta.disabled = false;
    inputPergunta.focus();
  }
});

inputPergunta.focus();
