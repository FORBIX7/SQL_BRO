import graphviz
import os
import tempfile
import logging
import json

logger = logging.getLogger("ERDiagramGenerator")

class ERDiagramGenerator:
    def __init__(self, tables_info):
        self.tables_info = tables_info

    def _flatten_foreign_keys(self) -> dict:
        mapping = {}
        for table_name, table_data in self.tables_info.items():
            for col, ref in table_data.get("foreign_keys", {}).items():
                mapping[f"{table_name}.{col}"] = ref
        return mapping

    def _create_table_node(self, dot, table_name, columns):
        label = f"""<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">
<TR><TD COLSPAN="2" BGCOLOR="#D0E6F8"><B>{table_name}</B></TD></TR>"""
        for col, dtype in columns.items():
            col_style = f"<B><U>{col}</U></B>" if self._is_primary_key(table_name, col) else col
            label += f'<TR><TD ALIGN="LEFT" PORT="{col}">{col_style}</TD><TD>{dtype}</TD></TR>'
        label += "</TABLE>>"
        dot.node(table_name, label=label, shape="plaintext")

    def _is_primary_key(self, table_name, column):
        return column in self.tables_info.get(table_name, {}).get("primary_keys", [])

    def generate_diagram(self, relevant_tables=None, output_path=None) -> str:
        import graphviz
        import tempfile
        import os

        dot = graphviz.Digraph(comment="ER Diagram", format='png')
        dot.attr(rankdir='LR', bgcolor='white', fontname='Arial', fontsize="10", nodesep="0.6", ranksep="0.6")
        dot.attr(dpi='300')

        included_tables = relevant_tables if relevant_tables else self.tables_info.keys()

        for table_name in included_tables:
            info = self.tables_info.get(table_name, {})
            logging.debug(f"[DEBUG] Таблица: {table_name}")
            logging.debug(f"[DEBUG] Первичные ключи: {info.get('primary_keys')}")
            logging.debug(f"[DEBUG] Внешние ключи: {info.get('foreign_keys')}")

        # Отрисовка узлов таблиц
        for table_name in included_tables:
            info = self.tables_info.get(table_name, {})
            columns = info.get("columns", {})
            if not columns:
                continue  # Пропускаем таблицы без колонок
            self._create_table_node(dot, table_name, columns)

        # Отрисовка связей (foreign keys)
        for table_name in included_tables:
            table = self.tables_info.get(table_name, {})
            for fk_col, target in table.get("foreign_keys", {}).items():
                try:
                    target_table, target_col = target.split(".")
                    if target_table in included_tables:
                        logging.debug(f"[DEBUG] Рисуем связь: {target_table}.{target_col} → {table_name}.{fk_col}")
                        dot.edge(
                            f"{target_table}:{target_col}",
                            f"{table_name}:{fk_col}",
                            label=f"{target_col} → {fk_col}",
                            arrowhead="vee",
                            style="solid",
                            color="black"
                        )
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка в foreign key {table_name}.{fk_col} → {target}: {e}")

        if not output_path:
            temp_dir = tempfile.mkdtemp()
            output_path = os.path.join(temp_dir, "er_diagram")

        try:
            rendered = dot.render(filename=output_path, cleanup=True)
            logger.debug(f"Диаграмма сохранена: {rendered}")
            return rendered
        except Exception as e:
            logger.error(f"Ошибка при рендеринге диаграммы: {e}", exc_info=True)
            return None

    def generate_diagram_from_logic(self, tables: list, relationships: list, output_path=None) -> str:
        import uuid
        import os

        os.makedirs("./generated", exist_ok=True)

        dot = graphviz.Digraph(comment="Logical ER Diagram", format='png')
        dot.attr(rankdir='LR', bgcolor='white', fontname='Arial', fontsize="10", nodesep="0.6", ranksep="0.6")
        dot.attr(dpi='300')

        # Отрисовываем таблицы
        for table_name in tables:
            info = self.tables_info.get(table_name, {})
            columns = info.get("columns", {})
            self._create_table_node(dot, table_name, columns)

        # ✅ Сохраняем реальные связи, чтобы не дублировать их
        real_edges = set()

        for table_name in tables:
            info = self.tables_info.get(table_name, {})
            for fk_col, target in info.get("foreign_keys", {}).items():
                try:
                    target_table, target_col = target.split(".")
                    if target_table in tables:
                        # Сохраняем в обеих направлениях для простоты сравнения
                        real_edges.add((table_name, fk_col, target_table, target_col))
                        real_edges.add((target_table, target_col, table_name, fk_col))

                        dot.edge(
                            f"{target_table}:{target_col}",
                            f"{table_name}:{fk_col}",
                            label=f"{target_col} → {fk_col}",
                            arrowhead="vee",
                            style="solid",
                            color="black"
                        )
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка в связи {table_name}.{fk_col} → {target}: {e}")

        # ✅ Добавляем логические связи от ИИ, если они не дублируют реальные
        for rel in relationships:
            t1 = rel.get("table1")
            t2 = rel.get("table2")
            join = rel.get("joining_columns", {})
            col1 = join.get(f"{t1}_column") or join.get(f"{t1.lower()}_column")
            col2 = join.get(f"{t2}_column") or join.get(f"{t2.lower()}_column")

            if not all([t1, t2, col1, col2]):
                continue

            # 🔒 Пропускаем, если уже есть как реальная связь
            if (t1, col1, t2, col2) in real_edges:
                continue

            is_guessed = rel.get("guessed", False)
            style = "dashed" if is_guessed else "solid"
            color = "blue" if is_guessed else "black"
            label = f"{col2} → {col1}" + (" [guessed]" if is_guessed else "")

            dot.edge(
                f"{t2}:{col2}",
                f"{t1}:{col1}",
                label=label,
                arrowhead="vee",
                style=style,
                color=color
            )

        unique_name = f"er_logical_{uuid.uuid4().hex[:8]}"
        output_path = os.path.join("generated", unique_name)

        try:
            rendered_path = dot.render(filename=output_path, cleanup=True)
            logger.debug(f"Диаграмма сохранена: {rendered_path}")
            return rendered_path
        except Exception as e:
            logger.error(f"Ошибка при рендеринге логической диаграммы: {e}", exc_info=True)
            return None
