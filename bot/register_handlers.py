
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

import logging

from bot.start import start
from bot.info_command import info_command
from bot.get_db_command import get_db_command
from bot.handle_message import handle_message
from bot.upload_command import upload_command
from bot.handle_file_upload import handle_file_upload

def register_handlers(application):
    try:
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("info", info_command))
        application.add_handler(CommandHandler("get", get_db_command))  # Регистрация новой команды
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(CommandHandler("upload", upload_command))
        application.add_handler(MessageHandler(filters.Document.ALL & ~filters.COMMAND, handle_file_upload))
    except Exception as e:
        logging.error(f"Error registering handlers: {e}", exc_info=True)



    except Exception as e:
        logging.error(f"Ошибка при регистрации обработчиков: {e}", exc_info=True)