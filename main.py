import asyncio
import sqlite3
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from telethon import TelegramClient

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Твои данные
BOT_TOKEN = "9155261524:AAHD1hhuOGFNKHWzGml2r7L6fpkR63FfnE8"
API_ID = 35556659
API_HASH = "d3cfb86ad3d3ad1f98041e99207d17ad"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Инициализация базы данных SQLite (добавили колонку prefix для каждого пользователя)
conn = sqlite3.connect("sessions.db", check_same_thread=False)
conn.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        user_id INTEGER PRIMARY KEY,
        session_string TEXT,
        prefix TEXT DEFAULT ','
    )
""")
conn.commit()

# Функция для получения личного префикса пользователя (по умолчанию запятая ",")
def get_user_prefix(user_id: int) -> str:
    row = conn.execute("SELECT prefix FROM sessions WHERE user_id = ?", (user_id,)).fetchone()
    return row[0] if row and row[0] else ","

# Функция для изменения личного префикса пользователя
def set_user_prefix(user_id: int, new_prefix: str):
    conn.execute("UPDATE sessions SET prefix = ? WHERE user_id = ?", (new_prefix, user_id))
    conn.commit()

active_userbots = {}

async def spawn_userbot(user_id: int, session_string: str):
    if user_id in active_userbots:
        try:
            await active_userbots[user_id].disconnect()
        except:
            pass
    
    client = TelegramClient(session_string, API_ID, API_HASH)
    await client.start()
    active_userbots[user_id] = client

async def disconnect_userbot(user_id: int, remove_session: bool = False):
    if user_id in active_userbots:
        try:
            await active_userbots[user_id].disconnect()
        except:
            pass
        del active_userbots[user_id]
    
    if remove_session:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.commit()
    return True

async def logout_userbot(user_id: int):
    if user_id in active_userbots:
        try:
            await active_userbots[user_id].log_out()
            await active_userbots[user_id].disconnect()
        except Exception as e:
            logging.error(f"Error logging out: {e}")
        del active_userbots[user_id]
    
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    return True

async def load_existing_userbots():
    rows = conn.execute("SELECT user_id, session_string FROM sessions").fetchall()
    for user_id, session_string in rows:
        try:
            await spawn_userbot(user_id, session_string)
        except Exception as e:
            logging.error(f"Failed to load userbot for {user_id}: {e}")

# ======================================================
# КОМАНДА СМЕНЫ ЛИЧНОГО ПРЕФИКСА ДЛЯ ИГРОКА
# ======================================================
@dp.message()
async def handle_user_commands(message: Message):
    if not message.text or not message.from_user:
        return
    
    user_id = message.from_user.id
    current_prefix = get_user_prefix(user_id)
    text = message.text.strip()

    # 1. Проверяем команду смены префикса: "{префикс}set prefix {новый_префикс}"
    if text.startswith(f"{current_prefix}set prefix"):
        args = text.split(maxsplit=2)
        if len(args) < 3:
            await message.answer(f"⚠️ Укажи новый префикс!\nПример: `{current_prefix}set prefix !`", parse_mode="Markdown")
            return
        
        new_prefix = args[2].strip()
        if len(new_prefix) > 5:
            await message.answer("⚠️ Префикс слишком длинный! Максимум 5 символов.")
            return

        # Проверяем, есть ли вообще сессия у юзера в базе
        row = conn.execute("SELECT user_id FROM sessions WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            await message.answer("⚠️ Сначала подключи свой юзербот через команду старт!")
            return

        set_user_prefix(user_id, new_prefix)
        await message.answer(f"✅ Твой личный префикс успешно изменен!\nНовый префикс: `{new_prefix}`\nПример: `{new_prefix}stop`", parse_mode="Markdown")
        return

    # 2. Команда старт
    if text.startswith(f"{current_prefix}start"):
        row = conn.execute("SELECT session_string FROM sessions WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            await message.answer(f"✅ У тебя уже подключен юзербот! Твой префикс: `{current_prefix}`\nИспользуй `{current_prefix}stop` или `{current_prefix}logout`.", parse_mode="Markdown")
        else:
            await message.answer(f"👋 Привет в **Horizon Control**!\nЧтобы подключить юзербот, отправь данные сессии или номер телефона.\nТвой текущий префикс: `{current_prefix}`", parse_mode="Markdown")
        return

    # 3. Команда стоп
    if text.startswith(f"{current_prefix}stop"):
        success = await disconnect_userbot(user_id, remove_session=False)
        if success:
            await message.answer(f"⏸ Твой юзербот остановлен. Аккаунт залогинен.\nЗапустить снова: `{current_prefix}restart`", parse_mode="Markdown")
        else:
            await message.answer("У тебя нет активного юзербота.")
        return

    # 4. Команда рестарт
    if text.startswith(f"{current_prefix}restart"):
        row = conn.execute("SELECT session_string FROM sessions WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            await message.answer(f"У тебя нет сохранённой сессии. Подключись заново через `{current_prefix}start`", parse_mode="Markdown")
            return
        await spawn_userbot(user_id, row[0])
        await message.answer(f"🚀 Твой юзербот запущен снова с префиксом `{current_prefix}`.", parse_mode="Markdown")
        return

    # 5. Команда логаут (выход)
    if text.startswith(f"{current_prefix}logout"):
        row = conn.execute("SELECT session_string FROM sessions WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            await message.answer("У тебя нет подключённого аккаунта.")
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, выйти", callback_data="logout_confirm"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="logout_cancel")
            ]
        ])
        await message.answer(
            "Вы правда хотите чтобы юзербот вышел с вашего аккаунта?",
            reply_markup=keyboard
        )
        return

@dp.callback_query(lambda c: c.data in ["logout_confirm", "logout_cancel"])
async def process_logout_callback(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    current_prefix = get_user_prefix(user_id)
    action = callback_query.data

    if action == "logout_cancel":
        await callback_query.message.edit_text("❌ Действие отменено.")
        await callback_query.answer()
        return

    await callback_query.message.edit_text("⏳ Выполняется выход из аккаунта...")
    success = await logout_userbot(user_id)
    
    if success:
        await callback_query.message.edit_text(f"👋 Аккаунт полностью отключён. Для повторного входа — `,start`")
    else:
        await callback_query.message.edit_text("⚠️ Ошибка при выходе или аккаунт уже был отключен.")
    
    await callback_query.answer()

# ======================================================
# ВЕБ-СЕРВЕР ДЛЯ ЗАЩИТЫ ОТ СНА НА RENDER
# ======================================================
async def handle_ping(request):
    return web.Response(text="Horizon Control is alive 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/ping", handle_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Веб-сервер запущен на порту {port}")

# ======================================================
# ТОЧКА ВХОДА
# ======================================================
async def main():
    await start_web_server()
    await load_existing_userbots()
    print("✅ Бот-менеджер Horizon Control запущен в облаке!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
