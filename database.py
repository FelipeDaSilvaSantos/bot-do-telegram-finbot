
import sqlite3
from contextlib import contextmanager
from datetime import datetime

BANCO = "finbot.db"



@contextmanager
def conectar():

    conexao = sqlite3.connect(BANCO)

    try:
        yield conexao
        conexao.commit()

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.close()



def criar_tabela():

    with conectar() as conexao:

        conexao.execute("""
            CREATE TABLE IF NOT EXISTS transacoes (

                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                valor INTEGER NOT NULL,
                categoria TEXT NOT NULL,
                descricao TEXT,
                data TEXT NOT NULL

            )
        """)



def registrar_transacao(
    usuario_id,
    tipo,
    valor,
    categoria,
    descricao
):

    with conectar() as conexao:

        conexao.execute("""
            INSERT INTO transacoes
            (usuario_id, tipo, valor, categoria, descricao, data)

            VALUES (?, ?, ?, ?, ?, ?)

        """, (
            usuario_id,
            tipo,
            valor,
            categoria,
            descricao,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))



def consultar_saldo(usuario_id):

    with conectar() as conexao:

        resultado = conexao.execute("""
            SELECT SUM(
                CASE
                    WHEN tipo = 'receita' THEN valor
                    ELSE -valor
                END
            )

            FROM transacoes

            WHERE usuario_id = ?

        """, (usuario_id,)).fetchone()

    return resultado[0] or 0




def consultar_extrato(usuario_id, limite=10):

    with conectar() as conexao:

        resultado = conexao.execute("""
            SELECT id, tipo, valor, categoria, descricao, data

            FROM transacoes

            WHERE usuario_id = ?

            ORDER BY id DESC

            LIMIT ?

        """, (usuario_id, limite)).fetchall()

    return resultado



def consultar_resumo(usuario_id, mes):

    with conectar() as conexao:

        resultado = conexao.execute("""
            SELECT

                SUM(CASE
                    WHEN tipo = 'receita' THEN valor
                    ELSE 0
                END),

                SUM(CASE
                    WHEN tipo = 'despesa' THEN valor
                    ELSE 0
                END)

            FROM transacoes

            WHERE usuario_id = ?
            AND substr(data, 1, 7) = ?

        """, (usuario_id, mes)).fetchone()

    receitas = resultado[0] or 0
    despesas = resultado[1] or 0

    return receitas, despesas



def excluir_transacao(usuario_id, transacao_id):

    with conectar() as conexao:

        cursor = conexao.execute("""
            DELETE FROM transacoes

            WHERE id = ?
            AND usuario_id = ?

        """, (transacao_id, usuario_id))

        return cursor.rowcount > 0
