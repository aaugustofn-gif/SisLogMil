from datetime import date, timedelta
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models import Exercicio, Categoria, Item, LancamentoDisponibilidade, LancamentoConsumo

router = APIRouter(prefix="/painel")
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def lista_exercicios(request: Request, db: Session = Depends(get_db)):
    exercicios = db.query(Exercicio).order_by(Exercicio.data_inicio.desc()).all()
    return templates.TemplateResponse("publico/lista.html", {"request": request, "exercicios": exercicios})


def _dados_disponibilidade(db: Session, item: Item, hoje: date) -> dict:
    """Soma as quantidades disponível/indisponível lançadas por todos os usuários hoje para o item."""
    linha = (
        db.query(
            func.coalesce(func.sum(LancamentoDisponibilidade.quantidade_disponivel), 0),
            func.coalesce(func.sum(LancamentoDisponibilidade.quantidade_indisponivel), 0),
        )
        .filter(LancamentoDisponibilidade.item_id == item.id, LancamentoDisponibilidade.data == hoje)
        .first()
    )
    disponivel, indisponivel = linha
    return {"disponivel": int(disponivel), "indisponivel": int(indisponivel)}


def _dados_consumo(db: Session, item: Item, data_inicio: date, data_fim: date) -> dict:
    """Monta a série diária (rótulo dd/mm, acumulado) do consumo de um item entre duas datas."""
    somas_por_dia = dict(
        db.query(LancamentoConsumo.data, func.sum(LancamentoConsumo.quantidade))
        .filter(LancamentoConsumo.item_id == item.id, LancamentoConsumo.data >= data_inicio, LancamentoConsumo.data <= data_fim)
        .group_by(LancamentoConsumo.data)
        .all()
    )
    rotulos, acumulado_serie = [], []
    acumulado = 0.0
    dia = data_inicio
    while dia <= data_fim:
        acumulado += float(somas_por_dia.get(dia, 0) or 0)
        rotulos.append(dia.strftime("%d/%m"))
        acumulado_serie.append(round(acumulado, 2))
        dia += timedelta(days=1)
    return {
        "rotulos": rotulos,
        "acumulado": acumulado_serie,
        "autorizado": item.consumo_autorizado or 0,
        "total_atual": acumulado_serie[-1] if acumulado_serie else 0,
        "marco1_nome": item.marco1_nome,
        "marco1_valor": item.marco1_valor,
        "marco2_nome": item.marco2_nome,
        "marco2_valor": item.marco2_valor,
    }


@router.get("/{exercicio_id}")
def visao_geral(exercicio_id: int, request: Request, db: Session = Depends(get_db)):
    ex = db.query(Exercicio).get(exercicio_id)
    if not ex:
        raise HTTPException(404, "Exercício não encontrado.")
    return templates.TemplateResponse(
        "publico/painel.html",
        {"request": request, "ex": ex, "aba_ativa": None, "categoria": None, "hoje": date.today()},
    )


@router.get("/{exercicio_id}/{categoria_id}")
def ver_categoria(exercicio_id: int, categoria_id: int, request: Request, db: Session = Depends(get_db)):
    ex = db.query(Exercicio).get(exercicio_id)
    if not ex:
        raise HTTPException(404, "Exercício não encontrado.")
    cat = db.query(Categoria).filter(Categoria.id == categoria_id, Categoria.exercicio_id == ex.id).first()
    if not cat:
        raise HTTPException(404, "Categoria não encontrada.")

    hoje = date.today()
    fim_serie = min(hoje, ex.data_fim)

    graficos = []
    for item in cat.itens:
        if cat.tipo_grafico == "disponibilidade":
            graficos.append({"item": item, **_dados_disponibilidade(db, item, hoje)})
        else:
            graficos.append({"item": item, **_dados_consumo(db, item, ex.data_inicio, fim_serie)})

    return templates.TemplateResponse(
        "publico/painel.html",
        {"request": request, "ex": ex, "aba_ativa": cat.id, "categoria": cat, "graficos": graficos, "hoje": hoje},
    )
