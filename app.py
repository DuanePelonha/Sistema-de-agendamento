import sqlite3
import csv
import smtplib
from io import StringIO
from datetime import datetime
from email.mime.text import MIMEText
from flask import Flask, render_template, request, redirect, session, jsonify, Response

app = Flask(__name__)
app.secret_key = "agendamento_advogados_2026_sistema"

# CONFIGURAÇÕES
LIMITE_MENSAL = 20
LIMITE_CANCELAMENTO_HORAS = 2

ADMIN_EMAIL = "admin@casadaadvocacia.com"
ADMIN_SENHA = "admin123"

EMAIL_REMETENTE = "duanepatrick00@gmail.com"
EMAIL_SENHA_APP = "DuPel@1985."

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
        nome TEXT,
        email TEXT UNIQUE,
        senha TEXT,
        oab TEXT,
        estado TEXT,
        cidade TEXT,
        telefone TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS salas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agendamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        advogado_id INTEGER,
        sala_id INTEGER,
        data_inicio TEXT,
        data_fim TEXT,
        status TEXT DEFAULT 'ativo',
        confirmado TEXT DEFAULT 'nao',
        aviso_enviado TEXT DEFAULT 'nao'
    )
    """)

    cursor.execute("SELECT COUNT(*) FROM salas")
    if cursor.fetchone()[0] == 0:
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

def verificar_confirmacoes():
    agora = datetime.now()
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, data_inicio, confirmado, aviso_enviado
        FROM agendamentos
        WHERE status = 'ativo'
    """)

    for ag in cursor.fetchall():
        ag_id, data_inicio, confirmado, aviso = ag
        inicio = datetime.fromisoformat(data_inicio)

        min_antes = (inicio - agora).total_seconds() / 60
        min_depois = (agora - inicio).total_seconds() / 60

        if 0 <= min_antes <= 15 and aviso == "nao":
            cursor.execute("UPDATE agendamentos SET aviso_enviado='sim' WHERE id=?", (ag_id,))

        if min_depois > 15 and confirmado != "sim":
            cursor.execute("UPDATE agendamentos SET status='cancelado' WHERE id=?", (ag_id,))

    conn.commit()
    conn.close()

@app.before_request
def before():
    verificar_confirmacoes()

# ROTAS

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
    conn = conectar()
    cursor = conn.cursor()

    try:
        cursor.execute("""
        INSERT INTO advogados (nome,email,senha,oab,estado,cidade,telefone)
        VALUES (?,?,?,?,?,?,?)
        """, (
            request.form["nome"],
            request.form["email"],
            request.form["senha"],
            request.form["oab"],
            request.form["estado"],
            request.form["cidade"],
            request.form["telefone"]
        ))
        conn.commit()
    except:
        return "Email já cadastrado"

    conn.close()
    return redirect("/login-page")

@app.route("/login", methods=["POST"])
def login():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM advogados WHERE email=? AND senha=?",
                   (request.form["email"], request.form["senha"]))

    user = cursor.fetchone()
    conn.close()

    if user:
        session["usuario_id"] = user[0]
        session["nome"] = user[1]
        session["oab"] = user[4]
        session["estado"] = user[5]
        return redirect("/")

    return "Login inválido"

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login-page")

@app.route("/agendar", methods=["POST"])
def agendar():
    dados = request.get_json()
    advogado_id = session["usuario_id"]

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO agendamentos
    (advogado_id,sala_id,data_inicio,data_fim)
    VALUES (?,?,?,?)
    """, (advogado_id, dados["sala_id"], dados["data_inicio"], dados["data_fim"]))

    conn.commit()
    

    # EMAIL
    cursor.execute("SELECT nome,email FROM advogados WHERE id=?", (advogado_id,))
    adv = cursor.fetchone()

    cursor.execute("SELECT nome FROM salas WHERE id=?", (dados["sala_id"],))
    sala = cursor.fetchone()

    enviar_email(
        adv[1],
        "Confirmação de Agendamento",
        f"{adv[0]}, seu agendamento foi confirmado na sala {sala[0]}"
    )

    conn.close()

    return jsonify({"mensagem": "Agendamento realizado!"})

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
        "restantes": LIMITE_MENSAL - usados
    })

@app.route("/cancelar-agendamento/<int:id>", methods=["POST"])
def cancelar(id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT adv.nome, adv.email, s.nome, ag.data_inicio, ag.data_fim
    FROM agendamentos ag
    JOIN advogados adv ON adv.id=ag.advogado_id
    JOIN salas s ON s.id=ag.sala_id
    WHERE ag.id=?
    """, (id,))

    dados = cursor.fetchone()

    cursor.execute("UPDATE agendamentos SET status='cancelado' WHERE id=?", (id,))
    conn.commit()

    if dados:
        enviar_email(
            dados[1],
            "Cancelamento",
            f"{dados[0]}, seu agendamento foi cancelado na sala {dados[2]}"
        )

    conn.close()
    return jsonify({"mensagem": "Cancelado!"})

@app.route("/confirmar-agendamento/<int:id>", methods=["POST"])
def confirmar(id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("UPDATE agendamentos SET confirmado='sim' WHERE id=?", (id,))
    conn.commit()
    conn.close()

    return jsonify({"mensagem": "Confirmado!"})

@app.route("/agendamentos")
def lista():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT ag.id,s.nome,ag.data_inicio,ag.data_fim
    FROM agendamentos ag
    JOIN salas s ON s.id=ag.sala_id
    WHERE ag.status='ativo'
    """)

    eventos = []
    for i in cursor.fetchall():
        eventos.append({
            "id": i[0],
            "title": i[1],
            "start": i[2],
            "end": i[3]
        })

    conn.close()
    return jsonify(eventos)

@app.route("/corrigir-salas")
def corrigir_salas():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM salas")

    salas = [(f"Coworking {i:02d}",) for i in range(1, 8)]
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

    return "Salas corrigidas com sucesso!"

@app.route("/usuario")
def usuario():
    if "usuario_id" not in session:
        return jsonify({"erro": "Não autenticado"}), 401

    return jsonify({
        "nome": session.get("nome"),
        "oab": session.get("oab"),
        "estado": session.get("estado")
    })

if __name__ == "__main__":
    inicializar_banco()
    app.run(debug=True)