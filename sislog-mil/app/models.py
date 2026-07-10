"""
Modelos de dados do SisLog Mil (versão flexível).

Hierarquia:
  Administrador -> cria Gerentes
  Gerente       -> cria Exercícios; dentro de cada Exercício, cria
                   Categorias (ex: Meios, Munição, Combustível, ou
                   qualquer outra que o gerente definir, como
                   "Insumos de Alimentação") e Usuários
  Categoria     -> tem um tipo de gráfico:
                     "disponibilidade" -> pizza (disponível/indisponível)
                     "consumo"         -> linha (acumulado x autorizado)
                   e contém Itens (ex: dentro de "Munição": "Grm Fum Azl")
  Usuário       -> vinculado a 1 Exercício; lança disponibilidade ou
                   consumo diário para os Itens das Categorias do exercício
"""
from datetime import date, datetime
from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from .database import Base

TIPOS_GRAFICO = ("disponibilidade", "consumo")


class Administrador(Base):
    __tablename__ = "administradores"

    id = Column(Integer, primary_key=True)
    nome = Column(String(120), nullable=False)
    login = Column(String(60), unique=True, nullable=False)
    senha_hash = Column(String(255), nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow)


class Gerente(Base):
    __tablename__ = "gerentes"

    id = Column(Integer, primary_key=True)
    nome = Column(String(120), nullable=False)
    login = Column(String(60), unique=True, nullable=False)
    senha_hash = Column(String(255), nullable=False)
    ativo = Column(Integer, default=1)
    criado_em = Column(DateTime, default=datetime.utcnow)

    exercicios = relationship("Exercicio", back_populates="gerente", cascade="all, delete-orphan")


class Exercicio(Base):
    __tablename__ = "exercicios"

    id = Column(Integer, primary_key=True)
    gerente_id = Column(Integer, ForeignKey("gerentes.id"), nullable=False)
    nome = Column(String(120), nullable=False)
    local = Column(String(160), nullable=False)
    data_inicio = Column(Date, nullable=False)
    data_fim = Column(Date, nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow)

    gerente = relationship("Gerente", back_populates="exercicios")
    categorias = relationship("Categoria", back_populates="exercicio", cascade="all, delete-orphan", order_by="Categoria.ordem")
    usuarios = relationship("Usuario", back_populates="exercicio", cascade="all, delete-orphan")

    @property
    def status(self) -> str:
        hoje = date.today()
        if hoje < self.data_inicio:
            return "PROGRAMADO"
        if hoje > self.data_fim:
            return "ENCERRADO"
        return "EM ANDAMENTO"

    @property
    def percentual_concluido(self) -> int:
        total_dias = (self.data_fim - self.data_inicio).days
        if total_dias <= 0:
            return 100
        decorridos = max(0, (min(date.today(), self.data_fim) - self.data_inicio).days)
        return round(min(decorridos, total_dias) / total_dias * 100)


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True)
    exercicio_id = Column(Integer, ForeignKey("exercicios.id"), nullable=False)
    nome = Column(String(120), nullable=False)
    login = Column(String(60), unique=True, nullable=False)
    senha_hash = Column(String(255), nullable=False)
    ativo = Column(Integer, default=1)
    criado_em = Column(DateTime, default=datetime.utcnow)

    exercicio = relationship("Exercicio", back_populates="usuarios")


class Categoria(Base):
    """
    Uma aba dentro de um exercício (ex: "Meios", "Munição", "Combustível",
    ou qualquer categoria nova que o gerente criar, como "Alimentação").
    """
    __tablename__ = "categorias"

    id = Column(Integer, primary_key=True)
    exercicio_id = Column(Integer, ForeignKey("exercicios.id"), nullable=False)
    nome = Column(String(120), nullable=False)
    tipo_grafico = Column(String(20), nullable=False)  # "disponibilidade" | "consumo"
    icone = Column(String(30), nullable=True)  # nome de ícone simples, ex: "truck", "target", "fuel"
    ordem = Column(Integer, nullable=False, default=0)

    exercicio = relationship("Exercicio", back_populates="categorias")
    itens = relationship("Item", back_populates="categoria", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("exercicio_id", "nome", name="uq_categoria_exercicio_nome"),
    )


class Item(Base):
    """
    Um item dentro de uma categoria.
    - Em categorias "disponibilidade" (ex: Meios): representa um meio, como "Piranha TP".
    - Em categorias "consumo" (ex: Munição): representa um tipo, como "Grm Fum Azl",
      com unidade de medida e consumo autorizado.
    """
    __tablename__ = "itens"

    id = Column(Integer, primary_key=True)
    categoria_id = Column(Integer, ForeignKey("categorias.id"), nullable=False)
    nome = Column(String(120), nullable=False)
    unidade = Column(String(30), nullable=True)          # usado só quando tipo_grafico = "consumo"
    consumo_autorizado = Column(Float, nullable=True)     # usado só quando tipo_grafico = "consumo"

    categoria = relationship("Categoria", back_populates="itens")
    lancamentos_disponibilidade = relationship("LancamentoDisponibilidade", back_populates="item", cascade="all, delete-orphan")
    lancamentos_consumo = relationship("LancamentoConsumo", back_populates="item", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("categoria_id", "nome", name="uq_item_categoria_nome"),)


class LancamentoDisponibilidade(Base):
    """Disponibilidade diária de um Item de categoria tipo 'disponibilidade'."""
    __tablename__ = "lancamentos_disponibilidade"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("itens.id"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    data = Column(Date, nullable=False, default=date.today)
    quantidade_disponivel = Column(Integer, nullable=False, default=0)
    quantidade_indisponivel = Column(Integer, nullable=False, default=0)
    criado_em = Column(DateTime, default=datetime.utcnow)

    item = relationship("Item", back_populates="lancamentos_disponibilidade")
    usuario = relationship("Usuario")

    __table_args__ = (UniqueConstraint("item_id", "usuario_id", "data", name="uq_disponibilidade_dia"),)


class LancamentoConsumo(Base):
    """Consumo diário de um Item de categoria tipo 'consumo'."""
    __tablename__ = "lancamentos_consumo"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("itens.id"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    data = Column(Date, nullable=False, default=date.today)
    quantidade = Column(Float, nullable=False, default=0)
    criado_em = Column(DateTime, default=datetime.utcnow)

    item = relationship("Item", back_populates="lancamentos_consumo")
    usuario = relationship("Usuario")
