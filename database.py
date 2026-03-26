"""
database.py — Banco de dados completo
======================================
"""

import hashlib, re, os
import sqlalchemy
import sqlalchemy.orm
from datetime import date, datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "boletos.db")
db      = sqlalchemy.create_engine(f"sqlite:///{DB_PATH}", echo=False)
Session = sqlalchemy.orm.sessionmaker(bind=db)
Base    = sqlalchemy.orm.declarative_base()


class Configuracao(Base):
    __tablename__ = "configuracoes"
    id    = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    chave = sqlalchemy.Column(sqlalchemy.String(100), unique=True, nullable=False)
    valor = sqlalchemy.Column(sqlalchemy.Text)

    @staticmethod
    def get(chave, padrao=None):
        with Session() as s:
            c = s.query(Configuracao).filter_by(chave=chave).first()
            return c.valor if c else padrao

    @staticmethod
    def set(chave, valor):
        with Session() as s:
            c = s.query(Configuracao).filter_by(chave=chave).first()
            if c: c.valor = valor
            else: s.add(Configuracao(chave=chave, valor=valor))
            s.commit()


class Empresa(Base):
    __tablename__ = "empresas"
    id            = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    razao_social  = sqlalchemy.Column(sqlalchemy.String(200), nullable=False)
    nome_fantasia = sqlalchemy.Column(sqlalchemy.String(200))
    cnpj          = sqlalchemy.Column(sqlalchemy.String(18), unique=True, nullable=False)
    email         = sqlalchemy.Column(sqlalchemy.String(150))
    telefone      = sqlalchemy.Column(sqlalchemy.String(20))
    logradouro    = sqlalchemy.Column(sqlalchemy.String(200))
    numero        = sqlalchemy.Column(sqlalchemy.String(10))
    complemento   = sqlalchemy.Column(sqlalchemy.String(100))
    bairro        = sqlalchemy.Column(sqlalchemy.String(100))
    cidade        = sqlalchemy.Column(sqlalchemy.String(100))
    uf            = sqlalchemy.Column(sqlalchemy.String(2))
    cep           = sqlalchemy.Column(sqlalchemy.String(9))
    logo_path     = sqlalchemy.Column(sqlalchemy.String(300))
    ativa         = sqlalchemy.Column(sqlalchemy.Boolean, default=True)
    criada_em     = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.utcnow)

    contas   = sqlalchemy.orm.relationship("ContaBancaria", back_populates="empresa", cascade="all, delete-orphan")
    boletos  = sqlalchemy.orm.relationship("Boleto", back_populates="empresa")
    usuarios = sqlalchemy.orm.relationship("Usuario", back_populates="empresa")
    clientes = sqlalchemy.orm.relationship("Cliente", back_populates="empresa")

    def __repr__(self): return f"<Empresa {self.razao_social}>"


class Usuario(Base):
    __tablename__ = "usuarios"
    PERFIS = ("admin", "operador", "visualizador")

    id           = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    empresa_id   = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("empresas.id"))
    nome         = sqlalchemy.Column(sqlalchemy.String(100), nullable=False)
    email        = sqlalchemy.Column(sqlalchemy.String(150), unique=True, nullable=False)
    senha        = sqlalchemy.Column(sqlalchemy.String(64), nullable=False)
    perfil       = sqlalchemy.Column(sqlalchemy.String(20), default="operador")
    ativo        = sqlalchemy.Column(sqlalchemy.Boolean, default=True)
    criado_em    = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.utcnow)
    ultimo_login = sqlalchemy.Column(sqlalchemy.DateTime)

    empresa = sqlalchemy.orm.relationship("Empresa", back_populates="usuarios")

    def __init__(self, nome, email, senha, perfil="operador", empresa_id=None):
        if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w{2,}$", email):
            raise ValueError(f"E-mail inválido: {email}")
        self.nome       = nome.strip()
        self.email      = email.strip().lower()
        self.senha      = self._hash(senha)
        self.perfil     = perfil
        self.empresa_id = empresa_id

    @staticmethod
    def _hash(senha): return hashlib.sha256(senha.encode()).hexdigest()

    def verificar_senha(self, senha): return self.senha == self._hash(senha)

    def pode(self, acao):
        permissoes = {
            "admin":        {"ver","criar","editar","excluir","configurar","relatorio"},
            "operador":     {"ver","criar","editar"},
            "visualizador": {"ver","relatorio"},
        }
        return acao in permissoes.get(self.perfil, set())

    def __repr__(self): return f"<Usuario {self.email} [{self.perfil}]>"


class Cliente(Base):
    __tablename__ = "clientes"
    id         = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    empresa_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("empresas.id"))
    tipo       = sqlalchemy.Column(sqlalchemy.String(2), nullable=False)
    nome       = sqlalchemy.Column(sqlalchemy.String(200), nullable=False)
    cpf        = sqlalchemy.Column(sqlalchemy.String(14))
    cnpj       = sqlalchemy.Column(sqlalchemy.String(18))
    email      = sqlalchemy.Column(sqlalchemy.String(150))
    telefone   = sqlalchemy.Column(sqlalchemy.String(20))
    ativo      = sqlalchemy.Column(sqlalchemy.Boolean, default=True)
    criado_em  = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.utcnow)

    enderecos = sqlalchemy.orm.relationship("Endereco", back_populates="cliente", cascade="all, delete-orphan")
    boletos   = sqlalchemy.orm.relationship("Boleto", back_populates="cliente")
    empresa   = sqlalchemy.orm.relationship("Empresa", back_populates="clientes")

    def __init__(self, nome, tipo, empresa_id, cpf=None, cnpj=None, email=None, telefone=None):
        tipo = tipo.upper()
        if tipo not in ("PF","PJ"): raise ValueError("tipo deve ser PF ou PJ")
        if tipo=="PF" and not cpf:  raise ValueError("CPF obrigatório para PF")
        if tipo=="PJ" and not cnpj: raise ValueError("CNPJ obrigatório para PJ")
        self.nome=nome.strip(); self.tipo=tipo; self.empresa_id=empresa_id
        self.cpf=cpf; self.cnpj=cnpj
        self.email=email.strip().lower() if email else None
        self.telefone=telefone

    @property
    def documento(self): return self.cpf if self.tipo=="PF" else self.cnpj

    def __repr__(self): return f"<Cliente {self.nome} [{self.tipo}]>"


class Endereco(Base):
    __tablename__ = "enderecos"
    id          = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    cliente_id  = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("clientes.id"), nullable=False)
    logradouro  = sqlalchemy.Column(sqlalchemy.String(200))
    numero      = sqlalchemy.Column(sqlalchemy.String(10))
    complemento = sqlalchemy.Column(sqlalchemy.String(100))
    bairro      = sqlalchemy.Column(sqlalchemy.String(100))
    cidade      = sqlalchemy.Column(sqlalchemy.String(100))
    uf          = sqlalchemy.Column(sqlalchemy.String(2))
    cep         = sqlalchemy.Column(sqlalchemy.String(9))
    principal   = sqlalchemy.Column(sqlalchemy.Boolean, default=True)
    cliente     = sqlalchemy.orm.relationship("Cliente", back_populates="enderecos")


class ContaBancaria(Base):
    __tablename__ = "contas_bancarias"
    id           = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    empresa_id   = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("empresas.id"), nullable=False)
    banco        = sqlalchemy.Column(sqlalchemy.String(100))
    codigo_banco = sqlalchemy.Column(sqlalchemy.String(5))
    agencia      = sqlalchemy.Column(sqlalchemy.String(10))
    conta        = sqlalchemy.Column(sqlalchemy.String(20))
    carteira     = sqlalchemy.Column(sqlalchemy.String(10))
    ativa        = sqlalchemy.Column(sqlalchemy.Boolean, default=True)
    empresa      = sqlalchemy.orm.relationship("Empresa", back_populates="contas")
    boletos      = sqlalchemy.orm.relationship("Boleto", back_populates="conta_bancaria")


class Boleto(Base):
    __tablename__ = "boletos"
    STATUS = ("PENDENTE","PAGO","VENCIDO","CANCELADO")

    id               = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    empresa_id       = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("empresas.id"), nullable=False)
    cliente_id       = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("clientes.id"), nullable=False)
    conta_id         = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("contas_bancarias.id"), nullable=False)
    valor            = sqlalchemy.Column(sqlalchemy.Numeric(10,2), nullable=False)
    data_emissao     = sqlalchemy.Column(sqlalchemy.Date, default=date.today)
    data_vencimento  = sqlalchemy.Column(sqlalchemy.Date, nullable=False)
    multa_percentual = sqlalchemy.Column(sqlalchemy.Numeric(5,2), default=2.00)
    juros_percentual = sqlalchemy.Column(sqlalchemy.Numeric(5,2), default=1.00)
    desconto_valor   = sqlalchemy.Column(sqlalchemy.Numeric(10,2), default=0.00)
    nosso_numero     = sqlalchemy.Column(sqlalchemy.String(20))
    codigo_barras    = sqlalchemy.Column(sqlalchemy.String(50))
    linha_digitavel  = sqlalchemy.Column(sqlalchemy.String(60))
    url_pdf          = sqlalchemy.Column(sqlalchemy.String(300))
    asaas_id         = sqlalchemy.Column(sqlalchemy.String(50))
    status           = sqlalchemy.Column(sqlalchemy.String(10), default="PENDENTE")
    descricao        = sqlalchemy.Column(sqlalchemy.String(200))
    email_enviado    = sqlalchemy.Column(sqlalchemy.Boolean, default=False)
    criado_em        = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.utcnow)

    empresa        = sqlalchemy.orm.relationship("Empresa", back_populates="boletos")
    cliente        = sqlalchemy.orm.relationship("Cliente", back_populates="boletos")
    conta_bancaria = sqlalchemy.orm.relationship("ContaBancaria", back_populates="boletos")
    pagamento      = sqlalchemy.orm.relationship("PagamentoBoleto", back_populates="boleto", uselist=False)

    def __init__(self, empresa_id, cliente_id, conta_id, valor,
                 data_vencimento, descricao=None, multa=2.00, juros=1.00, desconto=0.00):
        if float(valor) <= 0: raise ValueError("Valor deve ser maior que zero.")
        if data_vencimento < date.today(): raise ValueError("Vencimento não pode ser no passado.")
        self.empresa_id=empresa_id; self.cliente_id=cliente_id; self.conta_id=conta_id
        self.valor=valor; self.data_vencimento=data_vencimento; self.descricao=descricao
        self.multa_percentual=multa; self.juros_percentual=juros; self.desconto_valor=desconto

    def __repr__(self): return f"<Boleto #{self.id} R${self.valor} {self.status}>"


class PagamentoBoleto(Base):
    __tablename__ = "pagamentos_boleto"
    id             = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    boleto_id      = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("boletos.id"), unique=True)
    data_pagamento = sqlalchemy.Column(sqlalchemy.Date, default=date.today)
    valor_pago     = sqlalchemy.Column(sqlalchemy.Numeric(10,2))
    canal          = sqlalchemy.Column(sqlalchemy.String(50))
    comprovante    = sqlalchemy.Column(sqlalchemy.String(300))
    boleto         = sqlalchemy.orm.relationship("Boleto", back_populates="pagamento")


class LogAuditoria(Base):
    __tablename__ = "log_auditoria"
    id         = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    usuario_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("usuarios.id"))
    empresa_id = sqlalchemy.Column(sqlalchemy.Integer)
    acao       = sqlalchemy.Column(sqlalchemy.String(100))
    descricao  = sqlalchemy.Column(sqlalchemy.Text)
    criado_em  = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.utcnow)

    @staticmethod
    def registrar(usuario_id, acao, descricao, empresa_id=None):
        with Session() as s:
            s.add(LogAuditoria(usuario_id=usuario_id, empresa_id=empresa_id,
                               acao=acao, descricao=descricao))
            s.commit()


def inicializar():
    Base.metadata.create_all(bind=db)
    with Session() as s:
        defaults = {
            "tema": "escuro",
            "nome_sistema": "Sistema de Boletos",
            "notif_dias_antes": "3",
            "backup_automatico": "true",
            "smtp_host": "",
            "smtp_porta": "587",
            "smtp_usuario": "",
            "smtp_senha": "",
            "smtp_remetente": "",
        }
        for chave, valor in defaults.items():
            if not s.query(Configuracao).filter_by(chave=chave).first():
                s.add(Configuracao(chave=chave, valor=valor))
        if not s.query(Usuario).first():
            s.add(Usuario(nome="Administrador", email="admin@sistema.com",
                          senha="admin123", perfil="admin"))
        s.commit()
    print("Banco de dados inicializado.")


if __name__ == "__main__":
    inicializar()