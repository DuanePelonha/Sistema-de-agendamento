import os
import csv
import sqlite3
import smtplib
from io import StringIO
from datetime import datetime
from email.mime.text import MIMEText
from flask import Flask, render_template, request, redirect, session, jsonify, Response

app = Flask(__name__)
app.secret_key = "agendamento_advogados_2026_sistema"

LIMITE_MENSAL = 20
LIMITE_CANCELAMENTO_HORAS = 2

ADMIN_EMAIL = "admin@casadaadvocacia.com"
ADMIN_SENHA = "admin123"

EMAIL_REMETENTE = os.environ.get("EMAIL_REMETENTE")
EMAIL_SENHA_APP = os.environ.get("EMAIL_SENHA_APP")

LIMITES_SALAS = {
    "Coworking": 180,
    "Sala de Reunião": 120,
    "Escritório 01": 120,
    "Escritório 02": 120,
    "Sala de Audiência": 180,
    "Auditório": 300
}


def conectar():
    return sqlite3.connect("banco.db")


def enviar_email(destinatario, assunto, mensagem):
    if not EMAIL_REMETENTE or not EMAIL_SENHA_APP:
        print("Email não configurado.")
        return

    try:
        msg = MIMEText(mensagem, "plain", "utf-8")
        msg["Subject"] = assunto
        msg["From"] = EMAIL_REMETENTE
        msg["To"] = destinatario

        with smtplib.SMTP("smtp.gmail.com", 587) as servidor:
            servidor.starttls()
            servidor.login(EMAIL_REMETENTE, EMAIL_SENHA_APP)
            servidor.send_message(msg)

    except Exception as e:
        print("Erro ao enviar email:", e)


def inicializar_banco():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS advogados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL,
        oab TEXT NOT NULL,
        estado TEXT NOT NULL,
        cidade TEXT NOT NULL,
        telefone TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS salas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agendamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        advogado_id INTEGER NOT NULL,
        sala_id INTEGER NOT NULL,
        data_inicio TEXT NOT NULL,
        data_fim TEXT NOT NULL,
        status TEXT DEFAULT 'ativo',
        confirmado TEXT DEFAULT 'nao',
        aviso_enviado TEXT DEFAULT 'nao'
    )
    """)

    for coluna in ["confirmado", "aviso_enviado"]:
        try:
            cursor.execute(f"ALTER TABLE agendamentos ADD COLUMN {coluna} TEXT DEFAULT 'nao'")
        except sqlite3.OperationalError:
            pass

    criar_salas_padrao(cursor)

    conn.commit()
    conn.close()


def criar_salas_padrao(cursor):
    cursor.execute("SELECT COUNT(*) FROM salas")
    total = cursor.fetchone()[0]

    if total == 0:
        salas = [(f"Coworking {i:02d}",) for i in range(1, 11)]
        salas += [
            ("Sala de Reunião",),
            ("Escritório 01",),
            ("Escritório 02",),
            ("Sala de Audiência",),
            ("Auditório",)
        ]

        cursor.executemany("INSERT INTO salas (nome) VALUES (?)", salas)


def verificar_confirmacoes():
    agora = datetime.now()
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, data_inicio, confirmado, aviso_enviado
        FROM agendamentos
        WHERE status = 'ativo'
    """)

    agendamentos = cursor.fetchall()

    for ag in agendamentos:
        ag_id, data_inicio, confirmado, aviso_enviado = ag
        inicio = datetime.fromisoformat(data_inicio)

        minutos_para_inicio = (inicio - agora).total_seconds() / 60
        minutos_apos_inicio = (agora - inicio).total_seconds() / 60

        if 0 <= minutos_para_inicio <= 15 and aviso_enviado == "nao":
            cursor.execute("""
                UPDATE agendamentos
                SET aviso_enviado = 'sim'
                WHERE id = ?
            """, (ag_id,))

        if minutos_apos_inicio > 15 and confirmado != "sim":
            cursor.execute("""
                UPDATE agendamentos
                SET status = 'cancelado'
                WHERE id = ?
            """, (ag_id,))

    conn.commit()
    conn.close()


@app.before_request
def before_request():
    verificar_confirmacoes()


def verificar_limite_mensal(advogado_id, data_referencia):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM agendamentos
        WHERE advogado_id = ?
        AND strftime('%m', data_inicio) = ?
        AND strftime('%Y', data_inicio) = ?
        AND status = 'ativo'
    """, (
        advogado_id,
        data_referencia.strftime("%m"),
        data_referencia.strftime("%Y")
    ))

    total = cursor.fetchone()[0]
    conn.close()

    return total < LIMITE_MENSAL


def verificar_agendamento_dia(advogado_id, data_referencia):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM agendamentos
        WHERE advogado_id = ?
        AND date(data_inicio) = ?
        AND status = 'ativo'
    """, (
        advogado_id,
        data_referencia.strftime("%Y-%m-%d")
    ))

    total = cursor.fetchone()[0]
    conn.close()

    return total == 0


def verificar_conflito_horario(sala_id, inicio, fim):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM agendamentos
        WHERE sala_id = ?
        AND status = 'ativo'
        AND (
            (data_inicio < ? AND data_fim > ?)
            OR
            (data_inicio >= ? AND data_inicio < ?)
        )
    """, (sala_id, fim, inicio, inicio, fim))

    conflito = cursor.fetchone()[0] > 0
    conn.close()

    return conflito


def validar_tempo_sala(nome_sala, inicio_dt, fim_dt):
    duracao = (fim_dt - inicio_dt).total_seconds() / 60

    for chave, limite in LIMITES_SALAS.items():
        if chave in nome_sala:
            return duracao <= limite

    return True


@app.route("/")
def home():
    if "usuario_id" not in session:
        return redirect("/login-page")

    return render_template("index.html")


@app.route("/login-page")
def login_page():
    return render_template("login.html")


@app.route("/cadastro-page")
def cadastro_page():
    return render_template("cadastro.html")


@app.route("/cadastro", methods=["POST"])
def cadastro():
    nome = request.form["nome"].strip()
    email = request.form["email"].strip().lower()
    senha = request.form["senha"].strip()
    oab = request.form["oab"].strip()
    estado = request.form["estado"].strip().upper()
    cidade = request.form["cidade"].strip()
    telefone = request.form["telefone"].strip()

    conn = conectar()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO advogados
            (nome, email, senha, oab, estado, cidade, telefone)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (nome, email, senha, oab, estado, cidade, telefone))

        conn.commit()

    except sqlite3.IntegrityError:
        conn.close()
        return "<script>alert('Email já cadastrado'); window.location='/cadastro-page';</script>"

    conn.close()
    return "<script>alert('Cadastro realizado com sucesso!'); window.location='/login-page';</script>"


@app.route("/login", methods=["POST"])
def login():
    email = request.form["email"].strip().lower()
    senha = request.form["senha"].strip()

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, nome, oab, estado
        FROM advogados
        WHERE email = ? AND senha = ?
    """, (email, senha))

    usuario = cursor.fetchone()
    conn.close()

    if usuario:
        session["usuario_id"] = usuario[0]
        session["nome"] = usuario[1]
        session["oab"] = usuario[2]
        session["estado"] = usuario[3]
        return redirect("/")

    return "<script>alert('Login inválido. Verifique email e senha.'); window.location='/login-page';</script>"


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login-page")


@app.route("/usuario")
def usuario():
    if "usuario_id" not in session:
        return jsonify({"erro": "Não autenticado"}), 401

    return jsonify({
        "nome": session.get("nome"),
        "oab": session.get("oab"),
        "estado": session.get("estado")
    })


@app.route("/salas")
def listar_salas():
    conn = conectar()
    cursor = conn.cursor()

    criar_salas_padrao(cursor)
    conn.commit()

    cursor.execute("SELECT id, nome FROM salas ORDER BY id")
    salas = cursor.fetchall()

    conn.close()
    return jsonify(salas)


@app.route("/corrigir-salas")
def corrigir_salas():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM salas")

    salas = [(f"Coworking {i:02d}",) for i in range(1, 11)]
    salas += [
        ("Sala de Reunião",),
        ("Escritório 01",),
        ("Escritório 02",),
        ("Sala de Audiência",),
        ("Auditório",)
    ]

    cursor.executemany("INSERT INTO salas (nome) VALUES (?)", salas)

    conn.commit()
    conn.close()

    return "Salas criadas com sucesso!"


@app.route("/contador")
def contador():
    if "usuario_id" not in session:
        return jsonify({"erro": "Não autenticado"}), 401

    advogado_id = session["usuario_id"]
    hoje = datetime.now()

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM agendamentos
        WHERE advogado_id = ?
        AND strftime('%m', data_inicio) = ?
        AND strftime('%Y', data_inicio) = ?
        AND status = 'ativo'
    """, (
        advogado_id,
        hoje.strftime("%m"),
        hoje.strftime("%Y")
    ))

    usados = cursor.fetchone()[0]
    conn.close()

    return jsonify({
        "usados": usados,
        "limite": LIMITE_MENSAL,
        "restantes": max(0, LIMITE_MENSAL - usados)
    })


@app.route("/agendamentos")
def listar_agendamentos():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            ag.id,
            s.nome,
            ag.data_inicio,
            ag.data_fim,
            ag.confirmado
        FROM agendamentos ag
        JOIN salas s ON s.id = ag.sala_id
        WHERE ag.status = 'ativo'
    """)

    dados = cursor.fetchall()
    conn.close()

    eventos = []

    for item in dados:
        titulo = f"{item[1]} - Ocupado"

        if item[4] == "sim":
            titulo += " ✅ Confirmado"
        else:
            titulo += " ⚠️ Aguardando confirmação"

        eventos.append({
            "id": item[0],
            "title": titulo,
            "start": item[2],
            "end": item[3],
            "color": "#d13438"
        })

    return jsonify(eventos)


@app.route("/agendar", methods=["POST"])
def agendar():
    if "usuario_id" not in session:
        return jsonify({"erro": "Não autenticado"}), 401

    dados = request.get_json()

    advogado_id = session["usuario_id"]
    sala_id = dados.get("sala_id")
    data_inicio = dados.get("data_inicio")
    data_fim = dados.get("data_fim")

    if not sala_id or not data_inicio or not data_fim:
        return jsonify({"erro": "Preencha todos os campos"}), 400

    inicio_dt = datetime.fromisoformat(data_inicio)
    fim_dt = datetime.fromisoformat(data_fim)

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT nome FROM salas WHERE id = ?", (sala_id,))
    sala = cursor.fetchone()

    if not sala:
        conn.close()
        return jsonify({"erro": "Sala não encontrada"}), 404

    nome_sala = sala[0]

    if not verificar_agendamento_dia(advogado_id, inicio_dt):
        conn.close()
        return jsonify({"erro": "Você já possui um agendamento neste dia"}), 400

    if not validar_tempo_sala(nome_sala, inicio_dt, fim_dt):
        conn.close()
        return jsonify({"erro": f"Tempo máximo excedido para {nome_sala}"}), 400

    if not verificar_limite_mensal(advogado_id, inicio_dt):
        conn.close()
        return jsonify({"erro": "Limite mensal atingido"}), 400

    if verificar_conflito_horario(sala_id, data_inicio, data_fim):
        conn.close()
        return jsonify({"erro": "Sala já ocupada nesse horário"}), 400

    cursor.execute("""
        INSERT INTO agendamentos
        (advogado_id, sala_id, data_inicio, data_fim, status, confirmado, aviso_enviado)
        VALUES (?, ?, ?, ?, 'ativo', 'nao', 'nao')
    """, (advogado_id, sala_id, data_inicio, data_fim))

    conn.commit()

    cursor.execute("SELECT nome, email FROM advogados WHERE id = ?", (advogado_id,))
    advogado = cursor.fetchone()

    mensagem = f"""
Olá, Dr(a). {advogado[0]}.

Seu agendamento foi confirmado.

Sala: {nome_sala}
Início: {data_inicio}
Fim: {data_fim}

Você receberá aviso 15 minutos antes.
Caso não confirme presença até 15 minutos após o horário agendado, o agendamento poderá ser cancelado automaticamente.

Casa da Advocacia Hélio Xavier de Vasconcelos
"""

    enviar_email(advogado[1], "Confirmação de Agendamento", mensagem)

    conn.close()

    return jsonify({"mensagem": "✅ Agendamento confirmado com sucesso!"})


@app.route("/confirmar-agendamento/<int:id>", methods=["POST"])
def confirmar_agendamento(id):
    if "usuario_id" not in session:
        return jsonify({"erro": "Não autenticado"}), 401

    advogado_id = session["usuario_id"]

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT advogado_id, status
        FROM agendamentos
        WHERE id = ?
    """, (id,))

    agendamento = cursor.fetchone()

    if not agendamento:
        conn.close()
        return jsonify({"erro": "Agendamento não encontrado"}), 404

    if agendamento[0] != advogado_id:
        conn.close()
        return jsonify({"erro": "Você não pode confirmar este agendamento"}), 403

    if agendamento[1] != "ativo":
        conn.close()
        return jsonify({"erro": "Este agendamento não está ativo"}), 400

    cursor.execute("""
        UPDATE agendamentos
        SET confirmado = 'sim'
        WHERE id = ?
    """, (id,))

    conn.commit()
    conn.close()

    return jsonify({"mensagem": "Presença confirmada com sucesso!"})


@app.route("/cancelar-agendamento/<int:id>", methods=["POST"])
def cancelar_agendamento(id):
    if "usuario_id" not in session:
        return jsonify({"erro": "Não autenticado"}), 401

    advogado_id = session["usuario_id"]

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            ag.advogado_id,
            ag.data_inicio,
            ag.status,
            adv.nome,
            adv.email,
            s.nome,
            ag.data_fim
        FROM agendamentos ag
        JOIN advogados adv ON adv.id = ag.advogado_id
        JOIN salas s ON s.id = ag.sala_id
        WHERE ag.id = ?
    """, (id,))

    agendamento = cursor.fetchone()

    if not agendamento:
        conn.close()
        return jsonify({"erro": "Agendamento não encontrado"}), 404

    if agendamento[0] != advogado_id:
        conn.close()
        return jsonify({"erro": "Você não pode cancelar este agendamento"}), 403

    if agendamento[2] != "ativo":
        conn.close()
        return jsonify({"erro": "Este agendamento já foi cancelado"}), 400

    inicio = datetime.fromisoformat(agendamento[1])
    horas_restantes = (inicio - datetime.now()).total_seconds() / 3600

    if horas_restantes < LIMITE_CANCELAMENTO_HORAS:
        conn.close()
        return jsonify({
            "erro": f"Cancelamento bloqueado. Só é permitido cancelar com pelo menos {LIMITE_CANCELAMENTO_HORAS} horas de antecedência."
        }), 400

    cursor.execute("""
        UPDATE agendamentos
        SET status = 'cancelado'
        WHERE id = ?
    """, (id,))

    conn.commit()

    mensagem = f"""
Olá, Dr(a). {agendamento[3]}.

Seu agendamento foi cancelado.

Sala: {agendamento[5]}
Início: {agendamento[1]}
Fim: {agendamento[6]}

Casa da Advocacia Hélio Xavier de Vasconcelos
"""

    enviar_email(agendamento[4], "Cancelamento de Agendamento", mensagem)

    conn.close()

    return jsonify({"mensagem": "Agendamento cancelado com sucesso!"})


@app.route("/admin-login-page")
def admin_login_page():
    return render_template("admin_login.html")


@app.route("/admin-login", methods=["POST"])
def admin_login():
    email = request.form["email"].strip().lower()
    senha = request.form["senha"].strip()

    if email == ADMIN_EMAIL and senha == ADMIN_SENHA:
        session["admin"] = True
        return redirect("/admin")

    return "<script>alert('Credenciais de administrador inválidas'); window.location='/admin-login-page';</script>"


@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/admin-login-page")

    return render_template("admin.html")


@app.route("/admin/agendamentos")
def admin_agendamentos():
    if not session.get("admin"):
        return jsonify({"erro": "Não autorizado"}), 403

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            ag.id,
            adv.nome,
            adv.oab,
            adv.estado,
            s.nome,
            ag.data_inicio,
            ag.data_fim,
            ag.status
        FROM agendamentos ag
        JOIN advogados adv ON adv.id = ag.advogado_id
        JOIN salas s ON s.id = ag.sala_id
        ORDER BY ag.data_inicio DESC
    """)

    dados = cursor.fetchall()
    conn.close()

    return jsonify(dados)


@app.route("/admin/cancelar/<int:id>", methods=["POST"])
def admin_cancelar(id):
    if not session.get("admin"):
        return jsonify({"erro": "Não autorizado"}), 403

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE agendamentos
        SET status = 'cancelado'
        WHERE id = ?
    """, (id,))

    conn.commit()
    conn.close()

    return jsonify({"mensagem": "Agendamento cancelado pelo administrador!"})


@app.route("/admin/exportar")
def admin_exportar():
    if not session.get("admin"):
        return redirect("/admin-login-page")

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            ag.id,
            adv.nome,
            adv.oab,
            adv.estado,
            s.nome,
            ag.data_inicio,
            ag.data_fim,
            ag.status
        FROM agendamentos ag
        JOIN advogados adv ON adv.id = ag.advogado_id
        JOIN salas s ON s.id = ag.sala_id
        ORDER BY ag.data_inicio DESC
    """)

    dados = cursor.fetchall()
    conn.close()

    output = StringIO()
    writer = csv.writer(output, delimiter=';')

    writer.writerow(["ID", "Advogado", "OAB", "Estado", "Sala", "Início", "Fim", "Status"])
    writer.writerows(dados)

    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=agendamentos.csv"

    return response


@app.route("/admin-logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/admin-login-page")


if __name__ == "__main__":
    inicializar_banco()
    app.run(host="0.0.0.0", port=10000)