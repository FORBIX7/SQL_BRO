from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import logging

from bot.split_message import split_message


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает команду '/info', загружает базу данных с помощью агента SQL и отображает информацию о таблицах.
    """
    try:
        # Извлечение агента SQL из user_data
        agent = context.user_data.get('user_context', {}).get('agent')
        if not agent:
            logging.error("Агент SQL не найден для пользователя %s", update.message.from_user.id)
            await update.message.reply_text("Ошибка: агент SQL не найден.")
            return

        # Загружаем базу данных и получаем информацию о таблицах
        logging.info("Загрузка базы данных для пользователя %s", update.message.from_user.id)
        agent.load_database()
        tables_info = agent.display_tables_info()

        if not tables_info:
            logging.warning("Информация о таблицах пустая для пользователя %s", update.message.from_user.id)
            await update.message.reply_text("Нет данных для отображения.")
            return

        # Отправка информации по частям
        logging.info("Отправка информации о таблицах пользователю %s", update.message.from_user.id)
        for chunk in split_message(tables_info):
            await update.message.reply_text(chunk, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Ошибка при обработке команды /info для пользователя {update.message.from_user.id}: {e}",
                      exc_info=True)
        await update.message.reply_text("Произошла ошибка при выполнении команды.")