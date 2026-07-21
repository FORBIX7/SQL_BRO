import os
import discord
import asyncio
import functools
from discord.ext import commands
from discord import ButtonStyle, ui
import yt_dlp as youtube_dl
import logging
import traceback
from ai_client import AIClient
from dotenv import load_dotenv
import aiohttp
from bs4 import BeautifulSoup
from ai_config import AISettings


# Загрузка токена из .env
load_dotenv()
DISCORD_TOKEN = 'MTM3MzY0MTM0NDEzNTcyNTEyNw.GRAUGi.bDrINT3TYDNbhOGoeKcG77o9sg5Eg1oR5C0Kcc'

# --- Настройка AI (локальный или через OpenAI) ---
settings = AISettings()
ai = AIClient(
    ai_provider=settings.ai_provider,
    openai_api_key=settings.openai_api_key,
    openrouter_api_key=settings.openrouter_api_key,
    proxy=settings.proxy,
    local_url=os.getenv("AI_API_URL", "http://127.0.0.1:1234/v1/chat/completions")
)

# --- Discord intents ---
intents = discord.Intents.default()
intents.message_content = True

# --- Логгирование ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# --- Настройки yt-dlp ---
ffmpeg_options = {'options': '-vn'}
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': None
}
ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

# --- Создание бота ---
bot = commands.Bot(command_prefix='!', intents=intents)

# --- Очередь и текущий трек для каждого сервера ---
queues = {}
track_positions = {}
player_messages = {}  # guild_id -> discord.Message


def get_guild_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = []
        track_positions[guild_id] = 0
    return queues[guild_id]


def get_position(guild_id):
    if guild_id not in track_positions:
        track_positions[guild_id] = 0
    return track_positions[guild_id]


def set_position(guild_id, pos):
    track_positions[guild_id] = pos


def reset_queue(guild_id):
    queues[guild_id] = []
    track_positions[guild_id] = 0


# --- Асинхронный Lock для защиты play_next ---
play_locks = {}  # guild_id -> asyncio.Lock()


def get_play_lock(guild_id):
    if guild_id not in play_locks:
        play_locks[guild_id] = asyncio.Lock()
    return play_locks[guild_id]


# --- Discord View с кнопками управления ---
class PlayerControls(ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=None)
        self.ctx = ctx

    @ui.button(emoji="⏮️", style=ButtonStyle.primary)
    async def previous(self, interaction: discord.Interaction, button: ui.Button):
        await self.ctx.invoke(bot.get_command('previous'))

    @ui.button(emoji="⏸️", style=ButtonStyle.primary)
    async def pause(self, interaction: discord.Interaction, button: ui.Button):
        await self.ctx.invoke(bot.get_command('pause'))

    @ui.button(emoji="▶️", style=ButtonStyle.success)
    async def resume(self, interaction: discord.Interaction, button: ui.Button):
        await self.ctx.invoke(bot.get_command('resume'))

    @ui.button(emoji="⏹️", style=ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: ui.Button):
        await self.ctx.invoke(bot.get_command('stop'))

    @ui.button(emoji="⏭️", style=ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: ui.Button):
        await self.ctx.invoke(bot.get_command('skip'))


# --- Асинхронная функция получения информации о видео ---
async def extract_info_async(query):
    """Асинхронный вызов yt_dlp, не блокирует event loop"""
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None,
            functools.partial(ytdl.extract_info, query, False)
        )
    except Exception as e:
        logging.error(f"[MEME-ULTRA] yt_dlp error: {e}")
        return None


def get_best_audio_url(info):
    if not info:
        return None
    if info.get('age_limit', 0) >= 18:
        logging.warning(f"[AUDIO-URL] Возрастное ограничение на видео: {info.get('title', '')}")
        return None
    if 'url' in info:
        return info['url']
    for fmt in info.get('formats', []):
        if fmt.get('acodec') != "none":  # проверка на наличие аудио
            return fmt.get('url')
    return None

async def handle_next(ctx):
    try:
        await asyncio.sleep(1)  # Небольшая пауза между треками
        await play_next(ctx)
    except Exception as e:
        logging.error(f"[HANDLE_NEXT] Ошибка: {e}")

async def handle_next(ctx):
    try:
        await asyncio.sleep(1.5)  # даем Discord время обработать
        await play_next(ctx)
    except Exception as e:
        logging.error(f"[HANDLE_NEXT ERROR] {e}")
# --- Воспроизведение следующего трека из очереди ---
async def play_next(ctx):
    guild_id = ctx.guild.id
    async with get_play_lock(guild_id):
        queue = get_guild_queue(guild_id)
        pos = get_position(guild_id)

        if not queue or pos >= len(queue):
            reset_queue(guild_id)
            await ctx.send("📭 Очередь пуста. Отключаюсь от голосового канала.")
            if ctx.voice_client and ctx.voice_client.is_connected():
                await ctx.voice_client.disconnect()
            return

        track = queue[pos]
        title = track.get("title", "Без названия")
        yt_url = track.get("yt_url")

        logging.info(f"[QUEUE] Попытка воспроизведения: {title} ({yt_url})")

        info = await extract_info_async(yt_url)
        audio_url = get_best_audio_url(info)

        if not info or not audio_url:
            await ctx.send(f"⚠️ Пропускаю битый трек: **{title}**")
            logging.warning(f"[SKIP] Нет рабочего аудиофайла для {title}")
            set_position(guild_id, pos + 1)  # ← ОСТАВИТЬ
            await asyncio.sleep(1)
            await play_next(ctx)
            return

        voice_client = ctx.voice_client
        if not voice_client or not voice_client.is_connected():
            if ctx.author.voice:
                voice_client = await ctx.author.voice.channel.connect()
            else:
                await ctx.send("❌ Вы не в голосовом канале.")
                return

        # 🔁 Флаг, чтобы корректно вызвать следующий трек после завершения
        def after_playing(error=None):
            if error:
                logging.error(f"[AFTER_PLAY ERROR] {error}")
            else:
                logging.info("[AFTER_PLAY] Завершено, переходим к следующему треку.")

            # Обновляем позицию ТОЛЬКО после воспроизведения
            current_pos = get_position(ctx.guild.id)
            set_position(ctx.guild.id, current_pos + 1)

            # Отложенный запуск следующего трека
            bot.loop.call_soon_threadsafe(asyncio.create_task, handle_next(ctx))

        # ▶️ Воспроизведение аудио через ffmpeg
        try:
            source = discord.FFmpegPCMAudio(
                audio_url,
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn"
            )
            voice_client.play(source, after=after_playing)

            await ctx.send(f"▶️ Сейчас играет: **{title}**", view=PlayerControls(ctx))
        except Exception as e:
            logging.error(f"[FFMPEG ERROR] {e}")
            await ctx.send(f"❌ Ошибка при воспроизведении: **{title}**. Пропускаю.")
            set_position(guild_id, pos + 1)
            await asyncio.sleep(1)
            await play_next(ctx)

# --- Стандартные команды управления голосом и очередью ---

@bot.event
async def on_ready():
    logging.info(f'Бот запущен: {bot.user} (ID: {bot.user.id})')
    for guild_id in queues:
        track_positions[guild_id] = 0
        logging.info(f"[INIT] Позиция очереди для сервера {guild_id} сброшена.")


@bot.command(name='join')
async def join(ctx):
    try:
        if ctx.author.voice and ctx.author.voice.channel:
            await ctx.author.voice.channel.connect()
            await ctx.send("Подключился к голосовому каналу.")
            logging.info(f"Бот присоединился к каналу: {ctx.author.voice.channel}")
        else:
            await ctx.send("Вы должны быть в голосовом канале!")
    except Exception as e:
        logging.error(f"[JOIN] Ошибка: {e}")
        await ctx.send(f"Ошибка при подключении: {e}")


@bot.command(name='leave')
async def leave(ctx):
    try:
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("Отключился от голосового канала.")
            logging.info("Бот отключился от голосового канала")
            reset_queue(ctx.guild.id)
        else:
            await ctx.send("Бот не в голосовом канале!")
    except Exception as e:
        logging.error(f"[LEAVE] Ошибка: {e}")
        await ctx.send(f"Ошибка при отключении: {e}")


@bot.command(name='play')
async def play(ctx, *, query: str):
    try:
        queue = get_guild_queue(ctx.guild.id)
        async with ctx.typing():
            # Если это не ссылка, подставляем ytsearch:
            if not (query.startswith("http://") or query.startswith("https://")):
                search_str = f"ytsearch:{query}"
            else:
                search_str = query
            info = await extract_info_async(search_str)
            if 'entries' in info:
                info = info['entries'][0]
            url_source = info['url'] if 'url' in info else info['formats'][0]['url']
            title = info.get('title', 'Без названия')
            yt_url = info.get('webpage_url')
            queue.append({'yt_url': yt_url, 'title': title})

        await ctx.send(f"✅ Трек добавлен в очередь: **{title}**")
        voice_client = ctx.voice_client
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            await play_next(ctx)
    except Exception as e:
        logging.error(f"[PLAY] Ошибка: {e}\n{traceback.format_exc()}")

        await ctx.send(f"Ошибка воспроизведения: {e}")


@bot.command(name='skip')
async def skip(ctx):
    """Следующий трек"""
    try:
        voice_client = ctx.voice_client
        if voice_client.is_playing():
            voice_client.stop()
            await ctx.send("⏭️ Следующий трек...")
        else:
            await ctx.send("Ничего не воспроизводится.")
    except Exception as e:
        logging.error(f"[SKIP] Ошибка: {e}")
        await ctx.send(f"Ошибка при переходе к следующему треку: {e}")


@bot.command(name='previous')
async def previous(ctx):
    """Предыдущий трек"""
    try:
        pos = get_position(ctx.guild.id)
        if pos > 1:
            set_position(ctx.guild.id, pos - 2)  # шаг назад
            voice_client = ctx.voice_client
            if voice_client.is_playing():
                voice_client.stop()
            else:
                await play_next(ctx)
            msg = await ctx.send("⏮️ Предыдущий трек...")
            await msg.delete(delay=2)
        else:
            msg = await ctx.send("Это первый трек в очереди.")
            await msg.delete(delay=2)
    except Exception as e:
        logging.error(f"[PREVIOUS] Ошибка: {e}")
        await ctx.send(f"Ошибка при переходе к предыдущему треку: {e}")


@bot.command(name='pause')
async def pause(ctx):
    try:
        voice_client = ctx.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await ctx.send("Воспроизведение приостановлено.")
    except Exception as e:
        logging.error(f"[PAUSE] Ошибка: {e}")
        await ctx.send(f"Ошибка при паузе: {e}")


@bot.command(name='resume')
async def resume(ctx):
    try:
        voice_client = ctx.voice_client
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await ctx.send("Воспроизведение возобновлено.")
    except Exception as e:
        logging.error(f"[RESUME] Ошибка: {e}")
        await ctx.send(f"Ошибка при возобновлении: {e}")


@bot.command(name='stop')
async def stop(ctx):
    try:
        voice_client = ctx.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            await ctx.send("Остановка воспроизведения.")
        else:
            await ctx.send("Ничего не воспроизводится.")
    except Exception as e:
        logging.error(f"[STOP] Ошибка: {e}")
        await ctx.send(f"Ошибка при остановке: {e}")


@bot.command(name='queue')
async def show_queue(ctx):
    """Показать очередь треков"""
    queue = get_guild_queue(ctx.guild.id)
    if queue:
        pos = get_position(ctx.guild.id)
        tracks = [
            (f"**▶️ {i + 1}. {t['title']}**" if i == pos else f"{i + 1}. {t['title']}")
            for i, t in enumerate(queue)
        ]
        await ctx.send("Текущая очередь:\n" + "\n".join(tracks))
    else:
        await ctx.send("Очередь пуста.")


@bot.command(name='clear')
async def clear_queue(ctx):
    """Очистить очередь"""
    reset_queue(ctx.guild.id)
    await ctx.send("Очередь очищена.")


@bot.command(name='remove')
async def remove_track(ctx, pos: int):
    """Удалить трек по номеру (1-based)"""
    queue = get_guild_queue(ctx.guild.id)
    if 1 <= pos <= len(queue):
        removed = queue.pop(pos - 1)
        await ctx.send(f"Удалён трек: {removed['title']}")
        # Если удалили трек раньше текущей позиции, позицию тоже сдвигаем
        current_pos = get_position(ctx.guild.id)
        if pos - 1 < current_pos:
            set_position(ctx.guild.id, current_pos - 1)
    else:
        await ctx.send("Некорректный номер трека.")


@bot.command(name='now')
async def now_playing(ctx):
    """Текущий трек"""
    queue = get_guild_queue(ctx.guild.id)
    pos = get_position(ctx.guild.id)
    if queue and 0 <= pos - 1 < len(queue):
        track = queue[pos - 1]
        await ctx.send(f"Сейчас играет: **{track['title']}**")
    else:
        await ctx.send("Сейчас ничего не играет.")


async def search_soundbuttons(query: str, limit: int = 10):
    url = f"https://soundbuttons.net/search/?q={query.replace(' ', '+')}"
    headers = {"User-Agent": "Mozilla/5.0"}

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return []

            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")
            results = []

            for btn in soup.select(".sound-row")[:limit]:
                title = btn.select_one(".sound-title")
                if title:
                    results.append(title.text.strip())

            return results

async def pick_best_meme(query: str, options: list[str]) -> str:
    prompt = f"""
Пользователь описал ситуацию: "{query}"
Вот список звуков, найденных на soundbuttons.net:
{chr(10).join(f"- {o}" for o in options)}

Выбери ОДИН лучший звук, который идеально подойдёт. Только название, без комментариев.
"""
    result = await bot.loop.run_in_executor(
        None,
        functools.partial(ai.chat, prompt)
    )
    return result.strip()


# --- Команда для мема (с AI + поиск по YouTube) ---
@bot.command(name='meme')
async def meme(ctx, *, query: str):
    try:
        await ctx.send("🎧 Обрабатываю запрос...")

        # === 1. Парсим soundbuttons ===
        options = await search_soundbuttons(query)

        if not options:
            await ctx.send("❌ Не нашёл подходящих звуков на soundbuttons.net. Пробую через ИИ...")
            # fallback: просто использовать AI как раньше
            prompt_name = f"""
                Пользователь описал ситуацию: "{query}"
                Предложи подходящий звук, мем или трек, известный в TikTok, YouTube или Discord.
                Ответ: только название.
                """
            search_term = await bot.loop.run_in_executor(
                None, functools.partial(ai.chat, prompt_name, temperature=0.9)
            )
            search_term = search_term.strip()
        else:
            # === 2. AI выбирает лучший из найденных ===
            await ctx.send(f"🔎 Найдено {len(options)} звуков, выбираю лучший через ИИ...")
            search_term = await pick_best_meme(query, options)

        # === 3. Поиск на YouTube ===
        yt_query = f"ytsearch:{search_term} meme sound"
        info = await extract_info_async(yt_query)

        if not info or not info.get("entries"):
            await ctx.send("❌ Не удалось найти подходящий звук на YouTube.")
            return

        entry = info["entries"][0]
        audio_url = get_best_audio_url(entry)
        if not audio_url:
            await ctx.send("❌ Аудио не удалось извлечь.")
            return

        title = entry.get("title", search_term)
        yt_url = entry.get("webpage_url")

        # === 4. Добавить в очередь ===
        queue = get_guild_queue(ctx.guild.id)
        queue.append({'yt_url': yt_url, 'title': title})
        await ctx.send(f"🎵 Мем добавлен в очередь: **{title}**")

        if not ctx.voice_client or not ctx.voice_client.is_playing():
            await play_next(ctx)

    except Exception as e:
        logging.error(f"[MEME] Ошибка: {e}")
        await ctx.send("❌ Произошла ошибка при обработке мема.")


# --- LLM-ассистент (по приколу) ---
@bot.command(name='llm')
async def llm(ctx, *, prompt: str):
    TEAMMATE_PROMPT = """
    Ты — идеальный друг-тиммейт в Discord. Тебя зовут Бро (или любое имя, если спросят). 
    Твой стиль — дружеский, искренний, всегда чуть-чуть с юмором. 
    Ты хорошо разбираешься во всех играх, мемах, ПК, и всегда готов поддержать, посоветовать по жизни, поржать, или подколоть по-доброму. 
    Используй фразы, которые обычно говорят друзья в Дискорде. Можешь обращаться на "ты", использовать эмодзи и игровые/дискордные мемы.
    Если тебя спрашивают про конкретную игру — расскажи с опытом бывалого тиммейта, не занудствуй. 
    Если тебя зовут поиграть — соглашайся или шути. 
    Если у человека проблемы — поддержи, но как бро, не как психолог.
    Если просят что-то объяснить — объясняй просто, будто объясняешь другу.
    Общайся живо, можешь отвечать коротко или мемно, иногда вставлять приколы (“го в катку”, “аимбот тебе в помощь”, “изи катка”, “ну ты ракал, конечно, бро!” и т.п.)
    Не забывай быть добрым, но не приторным. 
    """

    try:
        full_prompt = TEAMMATE_PROMPT + "\n\n" + f"Вопрос/сообщение: {prompt}"
        answer = await bot.loop.run_in_executor(
            None,
            functools.partial(ai.chat, full_prompt)
        )
        await ctx.send(answer or "Нет ответа от Бро.")
    except Exception as e:
        logging.error(f"[LLM] Ошибка: {e}")
        await ctx.send("Ошибка при обращении к LLM.")


@bot.event
async def on_command_error(ctx, error):
    logging.error(f"[GLOBAL ERROR] {ctx.command}: {error}")
    await ctx.send(f"Ошибка выполнения команды: {error}")


# ---- Запуск бота ----
if not DISCORD_TOKEN:
    print("❌ Не найден DISCORD_TOKEN в .env файле!")
else:
    bot.run(DISCORD_TOKEN)
