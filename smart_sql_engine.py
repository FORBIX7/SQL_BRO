import difflib
import json
import re
import logging

logger = logging.getLogger("SmartSQLEngine")

class SmartSQLEngine:
    def __init__(self, ai_client, db):
        self.ai = ai_client
        self.db = db

    def generate(self, user_query: str, history: list = None) -> list[str]:
        history = history or []
        structure = self.db.get_compact_structure()
        query_type = self._determine_query_type(user_query)

        try:
            if query_type == "select":
                sqls = self._handle_select(user_query, structure, history)
            elif query_type == "create":
                sqls = self._handle_create(user_query, structure, history)
            elif query_type in ["insert", "update", "delete"]:
                sqls = self._handle_mutation(user_query, structure, history)
            else:
                sqls = self._handle_general(user_query, structure, history)
        except Exception as e:
            logger.warning(f"⚠️ Первая попытка генерации SQL вызвала исключение: {e}")
            sqls = []

        if not sqls or all(not s.strip() for s in sqls):
            logger.warning("⚠️ Первая генерация SQL не дала результата. Пробуем fallback...")
            fallback_prompt = f"Попробуй по-другому: {user_query}"
            sql = self._generate_sql_unbound(fallback_prompt, structure, history)
            sqls = [sql] if sql.strip() else []

        if not sqls or all(not s.strip() for s in sqls):
            raise RuntimeError("Модель не смогла сгенерировать SQL-запрос.")

        return sqls

    def _handle_select(self, user_query, structure, history):
        sel = self._select_tables(user_query, structure, history)
        tables = sel.get("tables", [])
        joins = self._validate_joins(sel.get("joins", []), structure)

        if not tables:
            raise RuntimeError("Не удалось определить таблицы для запроса.")

        sql = self._generate_sql_for_tables(user_query, tables, joins, structure, history)
        return self._execute_and_postprocess(sql, tables, query_type="select")

    def _handle_create(self, user_query, structure, history):
        sql = self._generate_sql_unbound(user_query, structure, history)
        return self._execute_and_postprocess(sql, [], query_type="create")

    def _handle_mutation(self, user_query, structure, history):
        sel = self._select_tables(user_query, structure, history)
        tables = sel.get("tables", [])
        joins = self._validate_joins(sel.get("joins", []), structure)
        sql = self._generate_sql_for_tables(user_query, tables, joins, structure, history)
        return self._execute_and_postprocess(sql, tables, query_type="mutation")

    def _handle_general(self, user_query, structure, history):
        sql = self._generate_sql_unbound(user_query, structure, history)
        return self._execute_and_postprocess(sql, [], query_type="general")

    def _execute_and_postprocess(self, sql, tables, query_type):
        queries = [sql]
        try:
            self.db.execute(queries)
            logger.info("✅ SQL выполнен успешно.")

            post_action = self._post_execution_followup(sql, tables, query_type)
            if post_action:
                self.db.execute([post_action])
                queries.append(post_action)

            return queries  # ← Возвращаем результат УСПЕШНОГО выполнения

        except Exception as e:
            if "already exists" in str(e).lower():
                logger.warning("⚠️ Таблица уже существует. Пропускаем ошибку.")
            else:
                logger.warning(f"⚠️ Ошибка выполнения SQL: {e}. Отправляем LLM на исправление.")
                fixed = self._fix_sql(sql, "", str(e), self.db.get_compact_structure(), [])
                if fixed:
                    try:
                        self.db.execute([fixed])
                        logger.info("✅ SQL после исправления ЛЛМ выполнен успешно.")
                        return [fixed]
                    except Exception as e2:
                        logger.error(f"❌ Повторная ошибка выполнения SQL после исправления ЛЛМ: {e2}")
                raise RuntimeError("Не удалось исправить SQL с помощью LLM.")

            return queries  # ← В случае «таблица уже существует»

        except Exception as e:
            logger.warning(f"⚠️ Ошибка выполнения SQL: {e}. Отправляем LLM на исправление.")
            fixed = self._fix_sql(sql, "", str(e), self.db.get_compact_structure(), [])
            if fixed:
                try:
                    self.db.execute([fixed])
                    logger.info("✅ SQL после исправления ЛЛМ выполнен успешно.")
                    return [fixed]
                except Exception as e2:
                    logger.error(f"❌ Повторная ошибка выполнения SQL после исправления ЛЛМ: {e2}")
            raise RuntimeError("Не удалось исправить SQL с помощью LLM.")

    def _determine_query_type(self, user_query: str) -> str:
        """
        Определяет тип SQL-запроса на основе пользовательского вопроса с помощью LLM.
        Возвращает один из: 'select', 'insert', 'update', 'delete', 'create', 'other'.
        """
        prompt = f"""
    Ты классификатор SQL-запросов. Задача — определить тип SQL-запроса, который, скорее всего, нужен для выполнения пользовательского запроса.

    Возможные типы:
    - select: если пользователь хочет получить данные или провести анализ
    - insert: если хочет добавить данные
    - update: если хочет обновить данные
    - delete: если хочет удалить записи
    - create: если хочет создать новую таблицу
    - other: если запрос не относится к SQL

    Пример формата ответа: select

    Запрос пользователя:
    "{user_query}"

    Ответи только типом (например: select).
    """
        try:
            result = self.ai.chat(prompt).strip().lower()
            if result in ["select", "insert", "update", "delete", "create", "other"]:
                return result
            logger.warning(f"⚠️ Непредвиденный тип запроса от модели: {result}")
        except Exception as e:
            logger.error(f"❌ Ошибка при классификации запроса: {e}")

        return "select"  # безопасный дефолт

    def _generate_sql_unbound(self, user_query, structure, history):
        prompt = f'''
        Generate a valid SQL query based on the user's request.
        The database may not yet contain the target table.
        If the query creates a table, always use: CREATE TABLE IF NOT EXISTS
        If the query deletes a table, always use: DELETE TABLE IF NOT EXISTS
        
        ⚠️ Ensure the query is compatible with SQLite, MySQL, and PostgreSQL:
- Do NOT use AUTO_INCREMENT.
- Use INTEGER PRIMARY KEY for auto-incrementing IDs.
- Prefer TEXT over VARCHAR(n).
- Use CURRENT_TIMESTAMP for default timestamps.

        User request:
        {user_query}

        Existing structure:
        {json.dumps(structure, indent=2, ensure_ascii=False)}

        Output ONLY the SQL inside <sql>...</sql> tags.
        '''
        logger.debug("📤 Prompt без таблиц:\n" + prompt)
        resp = self.ai.chat(prompt)
        return self._extract_sql(resp)

    def _select_tables(self, user_query, structure, history) -> dict:
        prompt = f"""
        You are a database schema expert.
        Given the query and the structure, list:
          1) the tables that are needed
          2) the JOIN conditions between them

        <query>
        {user_query}
        </query>

        <structure>
        {json.dumps(structure, indent=2, ensure_ascii=False)}
        </structure>

        Respond with JSON ONLY in the following format:
        <json>
        {{
          "tables": ["table1", "table2", ...],
          "joins": [
            {{"t1": "tableA", "c1": "colA", "t2": "tableB", "c2": "colB"}},
            ...
          ]
        }}
        </json>
        """
        logger.debug("📤 Prompt для выбора таблиц:\n" + prompt)
        resp = self.ai.chat(prompt)
        logger.debug("📩 Ответ (таблицы/joins):\n" + resp)
        return self._extract_json(resp)

    def _validate_joins(self, joins, structure):
        valid = []
        for join in joins:
            t1, c1, t2, c2 = join.get("t1"), join.get("c1"), join.get("t2"), join.get("c2")
            if t1 in structure and t2 in structure:
                if c1 in structure[t1]["columns"] and c2 in structure[t2]["columns"]:
                    valid.append(join)
                else:
                    logger.warning(f"❌ Пропущен join из-за отсутствующих колонок: {join}")
            else:
                logger.warning(f"❌ Пропущен join из-за неизвестных таблиц: {join}")
        return valid

    def _generate_sql_for_tables(self, user_query, tables, joins, structure, history) -> str:
        prompt = f"""
        Generate a valid SQL query (SELECT, INSERT, UPDATE, DELETE)
        that satisfies the user's request and follows the structure of the database.

        Use ONLY the following tables: {tables}
        Apply JOINs where needed: {joins}

        User request:
        {user_query}

        Database structure:
        {json.dumps(structure, indent=2, ensure_ascii=False)}

        Output ONLY the SQL inside <sql>...</sql> tags.
        """
        logger.debug("📤 Prompt для генерации SQL:\n" + prompt)
        resp = self.ai.chat(prompt)
        logger.debug("📩 Ответ (SQL):\n" + resp)
        return self._extract_sql(resp)

    def _post_execution_followup(self, sql: str, tables: list, query_type: str) -> str:
        sql_upper = sql.strip().upper()
        main_table = tables[0] if tables else None

        if query_type in ["insert", "update", "delete"] and main_table:
            return f"SELECT * FROM {main_table} LIMIT 20;"
        if query_type == "create":
            return "PRAGMA table_list;"
        return ""

    def _fix_sql(self, previous_sql, user_query, error_msg, structure, history) -> str:
        if "no such column" in error_msg.lower():
            missing_column_match = re.search(r"no such column: ([\w\.]+)", error_msg, re.IGNORECASE)
            if missing_column_match:
                missing_col = missing_column_match.group(1).split('.')[-1]
                all_columns = [col for t in structure.values() for col in t["columns"].keys()]
                closest = difflib.get_close_matches(missing_col, all_columns, n=1, cutoff=0.6)
                if closest:
                    fixed_sql = re.sub(rf"\b{missing_col}\b", closest[0], previous_sql)
                    logger.info(f"🔧 Заменили '{missing_col}' на ближайшее '{closest[0]}'")
                    return fixed_sql + ";" if not fixed_sql.strip().endswith(";") else fixed_sql

        prompt = f"""
        An error occurred during execution:
        {error_msg}

        SQL code:
        <sql>
        {previous_sql}
        </sql>

        Fix this SQL so that it satisfies the following request:
        "{user_query}"

        Use tables from the structure:
        {json.dumps(structure, indent=2, ensure_ascii=False)}

        Output ONLY the corrected SQL inside <sql>…</sql> tags.
        """
        logger.debug("📤 Prompt для автокоррекции SQL:\n" + prompt)
        resp = self.ai.chat(prompt)
        logger.debug("📩 Ответ (fixed SQL):\n" + resp)
        return self._extract_sql(resp)

    def _extract_json(self, text: str) -> dict:
        try:
            cleaned = re.sub(r"</?json>", "", text, flags=re.IGNORECASE).strip()
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            return json.loads(cleaned[start:end+1])
        except Exception as e:
            logger.error("❌ Не удалось распарсить JSON: %s", e)
            logger.debug("Сырой ответ:\n" + text)
            return {}

    def _extract_sql(self, text: str) -> str:
        try:
            logger.debug("📥 Ответ LLM:\n" + text)

            # Удаление <sql>...</sql> и <think>...</think>
            cleaned = re.sub(r"</?sql>", "", text, flags=re.IGNORECASE)
            cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"(PLAN|ACTION|ANSWER)\s*:", "", cleaned, flags=re.IGNORECASE).strip()

            # Попробуй найти SQL по ключевым словам
            m = re.search(r"(SELECT|INSERT|UPDATE|DELETE|CREATE|WITH)[\s\S]+?;", cleaned, re.IGNORECASE)
            sql = (m.group(0).strip() if m else cleaned).rstrip(";")

            if not sql or len(sql) < 10 or "<" in sql or ">" in sql:
                logger.warning("⚠️ SQL выглядит подозрительно или содержит HTML.")
            else:
                logger.info("📤 Извлечён SQL: %s", sql)

            return sql + ";" if sql else ""
        except Exception as e:
            logger.error("❌ Ошибка при извлечении SQL: %s", e)
            logger.debug("⚠️ Сырой ответ:\n" + text)
            return ""


