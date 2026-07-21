from sqlalchemy import MetaData, Table, text
import logging

def split_message(text, max_length=4096):
    """
    Разбивает длинное сообщение на части, подходящие для Telegram, чтобы оно не превышало максимальную длину.

    :param text: Текст, который необходимо разбить на части.
    :param max_length: Максимальная длина для каждого сообщения (по умолчанию 4096 символов).
    :return: Список строк (каждая строка — часть сообщения, подходящая по длине для Telegram).
    """
    try:
        if len(text) <= max_length:
            return [text]

        chunks = []
        current_chunk = ""

        # Разделение по строкам
        for line in text.splitlines():
            # Проверяем, если добавление новой строки превысит максимальную длину
            if len(current_chunk) + len(line) + 1 > max_length:
                chunks.append(current_chunk)
                current_chunk = line + "\n"  # Начинаем новый кусок с текущей строки
            else:
                current_chunk += line + "\n"  # Добавляем строку в текущий кусок

        if current_chunk:  # Добавляем последний кусок
            chunks.append(current_chunk)

        logging.debug(f"Сообщение разбито на {len(chunks)} частей.")
        return chunks

    except Exception as e:
        logging.error(f"Ошибка при разбиении сообщения: {e}", exc_info=True)
        return [text]  # В случае ошибки возвращаем исходный текст в виде одного сообщения