import asyncio
import logging
import sqlite3
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен бота (замените на свой)
BOT_TOKEN = os.getenv('BOT_TOKEN', '8088112270:AAEN4w49E0AawkLkOPZrXrhwKfqX-tgzrL4')
# ID администратора (замените на свой)
ADMIN_ID = int(os.getenv('ADMIN_ID', '8394493239'))

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ====================== Работа с базой данных ======================
DB_PATH = os.path.join(os.path.dirname(__file__), 'users.db')
SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), 'screenshots')

def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            phone TEXT NOT NULL,
            full_name TEXT NOT NULL,
            username TEXT,
            screenshot_count INTEGER DEFAULT 0,
            total_screenshots INTEGER DEFAULT 0,
            last_reset TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    
    # Создаем папку для скриншотов, если её нет
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cur.fetchone()
    conn.close()
    return user

def add_user(user_id, phone, full_name, username=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO users (user_id, phone, full_name, username, screenshot_count, total_screenshots, last_reset)
        VALUES (?, ?, ?, ?, 0, 0, ?)
    ''', (user_id, phone, full_name, username, datetime.now()))
    conn.commit()
    conn.close()

def increment_screenshot_count(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        UPDATE users 
        SET screenshot_count = screenshot_count + 1,
            total_screenshots = total_screenshots + 1
        WHERE user_id = ?
    ''', (user_id,))
    conn.commit()
    conn.close()

def reset_all_counts():
    """Обнуляет дневной счётчик скриншотов у всех пользователей"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        UPDATE users 
        SET screenshot_count = 0, last_reset = ?
    ''', (datetime.now(),))
    conn.commit()
    conn.close()
    logging.info("All daily screenshot counts reset to 0")

def get_all_users_stats():
    """Получает статистику по всем пользователям"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        SELECT user_id, phone, full_name, username, screenshot_count, total_screenshots, last_reset 
        FROM users 
        ORDER BY total_screenshots DESC
    ''')
    users = cur.fetchall()
    conn.close()
    return users

def get_user_stats(user_id):
    """Получает статистику конкретного пользователя"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        SELECT user_id, phone, full_name, username, screenshot_count, total_screenshots, last_reset 
        FROM users 
        WHERE user_id = ?
    ''', (user_id,))
    user = cur.fetchone()
    conn.close()
    return user

# ====================== Машина состояний ======================
class Form(StatesGroup):
    phone = State()
    screenshot = State()

# ====================== Обработчики ======================
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username
    
    user = get_user(user_id)
    if user:
        await state.set_state(Form.screenshot)
        await message.answer(
            f"С возвращением, {user[2]}! Отправьте новый скриншот регистрации в Яндексе.\n"
            f"Сегодня отправлено: {user[4]} скриншотов"
        )
    else:
        contact_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await state.set_state(Form.phone)
        await message.answer(
            "Добро пожаловать! Пожалуйста, отправьте ваш номер телефона и ФИО.\n"
            "Вы можете нажать кнопку ниже, чтобы отправить контакт, или ввести данные вручную в формате:\n"
            "(номер телефона) (Фамилия Имя Отчество)",
            reply_markup=contact_keyboard
        )

@dp.message(Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    if message.contact:
        phone = message.contact.phone_number
        await state.update_data(phone=phone)
        await message.answer(
            "Спасибо! Теперь отправьте ваше ФИО (Фамилия Имя Отчество).",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        parts = message.text.strip().split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Пожалуйста, введите номер телефона и ФИО через пробел.")
            return
        phone, full_name = parts
        add_user(message.from_user.id, phone, full_name, message.from_user.username)
        
        # Уведомление админу
        await bot.send_message(
            ADMIN_ID,
            f"✅ Новый пользователь зарегистрирован:\n"
            f"ID: {message.from_user.id}\n"
            f"Username: @{message.from_user.username or 'нет'}\n"
            f"ФИО: {full_name}\n"
            f"Телефон: {phone}"
        )
        
        await state.set_state(Form.screenshot)
        await message.answer(
            "Регистрация завершена! Теперь отправьте скриншот регистрации в Яндексе.",
            reply_markup=ReplyKeyboardRemove()
        )

@dp.message(Form.phone)
async def process_full_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if 'phone' in data:
        full_name = message.text.strip()
        if not full_name:
            await message.answer("Пожалуйста, введите ФИО.")
            return
        add_user(message.from_user.id, data['phone'], full_name, message.from_user.username)
        
        # Уведомление админу
        await bot.send_message(
            ADMIN_ID,
            f"✅ Новый пользователь зарегистрирован:\n"
            f"ID: {message.from_user.id}\n"
            f"Username: @{message.from_user.username or 'нет'}\n"
            f"ФИО: {full_name}\n"
            f"Телефон: {data['phone']}"
        )
        
        await state.set_state(Form.screenshot)
        await message.answer(
            "Регистрация завершена! Теперь отправьте скриншот регистрации в Яндексе.",
            reply_markup=ReplyKeyboardRemove()
        )

@dp.message(Form.screenshot)
async def process_screenshot(message: types.Message, state: FSMContext):
    if not message.photo:
        await message.answer("Пожалуйста, отправьте фото (скриншот).")
        return

    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(SCREENSHOTS_DIR, f"{message.from_user.id}_{timestamp}.jpg")
    await bot.download_file(file.file_path, filename)
    logging.info(f"Screenshot saved: {filename}")

    increment_screenshot_count(message.from_user.id)
    user_stats = get_user_stats(message.from_user.id)
    
    await message.answer(
        f"✅ Скриншот принят!\n"
        f"Сегодня отправлено: {user_stats[4]}\n"
        f"Всего отправлено: {user_stats[5]}"
    )
    
    # Уведомление админу
    await bot.send_message(
        ADMIN_ID,
        f"📸 Получен новый скриншот:\n"
        f"От: {user_stats[2]} (ID: {message.from_user.id})\n"
        f"Username: @{message.from_user.username or 'нет'}\n"
        f"Сегодня: {user_stats[4]} | Всего: {user_stats[5]}"
    )

# ====================== Команды администратора ======================
@dp.message(Command("report"))
async def cmd_report(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return
    
    users = get_all_users_stats()
    
    if not users:
        await message.answer("Пока нет зарегистрированных пользователей.")
        return
    
    report = "📊 **ОТЧЕТ ПО ВСЕМ ПОЛЬЗОВАТЕЛЯМ**\n\n"
    report += f"Всего пользователей: {len(users)}\n"
    report += "=" * 40 + "\n\n"
    
    total_all_screenshots = 0
    total_today_screenshots = 0
    
    for i, user in enumerate(users, 1):
        user_id, phone, full_name, username, today_count, total_count, last_reset = user
        
        report += f"{i}. **{full_name}**\n"
        report += f"   📱 ID: {user_id}\n"
        report += f"   📞 Телефон: {phone}\n"
        report += f"   🆔 Username: @{username or 'нет'}\n"
        report += f"   📸 Сегодня: {today_count}\n"
        report += f"   📸 Всего: {total_count}\n"
        report += "-" * 30 + "\n"
        
        total_all_screenshots += total_count
        total_today_screenshots += today_count
    
    report += "\n📈 **ОБЩАЯ СТАТИСТИКА:**\n"
    report += f"Всего скриншотов за все время: {total_all_screenshots}\n"
    report += f"Скриншотов за сегодня: {total_today_screenshots}\n"
    
    await message.answer(report, parse_mode="Markdown")

@dp.message(Command("user"))
async def cmd_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /user <telegram_id>")
        return
    
    try:
        user_id = int(parts[1])
    except ValueError:
        await message.answer("Пожалуйста, укажите корректный ID пользователя.")
        return
    
    user = get_user_stats(user_id)
    
    if not user:
        await message.answer(f"Пользователь с ID {user_id} не найден.")
        return
    
    user_id, phone, full_name, username, today_count, total_count, last_reset = user
    
    report = f"📊 **СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ**\n\n"
    report += f"👤 ФИО: {full_name}\n"
    report += f"🆔 ID: {user_id}\n"
    report += f"📞 Телефон: {phone}\n"
    report += f"📱 Username: @{username or 'нет'}\n"
    report += f"📸 Скриншотов сегодня: {today_count}\n"
    report += f"📸 Скриншотов всего: {total_count}\n"
    
    await message.answer(report, parse_mode="Markdown")

# ====================== Фоновая задача ======================
async def daily_reset():
    while True:
        now = datetime.now()
        next_reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        sleep_seconds = (next_reset - now).total_seconds()
        logging.info(f"Next reset in {sleep_seconds} seconds")
        await asyncio.sleep(sleep_seconds)
        
        reset_all_counts()
        
        users = get_all_users_stats()
        total_users = len(users)
        total_all_time = sum(user[5] for user in users)
        
        await bot.send_message(
            ADMIN_ID,
            f"🔄 **Ежедневный сброс счетчиков выполнен!**\n\n"
            f"Всего пользователей: {total_users}\n"
            f"Всего скриншотов за все время: {total_all_time}"
        )

# ====================== Запуск ======================
async def main():
    # Инициализация БД
    init_db()
    # Запуск фоновой задачи
    asyncio.create_task(daily_reset())
    # Запуск поллинга
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
