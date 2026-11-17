import os
import re
import sqlite3
import logging

from decimal import Decimal, InvalidOperation
from datetime import datetime
from contextlib import contextmanager

from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup
)

from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)


load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")

BANCO = "finbot.db"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)



TIPO, VALOR, CATEGORIA, DESCRICAO = range(4)



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




def converter_centavos(valor):

    valor = valor.strip()
    valor = valor.replace("R$", "").replace(" ", "")

    if not valor:
        raise ValueError("Informe um valor.")

    if "," in valor:
        valor = valor.replace(".", "").replace(",", ".")

    try:
        numero = Decimal(valor)

        if not numero.is_finite() or numero <= 0:
            raise ValueError("O valor precisa ser maior que zero.")

        if numero > Decimal("999999999999"):
            raise ValueError("Valor muito alto.")

        if numero.as_tuple().exponent < -2:
            raise ValueError("Utilize no máximo duas casas decimais.")

        return int(numero * 100)

    except InvalidOperation:
        raise ValueError("Valor inválido. Exemplo: 50,00")


def formatar_reais(centavos):

    valor = Decimal(centavos) / 100

    formatado = f"{valor:,.2f}"

    formatado = (
        formatado
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )

    return f"R$ {formatado}"



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




def consultar_extrato(usuario_id):

    with conectar() as conexao:

        resultado = conexao.execute("""

            SELECT id, tipo, valor, categoria, descricao, data

            FROM transacoes

            WHERE usuario_id = ?

            ORDER BY id DESC

            LIMIT 10

        """, (usuario_id,)).fetchall()

    return resultado




def consultar_resumo(usuario_id):

    mes_atual = datetime.now().strftime("%Y-%m")

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

        """, (usuario_id, mes_atual)).fetchone()

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



def menu_principal():

    teclado = [

        ["➕ Adicionar movimentação"],

        ["💰 Meu saldo", "📊 Resumo mensal"],

        ["📜 Histórico", "🗑️ Excluir movimentação"]

    ]

    return ReplyKeyboardMarkup(
        teclado,
        resize_keyboard=True
    )




async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    mensagem = """
👋 Olá! Bem-vindo ao FINBOT!

💰 Seu assistente financeiro pessoal.

Aqui você pode organizar suas finanças,
acompanhar receitas e despesas e consultar
seu saldo sempre que precisar.

Escolha uma opção no menu abaixo:
"""

    await update.message.reply_text(
        mensagem,
        reply_markup=menu_principal()
    )




async def iniciar_adicao(update, context):

    context.user_data.clear()

    teclado = [

        [

            InlineKeyboardButton(
                "🟢 Receita",
                callback_data="receita"
            ),

            InlineKeyboardButton(
                "🔴 Despesa",
                callback_data="despesa"
            )

        ]

    ]

    await update.effective_message.reply_text(

        "💰 NOVA MOVIMENTAÇÃO\n\n"
        "Qual tipo deseja registrar?",

        reply_markup=InlineKeyboardMarkup(teclado)

    )

    return TIPO



async def escolher_tipo(update, context):

    query = update.callback_query

    await query.answer()

    tipo = query.data

    context.user_data["tipo"] = tipo

    await query.edit_message_text(

        f"Você escolheu: {tipo.upper()}.\n\n"

        "💵 Qual valor deseja registrar?\n\n"

        "Exemplo: 50,00"

    )

    return VALOR



async def receber_valor(update, context):

    valor_digitado = update.message.text

    try:

        valor = converter_centavos(valor_digitado)

    except ValueError as erro:

        await update.message.reply_text(

            f"⚠️ {erro}\n\n"
            "Digite novamente. Exemplo: 50,00"

        )

        return VALOR

    context.user_data["valor"] = valor

    teclado = [

        [

            InlineKeyboardButton(
                "🍔 Alimentação",
                callback_data="categoria:Alimentação"
            ),

            InlineKeyboardButton(
                "🚗 Transporte",
                callback_data="categoria:Transporte"
            )

        ],

        [

            InlineKeyboardButton(
                "🏠 Moradia",
                callback_data="categoria:Moradia"
            ),

            InlineKeyboardButton(
                "🎮 Lazer",
                callback_data="categoria:Lazer"
            )

        ],

        [

            InlineKeyboardButton(
                "💊 Saúde",
                callback_data="categoria:Saúde"
            ),

            InlineKeyboardButton(
                "📦 Outros",
                callback_data="categoria:Outros"
            )

        ]

    ]

    await update.message.reply_text(

        f"💵 Valor informado: {formatar_reais(valor)}\n\n"

        "📂 Agora escolha a categoria:",

        reply_markup=InlineKeyboardMarkup(teclado)

    )

    return CATEGORIA



async def escolher_categoria(update, context):

    query = update.callback_query

    await query.answer()

    categoria = query.data.split(":", 1)[1]

    context.user_data["categoria"] = categoria

    teclado = [

        [

            InlineKeyboardButton(
                "⏭️ Pular descrição",
                callback_data="pular_descricao"
            )

        ]

    ]

    await query.edit_message_text(

        f"📂 Categoria: {categoria}\n\n"

        "📝 Deseja adicionar uma descrição?\n\n"

        "Exemplo: almoço no restaurante.",

        reply_markup=InlineKeyboardMarkup(teclado)

    )

    return DESCRICAO



async def salvar_movimentacao(update, context, descricao):

    usuario_id = update.effective_user.id

    tipo = context.user_data["tipo"]

    valor = context.user_data["valor"]

    categoria = context.user_data["categoria"]

    try:

        registrar_transacao(

            usuario_id,
            tipo,
            valor,
            categoria,
            descricao

        )

        saldo = consultar_saldo(usuario_id)

    except Exception:

        logger.exception("Erro ao salvar movimentação.")

        await update.effective_message.reply_text(

            "❌ Não foi possível salvar sua movimentação.\n"
            "Tente novamente mais tarde."

        )

        context.user_data.clear()

        return ConversationHandler.END

    mensagem = f"""
✅ MOVIMENTAÇÃO REGISTRADA!

━━━━━━━━━━━━━━━━

📌 Tipo: {tipo.capitalize()}

💵 Valor: {formatar_reais(valor)}

📂 Categoria: {categoria}

📝 Descrição: {descricao or "Não informada"}

━━━━━━━━━━━━━━━━

💰 SEU SALDO ATUAL:

{formatar_reais(saldo)}

Seu lançamento foi salvo com sucesso!
"""

    context.user_data.clear()

    await update.effective_message.reply_text(

        mensagem,

        reply_markup=menu_principal()

    )

    return ConversationHandler.END



async def receber_descricao(update, context):

    descricao = update.message.text.strip()

    if len(descricao) > 200:

        await update.message.reply_text(

            "⚠️ A descrição deve ter no máximo 200 caracteres."

        )

        return DESCRICAO

    return await salvar_movimentacao(

        update,
        context,
        descricao

    )


async def pular_descricao(update, context):

    query = update.callback_query

    await query.answer()

    return await salvar_movimentacao(

        update,
        context,
        ""

    )



async def cancelar(update, context):

    context.user_data.clear()

    await update.effective_message.reply_text(

        "❌ Operação cancelada!\n\n"
        "Nenhuma movimentação foi registrada.",

        reply_markup=menu_principal()

    )

    return ConversationHandler.END



async def saldo(update, context):

    usuario_id = update.effective_user.id

    valor = consultar_saldo(usuario_id)

    mensagem = f"""
💰 SEU SALDO ATUAL

━━━━━━━━━━━━━━━━

{formatar_reais(valor)}

━━━━━━━━━━━━━━━━
"""

    await update.effective_message.reply_text(mensagem)



async def historico(update, context):

    usuario_id = update.effective_user.id

    transacoes = consultar_extrato(usuario_id)

    if not transacoes:

        await update.effective_message.reply_text(

            "📜 Você ainda não possui movimentações."

        )

        return

    mensagem = "📜 SEU HISTÓRICO\n\n"

    for item in transacoes:

        id_transacao, tipo, valor, categoria, descricao, data = item

        emoji = "🟢" if tipo == "receita" else "🔴"

        mensagem += (

            f"{emoji} ID: {id_transacao}\n"
            f"Tipo: {tipo.capitalize()}\n"
            f"Valor: {formatar_reais(valor)}\n"
            f"Categoria: {categoria}\n"
            f"Descrição: {descricao or 'Não informada'}\n"
            f"Data: {data}\n"
            "━━━━━━━━━━━━━━\n"

        )

    await update.effective_message.reply_text(mensagem)



async def resumo(update, context):

    usuario_id = update.effective_user.id

    receitas, despesas = consultar_resumo(usuario_id)

    resultado = receitas - despesas

    mes = datetime.now().strftime("%m/%Y")

    mensagem = f"""
📊 RESUMO FINANCEIRO

Mês: {mes}

━━━━━━━━━━━━━━━━

🟢 Receitas:
{formatar_reais(receitas)}

🔴 Despesas:
{formatar_reais(despesas)}

━━━━━━━━━━━━━━━━

💰 Resultado do mês:
{formatar_reais(resultado)}
"""

    await update.effective_message.reply_text(mensagem)



async def iniciar_exclusao(update, context):

    usuario_id = update.effective_user.id

    transacoes = consultar_extrato(usuario_id)

    if not transacoes:

        await update.effective_message.reply_text(
            "Você não possui movimentações para excluir."
        )

        return

    teclado = []

    for item in transacoes:

        id_transacao, tipo, valor, categoria, descricao, data = item

        teclado.append([

            InlineKeyboardButton(

                f"ID {id_transacao} - {tipo} - "
                f"{formatar_reais(valor)}",

                callback_data=f"excluir:{id_transacao}"

            )

        ])

    await update.effective_message.reply_text(

        "🗑️ QUAL MOVIMENTAÇÃO DESEJA EXCLUIR?\n\n"
        "Selecione um lançamento abaixo:",

        reply_markup=InlineKeyboardMarkup(teclado)

    )


async def confirmar_exclusao(update, context):

    query = update.callback_query

    await query.answer()

    transacao_id = int(query.data.split(":")[1])

    usuario_id = update.effective_user.id

    resultado = excluir_transacao(usuario_id, transacao_id)

    if resultado:

        await query.edit_message_text(

            "✅ Movimentação excluída com sucesso!"

        )

    else:

        await query.edit_message_text(

            "⚠️ Movimentação não encontrada."

        )


async def tratar_erro(update, context):

    logger.error(
        "Erro durante a execução:",
        exc_info=context.error
    )


def main():

    if not TOKEN:

        raise RuntimeError(
            "Token não encontrado. Confira seu arquivo .env."
        )

    criar_tabela()

    app = Application.builder().token(TOKEN).build()


    conversa_adicionar = ConversationHandler(

        entry_points=[

            CommandHandler("adicionar", iniciar_adicao),

            MessageHandler(
                filters.Regex("^➕ Adicionar movimentação$"),
                iniciar_adicao
            )

        ],

        states={

            TIPO: [

                CallbackQueryHandler(
                    escolher_tipo,
                    pattern="^(receita|despesa)$"
                )

            ],

            VALOR: [

                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receber_valor
                )

            ],

            CATEGORIA: [

                CallbackQueryHandler(
                    escolher_categoria,
                    pattern="^categoria:"
                )

            ],

            DESCRICAO: [

                CallbackQueryHandler(
                    pular_descricao,
                    pattern="^pular_descricao$"
                ),

                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receber_descricao
                )

            ]

        },

        fallbacks=[

            CommandHandler("cancelar", cancelar)

        ],

        allow_reentry=True

    )


    app.add_handler(conversa_adicionar)

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CommandHandler("saldo", saldo))

    app.add_handler(CommandHandler("extrato", historico))

    app.add_handler(CommandHandler("resumo", resumo))

    app.add_handler(CommandHandler("cancelar", cancelar))

    app.add_handler(CommandHandler("excluir", iniciar_exclusao))

    # BOTÕES DO MENU PRINCIPAL

    app.add_handler(

        MessageHandler(
            filters.Regex("^💰 Meu saldo$"),
            saldo
        )

    )

    app.add_handler(

        MessageHandler(
            filters.Regex("^📊 Resumo mensal$"),
            resumo
        )

    )

    app.add_handler(

        MessageHandler(
            filters.Regex("^📜 Histórico$"),
            historico
        )

    )

    app.add_handler(

        MessageHandler(
            filters.Regex("^🗑️ Excluir movimentação$"),
            iniciar_exclusao
        )

    )


    app.add_handler(

        CallbackQueryHandler(
            confirmar_exclusao,
            pattern="^excluir:"
        )

    )

    app.add_error_handler(tratar_erro)

    print("FINBOT iniciado com sucesso!")

    app.run_polling()


if __name__ == "__main__":

    main()
