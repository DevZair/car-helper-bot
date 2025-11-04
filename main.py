import asyncio
import contextlib
import logging
import re
import sqlite3
from collections import defaultdict, deque
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, TimedOut, NetworkError
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from cars_database import (
    init_cars_db,
    get_cars_by_category,
    get_discounted_cars,
    get_cars_by_filters,
    get_all_cars,
)
from config import TELEGRAM_BOT_TOKEN
from database import init_db, get_answer, save_user, get_user_by_chat_id, save_feedback
from ai_module import ask_ollama

logging.basicConfig(filename="logs/bot.log", level=logging.INFO, format="%(asctime)s - %(message)s")

user_state = {}
user_info = {}
filter_info = {}
ai_sessions = {}

YES_ANSWERS = {"да", "ага", "конечно", "давай", "yes", "y"}
NO_ANSWERS = {"нет", "неа", "no", "n", "не надо"}
STOP_WORDS = {"стоп", "выход", "меню"}
AI_RESPONSE_TIMEOUT = 60

async def send_loading(message):
    try:
        return await message.reply_text("⏳ loading...")
    except (TimedOut, NetworkError) as exc:
        logging.warning("Не удалось отправить индикатор загрузки: %s", exc)
        return None


async def send_car_card(target_message, caption: str, image_name: str | None):
    if image_name:
        try:
            with open(f"data/reactions/{image_name}", "rb") as photo:
                await target_message.reply_photo(photo, caption=caption, parse_mode="Markdown")
                return
        except (FileNotFoundError, BadRequest, TimedOut, NetworkError) as exc:
            logging.warning("Не удалось отправить фото %s: %s", image_name, exc)
        except Exception as exc:
            logging.exception("Неизвестная ошибка при отправке фото %s: %s", image_name, exc)
    await target_message.reply_text(caption, parse_mode="Markdown")


async def finalize_loading(loading_message, fallback_target, text: str):
    if loading_message:
        try:
            await loading_message.edit_text(text)
            return
        except (BadRequest, NetworkError, TimedOut) as exc:
            logging.warning("Не удалось обновить сообщение: %s", exc)
            with contextlib.suppress(Exception):
                await loading_message.delete()
        except Exception as exc:
            logging.exception("Неизвестная ошибка при обновлении сообщения: %s", exc)
            with contextlib.suppress(Exception):
                await loading_message.delete()
    await fallback_target.reply_text(text)


async def edit_or_send(query, text: str, **kwargs):
    try:
        await query.edit_message_text(text, **kwargs)
    except (BadRequest, NetworkError, TimedOut) as exc:
        logging.warning("Не удалось изменить сообщение: %s", exc)
        await query.message.reply_text(text, **kwargs)
    except Exception as exc:
        logging.exception("Неизвестная ошибка при изменении сообщения: %s", exc)
        await query.message.reply_text(text, **kwargs)


def category_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚗 Легковой", callback_data="Легковой"),
            InlineKeyboardButton("🚙 Кроссовер", callback_data="Кроссовер"),
        ],
        [
            InlineKeyboardButton("🚚 Грузовой", callback_data="Грузовой"),
            InlineKeyboardButton("⚡ Электромобили", callback_data="Электромобили"),
        ],
        [
            InlineKeyboardButton("♻️ Гибриды", callback_data="Гибриды"),
            InlineKeyboardButton("🔥 Выгодные предложения", callback_data="discounted"),
        ],
        [
            InlineKeyboardButton("🎯 Фильтр", callback_data="filter"),
            InlineKeyboardButton("🔎 Искать по названию", callback_data="search_name"),
        ],
        [InlineKeyboardButton("💰 Искать по цене", callback_data="search_price")],
        [InlineKeyboardButton("🤖 Спросить совет у AI", callback_data="ask_ai")],
    ])


def get_ai_session(chat_id: int):
    session = ai_sessions.get(chat_id)
    if not session:
        session = {"history": deque(maxlen=10), "last_suggestions": []}
        ai_sessions[chat_id] = session
    return session


def get_or_load_user(chat_id: int):
    info = user_info.get(chat_id)
    if info:
        return info
    existing = get_user_by_chat_id(chat_id)
    if existing:
        data = {
            "id": existing["id"],
            "name": existing["name"],
            "age": existing["age"],
            "city": existing["city"],
        }
        user_info[chat_id] = data
        return data
    return None


def build_ai_prompt(chat_id: int, question: str):
    user = get_or_load_user(chat_id)
    cars = get_all_cars()
    grouped = defaultdict(list)
    for category, brand, model, price, description, image, specs in cars:
        grouped[category].append({
            "brand": brand,
            "model": model,
            "price": price,
            "specs": specs,
        })

    lines = []
    if user:
        city = f", город {user['city']}" if user.get("city") else ""
        age = user.get("age")
        age_text = f", {age} лет" if age else ""
        lines.append(f"Пользователь: {user['name']}{age_text}{city}")
    else:
        lines.append("Пользователь: данные не указаны, обращение первое.")

    session = ai_sessions.get(chat_id)
    history = session.get("history") if session else None
    if history:
        lines.append("История диалога:")
        for role, message in history:
            prefix = "Пользователь" if role == "user" else "Бот"
            lines.append(f"{prefix}: {message}")

    lines.append("Доступные автомобили (до 3 моделей в категории):")
    for category, items in grouped.items():
        lines.append(f"{category}:")
        for car in items[:3]:
            lines.append(f"- {car['brand']} {car['model']} — {car['price']} ({car['specs']})")

    lines.append("Задача: учитывая предпочтения пользователя, порекомендуй автомобили из базы и объясни выбор.")
    lines.append(f"Вопрос пользователя: {question}")
    lines.append(
        "Отвечай по-русски, дружелюбно и максимально кратко (не больше 2-3 предложений). "
        "Если информации не хватает, предложи уточнить детали."
    )
    lines.append(
        "В конце добавь строку в формате 'Рекомендую: <модель1>, <модель2>' с названиями моделей из списка. "
        "Если подходящих вариантов нет, напиши 'Рекомендую: нет данных'."
    )
    return "\n".join(lines)


def match_cars_from_response(response: str):
    marker = "рекомендую:"
    idx = response.lower().rfind(marker)
    if idx == -1:
        return []

    recommendations = response[idx + len(marker):].strip()
    if not recommendations:
        return []

    tokens = [token.strip(" .") for token in recommendations.replace("\n", " ").split(",")]
    tokens = [token for token in tokens if token]
    if not tokens:
        return []

    catalog = []
    for category, brand, model, price, description, image, specs in get_all_cars():
        catalog.append({
            "category": category,
            "brand": brand,
            "model": model,
            "price": price,
            "description": description,
            "image": image,
            "specs": specs,
            "full_name": f"{brand} {model}".lower(),
        })

    matches = []
    seen = set()
    for token in tokens:
        token_lower = token.lower()
        if token_lower in {"нет данных", "нет", "none"}:
            continue
        for car in catalog:
            if car["full_name"] == token_lower or token_lower in car["full_name"]:
                key = (car["brand"], car["model"])
                if key not in seen:
                    seen.add(key)
                    matches.append(car)
                if len(matches) >= 5:
                    break
        if len(matches) >= 5:
            break
    return matches


async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    payload = query.data.split("|", maxsplit=3)
    if not payload or payload[0] != "feedback":
        logging.warning("Получен неизвестный callback: %s", query.data)
        await query.answer("Действие не поддерживается", show_alert=True)
        return

    if len(payload) < 2:
        logging.warning("Повреждённый feedback payload: %s", query.data)
        await query.edit_message_text("Спасибо за отзыв! 🙌")
        return

    action = payload[1]
    question = payload[2] if len(payload) > 2 else ""
    answer = payload[3] if len(payload) > 3 else ""
    liked = 1 if action == "like" else 0

    user = get_or_load_user(query.from_user.id)
    user_id = user.get("id") if user else None

    if user_id:
        try:
            save_feedback(question, answer, user_id, liked)
        except Exception as exc:
            logging.exception("Не удалось сохранить feedback: %s", exc)

    await query.edit_message_text("Спасибо за отзыв! 🙌")


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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    existing_user = get_user_by_chat_id(chat_id)

    if existing_user:
        user_state[chat_id] = None
        user_info[chat_id] = {
            "id": existing_user["id"],
            "name": existing_user["name"],
            "age": existing_user["age"],
            "city": existing_user["city"],
        }
        city_text = f" из {existing_user['city']}" if existing_user.get("city") else ""
        await update.message.reply_text(
            f"Рад снова тебя видеть, {existing_user['name']}{city_text}! 🚘 Выбери категорию:",
            reply_markup=category_menu()
        )
        return

    await update.message.reply_text("👋 Привет! Как тебя зовут?")
    user_state[chat_id] = "ask_name"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    state = user_state.get(chat_id)
    text_lower = text.lower()

    if state == "ask_name":
        user_info[chat_id] = {"name": text}
        user_state[chat_id] = "ask_age"
        await update.message.reply_text("📅 Сколько тебе лет?")
        return

    elif state == "ask_age":
        user_info[chat_id]["age"] = text
        user_state[chat_id] = "ask_city"
        loading_message = await send_loading(update.message)
        await finalize_loading(loading_message, update.message, "🏙️ Из какого ты города?")
        return

    elif state == "ask_city":
        user_info[chat_id]["city"] = text
        user_id = save_user(
            user_info[chat_id]["name"],
            user_info[chat_id]["age"],
            user_info[chat_id]["city"],
            chat_id
        )
        user_info[chat_id]["id"] = user_id
        user_state[chat_id] = None
        await update.message.reply_text(
            f"Отлично, {user_info[chat_id]['name']}! 🚘 Выбери категорию:",
            reply_markup=category_menu()
        )
        return

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

        loading_message = await send_loading(update.message)

        cars = get_cars_by_filters(
            brand=info.get("brand"),
            model=info.get("model")
        )

        if cars:
            await finalize_loading(loading_message, update.message, "🎯 Результаты фильтра:\n")
            for brand, model, price, desc, img, specs in cars:
                caption = f"*{brand} {model}* — {price}\n_{desc}_\n\n⚙️ *Характеристики:* {specs}"
                await send_car_card(update.message, caption, img)
        else:
            await finalize_loading(loading_message, update.message, "😔 Машины по заданным параметрам не найдены.")

        filter_info.pop(chat_id, None)
        user_state[chat_id] = None
        await update.message.reply_text("Выбери следующее действие:", reply_markup=category_menu())
        return

    if state == "search_by_name":
        loading_message = await send_loading(update.message)
        result = search_car_by_name(text)
        if result:
            await finalize_loading(loading_message, update.message, "🔍 Результаты поиска:\n")
            for brand, model, price, desc, img, specs in result:
                caption = f"*{brand} {model}* — {price}\n_{desc}_\n\n⚙️ *Характеристики:* {specs}"
                await send_car_card(update.message, caption, img)
        else:
            await finalize_loading(loading_message, update.message, "😔 Машина не найдена.")
        user_state[chat_id] = None
        await update.message.reply_text("Выбери следующее действие:", reply_markup=category_menu())
        return

    if state == "search_by_price":
        digits = re.findall(r"\d+", text)
        if not digits:
            await update.message.reply_text("❗ Введите число (например: 12000000)")
            return
        price = int(digits[0])
        loading_message = await send_loading(update.message)
        result = search_car_by_price(price)
        if result:
            await finalize_loading(
                loading_message,
                update.message,
                f"💰 Машины около {price:,} ₸:\n".replace(",", " "),
            )
            for brand, model, price, desc, img, specs in result:
                caption = f"*{brand} {model}* — {price}\n_{desc}_\n\n⚙️ *Характеристики:* {specs}"
                await send_car_card(update.message, caption, img)
        else:
            await finalize_loading(loading_message, update.message, "😔 Ничего не найдено.")
        user_state[chat_id] = None
        await update.message.reply_text("Выбери следующее действие:", reply_markup=category_menu())
        return

    if state == "ask_ai_confirm":
        if text_lower in STOP_WORDS:
            user_state[chat_id] = None
            ai_sessions.pop(chat_id, None)
            await update.message.reply_text("Возвращаю тебя в главное меню 👇", reply_markup=category_menu())
            return

        session = ai_sessions.get(chat_id)
        suggestions = session.get("last_suggestions") if session else []

        if text_lower in YES_ANSWERS:
            if suggestions:
                loading_msg = await send_loading(update.message)
                for car in suggestions:
                    caption = (
                        f"*{car['brand']} {car['model']}* — {car['price']}\n"
                        f"_{car['description']}_\n\n⚙️ *Характеристики:* {car['specs']}"
                    )
                    await send_car_card(update.message, caption, car.get("image"))
                if loading_msg:
                    try:
                        await loading_msg.edit_text("Готово! Делюсь вариантами 👇")
                    except (BadRequest, NetworkError, TimedOut):
                        with contextlib.suppress(Exception):
                            await loading_msg.delete()
                        await update.message.reply_text("Готово! Делюсь вариантами 👇")
                else:
                    await update.message.reply_text("Готово! Делюсь вариантами 👇")
            else:
                await update.message.reply_text("Пока нечего показать, но я готов помочь с другими вариантами.")

            if session:
                session["last_suggestions"] = []
            user_state[chat_id] = "ask_ai"
            await update.message.reply_text("Можешь задать ещё вопрос или напиши 'стоп', чтобы вернуться в меню.")
            return

        if text_lower in NO_ANSWERS:
            user_state[chat_id] = "ask_ai"
            await update.message.reply_text("Хорошо! Можешь задать ещё вопрос или написать 'стоп'.")
            return

        await update.message.reply_text("Пожалуйста, ответь 'да' или 'нет'.")
        return

    if state == "ask_ai":
        if text_lower in STOP_WORDS:
            user_state[chat_id] = None
            ai_sessions.pop(chat_id, None)
            await update.message.reply_text("Возвращаю тебя в главное меню 👇", reply_markup=category_menu())
            return

        session = get_ai_session(chat_id)
        history = session["history"]
        history.append(("user", text))
        prompt = build_ai_prompt(chat_id, text)
        loading_message = await send_loading(update.message)
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(ask_ollama, prompt),
                timeout=AI_RESPONSE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            response = "AI долго думает. Попробуй задать вопрос ещё раз чуть позже."
        history.append(("assistant", response))
        suggestions = match_cars_from_response(response)
        session["last_suggestions"] = suggestions

        if loading_message:
            try:
                await loading_message.edit_text(response)
            except (BadRequest, NetworkError, TimedOut):
                with contextlib.suppress(Exception):
                    await loading_message.delete()
                await update.message.reply_text(response)
        else:
            await update.message.reply_text(response)
        if suggestions:
            await update.message.reply_text("Отправить фотографии этих машин? (да/нет)")
            user_state[chat_id] = "ask_ai_confirm"
        else:
            await update.message.reply_text("Можешь задать ещё вопрос или напиши 'стоп', чтобы вернуться в меню.")
        return

async def handle_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "discounted":
        await edit_or_send(query, "⏳ loading...")
        cars = get_discounted_cars()
        if not cars:
            await edit_or_send(query, "😔 Сейчас нет выгодных предложений.")
            return
        await edit_or_send(
            query,
            "🔥 *Выгодные предложения:*\n\nВыбери новую категорию ниже:",
            parse_mode="Markdown",
            reply_markup=category_menu(),
        )
        for brand, model, price, desc, img, specs in cars:
            caption = f"🔥 *{brand} {model}* — {price}\n_{desc}_\n\n⚙️ *Характеристики:* {specs}"
            await send_car_card(query.message, caption, img)
        await query.message.reply_text("Выбери другую категорию:", reply_markup=category_menu())
        return

    if data in ["Легковой", "Кроссовер", "Грузовой", "Электромобили", "Гибриды"]:
        await edit_or_send(query, "⏳ loading...")
        cars = get_cars_by_category(data)
        if not cars:
            await edit_or_send(query, f"🚫 Нет данных по категории: {data}")
            return
        await edit_or_send(
            query,
            f"🚘 Категория *{data}*:\n\nВыбери другую категорию ниже:",
            parse_mode="Markdown",
            reply_markup=category_menu(),
        )
        for brand, model, price, desc, img, specs in cars:
            caption = f"*{brand} {model}* — {price}\n_{desc}_\n\n⚙️ *Характеристики:* {specs}"
            await send_car_card(query.message, caption, img)
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

    elif data == "ask_ai":
        chat_id = query.from_user.id
        user_state[chat_id] = "ask_ai"
        session = get_ai_session(chat_id)
        session["history"].clear()
        session["last_suggestions"] = []
        await query.edit_message_text(
            "🤖 Привет! Я помогу подобрать машину. Расскажи, что важно: бюджет, тип кузова, топливо, задачи. "
            "Напиши 'стоп', чтобы вернуться в меню."
        )

def main():
    init_db()
    init_cars_db()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_feedback, pattern="^feedback"))
    app.add_handler(CallbackQueryHandler(handle_category))
    print("🤖 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
