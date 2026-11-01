from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    """O que o navegador envia no POST /chat."""

    session_id: str = Field(..., examples=["550e8400-e29b-41d4-a716-446655440000"])
    user_id: str = Field(
        default="usuario_teste",
        description="Identifica o usuário de forma estável entre sessões.",
        examples=["usuario_teste"],
    )
    pergunta: str = Field(
        ..., min_length=1, examples=["gastei 50 reais no mercado"]
    )


class ChatResponse(BaseModel):
    """O que a API devolve no POST /chat."""

    resposta: str
    agentes_chamados: list[str] = Field(default_factory=list)


class SessionResponse(BaseModel):
    """Ainda não é usado — é do Passo 6 da Etapa 3."""

    session_id: str
    resumo: str | None = None


class PerfilRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(..., min_length=1)
    renda_mensal: float = Field(..., gt=0, allow_inf_nan=False)
    objetivo: str = Field(..., min_length=1, max_length=120)
    tolerancia_risco: Literal["baixa", "media", "alta"]
    preferencias: str = Field(..., min_length=1)

    @field_validator("user_id", "objetivo", "preferencias", mode="before")
    @classmethod
    def remover_espacos_externos(cls, valor):
        return valor.strip() if isinstance(valor, str) else valor


class PerfilResponse(BaseModel):
    user_id: str
    renda_mensal: float
    objetivo: str
    tolerancia_risco: Literal["baixa", "media", "alta"]
    preferencias: str
