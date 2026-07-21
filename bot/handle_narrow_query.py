from bot.update_context_history import update_context_history
from bot.split_message import split_message
from bot.convert_md_to_html import convert_md_to_html


async def handle_narrow_query(update, agent, user_query, history,context):
    """
    Обрабатывает узконаправленные запросы.

    :param update: Объект Update.
    :param agent: Объект SQLAgent.
    :param user_query: Текст запроса пользователя.
    """
    await update.message.reply_text("Анализирую узконаправленный запрос...")
    narrow_query_response = agent.narrow_query_analyzer(user_query,history=history)

    if narrow_query_response:
        html_narrow_query_response = convert_md_to_html(narrow_query_response)
        for chunk in split_message(html_narrow_query_response):
            await update.message.reply_text(chunk, parse_mode="HTML")
    else:
        narrow_query_response = "Не удалось обработать узконаправленный запрос."
        await update.message.reply_text(narrow_query_response)

        # Добавляем запрос и ответ в историю
    update_context_history(context, user_query, narrow_query_response)