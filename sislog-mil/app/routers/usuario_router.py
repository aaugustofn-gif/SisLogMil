from datetime import date, datetime, timedelta
from urllib.parse import quote
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Usuario, Categoria, Item, LancamentoDisponibilidade, LancamentoConsumo
from ..auth import exigir_perfil, hash_senha, verificar_senha

router = APIRouter(prefix="/usuario")
templates = Jinja2Templates(directory="app/templates")

JANELA_EDICAO = timedelta(minutes=10)


def _usuario_atual(db: Session, sessao: dict) -> Usuario:
    usuario = db.query(Usuario).get(sessao["id"])
    if not usuario or not usuario.ativo:
        raise HTTPException(404, "Usuário não encontrado ou desativado.")
    return usuario


def _pode_editar(lanc: LancamentoDisponibilidade) -> bool:
    """Usuário só pode editar um lançamento de disponibilidade que ele mesmo fez
    dentro de 10 minutos da criação, e só uma única vez. Depois disso, só o gerente edita."""
    if lanc.editado:
        return False
    return (datetime.utcnow() - lanc.criado_em) <= JANELA_EDICAO


@router.get("")
def dashboard(request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "usuario")
    usuario = _usuario_atual(db, sessao)
    ex = usuario.exercicio
    hoje = date.today()

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
            meus_disponibilidade[item.id] = {
                "lanc": lanc,
                "editavel": (lanc is None) or _pode_editar(lanc),
            }

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
            meus_consumo[item.id] = [
                {"lanc": l, "editavel": (datetime.utcnow() - l.criado_em) <= JANELA_EDICAO}
                for l in lancs
            ]

    bloqueados = request.query_params.get("bloqueados", "")
    bloqueados = [b for b in bloqueados.split(",") if b]

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
            "bloqueados": bloqueados,
            "sucesso": request.query_params.get("ok") == "1",
        },
    )


@router.post("/lancar-tudo")
async def lancar_tudo(request: Request, db: Session = Depends(get_db)):
    """Processa, em uma única submissão, todos os lançamentos de disponibilidade
    e consumo preenchidos na tela do usuário."""
    sessao = exigir_perfil(request, "usuario")
    usuario = _usuario_atual(db, sessao)
    ex = usuario.exercicio
    hoje = date.today()
    form = await request.form()

    bloqueados = []

    for cat in ex.categorias:
        if cat.tipo_grafico == "disponibilidade":
            for item in cat.itens:
                disp_bruto = (form.get(f"disp_{item.id}_disponivel") or "").strip()
                indisp_bruto = (form.get(f"disp_{item.id}_indisponivel") or "").strip()
                if not disp_bruto and not indisp_bruto:
                    continue  # usuário não preencheu este item agora

                disponivel = int(disp_bruto) if disp_bruto else 0
                indisponivel = int(indisp_bruto) if indisp_bruto else 0

                lanc = (
                    db.query(LancamentoDisponibilidade)
                    .filter(
                        LancamentoDisponibilidade.item_id == item.id,
                        LancamentoDisponibilidade.usuario_id == usuario.id,
                        LancamentoDisponibilidade.data == hoje,
                    )
                    .first()
                )
                if lanc is None:
                    db.add(LancamentoDisponibilidade(
                        item_id=item.id, usuario_id=usuario.id, data=hoje,
                        quantidade_disponivel=disponivel, quantidade_indisponivel=indisponivel,
                    ))
                elif _pode_editar(lanc):
                    lanc.quantidade_disponivel = disponivel
                    lanc.quantidade_indisponivel = indisponivel
                    lanc.editado = 1
                else:
                    bloqueados.append(item.nome)

        else:
            for item in cat.itens:
                bruto = (form.get(f"consumo_{item.id}") or "").strip()
                if not bruto:
                    continue
                db.add(LancamentoConsumo(
                    item_id=item.id, usuario_id=usuario.id, data=hoje, quantidade=float(bruto),
                ))

    db.commit()

    destino = "/usuario?ok=1"
    if bloqueados:
        destino += "&bloqueados=" + quote(",".join(bloqueados))
    return RedirectResponse(destino, status_code=303)


@router.post("/consumo/{item_id}/lancamento/{lanc_id}/excluir")
def excluir_meu_consumo(item_id: int, lanc_id: int, request: Request, db: Session = Depends(get_db)):
    """Permite ao usuário desfazer um lançamento de consumo feito por ele mesmo,
    só dentro dos primeiros 10 minutos após o lançamento."""
    sessao = exigir_perfil(request, "usuario")
    usuario = _usuario_atual(db, sessao)
    lanc = db.query(LancamentoConsumo).get(lanc_id)
    if not lanc or lanc.item_id != item_id or lanc.usuario_id != usuario.id:
        raise HTTPException(404)
    if (datetime.utcnow() - lanc.criado_em) > JANELA_EDICAO:
        return RedirectResponse("/usuario?erro=prazo_consumo", status_code=303)
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
