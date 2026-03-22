import asyncio
import logging
import sqlite3
import os
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные окружения
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8703950276:AAGP5RX0Ib7cLBgFKJPMjqnA2dtbDuLaknk")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8394493239"))

# Пути для данных
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
DB_PATH = os.path.join(DATA_DIR, "yandex_bot.db")
SCREENSHOTS_DIR = os.path.join(DATA_DIR, "yandex_screenshots")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# ====================== Flask веб-сервер (обманка для Render) ======================
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Яндекс Бот работает! Статус: Online"

@app.route('/health')
def health():
    return "OK", 200

def run_web_server():
    """Запуск Flask сервера на порту 10000"""
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False)

# ====================== База данных ======================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            user_id INTEGER PRIMARY KEY,
            phone TEXT NOT NULL,
            full_name TEXT NOT NULL,
            username TEXT,
            registered_date TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS yandex_registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            photo_path TEXT,
            registration_date TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES employees (user_id)
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("Database initialized")

def get_employee(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT * FROM employees WHERE user_id = ?', (user_id,))
    emp = cur.fetchone()
    conn.close()
    if emp:
        return {'user_id': emp[0], 'phone': emp[1], 'full_name': emp[2], 'username': emp[3]}
    return None

def add_employee(user_id, phone, full_name, username):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('INSERT OR REPLACE INTO employees VALUES (?, ?, ?, ?, ?)',
                (user_id, phone, full_name, username, datetime.now()))
    conn.commit()
    conn.close()

def add_registration(user_id, photo_path):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('INSERT INTO yandex_registrations (user_id, photo_path, registration_date) VALUES (?, ?, ?)',
                (user_id, photo_path, datetime.now()))
    conn.commit()
    conn.close()

def get_registrations_count(user_id, date):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM yandex_registrations WHERE user_id = ? AND DATE(registration_date) = ?',
                (user_id, date))
    count = cur.fetchone()[0]
    conn.close()
    return count

def get_all_employees():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT user_id, full_name, username FROM employees ORDER BY full_name')
    employees = cur.fetchall()
    conn.close()
    return [{'user_id': e[0], 'full_name': e[1], 'username': e[2]} for e in employees]

def get_total_registrations(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM yandex_registrations WHERE user_id = ?', (user_id,))
    total = cur.fetchone()[0]
    conn.close()
    return total

def get_today_registrations():
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        SELECT e.full_name, COUNT(r.id)
        FROM employees e
        LEFT JOIN yandex_registrations r ON e.user_id = r.user_id AND DATE(r.registration_date) = ?
        GROUP BY e.full_name
    ''', (today,))
    stats = cur.fetchall()
    conn.close()
    return stats

def get_date_registrations(date):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        SELECT e.full_name, COUNT(r.id)
        FROM employees e
        LEFT JOIN yandex_registrations r ON e.user_id = r.user_id AND DATE(r.registration_date) = ?
        GROUP BY e.full_name
    ''', (date,))
    stats = cur.fetchall()
    conn.close()
    return stats

# ====================== Состояния ======================
class Form(StatesGroup):
    phone = State()
    full_name = State()
    screenshot = State()

# ====================== Клавиатуры ======================
def admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Сотрудники")],
            [KeyboardButton(text="📊 Сегодня")],
            [KeyboardButton(text="📅 По дате")],
            [KeyboardButton(text="📸 Все регистрации")]
        ],
        resize_keyboard=True
    )

def emp_keyboard(employees):
    keyboard = []
    for emp in employees:
        keyboard.append([InlineKeyboardButton(text=emp['full_name'], callback_data=f"emp_{emp['user_id']}")])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def date_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Сегодня", callback_data=f"today_{user_id}")],
        [InlineKeyboardButton(text="📆 Вчера", callback_data=f"yesterday_{user_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_emp")]
    ])

# ====================== Бот ======================
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
bot = Bot(token=BOT_TOKEN)

# ====================== Обработчики ======================
@dp.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    if user_id == ADMIN_ID:
        await message.answer("👋 Админ-панель Яндекс", reply_markup=admin_keyboard())
        return
    
    emp = get_employee(user_id)
    if emp:
        await state.set_state(Form.screenshot)
        await message.answer(f"👋 Здравствуйте, {emp['full_name']}!\n\n📸 Отправьте скриншот регистрации в Яндекс.Сервисах")
    else:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
            resize_keyboard=True, one_time_keyboard=True
        )
        await state.set_state(Form.phone)
        await message.answer("📞 Отправьте номер телефона:", reply_markup=keyboard)

@dp.message(Form.phone)
async def get_phone(message: types.Message, state: FSMContext):
    if message.contact:
        await state.update_data(phone=message.contact.phone_number)
        await state.set_state(Form.full_name)
        await message.answer("✍️ Отправьте ваше ФИО (Фамилия Имя Отчество):", reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("❌ Пожалуйста, используйте кнопку для отправки номера телефона")

@dp.message(Form.full_name)
async def get_fullname(message: types.Message, state: FSMContext):
    data = await state.get_data()
    full_name = message.text.strip()
    if not full_name:
        return await message.answer("❌ Пожалуйста, введите ФИО")
    
    add_employee(message.from_user.id, data['phone'], full_name, message.from_user.username)
    await bot.send_message(ADMIN_ID, f"✅ Новый сотрудник зарегистрирован!\n\n👤 ФИО: {full_name}\n🆔 ID: {message.from_user.id}\n📱 Username: @{message.from_user.username or 'нет'}")
    await state.set_state(Form.screenshot)
    await message.answer("✅ Регистрация завершена!\n\n📸 Теперь отправляйте скриншоты регистрации в Яндекс.Сервисах\nКаждый скриншот будет засчитан как одна регистрация")

@dp.message(Form.screenshot)
async def handle_screenshot(message: types.Message, state: FSMContext):
    if not message.photo:
        return await message.answer("❌ Пожалуйста, отправьте фото (скриншот регистрации в Яндексе)")
    
    emp = get_employee(message.from_user.id)
    if not emp:
        return await message.answer("❌ Ошибка! Пожалуйста, перезапустите бота командой /start")
    
    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        
        filename = os.path.join(SCREENSHOTS_DIR, f"{message.from_user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
        await bot.download_file(file.file_path, filename)
        add_registration(message.from_user.id, filename)
        
        today_count = get_registrations_count(message.from_user.id, datetime.now().strftime("%Y-%m-%d"))
        total = get_total_registrations(message.from_user.id)
        
        await message.answer(f"✅ Скриншот принят!\n\n📊 Сегодня: {today_count} регистраций\n📈 Всего: {total} регистраций")
        
        with open(filename, 'rb') as f:
            await bot.send_photo(ADMIN_ID, types.BufferedInputFile(f.read(), filename),
                               caption=f"📸 Новая регистрация в Яндекс!\n\n👤 Сотрудник: {emp['full_name']}\n🆔 ID: {message.from_user.id}\n📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n📊 Сегодня: {today_count} | Всего: {total}")
    except Exception as e:
        logger.error(e)
        await message.answer("❌ Произошла ошибка при обработке скриншота. Попробуйте еще раз")

# ====================== Админ-команды ======================
@dp.message(lambda m: m.text == "👥 Сотрудники" and m.from_user.id == ADMIN_ID)
async def admin_employees(message: types.Message):
    employees = get_all_employees()
    if not employees:
        return await message.answer("📭 Пока нет зарегистрированных сотрудников")
    
    text = "👥 **Список сотрудников:**\n\n"
    for emp in employees:
        total = get_total_registrations(emp['user_id'])
        text += f"👤 {emp['full_name']}\n   🆔 ID: {emp['user_id']}\n   📱 @{emp['username'] or 'нет'}\n   📸 {total} регистраций\n\n"
    
    await message.answer(text, parse_mode="Markdown", reply_markup=emp_keyboard(employees))

@dp.message(lambda m: m.text == "📊 Сегодня" and m.from_user.id == ADMIN_ID)
async def admin_today(message: types.Message):
    stats = get_today_registrations()
    if not stats:
        return await message.answer("📭 Пока нет данных")
    
    text = f"📊 **Статистика регистраций Яндекс**\n📅 {datetime.now().strftime('%d.%m.%Y')}\n\n"
    total = 0
    for name, count in stats:
        text += f"👤 {name}: {count} шт.\n"
        total += count
    text += f"\n📈 **Всего регистраций: {total}**"
    await message.answer(text, parse_mode="Markdown")

@dp.message(lambda m: m.text == "📅 По дате" and m.from_user.id == ADMIN_ID)
async def admin_date(message: types.Message):
    await message.answer("📅 Введите дату в формате **ГГГГ-ММ-ДД**\n\nПример: 2026-03-21\n\nБудет показана статистика регистраций за указанную дату", parse_mode="Markdown")

@dp.message(lambda m: m.text == "📸 Все регистрации" and m.from_user.id == ADMIN_ID)
async def admin_all(message: types.Message):
    employees = get_all_employees()
    text = "📸 **Все регистрации Яндекс по сотрудникам**\n\n"
    total_all = 0
    for emp in employees:
        total = get_total_registrations(emp['user_id'])
        total_all += total
        text += f"👤 **{emp['full_name']}**: {total} шт.\n"
    text += f"\n📈 **Общее количество регистраций: {total_all}**"
    await message.answer(text, parse_mode="Markdown")

@dp.message(lambda m: m.from_user.id == ADMIN_ID)
async def handle_date(message: types.Message):
    try:
        date = message.text.strip()
        datetime.strptime(date, "%Y-%m-%d")
        stats = get_date_registrations(date)
        formatted_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d.%m.%Y")
        
        text = f"📊 **Статистика регистраций Яндекс**\n📅 {formatted_date}\n\n"
        total = 0
        for name, count in stats:
            text += f"👤 {name}: {count} шт.\n"
            total += count
        text += f"\n📈 **Всего: {total}**"
        await message.answer(text, parse_mode="Markdown")
    except ValueError:
        pass

# ====================== Callbacks ======================
@dp.callback_query()
async def callbacks(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("Нет доступа")
    
    data = callback.data
    
    if data.startswith("emp_"):
        user_id = int(data.split("_")[1])
        emp = get_employee(user_id)
        if emp:
            total = get_total_registrations(user_id)
            await callback.message.edit_text(
                f"📊 **{emp['full_name']}**\n📈 Всего регистраций: {total}\n\nВыберите период для детального просмотра:",
                parse_mode="Markdown", reply_markup=date_keyboard(user_id)
            )
    
    elif data.startswith("today_"):
        user_id = int(data.split("_")[1])
        emp = get_employee(user_id)
        today = datetime.now().strftime("%Y-%m-%d")
        count = get_registrations_count(user_id, today)
        await callback.message.edit_text(
            f"📊 **{emp['full_name']}**\n📅 {datetime.now().strftime('%d.%m.%Y')}\n\n📸 Регистраций сегодня: {count}",
            parse_mode="Markdown", reply_markup=date_keyboard(user_id)
        )
    
    elif data.startswith("yesterday_"):
        user_id = int(data.split("_")[1])
        emp = get_employee(user_id)
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        count = get_registrations_count(user_id, yesterday)
        await callback.message.edit_text(
            f"📊 **{emp['full_name']}**\n📅 {(datetime.now() - timedelta(days=1)).strftime('%d.%m.%Y')}\n\n📸 Регистраций вчера: {count}",
            parse_mode="Markdown", reply_markup=date_keyboard(user_id)
        )
    
    elif data == "back_emp":
        employees = get_all_employees()
        text = "👥 **Список сотрудников:**\n\n"
        for emp in employees:
            total = get_total_registrations(emp['user_id'])
            text += f"👤 {emp['full_name']}\n   🆔 ID: {emp['user_id']}\n   📱 @{emp['username'] or 'нет'}\n   📸 {total} регистраций\n\n"
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=emp_keyboard(employees))
    
    elif data == "back":
        await callback.message.delete()
        await callback.message.answer("👋 Админ-панель Яндекс\n\nИспользуйте кнопки для управления:", reply_markup=admin_keyboard())
    
    await callback.answer()

# ====================== Запуск ======================
async def run_bot():
    """Запуск Telegram бота"""
    init_db()
    logger.info("Yandex Bot started")
    await dp.start_polling(bot, skip_updates=True)

async def main():
    """Запуск Flask и бота параллельно"""
    # Запускаем Flask в отдельном потоке
    web_thread = Thread(target=run_web_server)
    web_thread.daemon = True
    web_thread.start()
    
    # Запускаем бота
    await run_bot()

if __name__ == "__main__":
    asyncio.run(main())
