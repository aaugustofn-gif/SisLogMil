import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from .database import Base, engine, SessionLocal
from . import models
from .auth import hash_senha
from .routers import auth_router, admin_router, gerente_router, usuario_router, public_router

app = FastAPI(title="SisLog Mil")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(auth_router.router)
app.include_router(admin_router.router)
app.include_router(gerente_router.router)
app.include_router(usuario_router.router)
app.include_router(public_router.router)


@app.on_event("startup")
def iniciar():
    # Cria as tabelas caso ainda não existam (não apaga dados existentes)
    Base.metadata.create_all(bind=engine)

    # Migração simples e automática: adiciona colunas novas que passaram a
    # existir no modelo mas ainda não existem na tabela já criada em produção.
    # Isso evita ter que mexer manualmente no banco a cada pequena mudança.
    from sqlalchemy import inspect, text
    inspecao = inspect(engine)

    colunas_disponibilidade = [c["name"] for c in inspecao.get_columns("lancamentos_disponibilidade")]
    if "editado" not in colunas_disponibilidade:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE lancamentos_disponibilidade ADD COLUMN editado INTEGER NOT NULL DEFAULT 0"))

    colunas_itens = [c["name"] for c in inspecao.get_columns("itens")]
    novas_colunas_itens = {
        "marco1_nome": "VARCHAR(60)",
        "marco1_valor": "FLOAT",
        "marco2_nome": "VARCHAR(60)",
        "marco2_valor": "FLOAT",
    }
    for coluna, tipo_sql in novas_colunas_itens.items():
        if coluna not in colunas_itens:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE itens ADD COLUMN {coluna} {tipo_sql}"))

    # Garante que sempre exista um administrador para o primeiro acesso.
    # Login e senha padrão podem ser sobrescritos por variáveis de ambiente
    # no painel do Render (ADMIN_LOGIN / ADMIN_SENHA).
    db = SessionLocal()
    try:
        if db.query(models.Administrador).count() == 0:
            login_padrao = os.getenv("ADMIN_LOGIN", "admin")
            senha_padrao = os.getenv("ADMIN_SENHA", "admin123")
            admin = models.Administrador(
                nome="Administrador",
                login=login_padrao,
                senha_hash=hash_senha(senha_padrao),
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()


@app.get("/")
def raiz():
    return RedirectResponse("/login")
