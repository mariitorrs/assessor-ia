import httpx

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from app.config import GEMINI_API_KEY, GROQ_API_KEY


llm_gemini = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.7,
    google_api_key=GEMINI_API_KEY,
)


llm_groq = ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0.2,
    api_key=GROQ_API_KEY,
    reasoning_effort="low",
    model_kwargs={
        "include_reasoning": False,
    },
    http_client=httpx.Client(trust_env=False),
    http_async_client=httpx.AsyncClient(trust_env=False),
)


llm_especialista = llm_gemini.with_fallbacks([llm_groq])


llm_rapido = ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0.0,
    api_key=GROQ_API_KEY,
    reasoning_effort="low",
    model_kwargs={
        "include_reasoning": False,
    },
    http_client=httpx.Client(trust_env=False),
    http_async_client=httpx.AsyncClient(trust_env=False),
)
