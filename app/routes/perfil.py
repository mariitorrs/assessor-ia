from fastapi import APIRouter, HTTPException

from app.perfil import salvar_perfil
from app.schemas import PerfilRequest, PerfilResponse


router = APIRouter(tags=["perfil"])


@router.post("/perfil", response_model=PerfilResponse)
def gravar_perfil(perfil: PerfilRequest) -> PerfilResponse:
    try:
        return PerfilResponse(**salvar_perfil(perfil))
    except Exception as erro:
        print(f"[perfil] erro ao salvar: {erro}")
        raise HTTPException(
            status_code=503,
            detail="Não foi possível salvar o perfil agora.",
        ) from erro
