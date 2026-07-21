from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import os
import logging
async def get_db_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /get_db command by sending the current database file the user is working with.
    """
    try:
        # Получаем экземпляр SQLAgent из контекста пользователя
        agent = context.user_data.get('user_context', {}).get('agent')
        if not agent:
            logging.error("SQLAgent not found for user %s", update.message.from_user.id)
            await update.message.reply_text("Error: SQLAgent not found. Use /start to initiate the session.")
            return

        # Путь к файлу базы данных
        db_file_path = agent.db_path
        if not os.path.exists(db_file_path):
            logging.error("Файл базы данных не найден: %s", db_file_path)
            await update.message.reply_text("Файл базы данных не найден.")
            return

        # Отправляем файл базы данных пользователю
        with open(db_file_path, 'rb') as db_file:
            await update.message.reply_document(db_file, caption=f"Ваша база данных: {os.path.basename(db_file_path)}")

    except Exception as e:
        logging.error(f"Ошибка процесса /get команды: {e}", exc_info=True)
        await update.message.reply_text("An error occurred while sending the database file.")