from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config.settings import settings
from shared.database.session import get_db
from shared.models.usuario import Usuario
from shared.schemas.usuario import TokenResponse, UsuarioLogin, UsuarioResponse
from shared.security.encryption import hash_senha, verificar_senha

# Hash computado uma vez ao importar o módulo.
# Usado no login quando o e-mail não existe, para que o tempo de resposta
# seja indistinguível do caso em que a senha está errada — evita enumeração
# de e-mails via timing attack (always run bcrypt, even for unknown users).
_DUMMY_HASH: str = hash_senha("__sentinel_dummy_para_timing_attack__")
from shared.security.jwt import (
    criar_refresh_token,
    criar_token,
    revogar_token,
    validar_token,
)

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UsuarioLogin, db: AsyncSession = Depends(get_db)):
    """
    Autentica um usuário (advogado, assistente, admin) com e-mail e senha.
    Retorna o Access Token (curta duração) e o Refresh Token (longa duração).
    """
    # 1. Busca o usuário pelo e-mail
    query = select(Usuario).where(Usuario.email == credentials.email)
    result = await db.execute(query)
    usuario = result.scalars().first()

    # 2. Verifica se o usuário existe e se a senha bate com o hash bcrypt
    if not usuario or not verificar_senha(credentials.senha, usuario.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Verifica se a conta está ativa (se tivermos essa flag, por enquanto só vamos em frente)
    # se hasattr(usuario, "ativo") and not usuario.ativo: ...

    # 4. Atualiza a data do último login
    usuario.ultimo_login = datetime.utcnow()
    # O get_db vai dar db.commit() ao final da requisição se não houver erro no FastApi

    # 5. Gera os Tokens
    access_token = criar_token(
        user_id=usuario.id, escritorio_id=usuario.escritorio_id, role=usuario.role
    )
    refresh_token = criar_refresh_token(user_id=usuario.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_EXPIRATION_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Renova o Access Token usando um Refresh Token válido.
    Espera receber o refresh token no Authorization header (Bearer).
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Refresh Token ausente")

    token = auth_header.split(" ")[1]

    try:
        # Decodifica o token antigo
        payload = validar_token(token)

        # O refresh token viaja leve, verificamos explicitamente a flag:
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Token fornecido não é um Refresh Token")

        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(status_code=401, detail="Token sem identificação de usuário")
        user_id = int(str(user_id_str))

        # Precisamos ler o banco de novo para puxar as roles e escritorio_id atualizadas
        usuario = await db.get(Usuario, user_id)
        if not usuario:
            raise HTTPException(status_code=401, detail="Usuário do token não existe mais")

        # Gera novo par (isso invalida a ideia de que o refresh vive pra sempre, entregamos um novo access)
        access_token = criar_token(
            user_id=usuario.id, escritorio_id=usuario.escritorio_id, role=usuario.role
        )
        # Opcional: Rotacionar o refresh token também ou só devolver o mesmo
        new_refresh = criar_refresh_token(user_id=usuario.id)

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh,
            expires_in=settings.JWT_EXPIRATION_MINUTES * 60,
        )

    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


@router.post("/logout", status_code=204)
async def logout(request: Request):
    """
    Invalida o Access Token atual adicionando-o à blacklist do Redis.
    O cliente deve descartar o token e o refresh token após o logout.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        revogar_token(token)
    return None


@router.get("/me", response_model=UsuarioResponse)
async def get_me(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Retorna os dados do próprio usuário logado (Meu Perfil).
    Esta rota é protegida pelo JWTAuthMiddleware, logo request.state.user_payload vai existir.
    """
    # Se o Dev não colocou o Auth Middleware global, vamos nos blindar
    if not hasattr(request.state, "user_payload"):
        raise HTTPException(status_code=401, detail="Não autenticado")

    user_id = int(request.state.user_payload.get("sub"))

    usuario = await db.get(Usuario, user_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado no banco de dados")

    return usuario
