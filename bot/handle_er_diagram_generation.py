import os
from telegram.constants import ChatAction
import logging


async def handle_er_diagram_generation(update, agent, user_query, history, context):
    """
    Обрабатывает запросы на генерацию ER-диаграмм на основе запроса пользователя.
    """
    await update.message.reply_text("Строю диаграмму...")
    await context.bot.send_chat_action(chat_id=update.message.chat.id, action=ChatAction.UPLOAD_DOCUMENT)

    diagram_path = agent.analyze_query_for_relationships(user_query, history)

    if diagram_path and os.path.exists(diagram_path):
        try:
            with open(diagram_path, "rb") as photo:
                await update.message.reply_document(photo, caption="Диаграмма")
        except Exception as e:
            await update.message.reply_text("Ошибка при отправке диаграммы.")
            logging.error(f"Ошибка при отправке: {e}", exc_info=True)
    else:
        await update.message.reply_text("Ошибка: файл диаграммы не найден.")
