from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..database import get_db
from ..models import (
    Exercicio, Gerente, Categoria, Item, Usuario,
    LancamentoDisponibilidade, LancamentoConsumo,
)
from ..auth import exigir_perfil, hash_senha

router = APIRouter(prefix="/gerente")
templates = Jinja2Templates(directory="app/templates")


def _exercicio_do_gerente(db: Session, exercicio_id: int, gerente_id: int) -> Exercicio:
    """
    Apesar do nome (mantido para não precisar alterar todas as chamadas),
    esta função não restringe mais o acesso pelo gerente que criou o
    exercício: qualquer gerente pode ver e editar qualquer exercício,
    já que todos pertencem à FFE como um todo. O parâmetro gerente_id
    não é mais usado para filtrar, só fica disponível caso seja útil no futuro.
    """
    ex = db.query(Exercicio).filter(Exercicio.id == exercicio_id).first()
    if not ex:
        raise HTTPException(404, "Exercício não encontrado.")
    return ex


@router.get("")
def dashboard(request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "gerente")
    exercicios = db.query(Exercicio).order_by(Exercicio.data_inicio.desc()).all()
    return templates.TemplateResponse(
        "gerente/dashboard.html", {"request": request, "sessao": sessao, "exercicios": exercicios}
    )


@router.get("/exercicios/novo")
def novo_exercicio_form(request: Request):
    sessao = exigir_perfil(request, "gerente")
    return templates.TemplateResponse(
        "gerente/exercicio_form.html", {"request": request, "sessao": sessao, "exercicio": None}
    )


@router.post("/exercicios/novo")
def criar_exercicio(
    request: Request,
    nome: str = Form(...),
    local: str = Form(...),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    db: Session = Depends(get_db),
):
    sessao = exigir_perfil(request, "gerente")
    ex = Exercicio(
        gerente_id=sessao["id"],
        nome=nome.strip(),
        local=local.strip(),
        data_inicio=datetime.strptime(data_inicio, "%Y-%m-%d").date(),
        data_fim=datetime.strptime(data_fim, "%Y-%m-%d").date(),
    )
    db.add(ex)
    db.commit()
    return RedirectResponse(f"/gerente/exercicios/{ex.id}", status_code=303)


@router.get("/exercicios/{exercicio_id}/editar")
def editar_exercicio_form(exercicio_id: int, request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    return templates.TemplateResponse(
        "gerente/exercicio_form.html", {"request": request, "sessao": sessao, "exercicio": ex}
    )


@router.post("/exercicios/{exercicio_id}/editar")
def editar_exercicio(
    exercicio_id: int,
    request: Request,
    nome: str = Form(...),
    local: str = Form(...),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    db: Session = Depends(get_db),
):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    ex.nome = nome.strip()
    ex.local = local.strip()
    ex.data_inicio = datetime.strptime(data_inicio, "%Y-%m-%d").date()
    ex.data_fim = datetime.strptime(data_fim, "%Y-%m-%d").date()
    db.commit()
    return RedirectResponse(f"/gerente/exercicios/{ex.id}", status_code=303)


@router.get("/exercicios/{exercicio_id}")
def visao_geral_exercicio(exercicio_id: int, request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    return templates.TemplateResponse(
        "gerente/exercicio_visao_geral.html", {"request": request, "sessao": sessao, "ex": ex, "aba": "visao"}
    )


# ---------------------------------------------------------------------------
# Categorias (as "abas" configuráveis de um exercício)
# ---------------------------------------------------------------------------

@router.get("/exercicios/{exercicio_id}/categorias")
def categorias(exercicio_id: int, request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    return templates.TemplateResponse(
        "gerente/categorias.html", {"request": request, "sessao": sessao, "ex": ex, "aba": "categorias"}
    )


@router.get("/exercicios/{exercicio_id}/categorias/nova")
def nova_categoria_form(exercicio_id: int, request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    return templates.TemplateResponse(
        "gerente/categoria_form.html", {"request": request, "sessao": sessao, "ex": ex, "categoria": None}
    )


@router.post("/exercicios/{exercicio_id}/categorias/nova")
def criar_categoria(
    exercicio_id: int,
    request: Request,
    nome: str = Form(...),
    tipo_grafico: str = Form(...),
    db: Session = Depends(get_db),
):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    if tipo_grafico not in ("disponibilidade", "consumo"):
        raise HTTPException(400, "Tipo de gráfico inválido.")
    maior_ordem = max([c.ordem for c in ex.categorias], default=-1)
    cat = Categoria(exercicio_id=ex.id, nome=nome.strip(), tipo_grafico=tipo_grafico, ordem=maior_ordem + 1)
    db.add(cat)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            "gerente/categoria_form.html",
            {"request": request, "sessao": sessao, "ex": ex, "categoria": None, "erro": "Já existe uma categoria com esse nome neste exercício."},
            status_code=400,
        )
    return RedirectResponse(f"/gerente/exercicios/{ex.id}/categorias/{cat.id}", status_code=303)


def _categoria_do_exercicio(db: Session, ex: Exercicio, categoria_id: int) -> Categoria:
    cat = db.query(Categoria).filter(Categoria.id == categoria_id, Categoria.exercicio_id == ex.id).first()
    if not cat:
        raise HTTPException(404, "Categoria não encontrada.")
    return cat


@router.get("/exercicios/{exercicio_id}/categorias/{categoria_id}")
def detalhe_categoria(exercicio_id: int, categoria_id: int, request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    cat = _categoria_do_exercicio(db, ex, categoria_id)
    return templates.TemplateResponse(
        "gerente/categoria_detalhe.html", {"request": request, "sessao": sessao, "ex": ex, "cat": cat}
    )


@router.post("/exercicios/{exercicio_id}/categorias/{categoria_id}/excluir")
def excluir_categoria(exercicio_id: int, categoria_id: int, request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    cat = _categoria_do_exercicio(db, ex, categoria_id)
    db.delete(cat)
    db.commit()
    return RedirectResponse(f"/gerente/exercicios/{ex.id}/categorias", status_code=303)


# ---------------------------------------------------------------------------
# Itens dentro de uma categoria
# ---------------------------------------------------------------------------

@router.post("/exercicios/{exercicio_id}/categorias/{categoria_id}/itens/novo")
def criar_item(
    exercicio_id: int,
    categoria_id: int,
    request: Request,
    nome: str = Form(...),
    unidade: str = Form(""),
    consumo_autorizado: str = Form(""),
    marco1_nome: str = Form(""),
    marco1_valor: str = Form(""),
    marco2_nome: str = Form(""),
    marco2_valor: str = Form(""),
    db: Session = Depends(get_db),
):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    cat = _categoria_do_exercicio(db, ex, categoria_id)

    item = Item(categoria_id=cat.id, nome=nome.strip())
    if cat.tipo_grafico == "consumo":
        item.unidade = unidade.strip() or "Unidades"
        item.consumo_autorizado = float(consumo_autorizado) if consumo_autorizado else 0
        if marco1_nome.strip() and marco1_valor.strip():
            item.marco1_nome = marco1_nome.strip()
            item.marco1_valor = float(marco1_valor)
        if marco2_nome.strip() and marco2_valor.strip():
            item.marco2_nome = marco2_nome.strip()
            item.marco2_valor = float(marco2_valor)

    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return RedirectResponse(f"/gerente/exercicios/{ex.id}/categorias/{cat.id}", status_code=303)


@router.post("/exercicios/{exercicio_id}/categorias/{categoria_id}/itens/{item_id}/editar")
def editar_item(
    exercicio_id: int,
    categoria_id: int,
    item_id: int,
    request: Request,
    nome: str = Form(...),
    unidade: str = Form(""),
    consumo_autorizado: str = Form(""),
    marco1_nome: str = Form(""),
    marco1_valor: str = Form(""),
    marco2_nome: str = Form(""),
    marco2_valor: str = Form(""),
    db: Session = Depends(get_db),
):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    cat = _categoria_do_exercicio(db, ex, categoria_id)
    item = db.query(Item).filter(Item.id == item_id, Item.categoria_id == cat.id).first()
    if not item:
        raise HTTPException(404)
    item.nome = nome.strip()
    if cat.tipo_grafico == "consumo":
        item.unidade = unidade.strip() or "Unidades"
        item.consumo_autorizado = float(consumo_autorizado) if consumo_autorizado else 0
        item.marco1_nome = marco1_nome.strip() or None
        item.marco1_valor = float(marco1_valor) if marco1_valor.strip() else None
        item.marco2_nome = marco2_nome.strip() or None
        item.marco2_valor = float(marco2_valor) if marco2_valor.strip() else None
    db.commit()
    return RedirectResponse(f"/gerente/exercicios/{ex.id}/categorias/{cat.id}", status_code=303)


@router.post("/exercicios/{exercicio_id}/categorias/{categoria_id}/itens/{item_id}/excluir")
def excluir_item(exercicio_id: int, categoria_id: int, item_id: int, request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    cat = _categoria_do_exercicio(db, ex, categoria_id)
    item = db.query(Item).filter(Item.id == item_id, Item.categoria_id == cat.id).first()
    if not item:
        raise HTTPException(404)
    db.delete(item)
    db.commit()
    return RedirectResponse(f"/gerente/exercicios/{ex.id}/categorias/{cat.id}", status_code=303)


# ---------------------------------------------------------------------------
# Usuários do exercício
# ---------------------------------------------------------------------------

@router.get("/exercicios/{exercicio_id}/usuarios")
def usuarios(exercicio_id: int, request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    lista = db.query(Usuario).filter(Usuario.exercicio_id == ex.id).order_by(Usuario.nome).all()
    return templates.TemplateResponse(
        "gerente/usuarios.html", {"request": request, "sessao": sessao, "ex": ex, "usuarios": lista, "aba": "usuarios"}
    )


@router.get("/exercicios/{exercicio_id}/usuarios/novo")
def novo_usuario_form(exercicio_id: int, request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    return templates.TemplateResponse(
        "gerente/usuario_form.html", {"request": request, "sessao": sessao, "ex": ex, "usuario": None}
    )


@router.post("/exercicios/{exercicio_id}/usuarios/novo")
def criar_usuario(
    exercicio_id: int,
    request: Request,
    nome: str = Form(...),
    login: str = Form(...),
    senha: str = Form(...),
    db: Session = Depends(get_db),
):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    usuario = Usuario(exercicio_id=ex.id, nome=nome.strip(), login=login.strip(), senha_hash=hash_senha(senha))
    db.add(usuario)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            "gerente/usuario_form.html",
            {"request": request, "sessao": sessao, "ex": ex, "usuario": None, "erro": "Já existe um login com esse nome."},
            status_code=400,
        )
    return RedirectResponse(f"/gerente/exercicios/{ex.id}/usuarios", status_code=303)


@router.get("/exercicios/{exercicio_id}/usuarios/{usuario_id}/editar")
def editar_usuario_form(exercicio_id: int, usuario_id: int, request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id, Usuario.exercicio_id == ex.id).first()
    if not usuario:
        raise HTTPException(404)
    return templates.TemplateResponse(
        "gerente/usuario_form.html", {"request": request, "sessao": sessao, "ex": ex, "usuario": usuario}
    )


@router.post("/exercicios/{exercicio_id}/usuarios/{usuario_id}/editar")
def editar_usuario(
    exercicio_id: int,
    usuario_id: int,
    request: Request,
    nome: str = Form(...),
    login: str = Form(...),
    senha: str = Form(""),
    db: Session = Depends(get_db),
):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id, Usuario.exercicio_id == ex.id).first()
    if not usuario:
        raise HTTPException(404)
    usuario.nome = nome.strip()
    usuario.login = login.strip()
    if senha.strip():
        usuario.senha_hash = hash_senha(senha.strip())
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            "gerente/usuario_form.html",
            {"request": request, "sessao": sessao, "ex": ex, "usuario": usuario, "erro": "Já existe um login com esse nome."},
            status_code=400,
        )
    return RedirectResponse(f"/gerente/exercicios/{ex.id}/usuarios", status_code=303)


@router.post("/exercicios/{exercicio_id}/usuarios/{usuario_id}/alternar-status")
def alternar_status_usuario(exercicio_id: int, usuario_id: int, request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id, Usuario.exercicio_id == ex.id).first()
    if not usuario:
        raise HTTPException(404)
    usuario.ativo = 0 if usuario.ativo else 1
    db.commit()
    return RedirectResponse(f"/gerente/exercicios/{ex.id}/usuarios", status_code=303)


# ---------------------------------------------------------------------------
# Lançamentos (visualizar, editar, excluir o que os usuários lançaram)
# ---------------------------------------------------------------------------

@router.get("/exercicios/{exercicio_id}/lancamentos")
def lancamentos(exercicio_id: int, request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])

    disponibilidade = (
        db.query(LancamentoDisponibilidade)
        .join(Item, LancamentoDisponibilidade.item_id == Item.id)
        .join(Categoria, Item.categoria_id == Categoria.id)
        .filter(Categoria.exercicio_id == ex.id)
        .order_by(LancamentoDisponibilidade.data.desc())
        .limit(200)
        .all()
    )
    consumo = (
        db.query(LancamentoConsumo)
        .join(Item, LancamentoConsumo.item_id == Item.id)
        .join(Categoria, Item.categoria_id == Categoria.id)
        .filter(Categoria.exercicio_id == ex.id)
        .order_by(LancamentoConsumo.data.desc())
        .limit(200)
        .all()
    )
    return templates.TemplateResponse(
        "gerente/lancamentos.html",
        {"request": request, "sessao": sessao, "ex": ex, "disponibilidade": disponibilidade, "consumo": consumo, "aba": "lancamentos"},
    )


@router.get("/exercicios/{exercicio_id}/lancamentos/disponibilidade/{lanc_id}/editar")
def editar_disponibilidade_form(exercicio_id: int, lanc_id: int, request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    lanc = db.query(LancamentoDisponibilidade).get(lanc_id)
    if not lanc or lanc.item.categoria.exercicio_id != ex.id:
        raise HTTPException(404)
    return templates.TemplateResponse(
        "gerente/lancamento_disponibilidade_form.html", {"request": request, "sessao": sessao, "ex": ex, "lanc": lanc}
    )


@router.post("/exercicios/{exercicio_id}/lancamentos/disponibilidade/{lanc_id}/editar")
def editar_disponibilidade(
    exercicio_id: int,
    lanc_id: int,
    request: Request,
    quantidade_disponivel: int = Form(...),
    quantidade_indisponivel: int = Form(...),
    db: Session = Depends(get_db),
):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    lanc = db.query(LancamentoDisponibilidade).get(lanc_id)
    if not lanc or lanc.item.categoria.exercicio_id != ex.id:
        raise HTTPException(404)
    lanc.quantidade_disponivel = quantidade_disponivel
    lanc.quantidade_indisponivel = quantidade_indisponivel
    db.commit()
    return RedirectResponse(f"/gerente/exercicios/{ex.id}/lancamentos", status_code=303)


@router.post("/exercicios/{exercicio_id}/lancamentos/disponibilidade/{lanc_id}/excluir")
def excluir_disponibilidade(exercicio_id: int, lanc_id: int, request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    lanc = db.query(LancamentoDisponibilidade).get(lanc_id)
    if not lanc or lanc.item.categoria.exercicio_id != ex.id:
        raise HTTPException(404)
    db.delete(lanc)
    db.commit()
    return RedirectResponse(f"/gerente/exercicios/{ex.id}/lancamentos", status_code=303)


@router.get("/exercicios/{exercicio_id}/lancamentos/consumo/{lanc_id}/editar")
def editar_consumo_form(exercicio_id: int, lanc_id: int, request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    lanc = db.query(LancamentoConsumo).get(lanc_id)
    if not lanc or lanc.item.categoria.exercicio_id != ex.id:
        raise HTTPException(404)
    return templates.TemplateResponse(
        "gerente/lancamento_consumo_form.html", {"request": request, "sessao": sessao, "ex": ex, "lanc": lanc}
    )


@router.post("/exercicios/{exercicio_id}/lancamentos/consumo/{lanc_id}/editar")
def editar_consumo(
    exercicio_id: int,
    lanc_id: int,
    request: Request,
    quantidade: float = Form(...),
    db: Session = Depends(get_db),
):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    lanc = db.query(LancamentoConsumo).get(lanc_id)
    if not lanc or lanc.item.categoria.exercicio_id != ex.id:
        raise HTTPException(404)
    lanc.quantidade = quantidade
    db.commit()
    return RedirectResponse(f"/gerente/exercicios/{ex.id}/lancamentos", status_code=303)


@router.post("/exercicios/{exercicio_id}/lancamentos/consumo/{lanc_id}/excluir")
def excluir_consumo(exercicio_id: int, lanc_id: int, request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])
    lanc = db.query(LancamentoConsumo).get(lanc_id)
    if not lanc or lanc.item.categoria.exercicio_id != ex.id:
        raise HTTPException(404)
    db.delete(lanc)
    db.commit()
    return RedirectResponse(f"/gerente/exercicios/{ex.id}/lancamentos", status_code=303)


# ---------------------------------------------------------------------------
# Exportação para planilha (.xlsx)
# ---------------------------------------------------------------------------

@router.get("/exercicios/{exercicio_id}/exportar")
def exportar_planilha(exercicio_id: int, request: Request, db: Session = Depends(get_db)):
    sessao = exigir_perfil(request, "gerente")
    ex = _exercicio_do_gerente(db, exercicio_id, sessao["id"])

    from io import BytesIO
    from openpyxl import Workbook
    from fastapi.responses import StreamingResponse

    wb = Workbook()

    ws1 = wb.active
    ws1.title = "Disponibilidade"
    ws1.append(["Categoria", "Item", "Data", "Disponível", "Indisponível", "Lançado por"])
    disponibilidade = (
        db.query(LancamentoDisponibilidade)
        .join(Item, LancamentoDisponibilidade.item_id == Item.id)
        .join(Categoria, Item.categoria_id == Categoria.id)
        .filter(Categoria.exercicio_id == ex.id)
        .order_by(LancamentoDisponibilidade.data)
        .all()
    )
    for l in disponibilidade:
        ws1.append([
            l.item.categoria.nome, l.item.nome, l.data.strftime("%d/%m/%Y"),
            l.quantidade_disponivel, l.quantidade_indisponivel, l.usuario.nome,
        ])

    ws2 = wb.create_sheet("Consumo")
    ws2.append(["Categoria", "Item", "Data", "Quantidade", "Unidade", "Consumo autorizado", "Lançado por"])
    consumo = (
        db.query(LancamentoConsumo)
        .join(Item, LancamentoConsumo.item_id == Item.id)
        .join(Categoria, Item.categoria_id == Categoria.id)
        .filter(Categoria.exercicio_id == ex.id)
        .order_by(LancamentoConsumo.data)
        .all()
    )
    for l in consumo:
        ws2.append([
            l.item.categoria.nome, l.item.nome, l.data.strftime("%d/%m/%Y"),
            l.quantidade, l.item.unidade, l.item.consumo_autorizado, l.usuario.nome,
        ])

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    nome_arquivo = f"{ex.nome.replace(' ', '_')}_dados.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )


# ---------------------------------------------------------------------------
# Troca de senha do próprio gerente
# ---------------------------------------------------------------------------

@router.get("/senha")
def trocar_senha_form(request: Request):
    sessao = exigir_perfil(request, "gerente")
    return templates.TemplateResponse("gerente/senha.html", {"request": request, "sessao": sessao})


@router.post("/senha")
def trocar_senha(
    request: Request,
    senha_atual: str = Form(...),
    nova_senha: str = Form(...),
    db: Session = Depends(get_db),
):
    from ..auth import verificar_senha, hash_senha
    sessao = exigir_perfil(request, "gerente")
    gerente = db.query(Gerente).get(sessao["id"])
    if not verificar_senha(senha_atual, gerente.senha_hash):
        return templates.TemplateResponse(
            "gerente/senha.html",
            {"request": request, "sessao": sessao, "erro": "Senha atual incorreta."},
            status_code=400,
        )
    gerente.senha_hash = hash_senha(nova_senha)
    db.commit()
    return templates.TemplateResponse(
        "gerente/senha.html", {"request": request, "sessao": sessao, "sucesso": "Senha alterada com sucesso."}
    )
