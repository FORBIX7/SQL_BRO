from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
async def upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Информирует пользователя о возможности загрузить базу данных.
    """
    await update.message.reply_text(
        "Отправьте файл базы данных (например, .sqlite или .accdb), прикрепив его как документ."
    )