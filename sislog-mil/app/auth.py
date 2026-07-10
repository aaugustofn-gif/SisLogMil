"""
Autenticação simples baseada em cookie de sessão assinado (JWT).

Existem 3 tipos de login: administrador, gerente e usuario.
O token guarda o tipo e o id de quem logou, e cada rota protegida
confere se o tipo bate com o perfil esperado.
"""
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Request, HTTPException, status
from jose import jwt, JWTError
from passlib.context import CryptContext

SECRET_KEY = os.getenv("SECRET_KEY", "troque-esta-chave-em-producao-no-render")
ALGORITHM = "HS256"
EXPIRE_HOURS = 12

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_senha(senha: str) -> str:
    return pwd_context.hash(senha)


def verificar_senha(senha: str, senha_hash: str) -> bool:
    return pwd_context.verify(senha, senha_hash)


def criar_token(tipo: str, user_id: int, nome: str) -> str:
    payload = {
        "tipo": tipo,        # "admin" | "gerente" | "usuario"
        "id": user_id,
        "nome": nome,
        "exp": datetime.utcnow() + timedelta(hours=EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def ler_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def usuario_logado(request: Request) -> Optional[dict]:
    """Lê o cookie 'sessao' e retorna o payload, ou None se não houver sessão válida."""
    token = request.cookies.get("sessao")
    if not token:
        return None
    return ler_token(token)


def exigir_perfil(request: Request, tipo_esperado: str) -> dict:
    """Usado no início de cada rota protegida. Redireciona/erra se não autorizado."""
    sessao = usuario_logado(request)
    if not sessao or sessao.get("tipo") != tipo_esperado:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return sessao
