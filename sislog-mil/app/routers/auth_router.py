from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Administrador, Gerente, Usuario
from ..auth import verificar_senha, criar_token, usuario_logado

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _destino_por_perfil(tipo: str) -> str:
    return {
        "admin": "/admin",
        "gerente": "/gerente",
        "usuario": "/usuario",
    }[tipo]


@router.get("/login")
def tela_login(request: Request):
    sessao = usuario_logado(request)
    if sessao:
        return RedirectResponse(_destino_por_perfil(sessao["tipo"]))
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
def processar_login(request: Request, login: str = Form(...), senha: str = Form(...), db: Session = Depends(get_db)):
    login = login.strip()

    admin = db.query(Administrador).filter(Administrador.login == login).first()
    if admin and verificar_senha(senha, admin.senha_hash):
        token = criar_token("admin", admin.id, admin.nome)
        resp = RedirectResponse("/admin", status_code=303)
        resp.set_cookie("sessao", token, httponly=True, max_age=12 * 3600)
        return resp

    gerente = db.query(Gerente).filter(Gerente.login == login, Gerente.ativo == 1).first()
    if gerente and verificar_senha(senha, gerente.senha_hash):
        token = criar_token("gerente", gerente.id, gerente.nome)
        resp = RedirectResponse("/gerente", status_code=303)
        resp.set_cookie("sessao", token, httponly=True, max_age=12 * 3600)
        return resp

    usuario = db.query(Usuario).filter(Usuario.login == login, Usuario.ativo == 1).first()
    if usuario and verificar_senha(senha, usuario.senha_hash):
        token = criar_token("usuario", usuario.id, usuario.nome)
        resp = RedirectResponse("/usuario", status_code=303)
        resp.set_cookie("sessao", token, httponly=True, max_age=12 * 3600)
        return resp

    return templates.TemplateResponse(
        "login.html",
        {"request": request, "erro": "Login ou senha inválidos."},
        status_code=401,
    )


@router.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("sessao")
    return resp
