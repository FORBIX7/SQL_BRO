import requests
import json
import re
import logging

from PIL import Image
from ai_client import AIClient
from database_manager import DatabaseManager
from er_diagram_generator import ERDiagramGenerator
from utils import extract_json_from_response
from smart_sql_engine import SmartSQLEngine
from ai_config import AISettings
import html





# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# 🏗️ БЛОК: ИНИЦИАЛИЗАЦИЯ И НАСТРОЙКА КЛАССА
# ============================================================
# Этот раздел содержит методы, которые отвечают за создание объекта класса,
# настройку подключения к базе данных и загрузку метаданных.
#
# Методы в этом разделе:
# - __init__: Конструктор класса, инициализирует основные переменные.
# - create_database_engine: Создает подключение к базе данных в зависимости от её типа.
# - load_database: Загружает структуру базы данных, обновляет метаданные.
# - _update_tables_information: Обновляет информацию о таблицах после загрузки базы.
#
# Эти методы вызываются при создании объекта класса и при смене базы данных.

class SQLAgent:
    def __init__(self, db_type, db_path, ai_settings: AISettings):
        self.db_type = db_type
        self.db_path = db_path
        self.ai_settings = ai_settings

        self.db = DatabaseManager(
            db_type=self.db_type,
            db_path=self.db_path,
            proxy_user=ai_settings.proxy_username,
            proxy_pass=ai_settings.proxy_password,
            proxy_host=ai_settings.proxy_host,
            proxy_port=ai_settings.proxy_port
        )

        self.ai_client = AIClient(
            ai_provider=ai_settings.ai_provider,
            openai_api_key=ai_settings.openai_api_key,
            openrouter_api_key=ai_settings.openrouter_api_key,
            proxy=ai_settings.proxy
        )

        self.smart_sql = SmartSQLEngine(self.ai_client, self.db)

    def chatgpt_request(self, prompt, maximum_tokens=500, temperature=0, use_local=None, model_name=None):
        model_name = model_name or self.ai_settings.ai_model
        provider = self.ai_settings.ai_provider

        # Принудительный override провайдера (если явно задан use_local)
        if use_local is not None:
            provider = "local" if use_local else self.ai_settings.ai_provider

        logging.info(f"[SQLAgent.chatgpt_request] Провайдер: {provider}, модель: {model_name}")

        return self.ai_client.chat(
            prompt=prompt,
            model=model_name,
            max_tokens=maximum_tokens,
            temperature=temperature
        )

    def load_database(self):
        """Для совместимости со старым кодом."""
        self.db.load()

    # ============================================================
    # 🗄️ БЛОК: РАБОТА С БАЗОЙ ДАННЫХ
    # ============================================================
    # Этот раздел содержит методы, которые выполняют операции с базой данных.
    # Здесь реализованы функции для отображения структуры базы и выполнения SQL-запросов.
    #
    # Методы в этом разделе:
    # - display_tables_info: Отображает информацию о таблицах в базе данных.
    # - execute: Выполняет SQL-запросы в базе данных и возвращает результат.
    # - process_case_insensitive: Обрабатывает результаты SQL-запроса, сохраняя регистр.
    #
    # Эти методы используются при взаимодействии пользователя с базой через бота.

    def display_tables_info(self):
        """
        Возвращает информацию о таблицах базы данных, отформатированную для корректного отображения в Telegram.
        :return: Строка с отформатированной информацией или сообщение об отсутствии данных.
        """
        try:
            tables_info = self.db.get_tables_info()
            if not tables_info:
                logging.warning("Таблицы отсутствуют в базе данных.")
                return "Таблицы отсутствуют в базе данных."

            lines = []

            # Для каждой таблицы формируем отдельный блок
            for table_name, info in tables_info.items():
                lines.append(f"\n<b>Таблица:</b> {table_name}")
                lines.append("<i>Колонки:</i>")

                # Для каждой колонки – отдельная строка
                for col_name, col_type in info['columns'].items():
                    lines.append(f" • <code>{col_name}</code> (<i>{col_type}</i>)")

                pk = ", ".join(info['primary_keys']) if info['primary_keys'] else "Нет"
                lines.append(f"<i>Первичные ключи:</i> {pk}")

                if info['foreign_keys']:
                    fk_list = ", ".join([f"{col} → {fk}" for col, fk in info['foreign_keys'].items()])
                else:
                    fk_list = "Нет"
                lines.append(f"<i>Внешние ключи:</i> {fk_list}")

                # Разделитель между таблицами
                lines.append("────────────")

            result_message = "\n".join(lines)
            logging.info("Информация о таблицах успешно сформирована.")
            return result_message

        except Exception as e:
            logging.error(f"Ошибка при отображении информации о таблицах: {e}", exc_info=True)
            return "Произошла ошибка при отображении информации о таблицах."

    def _generate_db_structure(self, detailed: bool = True):
        """
        Генерирует структуру базы данных (подробно или кратко).
        """
        structure = {"tables": []}
        tables_info = self.db.get_tables_info()

        for table_name, info in tables_info.items():
            if detailed:
                table_data = {
                    "name": table_name.lower(),
                    "columns": [],
                    "indexes": [],
                    "relationships": []
                }

                for col_name, col_type in info["columns"].items():
                    table_data["columns"].append({
                        "name": col_name.lower(),
                        "type": str(col_type).split('(')[0].lower(),
                        "nullable": True,
                        "primary_key": col_name in info["primary_keys"]
                    })

                for fk_col, fk_info in info["foreign_keys"].items():
                    parts = fk_info.split('.')
                    table_data["relationships"].append({
                        "source_column": fk_col.lower(),
                        "target_table": parts[0].lower(),
                        "target_column": parts[1].lower()
                    })

            else:
                table_data = {
                    "table_name": table_name,
                    "columns": list(info['columns'].keys()),
                    "primary_keys": info['primary_keys'],
                    "foreign_keys": list(info['foreign_keys'].keys())
                }

            structure["tables"].append(table_data)

        return structure if not detailed else json.dumps(structure, indent=2)

    def process_case_insensitive(self, query):
        """
        Преобразует строковые условия WHERE в регистронезависимые, используя функцию LOWER().
        Например, 'WHERE City = "calgary"' -> 'WHERE LOWER(City) = LOWER("calgary")'.

        :param query: SQL-запрос, в котором нужно сделать условия WHERE регистронезависимыми.
        :return: SQL-запрос с преобразованными условиями WHERE.
        """
        try:
            logging.debug(f"Исходный запрос: {query}")

            # Регулярное выражение для поиска условий WHERE с использованием строковых значений
            pattern = re.compile(r"(WHERE\s+)(\w+)(\s*=\s*)'([^']*)'", re.IGNORECASE)

            # Замена условий на LOWER(field) = LOWER('value')
            def repl(match):
                result = f"{match.group(1)}LOWER({match.group(2)}){match.group(3)}LOWER('{match.group(4)}')"
                logging.debug(f"Преобразованное условие: {result}")
                return result

            # Применение преобразования
            transformed_query = pattern.sub(repl, query)

            logging.info(f"Преобразованный запрос: {transformed_query}")
            return transformed_query

        except re.error as e:
            logging.error(f"Ошибка при обработке регулярного выражения: {e}", exc_info=True)
            return query  # Возвращаем исходный запрос в случае ошибки
        except Exception as e:
            logging.error(f"Неожиданная ошибка при преобразовании запроса: {e}", exc_info=True)
            return query

    # ============================================================
    # 📝 БЛОК: ГЕНЕРАЦИЯ И ПРОВЕРКА SQL-ЗАПРОСОВ
    # ============================================================
    # Этот раздел содержит методы, которые анализируют пользовательские запросы,
    # генерируют SQL-код и проверяют его корректность.
    #
    # Методы в этом разделе:
    # - generate_sql: Генерирует SQL-запрос на основе пользовательского запроса.
    # - verify_sql_query: Проверяет SQL-запрос перед выполнением на корректность.
    # - _extract_sql_queries: Извлекает SQL-код из текстового ответа модели.
    # - narrow_query_analyzer: Оптимизирует SQL-запрос перед выполнением.
    # - analyze_sql_result: Анализирует результат SQL-запроса и формирует ответ.
    #
    # Эти методы работают в связке с OpenAI API и используются для работы с SQL.
    def refine_user_intent(self, user_query, db_structure):
        """
        Переформулирует пользовательский запрос, уточняя его смысл для точной генерации SQL.
        """
        prompt = f"""
    Ты — эксперт по анализу данных.

    Задача: понять смысл запроса пользователя и логически переформулировать его так, чтобы стало понятно, какой именно SQL-запрос нужно построить.

    Напиши кратко и точно, что именно нужно получить из базы данных, с акцентом на:
    - что выбрать,
    - по какому критерию сортировать,
    - какие агрегаты использовать,
    - сколько строк (например, "топ-1", "топ-10").

    Структура базы данных:
    {json.dumps(self.db.get_compact_structure(), indent=2, ensure_ascii=False)}

    Исходный запрос:
    "{user_query}"

    Ответи только уточнённой формулировкой задачи. Без SQL и лишних пояснений.
    """
        try:
            return self.ai_client.chat(prompt).strip()
        except Exception as e:
            logger.warning(f"❗ Не удалось переформулировать запрос: {e}")
            return user_query

    def narrow_query_analyzer(self, query, history):
        """
        Анализирует узконаправленный SQL-запрос, уточняет его, генерирует SQL-код, выполняет его и анализирует результат.
        """
        try:
            # Шаг 1: уточнение запроса
            db_structure = self.db.get_compact_structure()
            refined_query = self.refine_user_intent(query, db_structure)
            logger.info(f"🔍 Уточнённый запрос: {refined_query}")

            # Шаг 2: генерация SQL на основе уточнённого запроса
            engine = SmartSQLEngine(db=self.db, ai_client=self.ai_client)
            sql_queries = engine.generate(refined_query, history)
            if not sql_queries:
                logger.warning("❌ Не удалось сгенерировать SQL-запрос.")
                return "Не удалось обработать ваш запрос. Попробуйте задать его по-другому."

            final_analysis = ""

            for sql_query in sql_queries:
                logger.info(f"📥 Выполнение SQL-запроса: {sql_query}")
                result_list = self.db.execute([sql_query])

                for result in result_list:
                    if isinstance(result, list):  # результат запроса (SELECT)
                        analysis = self.analyze_sql_result(result, query, history, sql_query=sql_query)
                    else:
                        analysis = str(result)

                    escaped_query = html.escape(sql_query)
                    final_analysis += f"<b>Использованный SQL-запрос:</b>\n<pre>{escaped_query}</pre>\n\n<b>Результат анализа:</b>\n{analysis}\n\n"

            logger.info("✅ Анализ SQL-запроса завершён.")
            return final_analysis.strip()

        except Exception as e:
            logger.critical(f"💥 Ошибка при анализе запроса: {e}", exc_info=True)
            return "Произошла ошибка при анализе запроса. Попробуйте снова."

    def analyze_sql_result(self, sql_result, query, history, sql_query=None):
        """
        Анализирует результат SQL-запроса и отвечает на вопрос пользователя, основываясь на полученных данных.
        """
        if not sql_result:
            logging.warning("Нет данных для анализа результата запроса.")
            return "Результаты запроса не содержат данных. Проверьте правильность запроса или условия выборки."

        # Генерация строки результата SQL-запроса
        result_string = "\n".join([str(row) for row in sql_result])

        # Формирование промта для модели
        prompt = self._generate_sql_analysis_prompt(result_string, query, history, sql_query=sql_query)

        try:
            # Отправка запроса в модель
            analysis = self.chatgpt_request(prompt, maximum_tokens=2000, temperature=0.3)

            if not analysis:
                logging.warning("Модель вернула пустой ответ.")
                return "Не удалось получить ответ от модели."

            logging.info("Анализ SQL результата успешно получен.")
            return analysis

        except requests.exceptions.RequestException as error:
            logging.error(f"Ошибка при запросе к модели: {error}", exc_info=True)
            return "Ошибка при запросе к модели."

        except Exception as error:
            logging.error(f"Неожиданная ошибка при анализе результата SQL-запроса: {error}", exc_info=True)
            return "Неожиданная ошибка при анализе результата запроса."

    def _generate_sql_analysis_prompt(self, result_string, query, history, sql_query=None):
        """
        Формирует промт для модели для анализа результата SQL-запроса.
        """
        prompt = (
            "You are a highly skilled database expert with deep knowledge of SQL queries and data analysis. "
            "Your task is to interpret the provided SQL query result and answer the user's question in a clear, confident, and slightly conversational tone.\n\n"
            "Предыдущие ответы пользователя и ИИ (контекст общения):\n"
            f"<history>\n{history}\n</history>\n\n"
        )

        if sql_query:
            prompt += f"SQL-запрос, который был выполнен:\n<sql>\n{sql_query}\n</sql>\n\n"

        prompt += (
            f"Результат выполнения запроса:\n{result_string}\n\n"
            "Вопрос пользователя:\n"
            f"{query}\n\n"
            "На основе SQL-запроса и полученных данных:\n"
            "- Назови лучший результат (если применён LIMIT 1 — считай, что это наибольшее значение).\n"
            "- В одном-двух предложениях поясни, почему именно этот результат оказался лучшим — например, по сумме продаж или количеству.\n"
            "- Пиши по-русски, дружелюбно, но по делу. Без лишней формальности и технических терминов."
        )

        logging.debug("Промт для анализа SQL результата успешно сформирован.")
        return prompt

    # ============================================================
    # 🤖 БЛОК: ВЗАИМОДЕЙСТВИЕ С OPENAI API
    # ============================================================
    # Этот раздел содержит методы, которые взаимодействуют с моделью ChatGPT.
    # Методы отправляют запросы к API, получают и обрабатывают ответы.
    #
    # Методы в этом разделе:
    # - chatgpt_request: Универсальный метод для запроса к OpenAI API.
    # - chatgpt_request_online: Выполняет запрос к онлайн API OpenAI.
    # - chatgpt_request_local: Работает с локальной моделью (если поддерживается).
    # - classify_query: Классифицирует запрос пользователя (например, SQL или информационный).
    #
    # Эти методы позволяют боту понимать пользователя и генерировать корректные SQL-запросы.

    def classify_query(self, query: str, history: list = None) -> tuple[list[str], str]:
        def stringify_history_item(item):
            if isinstance(item, str):
                return item
            elif isinstance(item, dict):
                return item.get("query") or item.get("text") or str(item)
            return str(item)

        formatted_history = "\n".join(stringify_history_item(h) for h in (history or []))

        prompt = f"""
        You are an intelligent assistant specialized in understanding and classifying user requests about SQL databases.
        Your task is to infer the user's true intent, even when their phrasing is vague, indirect, or missing explicit keywords.

        Classify the request into one or more of the following **strictly defined** categories:

        - sql_generation:
          The user is asking for a SQL query or expression, regardless of whether the word “SQL” is used.
          The intent involves creating, reading, modifying, or deleting data via structured query language.

        - full_er_diagram_generation:
  The user requests an ER diagram that strictly represents the actual, defined structure of the database — that is, only relationships and entities that are explicitly defined in the schema (such as existing foreign keys). No speculative or inferred relationships. The output is a direct representation of the real database schema, without additions.

- er_diagram_generation:
  The user requests an ER diagram that may include both the real, defined structure *and* any additional relationships or connections that can be logically inferred, even if they are not explicitly defined in the schema. The output can be the full schema or a part of it, but is enhanced by the AI’s reasoning, filling gaps, suggesting likely connections, or hypothesizing missing links for better understanding or visualization.

        - general_db_info:
          The user wants to understand the meaning, function, or role of tables, fields, or the database as a whole.
          The focus is explanation and documentation, not data retrieval or transformation.

        - narrow_query:
          The user seeks specific data insights from actual database content — such as totals, ranks, comparisons, or filters.
          The request is narrow in scope and oriented toward the data, not the schema.

        - other:
          Everything that doesn't belong to the categories above — including off-topic questions, chit-chat, jokes, vague statements, or unclear intent.

        ---

        <query>
        {query.strip()}
        </query>

        <context>
        {formatted_history}
        </context>

        Your response must be a single valid JSON object, like:
        {{
          "type": [...],
          "reasoning": "..."
        }}

        Be precise. Think before answering. Output only valid JSON.
        """

        logger.debug("🤖 Prompt для классификации:\n" + prompt)
        response = self.ai_client.chat(prompt, temperature=0.7, max_tokens=500)
        logger.debug("📩 Ответ от ИИ:\n" + str(response))

        try:
            if isinstance(response, dict):
                result = response
            else:
                result = extract_json_from_response(response)

            return result.get("type", ["other"]), result.get("reasoning", "")
        except Exception as e:
            logger.warning("⚠️ Ошибка парсинга классификации: %s", e)
            return ["other"], "Failed to parse classification response"

    # ============================================================
    # 📊 БЛОК: ГЕНЕРАЦИЯ И АНАЛИЗ ER-ДИАГРАММ
    # ============================================================
    # Этот раздел содержит методы для работы с ER-диаграммами.
    # Они позволяют визуализировать структуру базы данных и связи между таблицами.
    #
    # Методы в этом разделе:
    # - generate_er_diagram_for_all: Генерирует ER-диаграмму для всей базы.
    # - generate_er_diagram: Создает ER-диаграмму для конкретных таблиц.
    # - analyze_query_for_relationships: Анализирует SQL-запрос и выявляет связи между таблицами.
    # - _generate_table_html_label: Формирует HTML-разметку таблицы для ER-диаграммы.
    #
    # Эти методы используются для наглядного отображения структуры базы в чат-боте.

    def analyze_query_for_relationships(self, query, history):
        try:
            structure = self.db.get_compact_structure()
            prompt = self.build_relationship_prompt(query, history, structure)
            logger.debug("📤 Prompt, отправляемый ИИ:\n" + prompt)

            model_response = self.ai_client.chat(prompt)
            logger.debug("📩 Ответ от модели:\n" + model_response)

            response_data = extract_json_from_response(model_response)
            tables = response_data.get("tables", [])
            relationships = response_data.get("relationships", [])

            valid_tables = set(self.db.get_tables_info().keys())
            invalid_tables = [t for t in tables if t not in valid_tables]
            if invalid_tables:
                logger.warning(f"⚠️ Модель указала таблицы, которых нет в базе: {', '.join(invalid_tables)}")

            filtered_tables = [t for t in tables if t in valid_tables]
            validated_relationships = self._validate_relationships(relationships)

            # 🔁 Добавляем недостающие таблицы из validated_relationships
            for rel in validated_relationships:
                t1 = rel["table1"]
                t2 = rel["table2"]
                if t1 not in filtered_tables:
                    filtered_tables.append(t1)
                if t2 not in filtered_tables:
                    filtered_tables.append(t2)

            if not filtered_tables:
                logger.warning("ИИ не выделил допустимых таблиц.")
                return None

            all_info = self.db.get_tables_info()
            diagram_generator = ERDiagramGenerator(all_info)
            return diagram_generator.generate_diagram_from_logic(filtered_tables, validated_relationships)

        except Exception as e:
            logger.error(f"❌ Ошибка при генерации логической ER-диаграммы: {e}", exc_info=True)
            return None

    def _validate_relationships(self, relationships):
        validated = []
        table_info = self.db.get_tables_info()
        for rel in relationships:
            t1 = rel.get("table1")
            t2 = rel.get("table2")
            join = rel.get("joining_columns", {})
            col1 = join.get(f"{t1}_column") or join.get(f"{t1.lower()}_column")
            col2 = join.get(f"{t2}_column") or join.get(f"{t2.lower()}_column")

            if not all([t1, t2, col1, col2]):
                continue

            if (
                t1 in table_info and
                t2 in table_info and
                col1 in table_info[t1]["columns"] and
                col2 in table_info[t2]["columns"]
            ):
                validated.append(rel)
            else:
                logger.warning(f"❌ Некорректная связь от ИИ: {t1}.{col1} ↔ {t2}.{col2}")
        return validated

    @staticmethod
    def build_relationship_prompt(query, history, structure: dict) -> str:
        logger.debug("Подаётся структура:\n" + json.dumps(structure, indent=2))
        logger.debug(f"История:\n{history}")
        logger.debug(f"Запрос:\n{query}")

        return f"""
    ⚠️ IMPORTANT:
    Only refer to tables and columns listed in <structure>.
    Do NOT invent tables or names that are not in the structure.
    1. Include all explicit foreign key relationships.
2. For "guessed" (inferred) relationships, only suggest if:
    - Both columns have compatible types (e.g., both INTEGER, or both TEXT).
    - The target column is a primary key or unique identifier.
    - The source column name suggests it references the target (e.g., "UserId" → "Users"."Id").
    - соблюдай тип атрибутов в связях таблицы, TEXT не совместим с INTEGER, INTEGER только с INTEGER
3. Do NOT match TEXT fields unless the naming and context is extremely clear.
4. If the best possible guess is still a weak connection, include a field "comment" with your reasoning.
5. If in doubt, **prefer not to add a guessed relationship**.

    ➕ Include all intermediary tables required to connect endpoints (even if not directly asked).
    📌 Use \"joining_columns\" instead of \"columns\", like this:

    \"joining_columns\": {{
      \"table1_column\": \"CustomerId\",
      \"table2_column\": \"CustomerId\"
    }}

    You are a smart SQL assistant. Your task is to identify which tables and fields are relevant to the following user query,
    and how they may be logically or structurally connected.
    

    <query>
    {query}
    </query>

    <history>
    {history}
    </history>

    <structure>
    {json.dumps(structure, indent=2)}
    </structure>

    Respond in JSON format like this:
    {{
      "tables": ["table1", "table2"],
      "relationships": [
        {{
          "table1": "table1",
          "table2": "table2",
          "joining_columns": {{
            "table1_column": "column_name",
            "table2_column": "column_name"
          }}
        }}
      ]
    }}
    """

    def generate_er_diagram(self, relevant_tables=None):
        diagram_generator = ERDiagramGenerator(self.db.get_tables_info())
        return diagram_generator.generate_diagram(relevant_tables=relevant_tables)

    def generate_info(self, query, history):
        """
        Гипер-интеллектуальный режим анализа пользовательского вопроса по БД.
        Анализирует структуру, рассуждает, может инициировать действия (SQL/диаграммы), отвечает умно.
        """
        if not self.db.get_tables_info():
            logging.warning("База данных пуста. Создайте таблицы перед запросом информации.")
            return "База данных пуста. Добавьте таблицы для анализа."

        try:
            db_structure = self._generate_db_structure()
            prompt = self._generate_info_prompt(query, db_structure, history)
            response = self.chatgpt_request(prompt, maximum_tokens=2000, temperature=0.7)

            if not response:
                logging.warning("Модель вернула пустой ответ.")
                return "Не удалось интерпретировать ваш запрос. Попробуйте иначе."

            plan = self._extract_tag(response, "plan")
            action = self._extract_tag(response, "action")
            answer = self._extract_tag(response, "answer")

            if not any([plan, action, answer]):
                fallback_answer = response.strip()
                if fallback_answer:
                    logging.warning("⚠️ Ответ без тегов. Используем fallback.")
                    return fallback_answer

                logging.warning("Ответ не содержит ни одного корректного тега.")
                return "⚠️ Не удалось интерпретировать ответ модели. Попробуйте переформулировать запрос."

            logging.info(f"Ответ модели получен.\nPLAN: {plan}\nACTION: {action}\nANSWER: {answer}")

            if action:
                if "SELECT" in action.upper():
                    try:
                        result = self.db.execute([action])
                        return f"📋 Запрос выполнен.\n\n<pre>{action}</pre>\n\nРезультаты:\n{result}"
                    except Exception as e:
                        logging.error(f"Ошибка при выполнении SQL из AI-действия: {e}")
                        return f"Ошибка при выполнении SQL: {e}"
                elif "diagram" in action.lower():
                    try:
                        path = self.generate_er_diagram()
                        return f"📈 Схема построена: {path}"
                    except Exception as e:
                        return f"Ошибка при построении схемы: {e}"

            return answer or response

        except Exception as error:
            logging.error(f"Ошибка при гипер-анализе запроса: {error}", exc_info=True)
            return "Произошла ошибка при анализе. Попробуйте позже."

    def _generate_info_prompt(self, query, db_structure, history):
        db_structure_json = json.dumps(db_structure, ensure_ascii=False, indent=2)
        return (
                "Ты продвинутый ИИ-ассистент по базам данных. Твоя задача — понимать структуру базы и анализировать пользовательский вопрос.\n\n"
                "Контекст общения:\n<history>\n" + str(history) + "\n</history>\n\n"
                                                                  "Структура базы данных:\n<database_structure>\n" + db_structure_json + "\n</database_structure>\n\n"
                                                                                                                                         "Инструкция:\n"
                                                                                                                                         "1. Если нужно — подумай, и опиши шаги в <plan>.\n"
                                                                                                                                         "2. Если нужен SQL — вставь его в <action> как SQL-запрос.\n"
                                                                                                                                         "3. Если нужно нарисовать схему — напиши 'diagram' в <action>.\n"
                                                                                                                                         "4. Выводи окончательный ответ в <answer>.\n"
                                                                                                                                         "5. Пиши понятно, на русском.\n\n"
                                                                                                                                         f"Вопрос пользователя:\n<user_question>\n{query}\n</user_question>\n"
                                                                                                                                         "Если вопрос простой, всё равно используй теги, даже если это всего один абзац. Например, <answer>Таблицы: ...</answer>\n"

        )

    def _extract_tag(self, text, tag):
        try:
            # Чёткое соответствие полным тегам
            pattern = fr"<{tag}>([\s\S]*?)</{tag}>"
            match = re.search(pattern, text, re.IGNORECASE)
            return match.group(1).strip() if match else ""
        except Exception as e:
            logging.warning(f"Не удалось извлечь тег {tag}: {e}")
            return ""
