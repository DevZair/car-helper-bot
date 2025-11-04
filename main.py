import logging
import re
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from cars_database import init_cars_db, get_cars_by_category, get_discounted_cars, get_cars_by_filters
from config import TELEGRAM_BOT_TOKEN
from database import init_db, get_answer, save_user
from ai_module import ask_ollama

# === ЛОГИ ===
logging.basicConfig(filename="logs/bot.log", level=logging.INFO, format="%(asctime)s - %(message)s")

user_state = {}
user_info = {}
filter_info = {}

# === МЕНЮ ===
def category_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚗 Легковой", callback_data="Легковой")],
        [InlineKeyboardButton("🚙 Кроссовер", callback_data="Кроссовер")],
        [InlineKeyboardButton("🚚 Грузовой", callback_data="Грузовой")],
        [InlineKeyboardButton("🔥 Выгодные предложения", callback_data="discounted")],
        [InlineKeyboardButton("🎯 Фильтр", callback_data="filter")],
        [InlineKeyboardButton("🔎 Искать по названию", callback_data="search_name")],
        [InlineKeyboardButton("💰 Искать по цене", callback_data="search_price")],
    ])

# === ПОИСК ПО НАЗВАНИЮ ===
def search_car_by_name(query: str):
    conn = sqlite3.connect("data/cars.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT brand, model, price, description, image, specs
        FROM cars
        WHERE LOWER(model) LIKE LOWER(?) OR LOWER(brand || ' ' || model) LIKE LOWER(?)
    """, (f"%{query}%", f"%{query}%"))
    result = cur.fetchall()
    conn.close()
    return result

# === ПОИСК ПО ЦЕНЕ ===
def search_car_by_price(price: int):
    lower = price - 2_000_000
    upper = price + 2_000_000
    conn = sqlite3.connect("data/cars.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT brand, model, price, description, image, specs
        FROM cars
        WHERE REPLACE(REPLACE(price, '₸', ''), ' ', '') + 0 BETWEEN ? AND ?
    """, (lower, upper))
    result = cur.fetchall()
    conn.close()
    return result

# === /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("👋 Привет! Как тебя зовут?")
    user_state[chat_id] = "ask_name"

# === ОСНОВНАЯ ЛОГИКА ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    state = user_state.get(chat_id)

    # === АНКЕТА ===
    if state == "ask_name":
        user_info[chat_id] = {"name": text}
        user_state[chat_id] = "ask_age"
        await update.message.reply_text("📅 Сколько тебе лет?")
        return

    elif state == "ask_age":
        user_info[chat_id]["age"] = text
        user_state[chat_id] = "ask_city"
        await update.message.reply_text("🏙️ Из какого ты города?")
        return

    elif state == "ask_city":
        user_info[chat_id]["city"] = text
        # сохраняем пользователя
        save_user(
            user_info[chat_id]["name"],
            user_info[chat_id]["age"],
            user_info[chat_id]["city"],
            chat_id
        )
        user_state[chat_id] = None
        await update.message.reply_text(
            f"Отлично, {user_info[chat_id]['name']}! 🚘 Выбери категорию:",
            reply_markup=category_menu()
        )
        return

    # === ФИЛЬТР ===
    if state == "filter_brand":
        if not text or text.lower() == "пропустить":
            filter_info[chat_id] = {"brand": None}
        else:
            filter_info[chat_id] = {"brand": text}
        user_state[chat_id] = "filter_model"
        await update.message.reply_text("✏️ Укажи модель (или напиши 'пропустить'):")
        return

    if state == "filter_model":
        info = filter_info.get(chat_id, {})
        if not text or text.lower() == "пропустить":
            info["model"] = None
        else:
            info["model"] = text
        filter_info[chat_id] = info

        cars = get_cars_by_filters(
            brand=info.get("brand"),
            model=info.get("model")
        )

        if cars:
            await update.message.reply_text("🎯 Результаты фильтра:\n")
            for brand, model, price, desc, img, specs in cars:
                caption = f"*{brand} {model}* — {price}\n_{desc}_\n\n⚙️ *Характеристики:* {specs}"
                try:
                    with open(f"data/reactions/{img}", "rb") as p:
                        await update.message.reply_photo(p, caption=caption, parse_mode="Markdown")
                except FileNotFoundError:
                    await update.message.reply_text(caption, parse_mode="Markdown")
        else:
            await update.message.reply_text("😔 Машины по заданным параметрам не найдены.")

        filter_info.pop(chat_id, None)
        user_state[chat_id] = None
        await update.message.reply_text("Выбери следующее действие:", reply_markup=category_menu())
        return

    # === ПОИСК ПО НАЗВАНИЮ ===
    if state == "search_by_name":
        result = search_car_by_name(text)
        if result:
            await update.message.reply_text("🔍 Результаты поиска:\n")
            for brand, model, price, desc, img, specs in result:
                caption = f"*{brand} {model}* — {price}\n_{desc}_\n\n⚙️ *Характеристики:* {specs}"
                try:
                    with open(f"data/reactions/{img}", "rb") as p:
                        await update.message.reply_photo(p, caption=caption, parse_mode="Markdown")
                except FileNotFoundError:
                    await update.message.reply_text(caption, parse_mode="Markdown")
        else:
            await update.message.reply_text("😔 Машина не найдена.")
        user_state[chat_id] = None
        await update.message.reply_text("Выбери следующее действие:", reply_markup=category_menu())
        return

    # === ПОИСК ПО ЦЕНЕ ===
    if state == "search_by_price":
        digits = re.findall(r"\d+", text)
        if not digits:
            await update.message.reply_text("❗ Введите число (например: 12000000)")
            return
        price = int(digits[0])
        result = search_car_by_price(price)
        if result:
            await update.message.reply_text(f"💰 Машины около {price:,} ₸:\n".replace(",", " "))
            for brand, model, price, desc, img, specs in result:
                caption = f"*{brand} {model}* — {price}\n_{desc}_\n\n⚙️ *Характеристики:* {specs}"
                try:
                    with open(f"data/reactions/{img}", "rb") as p:
                        await update.message.reply_photo(p, caption=caption, parse_mode="Markdown")
                except FileNotFoundError:
                    await update.message.reply_text(caption, parse_mode="Markdown")
        else:
            await update.message.reply_text("😔 Ничего не найдено.")
        user_state[chat_id] = None
        await update.message.reply_text("Выбери следующее действие:", reply_markup=category_menu())

# === ОБРАБОТКА КНОПОК ===
async def handle_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "discounted":
        cars = get_discounted_cars()
        if not cars:
            await query.edit_message_text("😔 Сейчас нет выгодных предложений.")
            return
        await query.edit_message_text("🔥 *Выгодные предложения:*\n", parse_mode="Markdown")
        for brand, model, price, desc, img, specs in cars:
            caption = f"🔥 *{brand} {model}* — {price}\n_{desc}_\n\n⚙️ *Характеристики:* {specs}"
            try:
                with open(f"data/reactions/{img}", "rb") as p:
                    await query.message.reply_photo(p, caption=caption, parse_mode="Markdown")
            except FileNotFoundError:
                await query.message.reply_text(caption, parse_mode="Markdown")
        await query.message.reply_text("Выбери другую категорию:", reply_markup=category_menu())
        return

    # обычные категории
    if data in ["Легковой", "Кроссовер", "Грузовой"]:
        cars = get_cars_by_category(data)
        if not cars:
            await query.edit_message_text(f"🚫 Нет данных по категории: {data}")
            return
        await query.edit_message_text(f"🚘 Категория *{data}*:", parse_mode="Markdown")
        for brand, model, price, desc, img, specs in cars:
            caption = f"*{brand} {model}* — {price}\n_{desc}_\n\n⚙️ *Характеристики:* {specs}"
            try:
                with open(f"data/reactions/{img}", "rb") as p:
                    await query.message.reply_photo(p, caption=caption, parse_mode="Markdown")
            except FileNotFoundError:
                await query.message.reply_text(caption, parse_mode="Markdown")
        await query.message.reply_text("Выбери другую категорию:", reply_markup=category_menu())

    elif data == "search_name":
        user_state[query.from_user.id] = "search_by_name"
        await query.edit_message_text("✏️ Введите название (например: Camry 50):")

    elif data == "search_price":
        user_state[query.from_user.id] = "search_by_price"
        await query.edit_message_text("💰 Введите примерную цену (например: 12000000):")

    elif data == "filter":
        filter_info[query.from_user.id] = {}
        user_state[query.from_user.id] = "filter_brand"
        await query.edit_message_text("🏷️ Укажи марку (или напиши 'пропустить'):")

# === MAIN ===
def main():
    init_db()
    init_cars_db()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_category))
    print("🤖 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
