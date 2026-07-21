from aiogram.client import telegram
from telegram import Update
from telegram.ext import ContextTypes
import os
import logging
import pandas as pd
import sqlite3
import pyodbc

from bot.split_message import split_message
from agent_manager import AgentManager

async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        document = update.message.document
        if not document:
            await update.message.reply_text("Ошибка: файл не найден. Попробуйте снова.")
            return

        allowed_extensions = {'.sqlite', '.db', '.accdb', '.mdb', '.csv', '.xlsx'}
        file_extension = os.path.splitext(document.file_name)[-1].lower()
        if file_extension not in allowed_extensions:
            await update.message.reply_text(
                "Неподдерживаемый тип файла. Используйте: .sqlite, .db, .accdb, .mdb, .csv, .xlsx"
            )
            return

        file = await document.get_file()
        original_path = f"databases/{document.file_name}"
        os.makedirs(os.path.dirname(original_path), exist_ok=True)
        await file.download_to_drive(original_path)

        db_type = 'sqlite'
        db_path = original_path  # обновится при необходимости

        # CSV / Excel → SQLite
        if file_extension in {'.csv', '.xlsx'}:
            db_path = f"{original_path}.sqlite"
            try:
                if file_extension == '.csv':
                    df = pd.read_csv(original_path)
                else:
                    df = pd.read_excel(original_path)

                conn = sqlite3.connect(db_path)
                table_name = os.path.splitext(document.file_name)[0].replace(" ", "_")
                df.to_sql(table_name, conn, if_exists='replace', index=False)
                conn.close()

            except Exception as e:
                logging.error(f"Ошибка pandas: {e}", exc_info=True)
                await update.message.reply_text(f"Ошибка при обработке {file_extension}-файла: {e}")
                return

        # Access → SQLite
        elif file_extension in {'.accdb', '.mdb'}:
            db_path = f"{original_path}.sqlite"
            try:
                conn_str = (
                    r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
                    rf'DBQ={original_path};'
                )
                acc_conn = pyodbc.connect(conn_str)
                cursor = acc_conn.cursor()

                tables = [row.table_name for row in cursor.tables(tableType='TABLE')]
                sqlite_conn = sqlite3.connect(db_path)

                for table in tables:
                    df = pd.read_sql(f"SELECT * FROM [{table}]", acc_conn)
                    df.to_sql(table, sqlite_conn, if_exists='replace', index=False)

                acc_conn.close()
                sqlite_conn.close()

            except Exception as e:
                logging.error(f"Ошибка Access: {e}", exc_info=True)
                await update.message.reply_text(f"Ошибка при обработке Access-файла: {e}")
                return

        # SQLite — без изменений
        elif file_extension in {'.sqlite', '.db'}:
            db_path = original_path

        # Создаем или обновляем агента с новой базой
        agent = AgentManager.get_agent(context, db_type=db_type, db_path=db_path, force_reload=True)
        context.user_data['user_context']['agent'] = agent

        try:
            agent.db.load()
        except Exception as e:
            logging.error(f"Ошибка при загрузке базы: {e}", exc_info=True)
            await update.message.reply_text("Ошибка при загрузке базы данных. Проверьте файл и повторите.")
            return

        tables_info = agent.display_tables_info()
        message = (
            f"База данных {document.file_name} загружена и подключена.\n"
            f"Доступные таблицы:\n{tables_info if tables_info else 'Таблицы не найдены.'}"
        )

        # ➕ Добавим информацию о проблемных таблицах
        if agent.db.failed_tables:
            message += (
                    "\n\n❌ Некоторые таблицы не удалось загрузить:\n" +
                    "\n".join(f"• {t}" for t in agent.db.failed_tables) +
                    "\n\nПроверьте, возможно база неполная или структура отличается от ожидаемой."
            )

        for chunk in split_message(message):
            try:
                await update.message.reply_text(chunk, parse_mode="HTML")
            except telegram.error.BadRequest as e:
                logging.error(f"Ошибка при отправке сообщения: {e}")
                await update.message.reply_text("Ошибка при отправке результата. Проверьте Telegram-формат.")

    except Exception as e:
        logging.error(f"Ошибка при обработке файла: {e}", exc_info=True)
        await update.message.reply_text("Произошла ошибка при загрузке файла. Повторите попытку.")