import html
from bot.update_context_history import update_context_history
from bot.split_message import split_message
from bot.convert_md_to_html import convert_md_to_html
import re

from bs4 import BeautifulSoup


def sanitize_html(html_text):
    try:
        # Удаляет незакрытые теги, приводит HTML к валидному виду
        return str(BeautifulSoup(html_text, "html.parser"))
    except Exception:
        return html.escape(html_text)

def format_sql_results(rows):
    if not rows:
        return "<i>Пустой результат</i>"

    try:
        headers = list(rows[0]._mapping.keys())
    except AttributeError:
        headers = []

    result_lines = []
    for row in rows:
        for col in headers:
            value = row._mapping.get(col, "")
            result_lines.append(f"<b>{col}:</b> {value}")
        result_lines.append("<i>--------------------------</i>")

    return "\n".join(result_lines)

def format_sql_results_for_history(rows):
    if not rows:
        return "<i>Пустой результат</i>"

    try:
        headers = list(rows[0]._mapping.keys())
    except AttributeError:
        headers = []

    result_lines = []
    for row in rows[:10]:
        for col in headers:
            value = row._mapping.get(col, "")
            result_lines.append(f"{col}: {value}")
        result_lines.append("--------------------")

    if len(rows) > 10:
        result_lines.append(f"... и еще {len(rows) - 10} строк")

    return "\n".join(result_lines)

def extract_table_name_from_create(sql):
    match = re.search(r"CREATE TABLE IF NOT EXISTS ([\wа-яА-Я_]+)", sql, re.IGNORECASE)
    if match:
        return match.group(1)
    return None

def get_post_check_sql(sql):
    sql_upper = sql.strip().upper()
    if sql_upper.startswith("CREATE TABLE"):
        table_name = extract_table_name_from_create(sql)
        if table_name:
            return f"PRAGMA table_info({table_name});"
        return "PRAGMA table_list;"
    if sql_upper.startswith("INSERT") or sql_upper.startswith("UPDATE") or sql_upper.startswith("DELETE"):
        match = re.search(r"(INTO|UPDATE|FROM)\s+([\wа-яА-Я_]+)", sql, re.IGNORECASE)
        if match:
            table = match.group(2)
            return f"SELECT * FROM {table} LIMIT 10;"
    return None

async def handle_sql_generation(update, agent, user_query, history, context):
    await update.message.reply_text("Пишу SQL-запрос...")

    from smart_sql_engine import SmartSQLEngine
    engine = SmartSQLEngine(db=agent.db, ai_client=agent.ai_client)

    try:
        sql_queries = engine.generate(user_query, history=history)
    except Exception as e:
        error_text = f"⚠️ Ошибка при генерации SQL-запроса: {e}"
        await update.message.reply_text(error_text)
        update_context_history(context, user_query, error_text)
        return

    if not sql_queries:
        response_text = "⚠️ Модель не сгенерировала SQL-запрос по этому запросу."
        await update.message.reply_text(response_text)
        update_context_history(context, user_query, response_text)
        return

    results = []
    history_results = []

    for query in sql_queries:
        try:
            execution_results = agent.db.execute([query])
            safe_query = html.escape(query)

            post_check_sql = get_post_check_sql(query)
            post_check_result = []
            if post_check_sql:
                try:
                    post_check_result = agent.db.execute([post_check_sql])[0]
                except Exception as post_err:
                    post_check_result = [f"Ошибка при проверке результата: {post_err}"]

            for result in execution_results:
                if isinstance(result, list):
                    formatted_rows = format_sql_results(result)
                    history_rows = format_sql_results_for_history(result)
                    results.append(f"<b>Результат запроса:</b>\n<pre>{safe_query}</pre>\n\n{formatted_rows}")
                    history_results.append(f"Результат запроса:\n{query}\n\n{history_rows}")
                else:
                    message = "✔️ Успешно выполнено." if result is None else str(result)
                    results.append(f"<b>Запрос выполнен:</b>\n<pre>{safe_query}</pre>\n\n{message}")
                    history_results.append(f"Запрос выполнен:\n{query}\n\n{message}")

            if post_check_result:
                if isinstance(post_check_result, list):
                    formatted = format_sql_results(post_check_result)
                    results.append(f"<b>Подтверждение выполнения:</b>\n<pre>{post_check_sql}</pre>\n\n{formatted}")
                    history_results.append(f"Подтверждение выполнения:\n{post_check_sql}\n\n{formatted}")
                else:
                    results.append(f"<b>Проверка:</b> {post_check_result}")
                    history_results.append(f"Проверка:\n{post_check_sql}\n\n{post_check_result}")

        except Exception as e:
            safe_query = html.escape(query)
            results.append(f"<b>Ошибка при выполнении запроса:</b>\n<code>{safe_query}</code>\n\n{e}")
            history_results.append(f"Ошибка при выполнении запроса:\n{query}\n\n{e}")

    response_text = "\n\n".join(results)
    html_response = convert_md_to_html(response_text)
    for chunk in split_message(html_response):
        safe_chunk = sanitize_html(chunk)
        await update.message.reply_text(safe_chunk, parse_mode="HTML")

    history_text = "\n\n".join(history_results)
    update_context_history(context, user_query, history_text)
