"""
app.py — Interface Desktop v5
================================
Sistema de Boletos completo e pronto para venda.

- Login para teste = admin@sistema.com
- Senha para teste = admin123
-Para rodar o sistema no terminal, use o comando: cd "D:\Projeto PIM"
python app.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading, os, sys, webbrowser, re, csv
import sqlalchemy as _sa
from datetime import date, timedelta, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import (
    inicializar, Session, Configuracao, Empresa, Usuario,
    Cliente, Endereco, ContaBancaria, Boleto, PagamentoBoleto, LogAuditoria
)
from services import (
    AsaasService, EmailService, BackupService, NotifService,
    criar_cliente, salvar_endereco, gerar_boleto, registrar_pagamento,
    _API_KEY, _SANDBOX
)

# ─────────────────────────────────────────────
# TEMAS
# ─────────────────────────────────────────────
TEMAS = {
    "escuro": {
        "bg":"#1a1a2e","painel":"#16213e","card":"#0f3460",
        "dest":"#e94560","txt":"#eaeaea","txt2":"#a0a0b0",
        "verde":"#00b894","amarelo":"#fdcb6e","vermelho":"#e17055",
        "azul":"#0984e3","roxo":"#6c5ce7","cinza":"#4a4a6a",
        "entry_bg":"#0f3460","entry_fg":"#eaeaea",
        "tree_bg":"#0f3460","tree_sel":"#e94560",
        "sidebar":"#16213e","sidebar_ativo":"#0f3460",
    },
    "claro": {
        "bg":"#f0f2f5","painel":"#ffffff","card":"#e8ecf0",
        "dest":"#e94560","txt":"#1a1a2e","txt2":"#555570",
        "verde":"#00b894","amarelo":"#c47c00","vermelho":"#d63031",
        "azul":"#0984e3","roxo":"#6c5ce7","cinza":"#9090a8",
        "entry_bg":"#ffffff","entry_fg":"#1a1a2e",
        "tree_bg":"#ffffff","tree_sel":"#e94560",
        "sidebar":"#1a1a2e","sidebar_ativo":"#0f3460",
    },
}

def C(k):
    t = Configuracao.get("tema","escuro")
    return TEMAS.get(t, TEMAS["escuro"]).get(k,"#ffffff")

FT = {
    "normal": ("Segoe UI",10), "titulo": ("Segoe UI",20,"bold"),
    "subtit": ("Segoe UI",13,"bold"), "label": ("Segoe UI",9),
    "botao":  ("Segoe UI",10,"bold"), "mono":  ("Consolas",10),
    "grande": ("Segoe UI",26,"bold"), "medio": ("Segoe UI",14,"bold"),
}

def _soma(col): return _sa.func.sum(col)
def _num(v):    return re.sub(r"\D","",v or "")

# ── MÁSCARAS ─────────────────────────────────
def _fmt_cpf(d):
    d=_num(d)[:11]
    if len(d)>9:  return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d)>6:  return f"{d[:3]}.{d[3:6]}.{d[6:]}"
    if len(d)>3:  return f"{d[:3]}.{d[3:]}"
    return d

def _fmt_cnpj(d):
    d=_num(d)[:14]
    if len(d)>12: return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d)>8:  return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:]}"
    if len(d)>5:  return f"{d[:2]}.{d[2:5]}.{d[5:]}"
    if len(d)>2:  return f"{d[:2]}.{d[2:]}"
    return d

def _fmt_cep(d):
    d=_num(d)[:8]
    return f"{d[:5]}-{d[5:]}" if len(d)>5 else d

def _fmt_tel(d):
    d=_num(d)[:11]
    if len(d)>10: return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d)>6:  return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    if len(d)>2:  return f"({d[:2]}) {d[2:]}"
    return d

def mascara(var,fn):
    bl=[False]
    def _cb(*_):
        if bl[0]: return
        bl[0]=True
        try: var.set(fn(var.get()))
        finally: bl[0]=False
    var.trace_add("write",_cb)
    return var

# ── COMPONENTES ──────────────────────────────
def btn(parent,txt,cmd,cor=None,w=16,**kw):
    cor=cor or C("dest")
    return tk.Button(parent,text=txt,command=cmd,bg=cor,fg="white",
                     font=FT["botao"],relief="flat",cursor="hand2",
                     width=w,padx=8,pady=6,
                     activebackground=cor,activeforeground="white",**kw)

def campo(parent,lbl_txt,row,col=0,fn_mask=None,opcoes=None,larg=24):
    bg=C("painel")
    tk.Label(parent,text=lbl_txt,bg=bg,fg=C("txt2"),
             font=FT["label"]).grid(row=row,column=col*2,sticky="w",padx=(0,4),pady=3)
    var=tk.StringVar()
    if opcoes:
        w=ttk.Combobox(parent,textvariable=var,values=opcoes,
                       font=FT["normal"],width=larg,state="readonly")
    else:
        w=tk.Entry(parent,textvariable=var,bg=C("entry_bg"),fg=C("entry_fg"),
                   font=FT["normal"],relief="flat",insertbackground=C("txt"),width=larg)
    w.grid(row=row,column=col*2+1,sticky="ew",padx=(0,12),pady=3)
    if fn_mask: mascara(var,fn_mask)
    return var

def _estilo_tree():
    s=ttk.Style(); s.theme_use("clam")
    s.configure("Treeview",background=C("tree_bg"),foreground=C("txt"),
                fieldbackground=C("tree_bg"),rowheight=30,font=FT["normal"])
    s.configure("Treeview.Heading",background=C("painel"),
                foreground=C("txt2"),font=FT["label"],relief="flat")
    s.map("Treeview",background=[("selected",C("tree_sel"))])

def _tree(parent,cols,altura=14,widths=None):
    f=tk.Frame(parent,bg=C("bg")); f.pack(fill="both",expand=True)
    tree=ttk.Treeview(f,columns=cols,show="headings",height=altura)
    for i,c in enumerate(cols):
        tree.heading(c,text=c)
        tree.column(c,width=(widths[i] if widths else 130),anchor="w")
    sb=ttk.Scrollbar(f,orient="vertical",command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left",fill="both",expand=True)
    sb.pack(side="right",fill="y")
    return tree,f

# ─────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────
class TelaLogin(tk.Tk):
    def __init__(self):
        super().__init__()
        nome=Configuracao.get("nome_sistema","Sistema de Boletos")
        self.title(nome); self.geometry("440x380")
        self.configure(bg=C("bg")); self.resizable(False,False)
        self.usuario_logado=None
        self._build()

    def _build(self):
        f=tk.Frame(self,bg=C("painel"),padx=40,pady=36)
        f.place(relx=.5,rely=.5,anchor="center",width=360,height=320)
        nome=Configuracao.get("nome_sistema","Sistema de Boletos")
        tk.Label(f,text="💳",bg=C("painel"),font=("Segoe UI",28)).pack()
        tk.Label(f,text=nome,bg=C("painel"),fg=C("txt"),font=FT["subtit"]).pack(pady=(4,2))
        tk.Label(f,text="Acesse sua conta",bg=C("painel"),fg=C("txt2"),font=FT["label"]).pack(pady=(0,18))

        tk.Label(f,text="E-mail",bg=C("painel"),fg=C("txt2"),font=FT["label"]).pack(anchor="w")
        self._email=tk.StringVar()
        tk.Entry(f,textvariable=self._email,bg=C("entry_bg"),fg=C("entry_fg"),
                 font=FT["normal"],relief="flat",insertbackground=C("txt"),
                 width=32).pack(fill="x",pady=(2,10))

        tk.Label(f,text="Senha",bg=C("painel"),fg=C("txt2"),font=FT["label"]).pack(anchor="w")
        self._senha=tk.StringVar()
        tk.Entry(f,textvariable=self._senha,show="●",bg=C("entry_bg"),fg=C("entry_fg"),
                 font=FT["normal"],relief="flat",insertbackground=C("txt"),
                 width=32).pack(fill="x",pady=(2,18))

        btn(f,"Entrar",self._login,w=32).pack(fill="x")
        self._msg=tk.StringVar()
        tk.Label(f,textvariable=self._msg,bg=C("painel"),
                 fg=C("vermelho"),font=FT["label"]).pack(pady=(8,0))
        self.bind("<Return>",lambda _:self._login())

    def _login(self):
        email=self._email.get().strip().lower()
        senha=self._senha.get().strip()
        with Session() as s:
            u=s.query(Usuario).filter_by(email=email,ativo=True).first()
            if u and u.verificar_senha(senha):
                u.ultimo_login=datetime.utcnow(); s.commit()
                LogAuditoria.registrar(u.id,"login",f"Login: {u.nome}",u.empresa_id)
                self.usuario_logado={"id":u.id,"nome":u.nome,
                                      "perfil":u.perfil,"empresa_id":u.empresa_id}
                self.destroy()
            else:
                self._msg.set("E-mail ou senha incorretos.")

# ─────────────────────────────────────────────
# APP PRINCIPAL
# ─────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self,usr):
        super().__init__()
        self.usr=usr; self.empresa_id=usr.get("empresa_id"); self._notifs=[]
        nome=Configuracao.get("nome_sistema","Sistema de Boletos")
        self.title(nome); self.geometry("1280x760")
        self.configure(bg=C("bg")); self.resizable(True,True); self.minsize(1000,640)
        _estilo_tree(); self._build(); self.mostrar_dashboard()
        BackupService.iniciar_backup_automatico()
        NotifService.iniciar_monitoramento(self._on_notif)

    def _build(self):
        self.sb=tk.Frame(self,bg=C("sidebar"),width=230)
        self.sb.pack(side="left",fill="y"); self.sb.pack_propagate(False)
        nome=Configuracao.get("nome_sistema","Sistema de Boletos")
        tk.Label(self.sb,text="💳",bg=C("sidebar"),font=("Segoe UI",22)).pack(pady=(20,0))
        tk.Label(self.sb,text=nome,bg=C("sidebar"),fg="white",
                 font=("Segoe UI",11,"bold")).pack(pady=(2,4))
        modo="● SANDBOX" if _SANDBOX else "● PRODUÇÃO"
        tk.Label(self.sb,text=modo,bg=C("sidebar"),
                 fg=C("amarelo") if _SANDBOX else C("verde"),font=FT["label"]).pack(pady=(0,2))
        tk.Label(self.sb,text=f"👤 {self.usr['nome']}",bg=C("sidebar"),
                 fg="white",font=FT["label"]).pack()
        tk.Label(self.sb,text=f"[{self.usr['perfil'].upper()}]",bg=C("sidebar"),
                 fg=C("dest"),font=FT["label"]).pack(pady=(0,12))
        tk.Frame(self.sb,bg=C("card"),height=1).pack(fill="x",padx=12)

        self._mbts={}
        menus=[
            ("🏠","Dashboard",    self.mostrar_dashboard,    True),
            ("👤","Clientes",     self.mostrar_clientes,     True),
            ("📄","Boletos",      self.mostrar_boletos,      True),
            ("➕","Novo Boleto",  self.mostrar_novo_boleto,  self.usr["perfil"]!="visualizador"),
            ("💰","Pagamentos",   self.mostrar_pagamentos,   True),
            ("📊","Relatório",    self.mostrar_relatorio,    True),
            ("🔔","Notificações", self.mostrar_notificacoes, True),
            ("⚙️","Configurações",self.mostrar_configuracoes,self.usr["perfil"]=="admin"),
        ]
        for ico,nome,cmd,vis in menus:
            if not vis: continue
            f=tk.Frame(self.sb,bg=C("sidebar"),cursor="hand2"); f.pack(fill="x")
            li=tk.Label(f,text=f"  {ico}  {nome}",bg=C("sidebar"),
                        fg="white",font=FT["normal"],anchor="w",padx=8,pady=11)
            li.pack(fill="x")
            for w in (f,li):
                w.bind("<Button-1>",lambda e,c=cmd:c())
                w.bind("<Enter>",lambda e,a=f,b=li:(a.config(bg=C("sidebar_ativo")),b.config(bg=C("sidebar_ativo"))))
                w.bind("<Leave>",lambda e,a=f,b=li,n=nome:(
                    a.config(bg=C("sidebar_ativo") if self._mbts.get("_ativo")==n else C("sidebar")),
                    b.config(bg=C("sidebar_ativo") if self._mbts.get("_ativo")==n else C("sidebar"))))
            self._mbts[nome]=(f,li)

        self._notif_lbl=tk.Label(self.sb,text="",bg=C("sidebar"),
                                  fg=C("vermelho"),font=FT["label"])
        self._notif_lbl.pack(pady=4)
        tk.Frame(self.sb,bg=C("sidebar")).pack(fill="y",expand=True)
        tk.Frame(self.sb,bg=C("card"),height=1).pack(fill="x",padx=12)
        btn(self.sb,"🚪 Sair",self._sair,cor=C("cinza"),w=22).pack(fill="x",padx=12,pady=12)
        self.area=tk.Frame(self,bg=C("bg")); self.area.pack(side="right",fill="both",expand=True)

    def _ativar(self,nome):
        ant=self._mbts.get("_ativo")
        if ant and ant in self._mbts:
            f,l=self._mbts[ant]; f.config(bg=C("sidebar")); l.config(bg=C("sidebar"))
        self._mbts["_ativo"]=nome
        if nome in self._mbts:
            f,l=self._mbts[nome]; f.config(bg=C("sidebar_ativo")); l.config(bg=C("sidebar_ativo"),fg=C("dest"))

    def _limpar(self):
        for w in self.area.winfo_children(): w.destroy()

    def _titulo(self,t,sub=None):
        f=tk.Frame(self.area,bg=C("bg")); f.pack(fill="x",padx=28,pady=(20,6))
        tk.Label(f,text=t,bg=C("bg"),fg=C("txt"),font=FT["titulo"]).pack(side="left")
        if sub: tk.Label(f,text=sub,bg=C("bg"),fg=C("txt2"),font=FT["label"]).pack(side="left",padx=12,pady=8)

    def _sair(self):
        if messagebox.askyesno("Sair","Deseja realmente sair?"): self.destroy()

    def _on_notif(self,boletos):
        self._notifs=boletos; n=len(boletos)
        self.after(0,lambda:self._notif_lbl.config(text=f"🔔 {n} vencendo!" if n else ""))

    # ── DASHBOARD ────────────────────────────
    def mostrar_dashboard(self):
        self._limpar(); self._ativar("Dashboard")
        self._titulo("Dashboard",f"Bem-vindo, {self.usr['nome']}")

        with Session() as s:
            q=s.query(Boleto)
            if self.empresa_id: q=q.filter_by(empresa_id=self.empresa_id)
            tot=q.count()
            pen=s.query(Boleto).filter_by(status="PENDENTE").count()
            pag=s.query(Boleto).filter_by(status="PAGO").count()
            vec=s.query(Boleto).filter_by(status="VENCIDO").count()
            qc=s.query(Cliente)
            if self.empresa_id: qc=qc.filter_by(empresa_id=self.empresa_id)
            cli=qc.filter_by(ativo=True).count()
            vp=float(s.query(_soma(Boleto.valor)).filter_by(status="PENDENTE").scalar() or 0)
            vg=float(s.query(_soma(Boleto.valor)).filter_by(status="PAGO").scalar() or 0)
            vv=float(s.query(_soma(Boleto.valor)).filter_by(status="VENCIDO").scalar() or 0)
            ults=s.query(Boleto).order_by(Boleto.id.desc()).limit(6).all()
            ult_d=[(b.id,s.get(Cliente,b.cliente_id).nome if s.get(Cliente,b.cliente_id) else "—",
                    float(b.valor),b.status,b.data_vencimento.strftime("%d/%m/%Y")) for b in ults]

        g1=tk.Frame(self.area,bg=C("bg")); g1.pack(fill="x",padx=28,pady=4)
        for i in range(4): g1.columnconfigure(i,weight=1)
        for i,(lbl_t,val,cor) in enumerate([
            ("Total Boletos",str(tot),C("txt")),("Pendentes",str(pen),C("amarelo")),
            ("Pagos",str(pag),C("verde")),("Vencidos",str(vec),C("vermelho"))]):
            f=tk.Frame(g1,bg=C("card"),padx=18,pady=16)
            f.grid(row=0,column=i,padx=6,pady=4,sticky="nsew")
            tk.Label(f,text=lbl_t,bg=C("card"),fg=C("txt2"),font=FT["label"]).pack(anchor="w")
            tk.Label(f,text=val,bg=C("card"),fg=cor,font=FT["grande"]).pack(anchor="w")

        g2=tk.Frame(self.area,bg=C("bg")); g2.pack(fill="x",padx=28,pady=4)
        for i in range(3): g2.columnconfigure(i,weight=1)
        for i,(lbl_t,val,cor) in enumerate([
            ("Clientes Ativos",str(cli),C("txt")),
            ("A Receber",f"R$ {vp:,.2f}",C("amarelo")),
            ("Recebido",f"R$ {vg:,.2f}",C("verde"))]):
            f=tk.Frame(g2,bg=C("card"),padx=18,pady=16)
            f.grid(row=0,column=i,padx=6,pady=4,sticky="nsew")
            tk.Label(f,text=lbl_t,bg=C("card"),fg=C("txt2"),font=FT["label"]).pack(anchor="w")
            tk.Label(f,text=val,bg=C("card"),fg=cor,font=FT["medio"]).pack(anchor="w")

        # Gráfico de barras
        gf=tk.Frame(self.area,bg=C("painel"),padx=16,pady=12)
        gf.pack(fill="x",padx=28,pady=4)
        tk.Label(gf,text="Distribuição financeira",bg=C("painel"),fg=C("txt2"),font=FT["label"]).pack(anchor="w",pady=(0,6))
        cv=tk.Canvas(gf,bg=C("painel"),height=60,highlightthickness=0); cv.pack(fill="x")
        total_v=vp+vg+vv+0.01; larg=700
        x=0
        for val,cor_k,lbl_t in [(vp,"amarelo","Pendente"),(vg,"verde","Pago"),(vv,"vermelho","Vencido")]:
            w=max(int(val/total_v*larg),2); cor=C(cor_k)
            cv.create_rectangle(x,10,x+w,40,fill=cor,outline="")
            if w>40: cv.create_text(x+w/2,25,text=f"R${val:,.0f}",fill="white",font=FT["label"])
            cv.create_text(x+w/2,52,text=lbl_t,fill=C("txt2"),font=FT["label"])
            x+=w

        # Últimos boletos
        fl=tk.Frame(self.area,bg=C("painel"),padx=16,pady=10)
        fl.pack(fill="x",padx=28,pady=4)
        tk.Label(fl,text="Últimos boletos",bg=C("painel"),fg=C("txt2"),font=FT["label"]).pack(anchor="w",pady=(0,6))
        cols=("ID","Cliente","Valor","Status","Vencimento")
        tree=ttk.Treeview(fl,columns=cols,show="headings",height=5)
        for c in cols: tree.heading(c,text=c); tree.column(c,width=140,anchor="w")
        tree.column("ID",width=40)
        for r in ult_d: tree.insert("","end",values=(r[0],r[1],f"R$ {r[2]:,.2f}",r[3],r[4]))
        tree.pack(fill="x")

        fb=tk.Frame(self.area,bg=C("bg")); fb.pack(anchor="w",padx=28,pady=8)
        btn(fb,"🔄 Atualizar Vencidos",self._att_vec).pack(side="left",padx=(0,8))
        btn(fb,"💾 Backup Agora",self._bkp_now,cor=C("azul")).pack(side="left")

    def _att_vec(self):
        n=AsaasService.atualizar_vencidos()
        messagebox.showinfo("Atualizado",f"{n} boleto(s) marcado(s) como VENCIDO.")
        self.mostrar_dashboard()

    def _bkp_now(self):
        ok,msg=BackupService.fazer_backup()
        messagebox.showinfo("Backup",msg) if ok else messagebox.showerror("Erro",msg)

    # ── CLIENTES ─────────────────────────────
    def mostrar_clientes(self,busca=""):
        self._limpar(); self._ativar("Clientes")
        self._titulo("Clientes")

        fb=tk.Frame(self.area,bg=C("bg")); fb.pack(fill="x",padx=28,pady=4)
        tk.Label(fb,text="🔍",bg=C("bg"),fg=C("txt2"),font=FT["normal"]).pack(side="left")
        self._buscac=tk.StringVar(value=busca)
        tk.Entry(fb,textvariable=self._buscac,bg=C("entry_bg"),fg=C("entry_fg"),
                 font=FT["normal"],relief="flat",width=30).pack(side="left",padx=6)
        btn(fb,"Buscar",lambda:self.mostrar_clientes(self._buscac.get()),cor=C("azul"),w=10).pack(side="left")
        if self.usr["perfil"]!="visualizador":
            btn(fb,"➕ Novo",lambda:self._form_cli(None),w=12).pack(side="right")

        self._tree_cli,_=_tree(self.area,
            ("ID","Nome","Tipo","Documento","E-mail","Telefone","Status"),
            altura=16,widths=[40,180,60,150,180,130,70])

        if self.usr["perfil"]!="visualizador":
            fb2=tk.Frame(self.area,bg=C("bg")); fb2.pack(anchor="w",padx=28,pady=6)
            btn(fb2,"✏️ Editar",self._edit_cli,cor=C("azul"),w=12).pack(side="left",padx=(0,6))
            btn(fb2,"✅ Ativar",self._tog_cli(True),cor=C("verde"),w=12).pack(side="left",padx=(0,6))
            btn(fb2,"🚫 Desativar",self._tog_cli(False),cor=C("cinza"),w=12).pack(side="left")

        self._load_cli(busca)

    def _load_cli(self,busca=""):
        self._tree_cli.delete(*self._tree_cli.get_children())
        with Session() as s:
            q=s.query(Cliente)
            if self.empresa_id: q=q.filter_by(empresa_id=self.empresa_id)
            if busca:
                q=q.filter(_sa.or_(Cliente.nome.ilike(f"%{busca}%"),
                                    Cliente.cnpj.ilike(f"%{busca}%"),
                                    Cliente.cpf.ilike(f"%{busca}%"),
                                    Cliente.email.ilike(f"%{busca}%")))
            for c in q.order_by(Cliente.id.desc()).all():
                self._tree_cli.insert("","end",iid=str(c.id),
                    values=(c.id,c.nome,c.tipo,c.documento,
                            c.email or "—",c.telefone or "—",
                            "Ativo" if c.ativo else "Inativo"))

    def _tog_cli(self,ativar):
        def _fn():
            sel=self._tree_cli.selection()
            if not sel: messagebox.showwarning("Atenção","Selecione um cliente."); return
            with Session() as s:
                c=s.get(Cliente,int(sel[0]))
                if c: c.ativo=ativar; s.commit()
            self._load_cli()
        return _fn

    def _edit_cli(self):
        sel=self._tree_cli.selection()
        if not sel: messagebox.showwarning("Atenção","Selecione um cliente."); return
        self._form_cli(int(sel[0]))

    def _form_cli(self,cid):
        win=tk.Toplevel(self)
        win.title("Novo Cliente" if not cid else "Editar Cliente")
        win.geometry("580x600"); win.configure(bg=C("painel")); win.resizable(False,False); win.grab_set()
        tk.Label(win,text="Dados do Cliente",bg=C("painel"),fg=C("txt"),font=FT["subtit"]).pack(pady=(16,10))
        f=tk.Frame(win,bg=C("painel"),padx=24); f.pack(fill="x")
        for i in range(4): f.columnconfigure(i,weight=1)

        vt=campo(f,"Tipo",0,0,opcoes=["PJ","PF"])
        vn=campo(f,"Nome",1,0); vd=campo(f,"CPF / CNPJ",2,0)
        ve=campo(f,"E-mail",3,0); vf=campo(f,"Telefone",4,0,fn_mask=_fmt_tel)
        vl=campo(f,"Logradouro",5,0); vnu=campo(f,"Número",5,1)
        vb=campo(f,"Bairro",6,0); vc=campo(f,"Cidade",6,1)
        vuf=campo(f,"UF",7,0); vz=campo(f,"CEP",7,1,fn_mask=_fmt_cep)
        vco=campo(f,"Complemento",8,0)

        bl=[False]
        def _dm(*_):
            fn=_fmt_cnpj if vt.get()=="PJ" else _fmt_cpf
            if bl[0]: return
            bl[0]=True
            try: vd.set(fn(vd.get()))
            finally: bl[0]=False
        vd.trace_add("write",_dm)

        if cid:
            with Session() as s:
                c=s.get(Cliente,cid)
                end=s.query(Endereco).filter_by(cliente_id=cid,principal=True).first()
                if c: vt.set(c.tipo); vn.set(c.nome); vd.set(c.documento or ""); ve.set(c.email or ""); vf.set(c.telefone or "")
                if end: vl.set(end.logradouro or ""); vnu.set(end.numero or ""); vb.set(end.bairro or ""); vc.set(end.cidade or ""); vuf.set(end.uf or ""); vz.set(end.cep or ""); vco.set(end.complemento or "")

        def _salvar():
            tipo=vt.get().upper(); doc=vd.get().strip()
            eid=self.empresa_id
            if not eid:
                with Session() as s:
                    emp=s.query(Empresa).first(); eid=emp.id if emp else None
            if not eid: messagebox.showerror("Erro","Empresa não configurada."); return

            if cid:
                with Session() as s:
                    c=s.get(Cliente,cid)
                    if c:
                        c.nome=vn.get().strip(); c.email=ve.get().strip(); c.telefone=vf.get().strip()
                        if tipo=="PF": c.cpf=doc
                        else: c.cnpj=doc
                        s.commit()
                salvar_endereco(cid,vl.get(),vnu.get(),vb.get(),vc.get(),vuf.get(),vz.get(),vco.get())
                messagebox.showinfo("Sucesso","Cliente atualizado!")
            else:
                c,err=criar_cliente(eid,vn.get().strip(),tipo,
                    cpf=doc if tipo=="PF" else None,cnpj=doc if tipo=="PJ" else None,
                    email=ve.get().strip(),telefone=vf.get().strip())
                if c:
                    salvar_endereco(c.id,vl.get(),vnu.get(),vb.get(),vc.get(),vuf.get(),vz.get(),vco.get())
                    messagebox.showinfo("Sucesso",f"Cliente '{c.nome}' cadastrado!")
                else:
                    messagebox.showerror("Erro",err or "Verifique os dados."); return
            win.destroy(); self.mostrar_clientes()

        fb=tk.Frame(win,bg=C("painel"),padx=24); fb.pack(pady=14)
        btn(fb,"💾 Salvar",_salvar,w=16).pack(side="left",padx=(0,8))
        btn(fb,"Cancelar",win.destroy,cor=C("cinza"),w=12).pack(side="left")

    # ── BOLETOS ──────────────────────────────
    def mostrar_boletos(self):
        self._limpar(); self._ativar("Boletos")
        self._titulo("Boletos")

        ff=tk.Frame(self.area,bg=C("bg")); ff.pack(fill="x",padx=28,pady=4)
        self._filtro=tk.StringVar(value="TODOS")
        for st in ("TODOS","PENDENTE","PAGO","VENCIDO","CANCELADO"):
            tk.Radiobutton(ff,text=st,variable=self._filtro,value=st,
                           command=self._load_bol,bg=C("bg"),fg=C("txt"),
                           selectcolor=C("card"),activebackground=C("bg"),
                           font=FT["label"]).pack(side="left",padx=4)

        fb=tk.Frame(self.area,bg=C("bg")); fb.pack(fill="x",padx=28,pady=2)
        self._buscab=tk.StringVar(); self._de=tk.StringVar(); self._ate=tk.StringVar()
        tk.Label(fb,text="🔍",bg=C("bg"),fg=C("txt2"),font=FT["normal"]).pack(side="left")
        tk.Entry(fb,textvariable=self._buscab,bg=C("entry_bg"),fg=C("entry_fg"),
                 font=FT["normal"],relief="flat",width=22).pack(side="left",padx=6)
        tk.Label(fb,text="De:",bg=C("bg"),fg=C("txt2"),font=FT["label"]).pack(side="left",padx=(10,4))
        tk.Entry(fb,textvariable=self._de,bg=C("entry_bg"),fg=C("entry_fg"),
                 font=FT["normal"],relief="flat",width=10).pack(side="left")
        tk.Label(fb,text="Até:",bg=C("bg"),fg=C("txt2"),font=FT["label"]).pack(side="left",padx=(8,4))
        tk.Entry(fb,textvariable=self._ate,bg=C("entry_bg"),fg=C("entry_fg"),
                 font=FT["normal"],relief="flat",width=10).pack(side="left")
        btn(fb,"Filtrar",self._load_bol,cor=C("azul"),w=8).pack(side="left",padx=6)

        self._tree_bol,_=_tree(self.area,
            ("ID","Cliente","Valor","Emissão","Vencimento","Status","📧","Linha Digitável"),
            altura=13,widths=[40,160,100,90,90,80,30,270])

        fb2=tk.Frame(self.area,bg=C("bg")); fb2.pack(anchor="w",padx=28,pady=6)
        btn(fb2,"🌐 PDF",self._ver_pdf,cor=C("verde"),w=10).pack(side="left",padx=(0,6))
        btn(fb2,"📧 E-mail",self._email_bol,cor=C("azul"),w=10).pack(side="left",padx=(0,6))
        if self.usr["perfil"]!="visualizador":
            btn(fb2,"✏️ Editar",self._edit_bol,cor=C("azul"),w=10).pack(side="left",padx=(0,6))
            btn(fb2,"💰 Pago",self._marcar_pago,cor=C("roxo"),w=10).pack(side="left",padx=(0,6))
        if self.usr["perfil"]=="admin":
            btn(fb2,"❌ Excluir",self._excluir_bol,cor=C("vermelho"),w=10).pack(side="left")

        self._load_bol()

    def _load_bol(self):
        self._tree_bol.delete(*self._tree_bol.get_children())
        filtro=self._filtro.get(); busca=self._buscab.get().strip()
        de=self._de.get().strip(); ate=self._ate.get().strip()
        with Session() as s:
            q=s.query(Boleto)
            if self.empresa_id: q=q.filter_by(empresa_id=self.empresa_id)
            if filtro!="TODOS": q=q.filter_by(status=filtro)
            if busca:
                ids=[c.id for c in s.query(Cliente).filter(_sa.or_(
                    Cliente.nome.ilike(f"%{busca}%"),Cliente.cnpj.ilike(f"%{busca}%"),
                    Cliente.cpf.ilike(f"%{busca}%")))]
                q=q.filter(Boleto.cliente_id.in_(ids))
            try:
                if de:  q=q.filter(Boleto.data_vencimento>=datetime.strptime(de,"%d/%m/%Y").date())
                if ate: q=q.filter(Boleto.data_vencimento<=datetime.strptime(ate,"%d/%m/%Y").date())
            except: pass
            for b in q.order_by(Boleto.id.desc()).all():
                cli=s.get(Cliente,b.cliente_id)
                self._tree_bol.insert("","end",iid=str(b.id),
                    values=(b.id,cli.nome if cli else "—",f"R$ {float(b.valor):,.2f}",
                            b.data_emissao.strftime("%d/%m/%Y") if b.data_emissao else "—",
                            b.data_vencimento.strftime("%d/%m/%Y"),b.status,
                            "✔" if b.email_enviado else "—",b.linha_digitavel or "—"))

    def _sel_bol(self):
        sel=self._tree_bol.selection()
        if not sel: messagebox.showwarning("Atenção","Selecione um boleto."); return None
        return int(sel[0])

    def _ver_pdf(self):
        bid=self._sel_bol()
        if not bid: return
        with Session() as s:
            b=s.get(Boleto,bid)
            if b and b.url_pdf: webbrowser.open(b.url_pdf)
            else: messagebox.showwarning("Atenção","PDF não disponível.")

    def _email_bol(self):
        bid=self._sel_bol()
        if not bid: return
        if not messagebox.askyesno("Confirmar","Enviar boleto por e-mail ao cliente?"): return
        ok,msg=EmailService.enviar_boleto(bid)
        messagebox.showinfo("E-mail",msg) if ok else messagebox.showerror("Erro",msg)
        self._load_bol()

    def _edit_bol(self):
        bid=self._sel_bol()
        if not bid: return
        with Session() as s:
            b=s.get(Boleto,bid)
            if not b or b.status!="PENDENTE":
                messagebox.showwarning("Atenção","Só boletos PENDENTES podem ser editados."); return

        win=tk.Toplevel(self); win.title("Editar Boleto"); win.geometry("400x280")
        win.configure(bg=C("painel")); win.resizable(False,False); win.grab_set()
        tk.Label(win,text="Editar Boleto",bg=C("painel"),fg=C("txt"),font=FT["subtit"]).pack(pady=(16,10))
        f=tk.Frame(win,bg=C("painel"),padx=24); f.pack(fill="x")
        for i in range(2): f.columnconfigure(i,weight=1)
        vv=campo(f,"Valor (R$)",0,0); vd=campo(f,"Vencimento (dd/mm/aaaa)",1,0); vdesc=campo(f,"Descrição",2,0)
        with Session() as s:
            b=s.get(Boleto,bid)
            vv.set(str(float(b.valor))); vd.set(b.data_vencimento.strftime("%d/%m/%Y")); vdesc.set(b.descricao or "")

        def _salvar():
            try: nv=float(vv.get().replace(",",".")); nd=datetime.strptime(vd.get(),"%d/%m/%Y").date()
            except: messagebox.showerror("Erro","Dados inválidos."); return
            with Session() as s:
                b=s.get(Boleto,bid)
                if b: b.valor=nv; b.data_vencimento=nd; b.descricao=vdesc.get(); s.commit()
            messagebox.showinfo("Sucesso","Boleto atualizado!")
            win.destroy(); self._load_bol()

        fb=tk.Frame(win,bg=C("painel"),padx=24); fb.pack(pady=14)
        btn(fb,"💾 Salvar",_salvar,w=14).pack(side="left",padx=(0,8))
        btn(fb,"Cancelar",win.destroy,cor=C("cinza"),w=10).pack(side="left")

    def _marcar_pago(self):
        bid=self._sel_bol()
        if not bid: return
        with Session() as s:
            b=s.get(Boleto,bid)
            if not b or b.status=="PAGO": messagebox.showinfo("Info","Boleto já pago."); return
            val=float(b.valor)
        if not messagebox.askyesno("Confirmar",f"Marcar boleto #{bid} como PAGO?"): return
        if registrar_pagamento(bid,val,canal="manual"):
            messagebox.showinfo("Sucesso","Boleto marcado como pago!")
            self._load_bol()

    def _excluir_bol(self):
        bid=self._sel_bol()
        if not bid: return
        if not messagebox.askyesno("Confirmar","Excluir este boleto? Será cancelado no Asaas."): return
        AsaasService.cancelar_boleto(bid)
        with Session() as s:
            b=s.get(Boleto,bid)
            if b: s.delete(b); s.commit()
        messagebox.showinfo("Sucesso","Boleto excluído.")
        self._load_bol()

    # ── NOVO BOLETO ──────────────────────────
    def mostrar_novo_boleto(self):
        self._limpar(); self._ativar("Novo Boleto")
        self._titulo("Gerar Novo Boleto")
        f=tk.Frame(self.area,bg=C("painel"),padx=24,pady=20)
        f.pack(fill="x",padx=28,pady=8)
        for i in range(2): f.columnconfigure(i,weight=1)

        self._nb_cnpj=campo(f,"CNPJ do cliente",0,0,fn_mask=_fmt_cnpj)
        self._nb_valor=campo(f,"Valor (R$)",1,0)
        self._nb_dias=campo(f,"Vencimento (dias)",2,0)
        self._nb_desc=campo(f,"Descrição",3,0)
        self._nb_dias.set("30")

        v_email=tk.BooleanVar(value=True)
        tk.Checkbutton(f,text="Enviar boleto por e-mail ao cliente após emissão",
                       variable=v_email,bg=C("painel"),fg=C("txt"),
                       selectcolor=C("card"),activebackground=C("painel"),
                       font=FT["normal"]).grid(row=4,column=0,columnspan=4,sticky="w",pady=6)

        self._nb_res=tk.Frame(self.area,bg=C("card"),padx=18,pady=14)
        fb=tk.Frame(f,bg=C("painel")); fb.grid(row=5,column=0,columnspan=4,pady=12,sticky="w")
        self._btn_emit=btn(fb,"📤 Emitir Boleto",lambda:self._emitir(v_email.get()),w=18)
        self._btn_emit.pack(side="left")

    def _emitir(self,env_email):
        cnpj=self._nb_cnpj.get().strip(); valor=self._nb_valor.get().strip()
        dias=self._nb_dias.get().strip(); desc=self._nb_desc.get().strip()
        if not cnpj or not valor: messagebox.showwarning("Atenção","Preencha CNPJ e valor."); return
        try: valor_f=float(valor.replace(",",".")); dias_i=int(dias)
        except: messagebox.showerror("Erro","Valor ou dias inválido."); return

        with Session() as s:
            q=s.query(Cliente).filter(_sa.or_(Cliente.cnpj==cnpj,Cliente.cpf==cnpj))
            if self.empresa_id: q=q.filter_by(empresa_id=self.empresa_id)
            cli=q.first()
        if not cli: messagebox.showerror("Erro",f"Cliente '{cnpj}' não encontrado."); return

        with Session() as s:
            emp=s.get(Empresa,self.empresa_id) if self.empresa_id else s.query(Empresa).first()
            ct=s.query(ContaBancaria).filter_by(empresa_id=emp.id).first() if emp else None
        if not emp or not ct: messagebox.showerror("Erro","Empresa ou conta não configurada."); return

        self._btn_emit.config(text="⏳ Aguarde...",state="disabled"); self.update()

        def _t():
            b,err=gerar_boleto(emp.id,cli.id,ct.id,valor_f,date.today()+timedelta(days=dias_i),desc)
            if not b: self.after(0,lambda:self._show_res(False,err,"","")); return
            ok,dados=AsaasService.emitir_boleto(b.id)
            if ok:
                if env_email and cli.email: EmailService.enviar_boleto(b.id)
                self.after(0,lambda:self._show_res(True,"",dados["linha"],dados["pdf"]))
            else:
                self.after(0,lambda:self._show_res(False,dados,"",""))
        threading.Thread(target=_t,daemon=True).start()

    def _show_res(self,ok,err,linha,pdf):
        self._btn_emit.config(text="📤 Emitir Boleto",state="normal")
        for w in self._nb_res.winfo_children(): w.destroy()
        if ok:
            tk.Label(self._nb_res,text="✔ Boleto emitido com sucesso!",
                     bg=C("card"),fg=C("verde"),font=FT["subtit"]).pack(anchor="w")
            tk.Label(self._nb_res,text="Linha digitável:",bg=C("card"),
                     fg=C("txt2"),font=FT["label"]).pack(anchor="w",pady=(8,2))
            vl=tk.StringVar(value=linha)
            tk.Entry(self._nb_res,textvariable=vl,bg=C("painel"),fg=C("txt"),
                     font=FT["mono"],relief="flat",state="readonly",width=55).pack(anchor="w")
            fb=tk.Frame(self._nb_res,bg=C("card")); fb.pack(anchor="w",pady=10)
            btn(fb,"📋 Copiar",lambda:self._copiar(linha),cor=C("azul"),w=12).pack(side="left",padx=(0,8))
            if pdf: btn(fb,"🌐 PDF",lambda:webbrowser.open(pdf),cor=C("verde"),w=10).pack(side="left"); webbrowser.open(pdf)
        else:
            tk.Label(self._nb_res,text=f"✘ {err}",bg=C("card"),fg=C("vermelho"),font=FT["normal"]).pack(anchor="w")
        self._nb_res.pack(fill="x",padx=28,pady=8)

    def _copiar(self,t):
        self.clipboard_clear(); self.clipboard_append(t)
        messagebox.showinfo("Copiado","Linha digitável copiada!")

    # ── PAGAMENTOS ───────────────────────────
    def mostrar_pagamentos(self):
        self._limpar(); self._ativar("Pagamentos")
        self._titulo("Histórico de Pagamentos")
        tree,_=_tree(self.area,("ID","Boleto","Cliente","Valor Pago","Data","Canal","Comprovante"),
                     altura=20,widths=[40,60,180,110,100,100,200])
        with Session() as s:
            for p in s.query(PagamentoBoleto).order_by(PagamentoBoleto.id.desc()).all():
                b=s.get(Boleto,p.boleto_id); cli=s.get(Cliente,b.cliente_id) if b else None
                tree.insert("","end",values=(p.id,p.boleto_id,cli.nome if cli else "—",
                    f"R$ {float(p.valor_pago):,.2f}",p.data_pagamento.strftime("%d/%m/%Y"),
                    p.canal or "—",p.comprovante or "—"))

    # ── RELATÓRIO ────────────────────────────
    def mostrar_relatorio(self):
        self._limpar(); self._ativar("Relatório")
        self._titulo("Relatório Financeiro")
        with Session() as s:
            q=s.query(Boleto)
            if self.empresa_id: q=q.filter_by(empresa_id=self.empresa_id)
            tot=q.count(); pen=q.filter_by(status="PENDENTE").count()
            pag=q.filter_by(status="PAGO").count(); vec=q.filter_by(status="VENCIDO").count()
            can=q.filter_by(status="CANCELADO").count()
            vp=float(s.query(_soma(Boleto.valor)).filter_by(status="PENDENTE").scalar() or 0)
            vg=float(s.query(_soma(Boleto.valor)).filter_by(status="PAGO").scalar() or 0)
            vv=float(s.query(_soma(Boleto.valor)).filter_by(status="VENCIDO").scalar() or 0)
            qc=s.query(Cliente)
            if self.empresa_id: qc=qc.filter_by(empresa_id=self.empresa_id)
            cli_t=qc.count(); cli_a=qc.filter_by(ativo=True).count()

        fr=tk.Frame(self.area,bg=C("painel"),padx=24,pady=16)
        fr.pack(fill="x",padx=28,pady=8)
        tk.Label(fr,text="Resumo Geral",bg=C("painel"),fg=C("txt"),font=FT["subtit"]).pack(anchor="w",pady=(0,10))

        for lbl_t,val,cor in [
            ("Total de boletos:",str(tot),C("txt")),
            ("  Pendentes:",f"{pen} — R$ {vp:,.2f}",C("amarelo")),
            ("  Pagos:",f"{pag} — R$ {vg:,.2f}",C("verde")),
            ("  Vencidos:",f"{vec} — R$ {vv:,.2f}",C("vermelho")),
            ("  Cancelados:",str(can),C("txt2")),
            ("","",""),
            ("Total de clientes:",str(cli_t),C("txt")),
            ("Clientes ativos:",str(cli_a),C("verde")),
            ("","",""),
            ("Taxa de recebimento:",f"{(pag/tot*100 if tot else 0):.1f}%",C("verde")),
            ("A Receber:",f"R$ {vp:,.2f}",C("amarelo")),
            ("Recebido:",f"R$ {vg:,.2f}",C("verde")),
            ("Em atraso:",f"R$ {vv:,.2f}",C("vermelho")),
        ]:
            if not lbl_t: tk.Frame(fr,bg=C("card"),height=1).pack(fill="x",pady=5); continue
            row=tk.Frame(fr,bg=C("painel")); row.pack(fill="x",pady=1)
            tk.Label(row,text=lbl_t,bg=C("painel"),fg=C("txt2"),font=FT["normal"],width=26,anchor="w").pack(side="left")
            tk.Label(row,text=val,bg=C("painel"),fg=cor,font=("Segoe UI",10,"bold")).pack(side="left")

        fb=tk.Frame(self.area,bg=C("bg")); fb.pack(anchor="w",padx=28,pady=8)
        btn(fb,"📥 Exportar CSV",self._exportar,cor=C("verde"),w=18).pack(side="left",padx=(0,8))
        btn(fb,"💾 Backup",self._bkp_now,cor=C("azul"),w=14).pack(side="left")

    def _exportar(self):
        path=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV","*.csv")],
            initialfile=f"relatorio_{date.today().strftime('%Y%m%d')}.csv")
        if not path: return
        with Session() as s, open(path,"w",newline="",encoding="utf-8-sig") as f:
            w=csv.writer(f)
            w.writerow(["ID","Cliente","Valor","Emissão","Vencimento","Status","Linha"])
            q=s.query(Boleto)
            if self.empresa_id: q=q.filter_by(empresa_id=self.empresa_id)
            for b in q.order_by(Boleto.id).all():
                cli=s.get(Cliente,b.cliente_id)
                w.writerow([b.id,cli.nome if cli else "—",float(b.valor),
                             b.data_emissao.strftime("%d/%m/%Y") if b.data_emissao else "—",
                             b.data_vencimento.strftime("%d/%m/%Y"),b.status,b.linha_digitavel or "—"])
        messagebox.showinfo("Exportado",f"Salvo em:\n{path}")

    # ── NOTIFICAÇÕES ─────────────────────────
    def mostrar_notificacoes(self):
        self._limpar(); self._ativar("Notificações")
        self._titulo("Notificações")
        dias=int(Configuracao.get("notif_dias_antes","3"))
        boletos=NotifService.boletos_vencendo(dias)

        if not boletos:
            tk.Label(self.area,text=f"✔ Nenhum boleto vencendo nos próximos {dias} dias.",
                     bg=C("bg"),fg=C("verde"),font=FT["normal"]).pack(padx=28,pady=20,anchor="w")
        else:
            tk.Label(self.area,text=f"⚠️ {len(boletos)} boleto(s) vencendo nos próximos {dias} dias:",
                     bg=C("bg"),fg=C("amarelo"),font=FT["subtit"]).pack(padx=28,pady=(8,4),anchor="w")
            tree,_=_tree(self.area,("ID","Cliente","Valor","Vencimento","Dias","E-mail"),
                         altura=10,widths=[40,200,110,100,80,200])
            for b in boletos:
                tree.insert("","end",values=(b["id"],b["cliente"],f"R$ {b['valor']:,.2f}",
                    b["vencimento"].strftime("%d/%m/%Y"),f"{b['dias']} dia(s)",b["email"] or "—"))
            fb=tk.Frame(self.area,bg=C("bg")); fb.pack(anchor="w",padx=28,pady=8)
            btn(fb,"📧 Enviar Lembretes",self._lembretes,cor=C("azul"),w=20).pack(side="left")

        fc=tk.Frame(self.area,bg=C("painel"),padx=16,pady=12)
        fc.pack(fill="x",padx=28,pady=8)
        tk.Label(fc,text="Notificar boletos vencendo em:",bg=C("painel"),fg=C("txt2"),font=FT["label"]).pack(side="left")
        vd=tk.StringVar(value=str(dias))
        tk.Entry(fc,textvariable=vd,bg=C("entry_bg"),fg=C("entry_fg"),font=FT["normal"],relief="flat",width=4).pack(side="left",padx=6)
        tk.Label(fc,text="dias",bg=C("painel"),fg=C("txt2"),font=FT["label"]).pack(side="left")
        btn(fc,"Salvar",lambda:Configuracao.set("notif_dias_antes",vd.get()) or
            messagebox.showinfo("Salvo","Configuração salva!"),cor=C("verde"),w=8).pack(side="left",padx=8)

    def _lembretes(self):
        n=NotifService.enviar_lembretes_automaticos()
        messagebox.showinfo("Lembretes",f"{n} lembrete(s) enviado(s).")

    # ── CONFIGURAÇÕES ────────────────────────
    def mostrar_configuracoes(self):
        self._limpar(); self._ativar("Configurações")
        self._titulo("Configurações")
        nb=ttk.Notebook(self.area); nb.pack(fill="both",expand=True,padx=28,pady=8)

        # Sistema
        f_sis=tk.Frame(nb,bg=C("painel"),padx=24,pady=16); nb.add(f_sis,text="⚙️ Sistema")
        for i in range(4): f_sis.columnconfigure(i,weight=1)
        tk.Label(f_sis,text="Configurações do Sistema",bg=C("painel"),fg=C("txt"),font=FT["subtit"]).grid(row=0,column=0,columnspan=4,sticky="w",pady=(0,10))
        vnome=campo(f_sis,"Nome do Sistema",1,0); vnome.set(Configuracao.get("nome_sistema","Sistema de Boletos"))
        tk.Label(f_sis,text="Tema",bg=C("painel"),fg=C("txt2"),font=FT["label"]).grid(row=2,column=0,sticky="w",pady=3)
        vtema=tk.StringVar(value=Configuracao.get("tema","escuro"))
        ttk.Combobox(f_sis,textvariable=vtema,values=["escuro","claro"],font=FT["normal"],width=22,state="readonly").grid(row=2,column=1,sticky="ew",padx=(0,12),pady=3)
        def _s_sis(): Configuracao.set("nome_sistema",vnome.get()); Configuracao.set("tema",vtema.get()); messagebox.showinfo("Salvo","Reinicie o app para aplicar o tema.")
        btn(f_sis,"💾 Salvar",_s_sis,w=16).grid(row=4,column=0,columnspan=2,pady=14,sticky="w")

        # Empresa
        f_emp=tk.Frame(nb,bg=C("painel"),padx=24,pady=16); nb.add(f_emp,text="🏢 Empresa")
        for i in range(4): f_emp.columnconfigure(i,weight=1)
        tk.Label(f_emp,text="Dados da Empresa",bg=C("painel"),fg=C("txt"),font=FT["subtit"]).grid(row=0,column=0,columnspan=4,sticky="w",pady=(0,10))
        ve_rs=campo(f_emp,"Razão Social",1,0); ve_fn=campo(f_emp,"Nome Fantasia",2,0)
        ve_cnpj=campo(f_emp,"CNPJ",3,0,fn_mask=_fmt_cnpj); ve_em=campo(f_emp,"E-mail",4,0)
        ve_tel=campo(f_emp,"Telefone",5,0,fn_mask=_fmt_tel); ve_log=campo(f_emp,"Logradouro",6,0)
        ve_num=campo(f_emp,"Número",6,1); ve_bai=campo(f_emp,"Bairro",7,0)
        ve_cid=campo(f_emp,"Cidade",7,1); ve_uf=campo(f_emp,"UF",8,0)
        ve_cep=campo(f_emp,"CEP",8,1,fn_mask=_fmt_cep)
        with Session() as s:
            e=s.query(Empresa).first()
            if e:
                ve_rs.set(e.razao_social or ""); ve_fn.set(e.nome_fantasia or "")
                ve_cnpj.set(e.cnpj or ""); ve_em.set(e.email or ""); ve_tel.set(e.telefone or "")
                ve_log.set(e.logradouro or ""); ve_num.set(e.numero or ""); ve_bai.set(e.bairro or "")
                ve_cid.set(e.cidade or ""); ve_uf.set(e.uf or ""); ve_cep.set(e.cep or "")
        def _s_emp():
            with Session() as s:
                e=s.query(Empresa).first()
                if not e: e=Empresa(); s.add(e)
                e.razao_social=ve_rs.get(); e.nome_fantasia=ve_fn.get(); e.cnpj=ve_cnpj.get()
                e.email=ve_em.get(); e.telefone=ve_tel.get(); e.logradouro=ve_log.get()
                e.numero=ve_num.get(); e.bairro=ve_bai.get(); e.cidade=ve_cid.get()
                e.uf=ve_uf.get(); e.cep=ve_cep.get(); s.commit()
            messagebox.showinfo("Salvo","Empresa salva!")
        btn(f_emp,"💾 Salvar",_s_emp,w=16).grid(row=9,column=0,columnspan=2,pady=14,sticky="w")

        # Conta
        f_ban=tk.Frame(nb,bg=C("painel"),padx=24,pady=16); nb.add(f_ban,text="🏦 Conta")
        for i in range(4): f_ban.columnconfigure(i,weight=1)
        tk.Label(f_ban,text="Conta Bancária",bg=C("painel"),fg=C("txt"),font=FT["subtit"]).grid(row=0,column=0,columnspan=4,sticky="w",pady=(0,10))
        vb_bco=campo(f_ban,"Banco",1,0); vb_cod=campo(f_ban,"Código",2,0)
        vb_ag=campo(f_ban,"Agência",3,0); vb_cc=campo(f_ban,"Conta",4,0); vb_car=campo(f_ban,"Carteira",5,0)
        with Session() as s:
            ct=s.query(ContaBancaria).first()
            if ct: vb_bco.set(ct.banco or ""); vb_cod.set(ct.codigo_banco or ""); vb_ag.set(ct.agencia or ""); vb_cc.set(ct.conta or ""); vb_car.set(ct.carteira or "")
        def _s_ban():
            with Session() as s:
                emp=s.query(Empresa).first()
                if not emp: messagebox.showerror("Erro","Salve a empresa primeiro."); return
                ct=s.query(ContaBancaria).first()
                if not ct: ct=ContaBancaria(); ct.empresa_id=emp.id; s.add(ct)
                ct.banco=vb_bco.get(); ct.codigo_banco=vb_cod.get(); ct.agencia=vb_ag.get(); ct.conta=vb_cc.get(); ct.carteira=vb_car.get(); s.commit()
            messagebox.showinfo("Salvo","Conta salva!")
        btn(f_ban,"💾 Salvar",_s_ban,w=16).grid(row=6,column=0,columnspan=2,pady=14,sticky="w")

        # E-mail
        f_em=tk.Frame(nb,bg=C("painel"),padx=24,pady=16); nb.add(f_em,text="📧 E-mail")
        for i in range(4): f_em.columnconfigure(i,weight=1)
        tk.Label(f_em,text="Configurações SMTP",bg=C("painel"),fg=C("txt"),font=FT["subtit"]).grid(row=0,column=0,columnspan=4,sticky="w",pady=(0,10))
        vm_h=campo(f_em,"Servidor",1,0); vm_p=campo(f_em,"Porta",2,0)
        vm_u=campo(f_em,"Usuário",3,0); vm_s=campo(f_em,"Senha",4,0)
        vm_r=campo(f_em,"Remetente",5,0)
        vm_h.set(Configuracao.get("smtp_host","smtp.gmail.com")); vm_p.set(Configuracao.get("smtp_porta","587"))
        vm_u.set(Configuracao.get("smtp_usuario","")); vm_s.set(Configuracao.get("smtp_senha",""))
        vm_r.set(Configuracao.get("smtp_remetente",""))
        def _s_em():
            for k,v in [("smtp_host",vm_h),("smtp_porta",vm_p),("smtp_usuario",vm_u),
                        ("smtp_senha",vm_s),("smtp_remetente",vm_r)]: Configuracao.set(k,v.get())
            messagebox.showinfo("Salvo","Configurações de e-mail salvas!")
        def _test_em():
            ok,msg=EmailService.testar_smtp()
            messagebox.showinfo("SMTP",msg) if ok else messagebox.showerror("Erro",msg)
        fb_em=tk.Frame(f_em,bg=C("painel")); fb_em.grid(row=6,column=0,columnspan=4,pady=14,sticky="w")
        btn(fb_em,"💾 Salvar",_s_em,w=14).pack(side="left",padx=(0,8))
        btn(fb_em,"🔌 Testar",_test_em,cor=C("azul"),w=14).pack(side="left")

        # Usuários
        f_usr=tk.Frame(nb,bg=C("painel"),padx=24,pady=16); nb.add(f_usr,text="👥 Usuários")
        tk.Label(f_usr,text="Usuários do Sistema",bg=C("painel"),fg=C("txt"),font=FT["subtit"]).pack(anchor="w",pady=(0,10))
        cols=("ID","Nome","E-mail","Perfil","Status","Último Login")
        tree_u=ttk.Treeview(f_usr,columns=cols,show="headings",height=6)
        for c in cols: tree_u.heading(c,text=c); tree_u.column(c,width=130,anchor="w")
        tree_u.column("ID",width=40); tree_u.pack(fill="x",pady=(0,10))

        def _load_u():
            tree_u.delete(*tree_u.get_children())
            with Session() as s:
                for u in s.query(Usuario).all():
                    ul=u.ultimo_login.strftime("%d/%m/%Y %H:%M") if u.ultimo_login else "—"
                    tree_u.insert("","end",iid=str(u.id),values=(u.id,u.nome,u.email,u.perfil,"Ativo" if u.ativo else "Inativo",ul))
        _load_u()

        f_nu=tk.Frame(f_usr,bg=C("painel")); f_nu.pack(anchor="w",pady=4)
        vu_n=tk.StringVar(); vu_e=tk.StringVar(); vu_s=tk.StringVar(); vp=tk.StringVar(value="operador")
        for lbl_t,var,w,show in [("Nome",vu_n,14,""),("E-mail",vu_e,20,""),("Senha",vu_s,14,"●")]:
            tk.Label(f_nu,text=lbl_t,bg=C("painel"),fg=C("txt2"),font=FT["label"]).pack(side="left")
            tk.Entry(f_nu,textvariable=var,bg=C("entry_bg"),fg=C("entry_fg"),font=FT["normal"],relief="flat",width=w,show=show).pack(side="left",padx=4)
        ttk.Combobox(f_nu,textvariable=vp,values=["admin","operador","visualizador"],width=14,state="readonly").pack(side="left",padx=4)
        def _add_u():
            try:
                u=Usuario(nome=vu_n.get(),email=vu_e.get(),senha=vu_s.get(),perfil=vp.get())
                with Session() as s: s.add(u); s.commit()
                messagebox.showinfo("Sucesso","Usuário criado!"); _load_u()
            except Exception as ex: messagebox.showerror("Erro",str(ex))
        btn(f_nu,"➕ Adicionar",_add_u,w=12).pack(side="left",padx=6)

        # Backup
        f_bkp=tk.Frame(nb,bg=C("painel"),padx=24,pady=16); nb.add(f_bkp,text="💾 Backup")
        tk.Label(f_bkp,text="Gerenciamento de Backup",bg=C("painel"),fg=C("txt"),font=FT["subtit"]).pack(anchor="w",pady=(0,10))
        v_auto=tk.BooleanVar(value=Configuracao.get("backup_automatico","true")=="true")
        tk.Checkbutton(f_bkp,text="Backup automático diário",variable=v_auto,bg=C("painel"),fg=C("txt"),selectcolor=C("card"),activebackground=C("painel"),font=FT["normal"]).pack(anchor="w")
        cols_b=("Arquivo","Tamanho")
        tree_b=ttk.Treeview(f_bkp,columns=cols_b,show="headings",height=8)
        for c in cols_b: tree_b.heading(c,text=c); tree_b.column(c,width=200,anchor="w")
        tree_b.pack(fill="x",pady=10)
        def _load_b():
            tree_b.delete(*tree_b.get_children())
            for arq in BackupService.listar_backups():
                p=os.path.join(BackupService.PASTA,arq)
                tree_b.insert("","end",values=(arq,f"{os.path.getsize(p)/1024:.1f} KB"))
        _load_b()
        def _do_b():
            Configuracao.set("backup_automatico","true" if v_auto.get() else "false")
            ok,msg=BackupService.fazer_backup()
            messagebox.showinfo("Backup",msg) if ok else messagebox.showerror("Erro",msg); _load_b()
        def _rest():
            sel=tree_b.selection()
            if not sel: messagebox.showwarning("Atenção","Selecione um backup."); return
            arq=tree_b.item(sel[0])["values"][0]
            if not messagebox.askyesno("Confirmar",f"Restaurar '{arq}'?"): return
            ok,msg=BackupService.restaurar(arq)
            messagebox.showinfo("OK",msg) if ok else messagebox.showerror("Erro",msg)
        fb_b=tk.Frame(f_bkp,bg=C("painel")); fb_b.pack(anchor="w",pady=6)
        btn(fb_b,"💾 Fazer Backup",_do_b,cor=C("verde"),w=18).pack(side="left",padx=(0,8))
        btn(fb_b,"♻️ Restaurar",_rest,cor=C("cinza"),w=14).pack(side="left")

# ─────────────────────────────────────────────
# INICIAR
# ─────────────────────────────────────────────
if __name__=="__main__":
    inicializar()
    if not _API_KEY:
        root=tk.Tk(); root.withdraw()
        messagebox.showerror("Configuração","Configure ASAAS_API_KEY no .env antes de continuar.")
        root.destroy()
    else:
        login=TelaLogin(); login.mainloop()
        if login.usuario_logado:
            App(login.usuario_logado).mainloop()
