from sqlalchemy import MetaData, Table, text
import re
import logging
@staticmethod
def convert_md_to_html(text):
    """
    Преобразует текст из формата Markdown в HTML, применяя соответствующие теги для ссылок, жирного текста,
    курсива и подчеркивания, с учетом формата для Telegram.

    :param text: Текст в формате Markdown, который необходимо преобразовать в HTML.
    :return: Текст в формате HTML.
    """
    try:
        if text is None:
            logging.warning("Передан пустой текст для преобразования в HTML.")
            return ""

        # Регулярные выражения и замены
        html_text = text

        # Замена ссылок Markdown на HTML
        md_link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        html_text = re.sub(md_link_pattern, r'<a href="\2">\1</a>', html_text)
        logging.debug("Обработаны ссылки в Markdown.")

        # Замена жирного текста Markdown на HTML
        bold_pattern = r'\*\*(.*?)\*\*'
        html_text = re.sub(bold_pattern, r'<b>\1</b>', html_text)
        logging.debug("Обработан жирный текст Markdown.")

        # Замена текста в курсе Markdown на HTML
        italic_pattern = r'\*(.*?)\*'
        html_text = re.sub(italic_pattern, r'<i>\1</i>', html_text)
        logging.debug("Обработан курсив в Markdown.")

        # Замена подчеркивания в Markdown на HTML
        underline_pattern = r'_(.*?)_'
        html_text = re.sub(underline_pattern, r'<u>\1</u>', html_text)
        logging.debug("Обработано подчеркивание в Markdown.")

        logging.info("Преобразование Markdown в HTML завершено.")
        return html_text

    except re.error as e:
        logging.error(f"Ошибка при обработке регулярных выражений: {e}", exc_info=True)
        return text  # В случае ошибки возвращаем исходный текст
    except Exception as e:
        logging.error(f"Неизвестная ошибка при преобразовании Markdown в HTML: {e}", exc_info=True)
        return text  # В случае неизвестной ошибки возвращаем исходный текст
