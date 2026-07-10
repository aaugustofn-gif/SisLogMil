"""
Configuração da conexão com o banco de dados.

A URL do banco vem da variável de ambiente DATABASE_URL, configurada
no painel do Render. Ela deve ser a "connection string" copiada do
TiDB Cloud (formato: mysql+pymysql://usuario:senha@host:4000/nome_do_banco?ssl_verify_cert=true&ssl_verify_identity=true).

Em desenvolvimento local, cai para um arquivo SQLite (sislog.db) só
para facilitar testes rápidos sem precisar de internet.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sislog.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# pool_recycle=280: o TiDB Cloud Starter fecha conexões ociosas depois de
# alguns minutos; reciclar a conexão periodicamente evita erros de
# "conexão perdida" quando o site fica um tempo sem uso.
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=280,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependência do FastAPI: abre uma sessão do banco e garante o fechamento."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
