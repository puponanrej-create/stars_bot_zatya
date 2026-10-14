import asyncio
import logging
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# НОВЫЙ ТОКЕН И ТВОЙ АЙДИ АДМИНА
TOKEN = "8211870455:AAHyJUn4bA690-dpgSHKQLoh1CNCJpcFZy8"
ADMIN_ID = 8596393850

DB = "stars_bot.sqlite3"
RATE = Decimal("1.4")
REQUISITES = "89878343491 (Альфа-Банк)"
STICKER_LINK = "https://t.me/addemoji/GiftRoadStars_bot"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

class Flow(StatesGroup):
    promo = State()
    friend = State()
    amount = State()
    receipt = State()


def db(query, args=(), one=False, commit=False):
    with sqlite3.connect(DB) as conn:
        cur = conn.execute(query, args)
        result = cur.fetchone() if one else cur.fetchall()
        if commit:
            conn.commit()
        return result


def init_db():
    with sqlite3.connect(DB) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          user_id INTEGER PRIMARY KEY, username TEXT, stars INTEGER NOT NULL DEFAULT 0,
          spent REAL NOT NULL DEFAULT 0, promo_discount REAL NOT NULL DEFAULT 0,
          promo_code TEXT, promo_used INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS promos(
          code TEXT PRIMARY KEY, discount REAL NOT NULL, enabled INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS orders(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, username TEXT,
          recipient TEXT NOT NULL, stars INTEGER NOT NULL, price REAL NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending'
        );
        """)
        # Тестовый промокод NEW на 10% скидки
        c.execute("INSERT OR IGNORE INTO promos(code, discount, enabled) VALUES('NEW', 10.0, 1)")

init_db()

async def ensure_user(user: types.User):
    db("INSERT OR IGNORE INTO users(user_id, username) VALUES(?,?)", (user.id, user.username or user.first_name), commit=True)
    db("UPDATE users SET username=? WHERE user_id=?", (user.username or user.first_name, user.id), commit=True)

# 3 кнопки под постом на главном экране (купить звезды, профиль, промокод)
def home_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌟 Купить звезды", callback_data="buy")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"), InlineKeyboardButton(text="🎟 Промокод", callback_data="promo")]
    ])

def recipient_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1. Себе", callback_data="recipient_self")],
        [InlineKeyboardButton(text="2. Другу", callback_data="recipient_friend")],
        [InlineKeyboardButton(text="3. Назад", callback_data="home")]
    ])

def amount_kb():
    values = [50, 100, 250, 500, 1000, 2500]
    rows = [[InlineKeyboardButton(text=f"{n} ⭐", callback_data=f"amount:{n}") for n in values[i:i+2]] for i in range(0, len(values), 2)]
    rows += [[InlineKeyboardButton(text="🔄 Сменить получателя", callback_data="change_recipient")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 На главную", callback_data="home")]])

async def show_home(message, user):
    name = f"@{user.username}" if user.username else (user.first_name or "друг")
    text = f"Привет {name} для того чтобы купить звезд нажмите кнопку снизу 👇"
    await message.answer(text, reply_markup=home_kb())

@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    await ensure_user(message.from_user)
    await show_home(message, message.from_user)

@dp.callback_query(F.data == "home")
async def home(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    try:
        await call.message.delete()
    except Exception:
        pass
    await show_home(call.message, call.from_user)

@dp.callback_query(F.data == "profile")
async def profile(call: types.CallbackQuery):
    await ensure_user(call.from_user)
    stars, spent = db("SELECT stars, spent FROM users WHERE user_id=?", (call.from_user.id,), one=True)
    nick = f"@{call.from_user.username}" if call.from_user.username else call.from_user.first_name
    text = f"👤 **Ваш профиль:**\n\nНик: {nick}\nПриобретено звёзд: {stars} ⭐\nПотрачено денег: {spent:.2f} ₽"
    try:
        await call.message.edit_text(text=text, reply_markup=back_kb())
    except Exception:
        await call.message.answer(text, reply_markup=back_kb())
    await call.answer()

@dp.callback_query(F.data == "promo")
async def promo_start(call: types.CallbackQuery, state: FSMContext):
    await ensure_user(call.from_user)
    await state.set_state(Flow.promo)
    await call.message.answer("Напишите свой промокод сюда:", reply_markup=back_kb())
    await call.answer()

@dp.message(Flow.promo, F.text)
async def promo_apply(message: types.Message, state: FSMContext):
    await ensure_user(message.from_user)
    code = message.text.strip().upper()
    row = db("SELECT discount FROM promos WHERE code=? AND enabled=1", (code,), one=True)
    user = db("SELECT promo_used, promo_code FROM users WHERE user_id=?", (message.from_user.id,), one=True)
    if not row:
        await message.answer("❌ Такого промокода не существует или он неактивен. Попробуйте ещё раз:", reply_markup=back_kb())
    elif user[0]:
        await message.answer("❌ Вы уже использовали промокод ранее.", reply_markup=back_kb())
        await state.clear()
    else:
        db("UPDATE users SET promo_discount=?, promo_code=? WHERE user_id=?", (row[0], code, message.from_user.id), commit=True)
        await message.answer(f"✅ Промокод успешно применен! Скидка {row[0]:g}% учтется при покупке.", reply_markup=back_kb())
        await state.clear()

@dp.callback_query(F.data == "buy")
async def buy(call: types.CallbackQuery, state: FSMContext):
    await ensure_user(call.from_user)
    await state.clear()
    await state.set_state(Flow.amount)
    try:
        await call.message.delete()
    except Exception:
        pass
    text = "Кому покупаем звезды?"
    await call.message.answer(text, reply_markup=recipient_kb())
    await call.answer()

async def ask_amount(message, state, recipient):
    await state.update_data(recipient=recipient)
    await state.set_state(Flow.amount)
    text = f"Сколько звезд? Получатель: {recipient}\nНапишите любое кол-во в чат например : 777 Или выберите готовую сумму ниже"
    await message.answer(text, reply_markup=amount_kb())

@dp.callback_query(F.data == "recipient_self")
async def self_recipient(call: types.CallbackQuery, state: FSMContext):
    recipient = f"@{call.from_user.username}" if call.from_user.username else str(call.from_user.id)
    await ask_amount(call.message, state, recipient)
    await call.answer()

@dp.callback_query(F.data == "recipient_friend")
async def friend_start(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Flow.friend)
    await call.message.answer("✏️ Введите @username друга, которому покупаем звезды:")
    await call.answer()

@dp.message(Flow.friend, F.text)
async def friend_input(message: types.Message, state: FSMContext):
    recipient = message.text.strip().lstrip("@")
    if not recipient or len(recipient) > 32 or not recipient.replace("_", "").isalnum():
        await message.answer("❌ Укажите корректный username (буквы, цифры и _).")
        return
    await ask_amount(message, state, "@" + recipient)

@dp.callback_query(F.data == "change_recipient")
async def change_recipient(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Flow.amount)
    await call.message.answer("Кому покупаем звезды?", reply_markup=recipient_kb())
    await call.answer()

async def make_order(message, state: FSMContext, count: int):
    if count < 1:
        await message.answer("Количество звезд должно быть больше 0.")
        return
    data = await state.get_data()
    await ensure_user(message.from_user)
    discount, code, used = db("SELECT promo_discount, promo_code, promo_used FROM users WHERE user_id=?", (message.from_user.id,), one=True)
    
    raw_price = Decimal(count) * RATE
    if discount and not used:
        final_price = raw_price * (Decimal(100) - Decimal(str(discount))) / Decimal(100)
    else:
        final_price = raw_price
    price = final_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    order_id = db("INSERT INTO orders(user_id, username, recipient, stars, price) VALUES(?,?,?,?,?) RETURNING id",
                  (message.from_user.id, message.from_user.username or message.from_user.first_name, data["recipient"], count, float(price)), one=True, commit=True)[0]
    
    await state.update_data(order_id=order_id, count=count, price=float(price))
    await state.set_state(Flow.receipt)
    
    text = (
        f"🌟 **Ваш заказ №{order_id}**\n"
        f"• Получатель: {data['recipient']}\n"
        f"• Количество: {count} ⭐\n"
        f"• К оплате: `{price:.2f}` ₽" + (f" (скидка {discount:g}%)" if discount and not used else "") + "\n\n"
        f"🏦 **Реквизиты для оплаты:** {REQUISITES}\n"
        f"🎁 **Telegram Премиум стикеры:** {STICKER_LINK}\n\n"
        f"⚠️ После перевода отправьте сюда скриншот или файл чека."
    )
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Сменить получателя", callback_data="change_recipient")]]))

@dp.callback_query(F.data.startswith("amount:"), Flow.amount)
async def amount_button(call: types.CallbackQuery, state: FSMContext):
    await make_order(call.message, state, int(call.data.split(":")[1]))
    await call.answer()

@dp.message(Flow.amount, F.text)
async def amount_text(message: types.Message, state: FSMContext):
    try:
        count = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите целое число (например: 777) или выберите сумму кнопкой.")
        return
    await make_order(message, state, count)

@dp.message(Flow.receipt, F.photo | F.document)
async def receipt(message: types.Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get("order_id")
    if not order_id:
        await message.answer("❌ Заказ не найден. Начните сначала: /start")
        await state.clear()
        return
    
    username = f"@{message.from_user.username}" if message.from_user.username else str(message.from_user.id)
    admin_text = (
        f"📦 **Пришел новый заказ!**\n"
        f"• Заказ №{order_id}\n"
        f"• Покупатель: {username} (ID: `{message.from_user.id}`)\n"
        f"• Получатель: {data['recipient']}\n"
        f"• Количество звезд: {data['count']} ⭐\n"
        f"• Сумма: {data['price']:.2f} ₽\n"
        f"• Реквизиты: {REQUISITES}\n"
        f"• Стикеры: {STICKER_LINK}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выполнено / Отправлено", callback_data=f"done:{order_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{order_id}")]
    ])
    
    await bot.send_message(ADMIN_ID, admin_text)
    if message.photo:
        await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, reply_markup=kb)
    else:
        await bot.send_document(ADMIN_ID, message.document.file_id, reply_markup=kb)
        
    db("UPDATE orders SET status='receipt_received' WHERE id=?", (order_id,), commit=True)
    await message.answer("Спасибо за покупку ,звезды будут отправлены в течении ≈5минут")
    await state.clear()

async def admin_order_action(call: types.CallbackQuery, action: str, order_id: int):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Недостаточно прав", show_alert=True)
        return
    order = db("SELECT user_id, stars, price, status FROM orders WHERE id=?", (order_id,), one=True)
    if not order:
        await call.answer("Заказ не найден", show_alert=True)
        return
    user_id, stars, price, status = order
    if status != "receipt_received":
        await call.answer("Заказ уже обработан или чек еще не прикреплен", show_alert=True)
        return
    
    name = call.from_user.first_name or "Админ"
    if action == "done":
        db("UPDATE orders SET status='completed' WHERE id=?", (order_id,), commit=True)
        db("UPDATE users SET stars=stars+?, spent=spent+?, promo_used=CASE WHEN promo_discount>0 THEN 1 ELSE promo_used END, promo_discount=0, promo_code=NULL WHERE user_id=?",
           (stars, price, user_id), commit=True)
        await bot.send_message(user_id, "🎉 Ваши звезды успешно отправлены! Спасибо за покупку ❤️")
        try:
            await call.message.edit_caption(caption=(call.message.caption or "") + f"\n\n🟢 СТАТУС: ВЫПОЛНЕНО ({name})")
        except Exception:
            try:
                await call.message.edit_text(text=(call.message.text or "") + f"\n\n🟢 СТАТУС: ВЫПОЛНЕНО ({name})")
            except Exception:
                pass
        await call.answer("Заказ отмечен выполненным")
    else:
        db("UPDATE orders SET status='rejected' WHERE id=?", (order_id,), commit=True)
        await bot.send_message(user_id, "❌ Ваш заказ был отклонен. Если это ошибка, напишите в поддержку.")
        try:
            await call.message.edit_caption(caption=(call.message.caption or "") + f"\n\n🔴 СТАТУС: ОТКЛОНЕНО ({name})")
        except Exception:
            try:
                await call.message.edit_text(text=(call.message.text or "") + f"\n\n🔴 СТАТУС: ОТКЛОНЕНО ({name})")
    
            except Exception:
                pass
        await call.answer("Заказ отклонён")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

@dp.callback_query(F.data.startswith("done:"))
async def done(call: types.CallbackQuery, state: FSMContext):
    await admin_order_action(call, "done", int(call.data.split(":")[1]))

@dp.callback_query(F.data.startswith("reject:"))
async def reject(call: types.CallbackQuery, state: FSMContext):
    await admin_order_action(call, "reject", int(call.data.split(":")[1]))

async def main():
    print("Бот успешно запущен с новым токеном!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
