"""
Sistema de Boletos — Banco de Dados + Integração Asaas
=======================================================
Requisitos:
  pip install requests python-dotenv flask sqlalchemy

Variáveis de ambiente (.env):
  ASAAS_API_KEY=sua_chave_aqui
  ASAAS_SANDBOX=true
"""

import os
import re
import hashlib
import requests
import sqlalchemy
import sqlalchemy.orm
from datetime import date, datetime, timedelta
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# CONFIGURAÇÃO DO BANCO
# ─────────────────────────────────────────────

db = sqlalchemy.create_engine("sqlite:///boletos.db", echo=False)
Session = sqlalchemy.orm.sessionmaker(bind=db)
Base = sqlalchemy.orm.declarative_base()


# ─────────────────────────────────────────────
# CONFIGURAÇÃO DO ASAAS
# ─────────────────────────────────────────────

_SANDBOX = os.getenv("ASAAS_SANDBOX", "true").lower() == "true"
_API_KEY  = os.getenv("ASAAS_API_KEY", "")

BASE_URL = (
    "https://sandbox.asaas.com/api/v3"
    if _SANDBOX else
    "https://api.asaas.com/v3"
)

HEADERS = {
    "accept":       "application/json",
    "content-type": "application/json",
    "access_token": _API_KEY,
}


# ─────────────────────────────────────────────
# MODELOS
# ──────────────────────────────────────────────

class Usuario(Base):
    __tablename__ = "usuarios"

    id    = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    nome  = sqlalchemy.Column(sqlalchemy.String(100), nullable=False)
    email = sqlalchemy.Column(sqlalchemy.String(150), unique=True, nullable=False)
    senha = sqlalchemy.Column(sqlalchemy.String(64),  nullable=False)
    ativo = sqlalchemy.Column(sqlalchemy.Boolean, default=True, nullable=False)

    def __init__(self, nome, email, senha):
        if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w{2,}$", email):
            raise ValueError(f"E-mail inválido: {email}")
        self.nome  = nome.strip()
        self.email = email.strip().lower()
        self.senha = hashlib.sha256(senha.encode()).hexdigest()

    def verificar_senha(self, senha):
        return self.senha == hashlib.sha256(senha.encode()).hexdigest()

    def __repr__(self):
        return f"<Usuario id={self.id} nome='{self.nome}'>"


class Empresa(Base):
    __tablename__ = "empresas"

    id           = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    razao_social = sqlalchemy.Column(sqlalchemy.String(200), nullable=False)
    cnpj         = sqlalchemy.Column(sqlalchemy.String(18),  unique=True, nullable=False)
    email        = sqlalchemy.Column(sqlalchemy.String(150))
    telefone     = sqlalchemy.Column(sqlalchemy.String(20))
    logradouro   = sqlalchemy.Column(sqlalchemy.String(200))
    numero       = sqlalchemy.Column(sqlalchemy.String(10))
    complemento  = sqlalchemy.Column(sqlalchemy.String(100))
    bairro       = sqlalchemy.Column(sqlalchemy.String(100))
    cidade       = sqlalchemy.Column(sqlalchemy.String(100))
    uf           = sqlalchemy.Column(sqlalchemy.String(2))
    cep          = sqlalchemy.Column(sqlalchemy.String(9))

    contas  = sqlalchemy.orm.relationship("ContaBancaria", back_populates="empresa",
                                          cascade="all, delete-orphan")
    boletos = sqlalchemy.orm.relationship("Boleto", back_populates="empresa")

    def __repr__(self):
        return f"<Empresa cnpj='{self.cnpj}' razao='{self.razao_social}'>"


class Cliente(Base):
    __tablename__ = "clientes"

    id        = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    tipo      = sqlalchemy.Column(sqlalchemy.String(2),   nullable=False)
    nome      = sqlalchemy.Column(sqlalchemy.String(200), nullable=False)
    cpf       = sqlalchemy.Column(sqlalchemy.String(14),  unique=True)
    cnpj      = sqlalchemy.Column(sqlalchemy.String(18),  unique=True)
    email     = sqlalchemy.Column(sqlalchemy.String(150))
    telefone  = sqlalchemy.Column(sqlalchemy.String(20))
    ativo     = sqlalchemy.Column(sqlalchemy.Boolean, default=True, nullable=False)
    criado_em = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.utcnow)

    enderecos = sqlalchemy.orm.relationship("Endereco", back_populates="cliente",
                                            cascade="all, delete-orphan")
    boletos   = sqlalchemy.orm.relationship("Boleto", back_populates="cliente")

    def __init__(self, nome, tipo, cpf=None, cnpj=None, email=None, telefone=None):
        tipo = tipo.upper()
        if tipo not in ("PF", "PJ"):
            raise ValueError("tipo deve ser 'PF' ou 'PJ'.")
        if tipo == "PF" and not cpf:
            raise ValueError("CPF é obrigatório para pessoa física.")
        if tipo == "PJ" and not cnpj:
            raise ValueError("CNPJ é obrigatório para pessoa jurídica.")
        self.nome     = nome.strip()
        self.tipo     = tipo
        self.cpf      = cpf
        self.cnpj     = cnpj
        self.email    = email.strip().lower() if email else None
        self.telefone = telefone

    @property
    def documento(self):
        return self.cpf if self.tipo == "PF" else self.cnpj

    def __repr__(self):
        return f"<Cliente tipo={self.tipo} nome='{self.nome}' doc='{self.documento}'>"


class Endereco(Base):
    __tablename__ = "enderecos"

    id          = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    cliente_id  = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("clientes.id"), nullable=False)
    logradouro  = sqlalchemy.Column(sqlalchemy.String(200), nullable=False)
    numero      = sqlalchemy.Column(sqlalchemy.String(10),  nullable=False)
    complemento = sqlalchemy.Column(sqlalchemy.String(100))
    bairro      = sqlalchemy.Column(sqlalchemy.String(100), nullable=False)
    cidade      = sqlalchemy.Column(sqlalchemy.String(100), nullable=False)
    uf          = sqlalchemy.Column(sqlalchemy.String(2),   nullable=False)
    cep         = sqlalchemy.Column(sqlalchemy.String(9),   nullable=False)
    principal   = sqlalchemy.Column(sqlalchemy.Boolean, default=True)

    cliente = sqlalchemy.orm.relationship("Cliente", back_populates="enderecos")

    def __repr__(self):
        return f"<Endereco {self.logradouro}, {self.numero} — {self.cidade}/{self.uf}>"


class ContaBancaria(Base):
    __tablename__ = "contas_bancarias"

    id          = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    empresa_id  = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("empresas.id"), nullable=False)
    banco       = sqlalchemy.Column(sqlalchemy.String(100), nullable=False)
    codigo_banco= sqlalchemy.Column(sqlalchemy.String(5),   nullable=False)
    agencia     = sqlalchemy.Column(sqlalchemy.String(10),  nullable=False)
    conta       = sqlalchemy.Column(sqlalchemy.String(20),  nullable=False)
    carteira    = sqlalchemy.Column(sqlalchemy.String(10))
    ativa       = sqlalchemy.Column(sqlalchemy.Boolean, default=True)

    empresa = sqlalchemy.orm.relationship("Empresa", back_populates="contas")
    boletos = sqlalchemy.orm.relationship("Boleto", back_populates="conta_bancaria")

    def __repr__(self):
        return f"<ContaBancaria banco='{self.banco}' ag={self.agencia} cc={self.conta}>"


class Boleto(Base):
    __tablename__ = "boletos"

    STATUS_PENDENTE  = "PENDENTE"
    STATUS_PAGO      = "PAGO"
    STATUS_VENCIDO   = "VENCIDO"
    STATUS_CANCELADO = "CANCELADO"

    id               = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    empresa_id       = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("empresas.id"),        nullable=False)
    cliente_id       = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("clientes.id"),        nullable=False)
    conta_id         = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("contas_bancarias.id"),nullable=False)
    valor            = sqlalchemy.Column(sqlalchemy.Numeric(10, 2), nullable=False)
    data_emissao     = sqlalchemy.Column(sqlalchemy.Date, nullable=False, default=date.today)
    data_vencimento  = sqlalchemy.Column(sqlalchemy.Date, nullable=False)
    multa_percentual = sqlalchemy.Column(sqlalchemy.Numeric(5, 2), default=2.00)
    juros_percentual = sqlalchemy.Column(sqlalchemy.Numeric(5, 2), default=1.00)
    desconto_valor   = sqlalchemy.Column(sqlalchemy.Numeric(10, 2), default=0.00)
    nosso_numero     = sqlalchemy.Column(sqlalchemy.String(20),  unique=True)
    codigo_barras    = sqlalchemy.Column(sqlalchemy.String(50))
    linha_digitavel  = sqlalchemy.Column(sqlalchemy.String(60))
    url_pdf          = sqlalchemy.Column(sqlalchemy.String(300))
    status           = sqlalchemy.Column(sqlalchemy.String(10), nullable=False, default="PENDENTE")
    descricao        = sqlalchemy.Column(sqlalchemy.String(200))
    criado_em        = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.utcnow)
    atualizado_em    = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    empresa        = sqlalchemy.orm.relationship("Empresa",        back_populates="boletos")
    cliente        = sqlalchemy.orm.relationship("Cliente",        back_populates="boletos")
    conta_bancaria = sqlalchemy.orm.relationship("ContaBancaria",  back_populates="boletos")
    pagamento      = sqlalchemy.orm.relationship("PagamentoBoleto",back_populates="boleto", uselist=False)

    def __init__(self, empresa_id, cliente_id, conta_id, valor, data_vencimento, descricao=None, multa=2.00, juros=1.00, desconto=0.00):
        if valor <= 0:
            raise ValueError("O valor do boleto deve ser maior que zero.")
        if data_vencimento < date.today():
            raise ValueError("A data de vencimento não pode ser no passado.")
        self.empresa_id       = empresa_id
        self.cliente_id       = cliente_id
        self.conta_id         = conta_id
        self.valor            = valor
        self.data_vencimento  = data_vencimento
        self.descricao        = descricao
        self.multa_percentual = multa
        self.juros_percentual = juros
        self.desconto_valor   = desconto
        self.status           = self.STATUS_PENDENTE

    def __repr__(self):
        return f"<Boleto id={self.id} valor=R${self.valor} venc={self.data_vencimento} status={self.status}>"


class PagamentoBoleto(Base):
    __tablename__ = "pagamentos_boleto"

    id             = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    boleto_id      = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("boletos.id"), unique=True, nullable=False)
    data_pagamento = sqlalchemy.Column(sqlalchemy.Date, nullable=False, default=date.today)
    valor_pago     = sqlalchemy.Column(sqlalchemy.Numeric(10, 2), nullable=False)
    canal          = sqlalchemy.Column(sqlalchemy.String(50))
    comprovante    = sqlalchemy.Column(sqlalchemy.String(300))

    boleto = sqlalchemy.orm.relationship("Boleto", back_populates="pagamento")

    def __repr__(self):
        return f"<Pagamento boleto_id={self.boleto_id} valor=R${self.valor_pago} data={self.data_pagamento}>"


Base.metadata.create_all(bind=db)


# ─────────────────────────────────────────────
# FUNÇÕES DO BANCO
# ─────────────────────────────────────────────

def criar_cliente(nome, tipo, cpf=None, cnpj=None, email=None, telefone=None):
    # Verifica se o cliente já existe antes de tentar salvar
    cliente_ja_existe = buscar_cliente(cpf=cpf, cnpj=cnpj)
    if cliente_ja_existe:
        print(f"ℹ️ Cliente já cadastrado no banco: {cliente_ja_existe.nome}")
        return cliente_ja_existe

    with Session() as s:
        try:
            cliente = Cliente(nome=nome, tipo=tipo, cpf=cpf, cnpj=cnpj, email=email, telefone=telefone)
            s.add(cliente)
            s.commit()
            s.refresh(cliente)
            print(f"✔ Cliente criado com sucesso: {cliente}")
            return cliente
        except Exception as e:
            s.rollback()
            print(f"✘ Erro inesperado ao criar cliente: {e}")
            return None


def buscar_cliente(cpf=None, cnpj=None):
    with Session() as s:
        if cnpj:
            return s.query(Cliente).filter_by(cnpj=cnpj).first()
        if cpf:
            return s.query(Cliente).filter_by(cpf=cpf).first()
        return None


def adicionar_endereco(cliente_id, logradouro, numero, bairro, cidade, uf, cep, complemento=None, principal=True):
    with Session() as s:
        try:
            end = Endereco(cliente_id=cliente_id, logradouro=logradouro, numero=numero,
                           complemento=complemento, bairro=bairro, cidade=cidade,
                           uf=uf, cep=cep, principal=principal)
            s.add(end)
            s.commit()
            s.refresh(end)
            print(f"✔ Endereço adicionado: {end}")
            return end
        except Exception as e:
            s.rollback()
            print(f"✘ Erro ao adicionar endereço: {e}")
            return None


def gerar_boleto(empresa_id, cliente_id, conta_id, valor, data_vencimento, descricao=None):
    with Session() as s:
        try:
            boleto = Boleto(empresa_id=empresa_id, cliente_id=cliente_id,
                            conta_id=conta_id, valor=valor,
                            data_vencimento=data_vencimento, descricao=descricao)
            s.add(boleto)
            s.commit()
            s.refresh(boleto)
            print(f"✔ Boleto gerado: {boleto}")
            return boleto
        except (ValueError, Exception) as e:
            s.rollback()
            print(f"✘ Erro ao gerar boleto: {e}")
            return None


def registrar_pagamento(boleto_id, valor_pago, canal=None, comprovante=None):
    with Session() as s:
        boleto = s.query(Boleto).get(boleto_id)
        if not boleto:
            print(f"✘ Boleto {boleto_id} não encontrado.")
            return False
        if boleto.status == Boleto.STATUS_PAGO:
            print(f"✘ Boleto {boleto_id} já foi pago.")
            return False
        pagamento = PagamentoBoleto(boleto_id=boleto_id, valor_pago=valor_pago,
                                    canal=canal, comprovante=comprovante)
        boleto.status = Boleto.STATUS_PAGO
        s.add(pagamento)
        s.commit()
        print(f"✔ Pagamento registrado: R${valor_pago:.2f} — Boleto {boleto_id} quitado.")
        return True


def atualizar_boletos_vencidos():
    with Session() as s:
        boletos = (s.query(Boleto)
                   .filter(Boleto.status == Boleto.STATUS_PENDENTE,
                           Boleto.data_vencimento < date.today())
                   .all())
        for b in boletos:
            b.status = Boleto.STATUS_VENCIDO
        s.commit()
        if boletos:
            print(f"✔ {len(boletos)} boleto(s) marcado(s) como VENCIDO.")
        return len(boletos)


# ─────────────────────────────────────────────
# FUNÇÕES DA API ASAAS
# ─────────────────────────────────────────────

def _apenas_numeros(texto):
    return "".join(c for c in (texto or "") if c.isdigit())


def _get(endpoint, params=None):
    r = requests.get(f"{BASE_URL}{endpoint}", headers=HEADERS, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def _post(endpoint, payload):
    r = requests.post(f"{BASE_URL}{endpoint}", headers=HEADERS, json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


def sincronizar_cliente_asaas(cliente):
    documento = _apenas_numeros(cliente.documento)
    try:
        resultado = _get("/customers", params={"cpfCnpj": documento})
        if resultado.get("data"):
            customer_id = resultado["data"][0]["id"]
            print(f"✔ Cliente já existe no Asaas: {customer_id}")
            return customer_id
    except requests.HTTPError as e:
        print(f"✘ Erro ao buscar cliente no Asaas: {e}")
        return None

    with Session() as s:
        end = s.query(Endereco).filter_by(cliente_id=cliente.id, principal=True).first()

    payload = {
        "name":       cliente.nome,
        "cpfCnpj":    documento,
        "email":      cliente.email,
        "phone":      _apenas_numeros(cliente.telefone or ""),
        "personType": "FISICA" if cliente.tipo == "PF" else "JURIDICA",
    }
    if end:
        payload.update({
            "address":       end.logradouro,
            "addressNumber": end.numero,
            "complement":    end.complemento or "",
            "province":      end.bairro,
            "city":          end.cidade,
            "state":         end.uf,
            "postalCode":    _apenas_numeros(end.cep),
        })

    try:
        resp = _post("/customers", payload)
        customer_id = resp["id"]
        print(f"✔ Cliente criado no Asaas: {customer_id}")
        return customer_id
    except requests.HTTPError as e:
        print(f"✘ Erro ao criar cliente no Asaas: {e.response.text}")
        return None


def emitir_boleto(boleto_id):
    with Session() as s:
        boleto  = s.query(Boleto).get(boleto_id)
        cliente = s.query(Cliente).get(boleto.cliente_id)

        if not boleto:
            print(f"✘ Boleto {boleto_id} não encontrado.")
            return False
        if boleto.status != Boleto.STATUS_PENDENTE:
            print(f"✘ Boleto {boleto_id} não está pendente.")
            return False

        customer_id = sincronizar_cliente_asaas(cliente)
        if not customer_id:
            return False

        payload = {
            "customer":    customer_id,
            "billingType": "BOLETO",
            "value":       float(boleto.valor),
            "dueDate":     boleto.data_vencimento.strftime("%Y-%m-%d"),
            "description": boleto.descricao or "",
            "fine":     {"value": float(boleto.multa_percentual)},
            "interest": {"value": float(boleto.juros_percentual)},
        }
        if boleto.desconto_valor and float(boleto.desconto_valor) > 0:
            payload["discount"] = {
                "value": float(boleto.desconto_valor),
                "dueDateLimitDays": 0,
                "type": "FIXED",
            }

        try:
            resp       = _post("/payments", payload)
            payment_id = resp["id"]
            bank_slip  = resp.get("bankSlipUrl", "")

            ident           = _get(f"/payments/{payment_id}/identificationField")
            linha_digitavel = ident.get("identificationField", "")
            codigo_barras   = ident.get("barCode", "")
            nosso_numero    = ident.get("nossoNumero", payment_id)

            boleto.nosso_numero    = nosso_numero
            boleto.codigo_barras   = codigo_barras
            boleto.linha_digitavel = linha_digitavel
            boleto.url_pdf         = bank_slip
            boleto.descricao       = (boleto.descricao or "") + f" [asaas:{payment_id}]"
            s.commit()

            print(f"\n✔ Boleto emitido com sucesso!")
            print(f"   Nosso número    : {nosso_numero}")
            print(f"   Linha digitável : {linha_digitavel}")
            print(f"   PDF             : {bank_slip}")
            return True

        except requests.HTTPError as e:
            print(f"✘ Erro ao emitir boleto no Asaas: {e.response.text}")
            return False


def cancelar_boleto(boleto_id):
    with Session() as s:
        boleto = s.query(Boleto).get(boleto_id)
        if not boleto:
            print(f"✘ Boleto {boleto_id} não encontrado.")
            return False

        asaas_id = re.search(r"\[asaas:(pay_[^\]]+)\]", boleto.descricao or "")
        if asaas_id:
            try:
                requests.delete(f"{BASE_URL}/payments/{asaas_id.group(1)}",
                                headers=HEADERS, timeout=15).raise_for_status()
                print(f"✔ Boleto cancelado no Asaas.")
            except requests.HTTPError as e:
                print(f"⚠ Não foi possível cancelar no Asaas: {e}")

        boleto.status = Boleto.STATUS_CANCELADO
        s.commit()
        print(f"✔ Boleto {boleto_id} marcado como CANCELADO.")
        return True


# ─────────────────────────────────────────────
# EXECUÇÃO PRINCIPAL
# ─────────────────────────────────────────────

if __name__ == "__main__":

    if not _API_KEY:
        print("⚠ Configure ASAAS_API_KEY no arquivo .env antes de continuar.")
        exit(1)

    print(f"🔧 Modo: {'SANDBOX' if _SANDBOX else 'PRODUÇÃO'}\n")

    # 1. Cria empresa se não existir
    with Session() as s:
        empresa = s.query(Empresa).first()
        if not empresa:
            empresa = Empresa(
                razao_social="Minha Empresa Ltda",
                cnpj="12.345.678/0001-99",
                email="financeiro@minhaempresa.com.br",
                logradouro="Rua das Flores", numero="100",
                bairro="Centro", cidade="São Paulo", uf="SP", cep="01310-100"
            )
            conta = ContaBancaria(
                banco="Bradesco", codigo_banco="237",
                agencia="1234", conta="56789-0", carteira="09"
            )
            empresa.contas.append(conta)
            s.add(empresa)
            s.commit()
            print(f"✔ Empresa criada: {empresa}")
        empresa_id = empresa.id
        conta_id   = empresa.contas[0].id if empresa.contas else None

    # 2. Busca cliente existente ou cria novo
    #cliente = buscar_cliente(cnpj="11.222.333/0001-81")
   # if not cliente:
    #    cliente = criar_cliente(
     #       nome="Acme Distribuidora Ltda",
      #      tipo="PJ",
       #     cnpj="11.222.333/0001-81",
        #    email="financeiro@acme.com.br",
         #   telefone="(11) 99999-0000"
        #)
        #if cliente:
         #   adicionar_endereco(
          #      cliente_id=cliente.id,
           #     logradouro="Av. Paulista", numero="1000",
            #    bairro="Bela Vista", cidade="São Paulo",
             #   uf="SP", cep="01310-200"
            #)
#
 #   else:
  #      print(f"✔ Cliente já existe: {cliente}")

    # 3. Gerar e emitir boleto
    if cliente and conta_id:
        boleto = gerar_boleto(
            empresa_id=empresa_id,
            cliente_id=cliente.id,
            conta_id=conta_id,
            valor=1500.00,
            data_vencimento=date.today() + timedelta(days=30),
            descricao="Fatura #001 — Serviços de TI"
        )
        if boleto:
            print("\n📤 Emitindo boleto no Asaas...")
            emitir_boleto(boleto.id)

    # 4. Atualizar vencidos
    atualizar_boletos_vencidos()
