"""
services.py — Lógica de negócio
=================================
Serviços:
  - AsaasService  : integração com API do Asaas
  - EmailService  : envio de e-mails com boleto
  - BackupService : backup automático do banco
  - NotifService  : notificações de boletos vencendo
"""

import os, re, shutil, smtplib, threading
from datetime import date, timedelta, datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import requests

from database import (
    Session, Boleto, Cliente, Empresa, ContaBancaria,
    PagamentoBoleto, Endereco, Configuracao, LogAuditoria
)

load_dotenv()

_API_KEY = os.getenv("ASAAS_API_KEY", "")
_SANDBOX = os.getenv("ASAAS_SANDBOX", "true").lower() == "true"
BASE_URL = "https://sandbox.asaas.com/api/v3" if _SANDBOX else "https://api.asaas.com/v3"
HEADERS  = {"accept": "application/json", "content-type": "application/json",
             "access_token": _API_KEY}

def _num(v): return re.sub(r"\D", "", v or "")


# ─────────────────────────────────────────────
# ASAAS
# ─────────────────────────────────────────────

class AsaasService:

    @staticmethod
    def _get(endpoint, params=None):
        r = requests.get(f"{BASE_URL}{endpoint}", headers=HEADERS,
                         params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _post(endpoint, payload):
        r = requests.post(f"{BASE_URL}{endpoint}", headers=HEADERS,
                          json=payload, timeout=15)
        r.raise_for_status()
        return r.json()

    @classmethod
    def sincronizar_cliente(cls, cliente_id):
        """Cria ou recupera o customer_id do Asaas."""
        with Session() as s:
            c   = s.get(Cliente, cliente_id)
            end = s.query(Endereco).filter_by(cliente_id=cliente_id, principal=True).first()

        if not c:
            return None, "Cliente não encontrado."

        doc = _num(c.documento)
        try:
            res = cls._get("/customers", params={"cpfCnpj": doc})
            if res.get("data"):
                return res["data"][0]["id"], None
        except requests.HTTPError as e:
            return None, f"Erro ao buscar cliente no Asaas: {e}"

        payload = {
            "name":       c.nome,
            "cpfCnpj":    doc,
            "email":      c.email or "",
            "phone":      _num(c.telefone or ""),
            "personType": "FISICA" if c.tipo == "PF" else "JURIDICA",
        }
        if end:
            payload.update({
                "address":       end.logradouro or "",
                "addressNumber": end.numero or "",
                "complement":    end.complemento or "",
                "province":      end.bairro or "",
                "city":          end.cidade or "",
                "state":         end.uf or "",
                "postalCode":    _num(end.cep or ""),
            })
        try:
            res = cls._post("/customers", payload)
            return res["id"], None
        except requests.HTTPError as e:
            return None, f"Erro ao criar cliente no Asaas: {e.response.text}"

    @classmethod
    def emitir_boleto(cls, boleto_id):
        """Emite boleto no Asaas e salva os dados no banco."""
        with Session() as s:
            b = s.get(Boleto, boleto_id)
            if not b:
                return False, "Boleto não encontrado."
            if b.status != "PENDENTE":
                return False, "Boleto não está pendente."

            customer_id, erro = cls.sincronizar_cliente(b.cliente_id)
            if erro:
                return False, erro

            payload = {
                "customer":    customer_id,
                "billingType": "BOLETO",
                "value":       float(b.valor),
                "dueDate":     b.data_vencimento.strftime("%Y-%m-%d"),
                "description": b.descricao or "",
                "fine":        {"value": float(b.multa_percentual)},
                "interest":    {"value": float(b.juros_percentual)},
            }
            if b.desconto_valor and float(b.desconto_valor) > 0:
                payload["discount"] = {
                    "value": float(b.desconto_valor),
                    "dueDateLimitDays": 0, "type": "FIXED"
                }
            try:
                resp       = cls._post("/payments", payload)
                payment_id = resp["id"]
                bank_slip  = resp.get("bankSlipUrl", "")
                ident      = cls._get(f"/payments/{payment_id}/identificationField")

                b.asaas_id        = payment_id
                b.nosso_numero    = ident.get("nossoNumero", payment_id)
                b.codigo_barras   = ident.get("barCode", "")
                b.linha_digitavel = ident.get("identificationField", "")
                b.url_pdf         = bank_slip
                s.commit()
                return True, {"linha": b.linha_digitavel, "pdf": bank_slip,
                               "payment_id": payment_id}
            except requests.HTTPError as e:
                return False, f"Erro Asaas: {e.response.text}"

    @classmethod
    def cancelar_boleto(cls, boleto_id):
        with Session() as s:
            b = s.get(Boleto, boleto_id)
            if not b: return False, "Boleto não encontrado."
            if b.asaas_id:
                try:
                    requests.delete(f"{BASE_URL}/payments/{b.asaas_id}",
                                    headers=HEADERS, timeout=15).raise_for_status()
                except: pass
            b.status = "CANCELADO"
            s.commit()
        return True, "Boleto cancelado."

    @classmethod
    def atualizar_vencidos(cls):
        with Session() as s:
            q = s.query(Boleto).filter(
                Boleto.status == "PENDENTE",
                Boleto.data_vencimento < date.today()
            )
            n = q.count()
            q.update({"status": "VENCIDO"})
            s.commit()
        return n


# ─────────────────────────────────────────────
# EMAIL
# ─────────────────────────────────────────────

class EmailService:

    @staticmethod
    def _cfg():
        return {
            "host":      Configuracao.get("smtp_host", ""),
            "porta":     int(Configuracao.get("smtp_porta", 587)),
            "usuario":   Configuracao.get("smtp_usuario", ""),
            "senha":     Configuracao.get("smtp_senha", ""),
            "remetente": Configuracao.get("smtp_remetente", ""),
        }

    @classmethod
    def _enviar(cls, destinatario, assunto, corpo_html):
        cfg = cls._cfg()
        if not cfg["host"] or not cfg["usuario"]:
            return False, "SMTP não configurado. Configure em Configurações > E-mail."
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = assunto
            msg["From"]    = cfg["remetente"] or cfg["usuario"]
            msg["To"]      = destinatario
            msg.attach(MIMEText(corpo_html, "html", "utf-8"))

            with smtplib.SMTP(cfg["host"], cfg["porta"], timeout=10) as srv:
                srv.starttls()
                srv.login(cfg["usuario"], cfg["senha"])
                srv.sendmail(msg["From"], [destinatario], msg.as_string())
            return True, "E-mail enviado com sucesso."
        except Exception as e:
            return False, f"Erro ao enviar e-mail: {e}"

    @classmethod
    def enviar_boleto(cls, boleto_id):
        """Envia o boleto por e-mail ao cliente."""
        with Session() as s:
            b   = s.get(Boleto, boleto_id)
            cli = s.get(Cliente, b.cliente_id) if b else None
            emp = s.get(Empresa, b.empresa_id) if b else None

        if not b or not cli or not cli.email:
            return False, "Cliente sem e-mail cadastrado."
        if not b.linha_digitavel:
            return False, "Boleto ainda não foi emitido no Asaas."

        nome_emp = emp.nome_fantasia or emp.razao_social if emp else "Sistema de Boletos"
        assunto  = f"Boleto #{b.id} — {nome_emp} — Vence em {b.data_vencimento.strftime('%d/%m/%Y')}"

        corpo = f"""
        <html><body style="font-family:Arial,sans-serif;background:#f5f5f5;padding:20px">
        <div style="max-width:600px;margin:auto;background:#fff;border-radius:10px;
                    padding:30px;box-shadow:0 2px 8px rgba(0,0,0,0.1)">
          <h2 style="color:#1a1a2e">{nome_emp}</h2>
          <p>Olá, <strong>{cli.nome}</strong>!</p>
          <p>Segue seu boleto para pagamento:</p>
          <table style="width:100%;border-collapse:collapse;margin:16px 0">
            <tr><td style="padding:8px;color:#666">Valor:</td>
                <td style="padding:8px;font-weight:bold">R$ {float(b.valor):,.2f}</td></tr>
            <tr style="background:#f9f9f9">
                <td style="padding:8px;color:#666">Vencimento:</td>
                <td style="padding:8px">{b.data_vencimento.strftime('%d/%m/%Y')}</td></tr>
            <tr><td style="padding:8px;color:#666">Descrição:</td>
                <td style="padding:8px">{b.descricao or '—'}</td></tr>
          </table>
          <div style="background:#f0f0f0;padding:14px;border-radius:6px;margin:16px 0">
            <p style="font-size:12px;color:#666;margin:0 0 6px">Linha digitável:</p>
            <p style="font-family:monospace;font-size:14px;margin:0;word-break:break-all">
              {b.linha_digitavel}</p>
          </div>
          {'<a href="'+b.url_pdf+'" style="display:inline-block;background:#e94560;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold">📄 Baixar Boleto PDF</a>' if b.url_pdf else ''}
          <p style="color:#999;font-size:12px;margin-top:24px">
            Este é um e-mail automático. Em caso de dúvidas, entre em contato com {nome_emp}.</p>
        </div></body></html>
        """
        ok, msg = cls._enviar(cli.email, assunto, corpo)
        if ok:
            with Session() as s:
                b2 = s.get(Boleto, boleto_id)
                if b2: b2.email_enviado = True; s.commit()
        return ok, msg

    @classmethod
    def enviar_lembrete(cls, boleto_id):
        """Envia lembrete de vencimento próximo."""
        with Session() as s:
            b   = s.get(Boleto, boleto_id)
            cli = s.get(Cliente, b.cliente_id) if b else None
            emp = s.get(Empresa, b.empresa_id) if b else None

        if not b or not cli or not cli.email: return False, "Sem e-mail."

        dias = (b.data_vencimento - date.today()).days
        nome_emp = emp.nome_fantasia or emp.razao_social if emp else "Sistema de Boletos"
        assunto  = f"⚠️ Lembrete: Boleto vence em {dias} dia(s) — {nome_emp}"

        corpo = f"""
        <html><body style="font-family:Arial,sans-serif;background:#f5f5f5;padding:20px">
        <div style="max-width:600px;margin:auto;background:#fff;border-radius:10px;padding:30px">
          <h2 style="color:#e94560">⚠️ Lembrete de Vencimento</h2>
          <p>Olá, <strong>{cli.nome}</strong>!</p>
          <p>Seu boleto vence em <strong>{dias} dia(s)</strong> ({b.data_vencimento.strftime('%d/%m/%Y')}).</p>
          <p><strong>Valor: R$ {float(b.valor):,.2f}</strong></p>
          <div style="background:#f0f0f0;padding:14px;border-radius:6px;margin:16px 0">
            <p style="font-size:12px;color:#666;margin:0 0 6px">Linha digitável:</p>
            <p style="font-family:monospace;font-size:14px;margin:0;word-break:break-all">
              {b.linha_digitavel}</p>
          </div>
          {'<a href="'+b.url_pdf+'" style="display:inline-block;background:#e94560;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold">📄 Pagar Boleto</a>' if b.url_pdf else ''}
        </div></body></html>
        """
        return cls._enviar(cli.email, assunto, corpo)

    @classmethod
    def testar_smtp(cls):
        cfg = cls._cfg()
        if not cfg["host"]: return False, "SMTP não configurado."
        try:
            with smtplib.SMTP(cfg["host"], cfg["porta"], timeout=10) as srv:
                srv.starttls()
                srv.login(cfg["usuario"], cfg["senha"])
            return True, "Conexão SMTP testada com sucesso!"
        except Exception as e:
            return False, f"Falha na conexão: {e}"


# ─────────────────────────────────────────────
# BACKUP
# ─────────────────────────────────────────────

class BackupService:

    PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")

    @classmethod
    def fazer_backup(cls):
        """Copia o banco de dados para a pasta de backups."""
        os.makedirs(cls.PASTA, exist_ok=True)
        origem  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "boletos.db")
        ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = os.path.join(cls.PASTA, f"backup_{ts}.db")

        if not os.path.exists(origem):
            return False, "Banco de dados não encontrado."
        try:
            shutil.copy2(origem, destino)
            cls._limpar_antigos()
            return True, f"Backup salvo: backup_{ts}.db"
        except Exception as e:
            return False, f"Erro no backup: {e}"

    @classmethod
    def _limpar_antigos(cls, manter=10):
        """Mantém apenas os N backups mais recentes."""
        arquivos = sorted(
            [f for f in os.listdir(cls.PASTA) if f.endswith(".db")],
            reverse=True
        )
        for arq in arquivos[manter:]:
            os.remove(os.path.join(cls.PASTA, arq))

    @classmethod
    def listar_backups(cls):
        os.makedirs(cls.PASTA, exist_ok=True)
        return sorted(
            [f for f in os.listdir(cls.PASTA) if f.endswith(".db")],
            reverse=True
        )

    @classmethod
    def restaurar(cls, nome_arquivo):
        origem  = os.path.join(cls.PASTA, nome_arquivo)
        destino = os.path.join(os.path.dirname(os.path.abspath(__file__)), "boletos.db")
        if not os.path.exists(origem):
            return False, "Arquivo não encontrado."
        try:
            shutil.copy2(origem, destino)
            return True, "Banco restaurado. Reinicie o sistema."
        except Exception as e:
            return False, f"Erro ao restaurar: {e}"

    @classmethod
    def iniciar_backup_automatico(cls, intervalo_horas=24):
        """Inicia thread de backup automático."""
        if Configuracao.get("backup_automatico", "true") != "true":
            return
        def _loop():
            while True:
                import time
                cls.fazer_backup()
                time.sleep(intervalo_horas * 3600)
        t = threading.Thread(target=_loop, daemon=True)
        t.start()


# ─────────────────────────────────────────────
# NOTIFICAÇÕES
# ─────────────────────────────────────────────

class NotifService:

    @staticmethod
    def boletos_vencendo(dias_antes=None):
        """Retorna boletos que vencem nos próximos N dias."""
        if dias_antes is None:
            dias_antes = int(Configuracao.get("notif_dias_antes", "3"))
        hoje  = date.today()
        limite = hoje + timedelta(days=dias_antes)
        with Session() as s:
            boletos = s.query(Boleto).filter(
                Boleto.status == "PENDENTE",
                Boleto.data_vencimento >= hoje,
                Boleto.data_vencimento <= limite
            ).all()
            resultado = []
            for b in boletos:
                cli = s.get(Cliente, b.cliente_id)
                resultado.append({
                    "id":         b.id,
                    "cliente":    cli.nome if cli else "—",
                    "email":      cli.email if cli else None,
                    "valor":      float(b.valor),
                    "vencimento": b.data_vencimento,
                    "dias":       (b.data_vencimento - hoje).days,
                })
        return resultado

    @classmethod
    def enviar_lembretes_automaticos(cls):
        """Envia lembretes por e-mail para todos os boletos próximos do vencimento."""
        boletos = cls.boletos_vencendo()
        enviados = 0
        for b in boletos:
            if b["email"]:
                ok, _ = EmailService.enviar_lembrete(b["id"])
                if ok: enviados += 1
        return enviados

    @classmethod
    def iniciar_monitoramento(cls, callback_notif=None, intervalo_min=60):
        """Thread que monitora vencimentos e chama callback para notificar na UI."""
        def _loop():
            import time
            while True:
                boletos = cls.boletos_vencendo()
                if boletos and callback_notif:
                    callback_notif(boletos)
                AsaasService.atualizar_vencidos()
                time.sleep(intervalo_min * 60)
        t = threading.Thread(target=_loop, daemon=True)
        t.start()


# ─────────────────────────────────────────────
# HELPERS DE BANCO (usados pelo app)
# ─────────────────────────────────────────────

def criar_cliente(empresa_id, nome, tipo, cpf=None, cnpj=None,
                  email=None, telefone=None):
    with Session() as s:
        try:
            c = Cliente(nome=nome, tipo=tipo, empresa_id=empresa_id,
                        cpf=cpf, cnpj=cnpj, email=email, telefone=telefone)
            s.add(c); s.commit(); s.refresh(c)
            return c, None
        except Exception as e:
            s.rollback()
            return None, str(e)


def salvar_endereco(cliente_id, logradouro, numero, bairro, cidade,
                    uf, cep, complemento=None):
    with Session() as s:
        end = s.query(Endereco).filter_by(cliente_id=cliente_id, principal=True).first()
        if end:
            end.logradouro=logradouro; end.numero=numero; end.bairro=bairro
            end.cidade=cidade; end.uf=uf; end.cep=cep; end.complemento=complemento
        else:
            s.add(Endereco(cliente_id=cliente_id, logradouro=logradouro,
                           numero=numero, bairro=bairro, cidade=cidade,
                           uf=uf, cep=cep, complemento=complemento, principal=True))
        s.commit()


def gerar_boleto(empresa_id, cliente_id, conta_id, valor,
                 data_vencimento, descricao=None):
    with Session() as s:
        try:
            b = Boleto(empresa_id=empresa_id, cliente_id=cliente_id,
                       conta_id=conta_id, valor=valor,
                       data_vencimento=data_vencimento, descricao=descricao)
            s.add(b); s.commit(); s.refresh(b)
            return b, None
        except Exception as e:
            s.rollback()
            return None, str(e)


def registrar_pagamento(boleto_id, valor_pago, canal="manual", comprovante=None):
    with Session() as s:
        b = s.get(Boleto, boleto_id)
        if not b or b.status == "PAGO":
            return False
        s.add(PagamentoBoleto(boleto_id=boleto_id, valor_pago=valor_pago,
                               canal=canal, comprovante=comprovante))
        b.status = "PAGO"
        s.commit()
        return True
