import logging
from html import escape

from bot.update_context_history import update_context_history
from bot.split_message import split_message
from bot.convert_md_to_html import convert_md_to_html


def extract_tag(text: str, tag: str) -> str:
    """Извлекает содержимое указанного тега из текста, например <answer>...</answer>"""
    import re
    pattern = fr"<{tag}>([\s\S]*?)</{tag}>"
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def clean_tags_for_telegram(text: str) -> str:
    """Заменяет нестандартные теги на понятный HTML для Telegram"""
    return (
        text.replace("<plan>", "<b>План:</b>\n")
            .replace("</plan>", "\n")
            .replace("<action>", "<b>Действие:</b>\n")
            .replace("</action>", "\n")
            .replace("<answer>", "<b>Ответ:</b>\n")
            .replace("</answer>", "\n")
            .replace("<user_question>", "<i>Вопрос:</i>\n")
            .replace("</user_question>", "\n")
            .replace("<history>", "<i>Контекст:</i>\n")
            .replace("</history>", "\n")
    )


async def handle_general_db_info(update, agent, user_query, history, context):
    """Обрабатывает запросы на получение общей информации о базе данных."""
    try:
        await update.message.reply_text("Анализирую информацию о базе данных...")

        raw_response = agent.generate_info(user_query, history=history)
        if not raw_response:
            await update.message.reply_text("❌ Не удалось получить информацию о базе данных.")
            return

        # Извлекаем <answer>, если есть
        answer = extract_tag(raw_response, "answer") or raw_response

        # Безопасная HTML-подготовка
        clean_text = clean_tags_for_telegram(answer)
        html_ready = convert_md_to_html(clean_text)

        # Разбивка и отправка
        for chunk in split_message(html_ready):
            try:
                await update.message.reply_text(chunk, parse_mode="HTML")
            except Exception as e:
                logging.error(f"⚠️ Telegram не принял сообщение: {e}")
                await update.message.reply_text("⚠️ Ошибка при отправке HTML-сообщения.")

        # Добавляем в историю
        update_context_history(context, user_query, answer)

    except Exception as e:
        logging.exception("💥 Ошибка в обработке general_db_info")
        await update.message.reply_text("❌ Произошла ошибка при анализе базы данных.")
