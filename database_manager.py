import sqlalchemy as sa
from sqlalchemy import MetaData, Table
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import inspect
import logging

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_type, db_path, proxy_user=None, proxy_pass=None, proxy_host=None, proxy_port=None):
        self.db_type = db_type
        self.db_path = db_path
        self.proxy_user = proxy_user
        self.proxy_pass = proxy_pass
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port

        self.engine = self._create_engine()
        self.metadata = MetaData()
        self.tables_info = {}
        self.failed_tables = []

        self.load()

    def _create_engine(self):
        if self.db_type == 'sqlite':
            return sa.create_engine(f"sqlite:///{self.db_path}")
        elif self.db_type == 'mysql':
            return sa.create_engine(
                f"mysql+pymysql://{self.proxy_user}:{self.proxy_pass}@{self.proxy_host}:{self.proxy_port}/{self.db_path}")
        elif self.db_type == 'postgresql':
            return sa.create_engine(
                f"postgresql://{self.proxy_user}:{self.proxy_pass}@{self.proxy_host}:{self.proxy_port}/{self.db_path}")
        elif self.db_type == 'mariadb':
            return sa.create_engine(
                f"mariadb+pymysql://{self.proxy_user}:{self.proxy_pass}@{self.proxy_host}:{self.proxy_port}/{self.db_path}")
        elif self.db_type == 'oracle':
            return sa.create_engine(
                f"oracle+cx_oracle://{self.proxy_user}:{self.proxy_pass}@{self.proxy_host}:{self.proxy_port}/{self.db_path}")
        elif self.db_type == 'mssql':
            return sa.create_engine(
                f"mssql+pymssql://{self.proxy_user}:{self.proxy_pass}@{self.proxy_host}:{self.proxy_port}/{self.db_path}")
        else:
            raise ValueError(f"Unsupported database type: {self.db_type}")

    def load(self):
        try:
            self.metadata = MetaData()
            self.engine = self._create_engine()
            self.failed_tables = []

            inspector = inspect(self.engine)
            table_names = inspector.get_table_names()

            if not table_names:
                logger.warning("База данных не содержит таблиц.")
                self.tables_info = {}
                return

            logger.info(f"Найдены таблицы: {', '.join(table_names)}")

            # Отражаем таблицы по одной, чтобы не падать при ошибках
            for table_name in table_names:
                try:
                    Table(table_name, self.metadata, autoload_with=self.engine)
                except SQLAlchemyError as e:
                    logger.warning(f"Не удалось загрузить таблицу {table_name}: {e}")
                    self.failed_tables.append(table_name)

            if not self.metadata.tables:
                logger.warning("Ни одну таблицу не удалось отразить.")
                self.tables_info = {}
                return

            self._update_tables_info()

        except Exception as e:
            logger.critical(f"Критическая ошибка при загрузке базы данных: {e}")
            self.tables_info = {}

    def _update_tables_info(self):
        self.tables_info = {}
        for table_name in self.metadata.tables:
            table = self.metadata.tables[table_name]
            self.tables_info[table_name] = {
                'columns': {col.name: str(col.type) for col in table.columns},
                'primary_keys': [col.name for col in table.primary_key],
                'foreign_keys': {
                    fk.parent.name: str(fk.column.table.name) + '.' + fk.column.name
                    for fk in table.foreign_keys
                }
            }

    def get_compact_structure(self) -> dict:
        """
        Возвращает компактную структуру таблиц и связей для анализа ИИ.
        """
        result = {
            "tables": {},
            "foreign_keys": {}
        }
        for table_name, info in self.get_tables_info().items():
            result["tables"][table_name] = []
            for col_name, col_type in info["columns"].items():
                marker = ""
                if col_name in info.get("primary_keys", []):
                    marker = " (PK)"
                elif col_name in info.get("foreign_keys", {}):
                    marker = " (FK)"
                result["tables"][table_name].append(f"{col_name}{marker}")
            for fk_col, ref in info.get("foreign_keys", {}).items():
                result["foreign_keys"][f"{table_name}.{fk_col}"] = ref
        return result

    def execute(self, queries):
        results = []
        try:
            with self.engine.connect() as connection:
                for query in queries:
                    try:
                        result = connection.execute(sa.text(query))
                        if result.returns_rows:
                            rows = result.fetchall()
                            results.append(rows)
                        else:
                            connection.commit()
                            results.append("Запрос выполнен успешно.")
                    except SQLAlchemyError as e:
                        logger.error(f"SQL ошибка: {e}")
                        return [f"Ошибка выполнения SQL: {e}"]
            return results
        except Exception as e:
            logger.critical(f"Ошибка подключения к базе данных: {e}")
            return [f"Критическая ошибка: {e}"]

    def get_tables_info(self):
        return self.tables_info

    def get_metadata(self):
        return self.metadata

    def get_summary_report(self) -> str:
        """
        Возвращает строку с кратким отчётом:
        - какие таблицы загружены
        - какие не удалось загрузить
        """
        report = []

        if self.tables_info:
            report.append("📊 Загружены таблицы:\n" + "\n".join(f"• {t}" for t in self.tables_info))
        else:
            report.append("⚠️ В базе данных не удалось загрузить ни одной таблицы.")

        if self.failed_tables:
            report.append(
                "\n❌ Не удалось загрузить таблицы:\n" + "\n".join(f"• {t}" for t in self.failed_tables)
            )

        return "\n".join(report)
