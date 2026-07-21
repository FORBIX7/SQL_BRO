import os

async def handle_er_diagram_generation_full(update, agent, user_query):
    """
    Обрабатывает запросы на генерацию ER-диаграмм.
    :param update: Объект Update.
    :param agent: Объект SQLAgent.
    :param user_query: Текст запроса пользователя.
    """
    await update.message.reply_text("Строю диаграмму...")

    # Получаем полный путь к файлу (например: ./generated/er_full_abc123.png)
    diagram_path = agent.generate_er_diagram()

    if diagram_path and os.path.exists(diagram_path):
        try:
            with open(diagram_path, "rb") as photo:
                await update.message.reply_document(photo, caption="Диаграмма")
        except Exception as e:
            await update.message.reply_text("Ошибка при отправке диаграммы.")
            logging.error(f"Не удалось отправить диаграмму: {e}", exc_info=True)
    else:
        await update.message.reply_text("Ошибка: файл диаграммы не найден.")
