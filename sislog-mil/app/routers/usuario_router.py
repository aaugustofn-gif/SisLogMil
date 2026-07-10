from datetime import date
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Usuario, Categoria, Item, LancamentoDisponibilidade, LancamentoConsumo
from ..auth import exigir_perfil, hash_senha, verificar_senha

router = APIRouter(prefix="/usuario")
templates = Jinja2Templates(directory="app/templates")


def _usuario_atual(db: Session, sessao: dict) -> Usuario:
    usuario = db.query(Usuario).get(sessao["id"])
    if not usuario or not usuario.ativo:
        raise HTTPException(404, "Usuário não encontrado ou desativado.")
    return usuario


@router.get("")
def dashboard(request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "usuario")
    usuario = _usuario_atual(db, sessao)
    ex = usuario.exercicio
    hoje = date.today()

    # Para cada item de categoria "disponibilidade", busca o lançamento
    # que ESTE usuário já fez hoje (se houver), para pré-preencher o formulário.
    meus_disponibilidade = {}
    for cat in ex.categorias:
        if cat.tipo_grafico != "disponibilidade":
            continue
        for item in cat.itens:
            lanc = (
                db.query(LancamentoDisponibilidade)
                .filter(
                    LancamentoDisponibilidade.item_id == item.id,
                    LancamentoDisponibilidade.usuario_id == usuario.id,
                    LancamentoDisponibilidade.data == hoje,
                )
                .first()
            )
            meus_disponibilidade[item.id] = lanc

    # Para categorias "consumo", mostra os lançamentos que ESTE usuário já
    # fez hoje para cada item (pode haver mais de um, é um registro cumulativo).
    meus_consumo = {}
    for cat in ex.categorias:
        if cat.tipo_grafico != "consumo":
            continue
        for item in cat.itens:
            lancs = (
                db.query(LancamentoConsumo)
                .filter(
                    LancamentoConsumo.item_id == item.id,
                    LancamentoConsumo.usuario_id == usuario.id,
                    LancamentoConsumo.data == hoje,
                )
                .order_by(LancamentoConsumo.criado_em.desc())
                .all()
            )
            meus_consumo[item.id] = lancs

    return templates.TemplateResponse(
        "usuario/dashboard.html",
        {
            "request": request,
            "sessao": sessao,
            "usuario": usuario,
            "ex": ex,
            "hoje": hoje,
            "meus_disponibilidade": meus_disponibilidade,
            "meus_consumo": meus_consumo,
        },
    )


@router.post("/disponibilidade/{item_id}")
def lancar_disponibilidade(
    item_id: int,
    request: Request,
    quantidade_disponivel: int = Form(...),
    quantidade_indisponivel: int = Form(...),
    db: Session = Depends(get_db),
):
    sessao = exigir_perfil(request, "usuario")
    usuario = _usuario_atual(db, sessao)
    item = db.query(Item).get(item_id)
    if not item or item.categoria.exercicio_id != usuario.exercicio_id or item.categoria.tipo_grafico != "disponibilidade":
        raise HTTPException(404)

    hoje = date.today()
    lanc = (
        db.query(LancamentoDisponibilidade)
        .filter(
            LancamentoDisponibilidade.item_id == item.id,
            LancamentoDisponibilidade.usuario_id == usuario.id,
            LancamentoDisponibilidade.data == hoje,
        )
        .first()
    )
    if lanc:
        lanc.quantidade_disponivel = quantidade_disponivel
        lanc.quantidade_indisponivel = quantidade_indisponivel
    else:
        lanc = LancamentoDisponibilidade(
            item_id=item.id, usuario_id=usuario.id, data=hoje,
            quantidade_disponivel=quantidade_disponivel,
            quantidade_indisponivel=quantidade_indisponivel,
        )
        db.add(lanc)
    db.commit()
    return RedirectResponse("/usuario", status_code=303)


@router.post("/consumo/{item_id}")
def lancar_consumo(
    item_id: int,
    request: Request,
    quantidade: float = Form(...),
    db: Session = Depends(get_db),
):
    sessao = exigir_perfil(request, "usuario")
    usuario = _usuario_atual(db, sessao)
    item = db.query(Item).get(item_id)
    if not item or item.categoria.exercicio_id != usuario.exercicio_id or item.categoria.tipo_grafico != "consumo":
        raise HTTPException(404)

    lanc = LancamentoConsumo(item_id=item.id, usuario_id=usuario.id, data=date.today(), quantidade=quantidade)
    db.add(lanc)
    db.commit()
    return RedirectResponse("/usuario", status_code=303)


@router.post("/consumo/{item_id}/lancamento/{lanc_id}/excluir")
def excluir_meu_consumo(item_id: int, lanc_id: int, request: Request, db: Session = Depends(get_db)):
    """Permite ao usuário desfazer um lançamento de consumo que ele mesmo fez hoje, por engano."""
    sessao = exigir_perfil(request, "usuario")
    usuario = _usuario_atual(db, sessao)
    lanc = db.query(LancamentoConsumo).get(lanc_id)
    if not lanc or lanc.item_id != item_id or lanc.usuario_id != usuario.id or lanc.data != date.today():
        raise HTTPException(404)
    db.delete(lanc)
    db.commit()
    return RedirectResponse("/usuario", status_code=303)


@router.get("/senha")
def trocar_senha_form(request: Request):
    sessao = exigir_perfil(request, "usuario")
    return templates.TemplateResponse("usuario/senha.html", {"request": request, "sessao": sessao})


@router.post("/senha")
def trocar_senha(
    request: Request,
    senha_atual: str = Form(...),
    nova_senha: str = Form(...),
    db: Session = Depends(get_db),
):
    sessao = exigir_perfil(request, "usuario")
    usuario = _usuario_atual(db, sessao)
    if not verificar_senha(senha_atual, usuario.senha_hash):
        return templates.TemplateResponse(
            "usuario/senha.html",
            {"request": request, "sessao": sessao, "erro": "Senha atual incorreta."},
            status_code=400,
        )
    usuario.senha_hash = hash_senha(nova_senha)
    db.commit()
    return templates.TemplateResponse(
        "usuario/senha.html", {"request": request, "sessao": sessao, "sucesso": "Senha alterada com sucesso."}
    )
