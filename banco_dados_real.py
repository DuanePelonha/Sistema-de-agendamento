import sqlite3


def conectar():
    return sqlite3.connect("banco.db")


def criar_banco():
    conn = conectar()
    cursor = conn.cursor()

    # Tabela de advogados
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

    # Tabela de salas
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS salas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL
    )
    """)

    # Tabela de agendamentos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agendamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        advogado_id INTEGER NOT NULL,
        sala_id INTEGER NOT NULL,
        data_inicio TEXT NOT NULL,
        data_fim TEXT NOT NULL,
        status TEXT DEFAULT 'ativo',
        FOREIGN KEY (advogado_id) REFERENCES advogados(id),
        FOREIGN KEY (sala_id) REFERENCES salas(id)
        ALTER TABLE agendamentos ADD COLUMN confirmado TEXT DEFAULT 'nao';
        ALTER TABLE agendamentos ADD COLUMN aviso_enviado TEXT DEFAULT 'nao';
    )
    """)

    # Inserir salas padrão se ainda não existirem
    cursor.execute("SELECT COUNT(*) FROM salas")
    total_salas = cursor.fetchone()[0]

    if total_salas == 0:
        salas_padrao = [
    ("Coworking 01",),
    ("Coworking 02",),
    ("Coworking 03",),
    ("Coworking 04",),
    ("Coworking 05",),
    ("Coworking 06",),
    ("Coworking 07",),
    ("Coworking 08",),
    ("Sala de Reunião",),
    ("Escritório 01",),
    ("Escritório 02",),
    ("Sala de Audiência",),
    ("Auditório",)
]

        cursor.executemany(
            "INSERT INTO salas (nome) VALUES (?)",
            salas_padrao
        )

    conn.commit()
    conn.close()

    print("Banco de dados criado com sucesso!")


if __name__ == "__main__":
    criar_banco()
