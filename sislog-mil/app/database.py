"""
Configuração da conexão com o banco de dados.

A URL do banco vem da variável de ambiente DATABASE_URL, configurada
no painel do Render. Ela deve ser a "connection string" copiada do
TiDB Cloud (formato: mysql+pymysql://usuario:senha@host:4000/nome_do_banco?ssl_verify_cert=true&ssl_verify_identity=true).

Em desenvolvimento local, cai para um arquivo SQLite (sislog.db) só
para facilitar testes rápidos sem precisar de internet.
"""
import os
from urllib.parse import urlsplit, urlunsplit
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


def _normalizar_url(url: str) -> str:
    """
    Normaliza a connection string vinda do TiDB Cloud para o formato que
    o driver PyMySQL (instalado via requirements.txt) entende.

    O TiDB Cloud às vezes fornece a string já pronta para o driver
    "mysqlclient" (mysql+mysqldb://...) com um caminho de certificado
    (ssl_ca=/etc/ssl/cert.pem) que só existe em alguns sistemas — não no
    servidor do Render. Por isso, forçamos o driver para "pymysql" e
    confiamos na validação de certificado padrão do sistema, sem exigir
    um arquivo de certificado específico.
    """
    if url.startswith("sqlite"):
        return url

    partes = urlsplit(url)
    esquema = "mysql+pymysql" if partes.scheme.startswith("mysql") else partes.scheme

    query_params = [
        p for p in partes.query.split("&")
        if p and not p.startswith("ssl_ca") and not p.startswith("ssl_mode")
    ]
    if not any(p.startswith("ssl_verify_cert") for p in query_params):
        query_params.append("ssl_verify_cert=true")
    if not any(p.startswith("ssl_verify_identity") for p in query_params):
        query_params.append("ssl_verify_identity=true")

    return urlunsplit((esquema, partes.netloc, partes.path, "&".join(query_params), partes.fragment))


DATABASE_URL = _normalizar_url(os.getenv("DATABASE_URL", "sqlite:///./sislog.db"))

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
