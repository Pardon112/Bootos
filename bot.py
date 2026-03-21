import asyncio
import logging
import sqlite3
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramNetworkError

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Токен бота и ID администратора
BOT_TOKEN = "8703950276:AAGP5RX0Ib7cLBgFKJPMjqnA2dtbDuLaknk"
ADMIN_ID = 8394493239

# Настройки для стабильности
RECONNECT_DELAY = 5
MAX_RECONNECT_ATTEMPTS = 10

# Пути к файлам
DB_PATH = os.path.join(os.path.dirname(__file__), 'yandex_bot.db')
SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), 'yandex_screenshots')

def init_db():
    """Инициализация базы данных SQLite"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Таблица сотрудников
        cur.execute('''
            CREATE TABLE IF NOT EXISTS employees (
                user_id INTEGER PRIMARY KEY,
                phone TEXT NOT NULL,
                full_name TEXT NOT NULL,
                username TEXT,
                registered_date TIMESTAMP
            )
        ''')
        
        # Таблица скриншотов регистрации Яндекс
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
        
        os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
        logger.info(f"Database initialized successfully at {DB_PATH}")
        return True
    except Exception as e:
        logger.error(f"Database init error: {e}")
        return False

def get_employee(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('SELECT * FROM employees WHERE user_id = ?', (user_id,))
        employee = cur.fetchone()
        conn.close()
        if employee:
            return {
                'user_id': employee[0],
                'phone': employee[1],
                'full_name': employee[2],
                'username': employee[3],
                'registered_date': employee[4]
            }
        return None
    except Exception as e:
        logger.error(f"Error getting employee: {e}")
        return None

def add_employee(user_id, phone, full_name, username=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('''
            INSERT OR REPLACE INTO employees (user_id, phone, full_name, username, registered_date)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, phone, full_name, username, datetime.now()))
        conn.commit()
        conn.close()
        logger.info(f"New employee added: {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error adding employee: {e}")
        return False

def add_yandex_registration(user_id, photo_path):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO yandex_registrations (user_id, photo_path, registration_date)
            VALUES (?, ?, ?)
        ''', (user_id, photo_path, datetime.now()))
        conn.commit()
        conn.close()
        logger.info(f"New Yandex registration added: {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error adding registration: {e}")
        return False

def get_registrations_stats(user_id, date):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('''
            SELECT COUNT(*) as count
            FROM yandex_registrations 
            WHERE user_id = ? AND DATE(registration_date) = ?
        ''', (user_id, date))
        stats = cur.fetchone()
        conn.close()
        return stats[0] if stats else 0
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return 0

def get_all_employees():
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('SELECT user_id, full_name, phone, username FROM employees ORDER BY full_name')
        employees = cur.fetchall()
        conn.close()
        return [{'user_id': e[0], 'full_name': e[1], 'phone': e[2], 'username': e[3]} for e in employees]
    except Exception as e:
        logger.error(f"Error getting employees: {e}")
        return []

def get_employee_registrations_total(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM yandex_registrations WHERE user_id = ?', (user_id,))
        total = cur.fetchone()[0]
        conn.close()
        return total or 0
    except Exception as e:
        logger.error(f"Error getting employee total: {e}")
        return 0

def get_today_stats():
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('''
            SELECT e.full_name, COUNT(r.id) as count
            FROM employees e
            LEFT JOIN yandex_registrations r ON e.user_id = r.user_id AND DATE(r.registration_date) = ?
            GROUP BY e.full_name
            ORDER BY e.full_name
        ''', (today,))
        stats = cur.fetchall()
        conn.close()
        return [{'full_name': s[0], 'count': s[1]} for s in stats]
    except Exception as e:
        logger.error(f"Error getting today stats: {e}")
        return []

def get_date_stats(date):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('''
            SELECT e.full_name, COUNT(r.id) as count
            FROM employees e
            LEFT JOIN yandex_registrations r ON e.user_id = r.user_id AND DATE(r.registration_date) = ?
            GROUP BY e.full_name
            ORDER BY e.full_name
        ''', (date,))
        stats = cur.fetchall()
        conn.close()
        return [{'full_name': s[0], 'count': s[1]} for s in stats]
    except Exception as e:
        logger.error(f"Error getting date stats: {e}")
        return []

# ====================== Машина состояний ======================
class Form(StatesGroup):
    phone = State()
    full_name = State()
    screenshot = State()

# ====================== Клавиатуры ======================
def get_admin_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Список сотрудников")],
            [KeyboardButton(text="📊 Статистика за сегодня")],
            [KeyboardButton(text="📅 Статистика за дату")],
            [KeyboardButton(text="📸 Все регистрации")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_employee_list_keyboard(employees):
    keyboard = []
    for emp in employees:
        keyboard.append([InlineKeyboardButton(text=emp['full_name'], callback_data=f"emp_{emp['user_id']}")])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_date_keyboard(employee_id):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Сегодня", callback_data=f"date_today_{employee_id}")],
        [InlineKeyboardButton(text="📆 Вчера", callback_data=f"date_yesterday_{employee_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_employees")]
    ])
    return keyboard

# ====================== Создание бота ======================
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
bot = Bot(token=BOT_TOKEN)

# ====================== Обработчики ======================
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    if user_id == ADMIN_ID:
        await message.answer(
            "👋 Здравствуйте, Администратор!\n\n"
            "🤖 Бот для учёта скриншотов регистрации в Яндекс.Сервисах\n"
            "💾 Данные сохраняются локально на сервере\n\n"
            "Используйте кнопки для управления:",
            reply_markup=get_admin_keyboard()
        )
        return
    
    employee = get_employee(user_id)
    if employee:
        await state.set_state(Form.screenshot)
        await message.answer(
            f"👋 Здравствуйте, {employee['full_name']}!\n\n"
            "📸 Пришлите фото регистрации в Яндекс.Сервисах.\n"
            "✅ Каждый скриншот будет засчитан как одна регистрация."
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
            "🌟 Добро пожаловать!\n\n"
            "Для регистрации отправьте номер телефона:",
            reply_markup=contact_keyboard
        )

@dp.message(Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    if message.contact:
        await state.update_data(phone=message.contact.phone_number)
        await state.set_state(Form.full_name)
        await message.answer(
            "✅ Спасибо! Теперь отправьте ваше ФИО (Фамилия Имя Отчество).",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await message.answer("❌ Пожалуйста, используйте кнопку для отправки номера телефона.")

@dp.message(Form.full_name)
async def process_full_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    full_name = message.text.strip()
    
    if not full_name:
        await message.answer("❌ Пожалуйста, введите ФИО.")
        return
    
    add_employee(message.from_user.id, data['phone'], full_name, message.from_user.username)
    
    try:
        await bot.send_message(
            ADMIN_ID,
            f"✅ **Новый сотрудник зарегистрирован!**\n\n"
            f"🆔 ID: {message.from_user.id}\n"
            f"📱 Username: @{message.from_user.username or 'нет'}\n"
            f"👤 ФИО: {full_name}\n"
            f"📞 Телефон: {data['phone']}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error sending admin notification: {e}")
    
    await state.set_state(Form.screenshot)
    await message.answer(
        "✅ Регистрация завершена!\n\n"
        "📸 Теперь отправляйте скриншоты регистрации в Яндекс.Сервисах.\n"
        "💾 Каждый скриншот будет сохранен!",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(Form.screenshot)
async def process_screenshot(message: types.Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Пожалуйста, отправьте фото (скриншот регистрации в Яндексе).")
        return
    
    employee = get_employee(message.from_user.id)
    if not employee:
        await message.answer("❌ Ошибка! Пожалуйста, перезапустите бота командой /start")
        return
    
    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        
        os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(SCREENSHOTS_DIR, f"{message.from_user.id}_{timestamp}.jpg")
        await bot.download_file(file.file_path, filename)
        
        add_yandex_registration(message.from_user.id, filename)
        
        today = datetime.now().strftime("%Y-%m-%d")
        today_count = get_registrations_stats(message.from_user.id, today)
        total_count = get_employee_registrations_total(message.from_user.id)
        
        await message.answer(
            f"✅ **Скриншот принят!**\n\n"
            f"📊 Сегодня: {today_count} регистраций\n"
            f"📈 Всего: {total_count} регистраций",
            parse_mode="Markdown"
        )
        
        with open(filename, 'rb') as photo_file:
            await bot.send_photo(
                ADMIN_ID,
                types.BufferedInputFile(photo_file.read(), filename=f"yandex_{message.from_user.id}_{timestamp}.jpg"),
                caption=f"📸 **Новая регистрация в Яндекс!**\n\n"
                        f"👤 Сотрудник: {employee['full_name']}\n"
                        f"🆔 ID: {message.from_user.id}\n"
                        f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
                        f"📊 Сегодня: {today_count} | Всего: {total_count}",
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Error processing screenshot: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте еще раз.")

# ====================== Админ-команды ======================
@dp.message(lambda message: message.text == "👥 Список сотрудников")
async def admin_employees(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    employees = get_all_employees()
    if not employees:
        await message.answer("📭 Пока нет зарегистрированных сотрудников.")
        return
    
    text = "👥 **Список сотрудников:**\n\n"
    for i, emp in enumerate(employees, 1):
        total = get_employee_registrations_total(emp['user_id'])
        text += f"{i}. {emp['full_name']}\n"
        text += f"   🆔 ID: {emp['user_id']}\n"
        text += f"   📱 Username: @{emp['username'] or 'нет'}\n"
        text += f"   📸 Всего регистраций: {total}\n\n"
    
    await message.answer(text, parse_mode="Markdown", reply_markup=get_employee_list_keyboard(employees))

@dp.message(lambda message: message.text == "📊 Статистика за сегодня")
async def admin_today_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    today = datetime.now().strftime("%d.%m.%Y")
    stats = get_today_stats()
    
    if not stats:
        await message.answer("📭 Пока нет данных.")
        return
    
    text = f"📊 **Статистика регистраций Яндекс**\n"
    text += f"📅 {today}\n\n"
    total = 0
    
    for stat in stats:
        count = stat['count']
        total += count
        text += f"👤 {stat['full_name']}: {count} шт.\n"
    
    text += f"\n📈 **Всего регистраций: {total}**"
    await message.answer(text, parse_mode="Markdown")

@dp.message(lambda message: message.text == "📅 Статистика за дату")
async def admin_ask_date(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "📅 Введите дату в формате **ГГГГ-ММ-ДД**\n\n"
        "Пример: 2026-03-21",
        parse_mode="Markdown"
    )

@dp.message(lambda message: message.text == "📸 Все регистрации")
async def admin_all_sales(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    employees = get_all_employees()
    if not employees:
        await message.answer("📭 Пока нет данных.")
        return
    
    text = "📸 **Все регистрации Яндекс по сотрудникам**\n\n"
    total_all = 0
    
    for emp in employees:
        total = get_employee_registrations_total(emp['user_id'])
        total_all += total
        text += f"👤 **{emp['full_name']}**: {total} шт.\n"
    
    text += f"\n📈 **Общее количество регистраций: {total_all}**"
    await message.answer(text, parse_mode="Markdown")

@dp.message()
async def handle_date_input(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        date = message.text.strip()
        datetime.strptime(date, "%Y-%m-%d")
        
        stats = get_date_stats(date)
        formatted_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d.%m.%Y")
        
        text = f"📊 **Статистика регистраций Яндекс**\n"
        text += f"📅 {formatted_date}\n\n"
        total = 0
        
        for stat in stats:
            count = stat['count']
            total += count
            text += f"👤 {stat['full_name']}: {count} шт.\n"
        
        text += f"\n📈 **Всего: {total}**"
        await message.answer(text, parse_mode="Markdown")
        
    except ValueError:
        pass

# ====================== Callback handlers ======================
@dp.callback_query()
async def handle_callbacks(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа")
        return
    
    data = callback.data
    
    if data.startswith("emp_"):
        employee_id = int(data.split("_")[1])
        employee = get_employee(employee_id)
        if employee:
            total = get_employee_registrations_total(employee_id)
            await callback.message.edit_text(
                f"📊 **{employee['full_name']}**\n\n"
                f"📈 Всего регистраций: {total}\n\n"
                f"Выберите период для детального просмотра:",
                parse_mode="Markdown",
                reply_markup=get_date_keyboard(employee_id)
            )
    
    elif data.startswith("date_today_"):
        employee_id = int(data.split("_")[2])
        employee = get_employee(employee_id)
        today = datetime.now().strftime("%Y-%m-%d")
        count = get_registrations_stats(employee_id, today)
        
        await callback.message.edit_text(
            f"📊 **{employee['full_name']}**\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y')}\n\n"
            f"📸 Регистраций сегодня: {count}",
            parse_mode="Markdown",
            reply_markup=get_date_keyboard(employee_id)
        )
    
    elif data.startswith("date_yesterday_"):
        employee_id = int(data.split("_")[2])
        employee = get_employee(employee_id)
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        count = get_registrations_stats(employee_id, yesterday)
        
        await callback.message.edit_text(
            f"📊 **{employee['full_name']}**\n"
            f"📅 {(datetime.now() - timedelta(days=1)).strftime('%d.%m.%Y')}\n\n"
            f"📸 Регистраций вчера: {count}",
            parse_mode="Markdown",
            reply_markup=get_date_keyboard(employee_id)
        )
    
    elif data == "back_employees":
        employees = get_all_employees()
        text = "👥 **Список сотрудников:**\n\n"
        for i, emp in enumerate(employees, 1):
            total = get_employee_registrations_total(emp['user_id'])
            text += f"{i}. {emp['full_name']}\n"
            text += f"   🆔 ID: {emp['user_id']}\n"
            text += f"   📱 Username: @{emp['username'] or 'нет'}\n"
            text += f"   📸 Всего регистраций: {total}\n\n"
        
        await callback.message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=get_employee_list_keyboard(employees)
        )
    
    elif data == "back":
        await callback.message.delete()
        await callback.message.answer(
            "👋 Здравствуйте, Администратор!\n\n"
            "🤖 Бот для учёта скриншотов регистрации в Яндекс.Сервисах\n"
            "💾 Данные сохраняются локально на сервере\n\n"
            "Используйте кнопки для управления:",
            reply_markup=get_admin_keyboard()
        )
    
    await callback.answer()

# ====================== Запуск ======================
async def main():
    """Основная функция"""
    # Инициализация базы данных
    init_db()
    
    logger.info("Starting bot polling...")
    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
        skip_updates=True
    )

if __name__ == "__main__":
    asyncio.run(main())
