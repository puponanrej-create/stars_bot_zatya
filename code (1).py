import logging
import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# --- ТВОИ ДАННЫЕ ---
API_TOKEN = '8211870455:AAGa_p1hwXYCNXZWjl518fwNdll_QxnHVLw'
ADMIN_ID = 8596393850  # Твой ID
REQUISITES = "89878343491 (Альфа Банк)"
STARS_RATE = 1.44
STEAM_COMMISSION = 1.05

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ (создается автоматически) ---
conn = sqlite3.connect('bot_data.db')
cur = conn.cursor()
cur.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0)''')
conn.commit()

# --- СОСТОЯНИЯ ---
class Order(StatesGroup):
    steam_data = State()
    stars_count = State()
    stars_recipient = State()
    waiting_payment = State()

# --- КЛАВИАТУРЫ ---
def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎮 Пополнить Steam"), KeyboardButton(text="🌟 Купить Stars")],
        [KeyboardButton(text="🎟 Ввести промокод"), KeyboardButton(text="👨‍💻 Поддержка")]
    ], resize_keyboard=True)

def stars_count_kb():
    buttons = [
        [InlineKeyboardButton(text="50 ⭐", callback_query_data="stars_50"), InlineKeyboardButton(text="100 ⭐", callback_query_data="stars_100")],
        [InlineKeyboardButton(text="500 ⭐", callback_query_data="stars_500"), InlineKeyboardButton(text="1000 ⭐", callback_query_data="stars_1000")],
        [InlineKeyboardButton(text="Своё кол-во", callback_query_data="stars_custom")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- ОБРАБОТКА КОМАНД ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        f"Привет! 👋 Ты попал в сервис пополнения Steam и Stars.\nВыбери услугу в меню ниже:",
        reply_markup=main_kb()
    )

@dp.message(F.text == "👨‍💻 Поддержка")
async def support(message: types.Message):
    await message.answer(f"По всем вопросам и для связи с админом: @твоё_имя_в_тг")

# --- ЛОГИКА STEAM ---
@dp.message(F.text == "🎮 Пополнить Steam")
async def steam_start(message: types.Message, state: FSMContext):
    await message.answer("Напишите ваш **Логин Steam** и **Сумму** через пробел:\n(Пример: `ivanov123 500`)")
    await state.set_state(Order.steam_data)

@dp.message(Order.steam_data)
async def steam_process(message: types.Message, state: FSMContext):
    try:
        parts = message.text.split()
        login = parts[0]
        amount = float(parts[1])
        total = amount * STEAM_COMMISSION
        
        await state.update_data(service="Steam", login=login, amount=amount, total=total)
        await message.answer(
            f"📊 **Заказ Steam**\nЛогин: `{login}`\nК зачислению: {amount} руб.\n\n"
            f"💳 **К оплате (с комиссией):** `{total:.2f}` руб.\n"
            f"Реквизиты: `{REQUISITES}`\n\n"
            f"Пришлите скриншот оплаты:"
        )
        await state.set_state(Order.waiting_payment)
    except:
        await message.answer("Пожалуйста, введите данные через пробел: Логин и Сумма (число).")

# --- ЛОГИКА STARS ---
@dp.message(F.text == "🌟 Купить Stars")
async def stars_start(message: types.Message):
    await message.answer("Выберите количество звезд:", reply_markup=stars_count_kb())

@dp.callback_query(F.data.startswith("stars_"))
async def stars_select(callback: types.CallbackQuery, state: FSMContext):
    count_data = callback.data.split("_")[1]
    if count_data == "custom":
        await callback.message.answer("Введите количество звезд (от 50):")
        await state.set_state(Order.stars_count)
    else:
        await state.update_data(stars_count=int(count_data))
        await ask_recipient(callback.message)
    await callback.answer()

async def ask_recipient(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Себе", callback_query_data="target_me")],
        [InlineKeyboardButton(text="Другому (ввести юзернейм)", callback_query_data="target_other")]
    ])
    await message.answer("Кому отправить звёзды?", reply_markup=kb)

@dp.callback_query(F.data.startswith("target_"))
async def stars_target(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "target_me":
        data = await state.get_data()
        total = data['stars_count'] * STARS_RATE
        await state.update_data(recipient=f"@{callback.from_user.username}", total=total, service="Stars")
        await finalize_stars_order(callback.message, state)
    else:
        await callback.message.answer("Введите @юзернейм получателя:")
        await state.set_state(Order.stars_recipient)
    await callback.answer()

@dp.message(Order.stars_recipient)
async def stars_custom_target(message: types.Message, state: FSMContext):
    data = await state.get_data()
    total = data['stars_count'] * STARS_RATE
    await state.update_data(recipient=message.text, total=total, service="Stars")
    await finalize_stars_order(message, state)

async def finalize_stars_order(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await message.answer(
        f"📊 **Заказ Stars**\nКол-во: {data['stars_count']}\nПолучатель: {data['recipient']}\n\n"
        f"💳 **К оплате:** `{data['total']:.2f}` руб.\n"
        f"Реквизиты: `{REQUISITES}`\n\nПришлите скриншот оплаты:"
    )
    await state.set_state(Order.waiting_payment)

# --- ПРИЕМ ОПЛАТЫ ---
@dp.message(Order.waiting_payment, F.photo | F.document)
async def handle_payment(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    # Текст заказа для тебя (админа)
    admin_msg = (
        f"📦 **НОВЫЙ ЗАКАЗ**\n"
        f"От: @{message.from_user.username} (ID: {message.from_user.id})\n"
        f"Услуга: {data['service']}\n"
        f"Данные: {data.get('login') or data.get('recipient')}\n"
        f"Сумма: {data['total']:.2f} руб."
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выполнено", callback_query_data=f"op_done_{message.from_user.id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_query_data=f"op_cancel_{message.from_user.id}")]
    ])
    
    await bot.send_message(ADMIN_ID, admin_msg)
    
    if message.photo:
        await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, reply_markup=kb)
    else:
        await bot.send_document(ADMIN_ID, message.document.file_id, reply_markup=kb)
        
    await message.answer("⏳ Чек отправлен на проверку. Ожидайте уведомления о выполнении!")
    await state.clear()

# --- ОБРАБОТКА КНОПОК АДМИНА ---
@dp.callback_query(F.data.startswith("op_"))
async def admin_action(callback: types.CallbackQuery):
    action, status, user_id = callback.data.split("_")
    if status == "done":
        await bot.send_message(user_id, "✅ Ваш заказ успешно выполнен! Спасибо за покупку!")
        await callback.message.edit_caption(caption=callback.message.caption + "\n\nСТАТУС: ВЫПОЛНЕНО ✅")
    else:
        await bot.send_message(user_id, "❌ Заказ отклонен. Если возникла ошибка — напишите в поддержку.")
        await callback.message.edit_caption(caption=callback.message.caption + "\n\nСТАТУС: ОТКЛОНЕНО ❌")
    await callback.answer()

# --- ЗАПУСК ---
async def main():
    print("Бот запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен")