from collections import deque
import logging
from telegram import Update
from telegram.ext import ContextTypes

from bot.handle_sql_generation import handle_sql_generation
from bot.handle_er_diagram_generation_full import handle_er_diagram_generation_full
from bot.handle_er_diagram_generation import handle_er_diagram_generation
from bot.handle_general_db_info import handle_general_db_info
from bot.handle_narrow_query import handle_narrow_query

logger = logging.getLogger(__name__)

# Мапа обработчиков
HANDLER_MAPPING = {
    'sql_generation': handle_sql_generation,
    'full_er_diagram_generation': handle_er_diagram_generation_full,
    'er_diagram_generation': handle_er_diagram_generation,
    'general_db_info': handle_general_db_info,
    'narrow_query': handle_narrow_query,
    'other': handle_general_db_info,  # ✅ Добавь обработчик для `other`
}

# Какие обработчики требуют context
NEEDS_CONTEXT = {'sql_generation', 'general_db_info', 'narrow_query', 'er_diagram_generation', 'other'}


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = message.from_user.id if message and message.from_user else "неизвестен"

    if not message or not message.text:
        await update.message.reply_text("Ошибка: пустой запрос. Попробуйте ввести текст.")
        return

    user_query = message.text.strip().lower()

    if not user_query:
        await message.reply_text("Ошибка: пустой запрос. Попробуйте ввести текст.")
        return

    try:
        user_context = context.user_data.setdefault("user_context", {})
        agent = user_context.get("agent")

        if not agent:
            logger.error("SQL-агент не найден для пользователя %s", user_id)
            await message.reply_text("Ошибка: агент SQL не найден. Используйте /start для начала работы.")
            return

        # Инициализация истории
        user_context.setdefault("history", deque(maxlen=6))
        history = list(user_context["history"])

        logger.info("Пользователь %s отправил запрос: %s", user_id, user_query)
        await message.reply_text("Анализирую запрос...")

        # Загрузка базы данных
        try:
            agent.load_database()
        except Exception as e:
            logger.error("Ошибка при загрузке базы данных: %s", e, exc_info=True)
            await message.reply_text("Ошибка при загрузке базы данных. Попробуйте позже.")
            return

        # Классификация запроса
        try:
            query_type, reasoning = agent.classify_query(user_query, history)
            logger.info("Определен тип запроса: %s", query_type)
            logger.debug("Обоснование классификации: %s", reasoning)
        except Exception as e:
            logger.error("Ошибка при классификации запроса: %s", e, exc_info=True)
            await message.reply_text("Ошибка при анализе запроса. Попробуйте переформулировать вопрос.")
            return

        # Преобразование строки в список
        if isinstance(query_type, str):
            query_type = [query_type]

        # Поиск и выполнение подходящего обработчика
        for key in query_type:
            handler = HANDLER_MAPPING.get(key)
            if handler:
                try:
                    if key in NEEDS_CONTEXT:
                        await handler(update, agent, user_query, history, context)
                    else:
                        await handler(update, agent, user_query)

                    # Сохраняем запрос в историю
                    user_context["history"].append({
                        "query": user_query,
                        "type": key,
                        "reasoning": reasoning
                    })
                    return
                except Exception as e:
                    logger.error("Ошибка при вызове обработчика %s: %s", key, e, exc_info=True)
                    await message.reply_text("Произошла ошибка при обработке запроса. Попробуйте ещё раз.")
                    return

        logger.warning("Не удалось классифицировать запрос: %s", user_query)
        await message.reply_text("Не удалось классифицировать запрос. Попробуйте задать его по-другому.")

    except Exception as e:
        logger.critical("Критическая ошибка в обработке сообщений: %s", e, exc_info=True)
        await update.message.reply_text("Внутренняя ошибка бота. Администратор уже уведомлён.")
