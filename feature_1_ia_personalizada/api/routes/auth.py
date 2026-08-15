from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.api.middleware.csrf import (
    _COOKIE_MAX_AGE,
    _COOKIE_NAME,
    gerar_csrf_token,
)
from shared.config.settings import settings
from shared.database.session import get_db
from shared.models.usuario import Usuario
from shared.schemas.usuario import (
    TokenResponse,
    UsuarioChangePassword,
    UsuarioLogin,
    UsuarioResponse,
)
from shared.security.encryption import hash_senha, verificar_senha
from shared.security.jwt import (
    criar_refresh_token,
    criar_token,
    revogar_token,
    token_esta_revogado,
    validar_token,
)

# Hash computado uma vez ao importar o módulo.
# Usado no login quando o e-mail não existe, para que o tempo de resposta
# seja indistinguível do caso em que a senha está errada — evita enumeração
# de e-mails via timing attack (always run bcrypt, even for unknown users).
_DUMMY_HASH: str = hash_senha("__sentinel_dummy_para_timing_attack__")

router = APIRouter(prefix="/auth", tags=["Autenticação"])


_LOGIN_MAX_FALHAS = 10  # tentativas antes do bloqueio
_LOGIN_FALHA_JANELA_S = 3600  # 1 hora — janela de contagem de falhas
_LOGIN_LOCKOUT_S = 900  # 15 min — duração do bloqueio


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request, credentials: UsuarioLogin, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """
    Autentica um usuário (advogado, assistente, admin) com e-mail e senha.
    Retorna o Access Token (curta duração) e o Refresh Token (longa duração).
    """
    redis = getattr(request.app.state, "redis_client", None)
    email_key = credentials.email.lower().strip()
    lockout_key = f"login:lockout:{email_key}"
    falhas_key = f"login:fail:{email_key}"

    # 1. Verifica lockout por conta (complementa o rate limit por IP do middleware)
    if redis is not None and await redis.exists(lockout_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Conta temporariamente bloqueada por excesso de tentativas. Tente em 15 minutos.",
        )

    # 2. Busca o usuário pelo e-mail
    query = select(Usuario).where(Usuario.email == credentials.email)
    result = await db.execute(query)
    usuario = result.scalars().first()

    # 3. Sempre executa o bcrypt (mesmo quando o usuário não existe) para que o tempo
    #    de resposta seja constante — impede enumeração de e-mails via timing attack.
    hash_ref = usuario.senha_hash if usuario else _DUMMY_HASH
    senha_ok = verificar_senha(credentials.senha, hash_ref)

    if not usuario or not senha_ok:
        # Incrementa contador de falhas por conta
        if redis is not None:
            falhas = await redis.incr(falhas_key)
            if falhas == 1:
                await redis.expire(falhas_key, _LOGIN_FALHA_JANELA_S)
            if falhas >= _LOGIN_MAX_FALHAS:
                await redis.setex(lockout_key, _LOGIN_LOCKOUT_S, "1")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 4. Login bem-sucedido — limpa contadores de falha
    if redis is not None:
        await redis.delete(falhas_key, lockout_key)

    # 5. Verifica se a conta está ativa (se tivermos essa flag, por enquanto só vamos em frente)
    # se hasattr(usuario, "ativo") and not usuario.ativo: ...

    # 6. Atualiza a data do último login
    usuario.ultimo_login = datetime.utcnow()
    # O get_db vai dar db.commit() ao final da requisição se não houver erro no FastApi

    # 7. Gera os Tokens
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
async def refresh(request: Request, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """
    Renova o Access Token usando um Refresh Token válido.
    Espera receber o refresh token no Authorization header (Bearer).
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Refresh Token ausente")

    token = auth_header.split(" ")[1]

    try:
        # Rejeita tokens já revogados (ex: refresh reutilizado após rotação)
        if token_esta_revogado(token):
            raise HTTPException(
                status_code=401, detail="Refresh token revogado. Faça login novamente."
            )

        payload = validar_token(token)

        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Token fornecido não é um Refresh Token")

        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(status_code=401, detail="Token sem identificação de usuário")
        user_id = int(str(user_id_str))

        # Busca roles e escritorio_id atualizados do banco
        usuario = await db.get(Usuario, user_id)
        if not usuario:
            raise HTTPException(status_code=401, detail="Usuário do token não existe mais")

        # Emite novo par de tokens
        access_token = criar_token(
            user_id=usuario.id, escritorio_id=usuario.escritorio_id, role=usuario.role
        )
        new_refresh = criar_refresh_token(user_id=usuario.id)

        # Revoga o refresh token antigo — rotação real: token usado uma única vez
        revogar_token(token)

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh,
            expires_in=settings.JWT_EXPIRATION_MINUTES * 60,
        )

    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


@router.post("/logout", status_code=204)
async def logout(request: Request, body: LogoutRequest | None = None) -> None:
    """
    Invalida o Access Token (Authorization header) e o Refresh Token (body).
    Ambos são adicionados à blacklist do Redis com TTL até a expiração natural.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        revogar_token(auth_header.split(" ")[1])
    if body and body.refresh_token:
        revogar_token(body.refresh_token)
    return None


@router.get("/csrf-token", include_in_schema=True)
async def csrf_token() -> JSONResponse:
    """
    Emite um novo token CSRF.

    O token é devolvido tanto no corpo JSON quanto definido como cookie
    `csrf_token` (HttpOnly=False para que o JavaScript possa lê-lo).

    O frontend deve:
    1. Chamar este endpoint uma vez ao iniciar a sessão.
    2. Armazenar o valor retornado.
    3. Incluí-lo no header `X-CSRF-Token` em todas as requisições POST/PUT/PATCH/DELETE.
    """
    token = gerar_csrf_token()
    response = JSONResponse(content={"csrf_token": token})
    is_prod = getattr(settings, "ENVIRONMENT", "development") == "production"
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=False,  # precisa ser lido pelo JS (Double Submit Cookie)
        samesite=(
            "none" if is_prod else "lax"
        ),  # "none" exigido para requisições cross-origin (frontend em outro domínio)
        secure=is_prod,  # False em dev (HTTP); True em prod (HTTPS)
        max_age=_COOKIE_MAX_AGE,
    )
    return response


@router.get("/me", response_model=UsuarioResponse)
async def get_me(request: Request, db: AsyncSession = Depends(get_db)) -> Usuario:
    """
    Retorna os dados do próprio usuário logado (Meu Perfil).
    Esta rota é protegida pelo JWTAuthMiddleware, logo request.state.user_payload vai existir.
    """
    # Se o Dev não colocou o Auth Middleware global, vamos nos blindar
    if not hasattr(request.state, "user_payload"):
        raise HTTPException(status_code=401, detail="Não autenticado")

    sub = request.state.user_payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=401, detail="Token inválido: sub ausente")
    user_id = int(sub)

    usuario = await db.get(Usuario, user_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado no banco de dados")

    return usuario


@router.post("/change-password")
async def change_password(
    request: Request, payload: UsuarioChangePassword, db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    """
    Altera a senha do usuário autenticado.
    """
    if not hasattr(request.state, "user_payload"):
        raise HTTPException(status_code=401, detail="Não autenticado")

    sub = request.state.user_payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=401, detail="Token inválido: sub ausente")

    user_id = int(sub)
    usuario = await db.get(Usuario, user_id)

    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    if not verificar_senha(payload.senha_atual, usuario.senha_hash):
        raise HTTPException(status_code=400, detail="Senha atual incorreta")

    usuario.senha_hash = hash_senha(payload.nova_senha)
    usuario.updated_at = datetime.utcnow()
    # O get_db lida com o db.commit() ao final da requisição no middleware/dependency
    return {"status": "ok", "message": "Senha atualizada com sucesso"}
