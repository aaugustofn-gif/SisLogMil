from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..database import get_db
from ..models import Gerente
from ..auth import exigir_perfil, hash_senha

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def dashboard(request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "admin")
    gerentes = db.query(Gerente).order_by(Gerente.nome).all()
    return templates.TemplateResponse(
        "admin/dashboard.html",
        {"request": request, "sessao": sessao, "gerentes": gerentes},
    )


@router.get("/gerentes/novo")
def novo_gerente_form(request: Request):
    sessao = exigir_perfil(request, "admin")
    return templates.TemplateResponse(
        "admin/gerente_form.html",
        {"request": request, "sessao": sessao, "gerente": None},
    )


@router.post("/gerentes/novo")
def criar_gerente(
    request: Request,
    nome: str = Form(...),
    login: str = Form(...),
    senha: str = Form(...),
    db: Session = Depends(get_db),
):
    exigir_perfil(request, "admin")
    gerente = Gerente(nome=nome.strip(), login=login.strip(), senha_hash=hash_senha(senha))
    db.add(gerente)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            "admin/gerente_form.html",
            {"request": request, "gerente": None, "erro": "Já existe um login com esse nome."},
            status_code=400,
        )
    return RedirectResponse("/admin", status_code=303)


@router.get("/gerentes/{gerente_id}/editar")
def editar_gerente_form(gerente_id: int, request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "admin")
    gerente = db.query(Gerente).get(gerente_id)
    if not gerente:
        raise HTTPException(404)
    return templates.TemplateResponse(
        "admin/gerente_form.html",
        {"request": request, "sessao": sessao, "gerente": gerente},
    )


@router.post("/gerentes/{gerente_id}/editar")
def editar_gerente(
    gerente_id: int,
    request: Request,
    nome: str = Form(...),
    login: str = Form(...),
    senha: str = Form(""),
    db: Session = Depends(get_db),
):
    exigir_perfil(request, "admin")
    gerente = db.query(Gerente).get(gerente_id)
    if not gerente:
        raise HTTPException(404)
    gerente.nome = nome.strip()
    gerente.login = login.strip()
    if senha.strip():
        gerente.senha_hash = hash_senha(senha.strip())
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            "admin/gerente_form.html",
            {"request": request, "gerente": gerente, "erro": "Já existe um login com esse nome."},
            status_code=400,
        )
    return RedirectResponse("/admin", status_code=303)


@router.post("/gerentes/{gerente_id}/alternar-status")
def alternar_status_gerente(gerente_id: int, request: Request, db: Session = Depends(get_db)):
    """Ativa ou desativa o acesso do gerente, sem apagar seus dados/exercícios."""
    exigir_perfil(request, "admin")
    gerente = db.query(Gerente).get(gerente_id)
    if not gerente:
        raise HTTPException(404)
    gerente.ativo = 0 if gerente.ativo else 1
    db.commit()
    return RedirectResponse("/admin", status_code=303)
