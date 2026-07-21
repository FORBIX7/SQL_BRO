import sqlite3
import platform
import time

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import logging
from dotenv import load_dotenv
import os
import shutil
import subprocess
import pyodbc  # Не забудь указать в requirements.txt
from bot.register_handlers import register_handlers
import telegram

ENV_TEMPLATE = """
# 🔐 Telegram Bot Token
BOT_TOKEN=твой_токен_от_botfather

# 🔑 Ключ OpenAI (если используешь OpenAI напрямую)
OPENAI_API_KEY=sk-...

# 🌐 Прокси для OpenAI/OpenRouter (если нужен)
PROXY_HOST=proxy.host.com
PROXY_PORT=1234
PROXY_USERNAME=your_username
PROXY_PASSWORD=your_password

# 🗃️ Настройки базы данных
DB_TYPE=sqlite               # sqlite / access / mysql / ...
DB_PATH=databases/test.db    # путь до .db файла

# 🧠 URL локального LLM (например LM Studio или Ollama)
AI_API_URL=http://127.0.0.1:1234/v1/chat/completions

# 🧠 Провайдер ИИ (local / openai / openrouter)
AI_PROVIDER=openrouter

# 🤖 Модель по умолчанию:
# - openrouter: openai/gpt-3.5-turbo, meta-llama/llama-3.3-8b-instruct:free
# - openai: gpt-4o
# - local: llama3, mistral и др.
AI_MODEL=meta-llama/llama-3.3-8b-instruct:free

# 🔑 Ключ OpenRouter
OPENROUTER_API_KEY=sk-or-...
"""

def first_time_setup():
    print("[init] Проверка окружения...")

    if not os.path.exists(".env"):
        with open(".env", "w", encoding="utf-8") as f:
            f.write(ENV_TEMPLATE.strip())
        print("[init] 🧾 Сгенерирован .env с пояснениями")

        # Открытие в редакторе
        try:
            if platform.system() == "Windows":
                os.system("start notepad .env")
            elif platform.system() == "Darwin":
                os.system("open -t .env")
            else:
                os.system("nano .env")
        except Exception as e:
            print(f"⚠️ Не удалось открыть .env автоматически: {e}")

        print("\n✍️ Отредактируй .env и нажми [Enter] для запуска бота...")
        input()

    # Папки
    for folder in ["databases", "generated", "temp"]:
        if not os.path.exists(folder):
            os.makedirs(folder)
            print(f"[init] Создана папка: {folder}")

    # Тестовая база
    db_path = os.path.join("databases", "chinook.db")
    if not os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS demo (id INTEGER PRIMARY KEY, name TEXT);")
        conn.commit()
        conn.close()
        print("[init] Создана тестовая база данных")


    # 4. Проверка Graphviz
    if shutil.which("dot") is None:
        print("⚠️ Graphviz (dot.exe) не найден! Скачайте: https://graphviz.org/download/")
    else:
        print("[ok] Graphviz найден")

    # 5. Проверка Access драйвера через pyodbc
    try:
        import pyodbc
        drivers = [d for d in pyodbc.drivers() if "Access" in d]
        if not drivers:
            print(
                "⚠️ Драйвер MS Access не найден. Скачайте: https://www.microsoft.com/en-us/download/details.aspx?id=54920")
        else:
            print(f"[ok] Найден драйвер Access: {drivers[0]}")
    except ImportError:
        print("⚠️ Модуль pyodbc не установлен")


def check_graphviz():
    dot_path = shutil.which("dot")
    if dot_path:
        logging.info(f"Graphviz найден: {dot_path}")
    else:
        logging.warning("Graphviz (dot.exe) не найден в PATH. Установи Graphviz и добавь его в переменные среды.")
        print("⚠️ Внимание: Graphviz не найден. Установите с https://graphviz.org/download/")


def check_access_engine():
    try:
        # Пробуем получить список драйверов
        drivers = [x for x in pyodbc.drivers() if "Access" in x]
        if drivers:
            logging.info(f"Найден драйвер Access: {drivers}")
        else:
            logging.warning("Драйвер Access не найден. Установи Microsoft Access Database Engine.")
            print(
                "⚠️ Внимание: драйвер Access не найден. Установите с https://www.microsoft.com/en-us/download/details.aspx?id=54920")
    except Exception as e:
        logging.error(f"Ошибка при проверке Access Engine: {e}")
        print("⚠️ Ошибка при проверке Access Engine:", e)


if __name__ == '__main__':
    # Настройка логирования
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Проверка зависимостей
    check_graphviz()
    check_access_engine()
    first_time_setup()

    # Загрузка переменных из .env
    load_dotenv()

    # Получение токена из .env
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        raise ValueError("Не удалось загрузить BOT_TOKEN из .env файла.")

    try:
        # Создаем приложение и регистрируем обработчики
        application = ApplicationBuilder().token(BOT_TOKEN).build()
        register_handlers(application)

        # Запуск бота
        application.run_polling()
        logger.info("Бот запущен успешно.")

    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}", exc_info=True)

# --- Импорты для PyInstaller (не удалять!) ---
import telegram
import telegram.ext
import aiogram
import dotenv
import sqlalchemy
import pyodbc
import graphviz
from openai import OpenAI
import requests
import pandas as pd
import PIL
from PIL import Image
from bs4 import BeautifulSoup

# ----------------------------------------------
