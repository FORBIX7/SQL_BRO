from collections import deque
from telegram import Update
from telegram.ext import ContextTypes
import logging
import os
from dotenv import load_dotenv

from agent_manager import AgentManager  # <--- новое
load_dotenv()

DB_PATH = os.getenv("DB_PATH")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.message.from_user
        user_id = user.id

        context.user_data.setdefault("user_context", {"history": deque(maxlen=3)})

        agent = AgentManager.get_agent(context, db_type="sqlite", db_path=DB_PATH)
        logging.info(f"Создан или получен SQL агент для пользователя {user_id}.")
        await update.message.reply_text('Привет! Я SQL бот. Введи свой запрос. Вывести данные БД: /info')

    except Exception as e:
        logging.error(f"Ошибка при обработке команды /start: {e}", exc_info=True)
        await update.message.reply_text("Произошла ошибка при инициализации сессии. Попробуйте снова.")
