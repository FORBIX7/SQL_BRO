from collections import deque
import logging
def update_context_history(context, user_query, response_text):
    """
    Обновляет глобальную историю запросов и ответов.

    :param context: Объект Context.
    :param user_query: Запрос пользователя.
    :param response_text: Ответ модели.
    """
    # Проверяем существование 'user_context' в context.user_data
    user_context = context.user_data.setdefault('user_context', {})

    if 'history' not in user_context:
        user_context['history'] = deque(maxlen=6)

    # Добавляем запрос и ответ в историю
    user_context['history'].append({'user': user_query, 'response': response_text})

    # Логирование истории для проверки
    logging.info("Обновленная глобальная история: %s", list(user_context['history']))