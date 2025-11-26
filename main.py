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
from database import (
    init_db,
    init_help_db,
    get_answer,
    save_user,
    get_user_by_chat_id,
    save_feedback,
    get_help_sections,
    get_help_section_by_key,
    save_ai_dialog,
)
from ai_module import ask_ollama

logging.basicConfig(filename="logs/bot.log", level=logging.INFO, format="%(asctime)s - %(message)s")

user_state = {}
user_info = {}
filter_info = {}
ai_sessions = {}
help_messages = {}

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
        [InlineKeyboardButton("❓ Помощь при покупке", callback_data="help_menu")],
        [InlineKeyboardButton("🤖 Спросить совет у AI", callback_data="ask_ai")],
    ])


def feedback_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Да 👍", callback_data="feedback|like"),
            InlineKeyboardButton("Нет 👎", callback_data="feedback|dislike"),
        ],
    ])


def help_categories_keyboard():
    sections = get_help_sections()
    rows = []
    current_row = []
    for section in sections:
        current_row.append(InlineKeyboardButton(section["button"], callback_data=f"help_cat|{section['key']}"))
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    rows.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)


def help_questions_keyboard(section):
    buttons = []
    row = []
    for idx, _ in enumerate(section["questions"], start=1):
        row.append(InlineKeyboardButton(str(idx), callback_data=f"help_q|{section['key']}|{idx - 1}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("⬅️ Категории", callback_data="help_menu")])
    return InlineKeyboardMarkup(buttons)


def format_help_questions(section):
    lines = [section["label"], "", "Выбери вопрос по номеру или задай его текстом:"]
    for idx, item in enumerate(section["questions"], start=1):
        lines.append(f"{idx}. {item['question']}")
    return "\n".join(lines)


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


async def clear_help_history(chat_id: int, bot):
    messages = help_messages.pop(chat_id, [])
    for message_id in messages:
        with contextlib.suppress(BadRequest, NetworkError, TimedOut):
            await bot.delete_message(chat_id, message_id)


def get_ai_session(chat_id: int):
    session = ai_sessions.get(chat_id)
    if not session:
        session = {
            "history": deque(maxlen=10),
            "last_suggestions": [],
            "last_feedback": None,
        }
        ai_sessions[chat_id] = session
    else:
        session.setdefault("history", deque(maxlen=10))
        session.setdefault("last_suggestions", [])
        session.setdefault("last_feedback", None)
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


async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    payload = query.data.split("|", maxsplit=3)
    if not payload or payload[0] != "feedback":
        logging.warning("Получен неизвестный callback: %s", query.data)
        await query.answer("Действие не поддерживается", show_alert=True)
        return

    action = payload[1] if len(payload) > 1 else None
    if action not in {"like", "dislike"}:
        logging.warning("Неизвестный тип feedback: %s", query.data)
        await query.edit_message_text("Спасибо за отзыв! 🙌")
        return

    session = ai_sessions.get(query.from_user.id)
    entry = session.get("last_feedback") if session else None
    if not entry:
        logging.warning("Нет данных последнего ответа для feedback")
        await query.edit_message_text("Спасибо за отзыв! 🙌")
        return

    liked = 1 if action == "like" else 0
    question = entry.get("question", "")
    answer = entry.get("answer", "")
    user = get_or_load_user(query.from_user.id)
    user_id = user.get("id") if user else None

    if user_id:
        try:
            save_feedback(question, answer, user_id, liked)
        except Exception as exc:
            logging.exception("Не удалось сохранить feedback: %s", exc)

    if session:
        session["last_feedback"] = None

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
            await clear_help_history(chat_id, context.bot)
            user_state[chat_id] = None
            ai_sessions.pop(chat_id, None)
            await update.message.reply_text("Возвращаю тебя в главное меню 👇", reply_markup=category_menu())
            return

        session = get_ai_session(chat_id)
        history = session["history"]
        history.append(("user", text))
        await clear_help_history(chat_id, context.bot)
        stored = get_answer(text)
        if stored:
            response = stored["answer"]
            history.append(("assistant", response))
            session["last_suggestions"] = []
            session["last_feedback"] = {"question": text, "answer": response}
            sent_messages = []
            msg = await update.message.reply_text(response)
            sent_messages.append(msg.message_id)
            feedback_msg = await update.message.reply_text("Понравился наш ответ?", reply_markup=feedback_keyboard())
            sent_messages.append(feedback_msg.message_id)
            info_msg = await update.message.reply_text("Можешь задать ещё вопрос или напиши 'стоп', чтобы вернуться в меню.")
            sent_messages.append(info_msg.message_id)
            return

        prompt = build_ai_prompt(chat_id, text)
        loading_message = await send_loading(update.message)
        sent_messages = []
        status = "ok"
        error_text = None
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(ask_ollama, prompt),
                timeout=AI_RESPONSE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            status = "timeout"
            response = "AI долго думает. Попробуй задать вопрос ещё раз чуть позже."
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error_text = str(exc)
            logging.exception("Ошибка при запросе к ИИ: %s", exc)
            response = "Не удалось получить ответ от ИИ. Попробуй ещё раз позже."
        history.append(("assistant", response))
        suggestions = match_cars_from_response(response)
        session["last_suggestions"] = suggestions
        session["last_feedback"] = {"question": text, "answer": response}

        if loading_message:
            try:
                await loading_message.edit_text(response)
                sent_messages.append(loading_message.message_id)
            except (BadRequest, NetworkError, TimedOut):
                with contextlib.suppress(Exception):
                    await loading_message.delete()
                msg = await update.message.reply_text(response)
                sent_messages.append(msg.message_id)
        else:
            msg = await update.message.reply_text(response)
            sent_messages.append(msg.message_id)

        feedback_msg = await update.message.reply_text("Понравился наш ответ?", reply_markup=feedback_keyboard())
        sent_messages.append(feedback_msg.message_id)

        if suggestions:
            prompt_msg = await update.message.reply_text("Отправить фотографии этих машин? (да/нет)")
            sent_messages.append(prompt_msg.message_id)
            user_state[chat_id] = "ask_ai_confirm"
        else:
            info_msg = await update.message.reply_text("Можешь задать ещё вопрос или напиши 'стоп', чтобы вернуться в меню.")
            sent_messages.append(info_msg.message_id)

        try:
            user_id = user_info.get(chat_id, {}).get("id")
            if user_id is None:
                db_user = get_user_by_chat_id(chat_id)
                user_id = db_user["id"] if db_user else None
            save_ai_dialog(
                question=text,
                answer=response,
                user_id=user_id,
                prompt=prompt or text,
                status=status,
                error=error_text,
            )
        except Exception as exc:
            logging.exception("Не удалось сохранить диалог ИИ: %s", exc)

        return

async def handle_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.from_user.id
    await clear_help_history(chat_id, context.bot)

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

    elif data == "help_menu":
        await edit_or_send(
            query,
            "📘 Помощь при покупке машины. Выбери категорию:",
            reply_markup=help_categories_keyboard(),
        )

    elif data == "main_menu":
        await edit_or_send(query, "Выбери раздел:", reply_markup=category_menu())

    elif data.startswith("help_cat|"):
        _, key = data.split("|", maxsplit=1)
        section = get_help_section_by_key(key)
        if not section:
            await query.answer("Категория недоступна", show_alert=True)
            return
        await edit_or_send(
            query,
            format_help_questions(section),
            reply_markup=help_questions_keyboard(section),
        )

    elif data.startswith("help_q|"):
        parts = data.split("|")
        if len(parts) != 3:
            await query.answer("Вопрос недоступен", show_alert=True)
            return
        key = parts[1]
        try:
            index = int(parts[2])
        except ValueError:
            await query.answer("Некорректный номер вопроса", show_alert=True)
            return
        section = get_help_section_by_key(key)
        if not section:
            await query.answer("Категория недоступна", show_alert=True)
            return
        questions = section["questions"]
        if index < 0 or index >= len(questions):
            await query.answer("Вопрос недоступен", show_alert=True)
            return
        qa_item = questions[index]
        msg = await query.message.reply_text(f"{qa_item['question']}\n\n{qa_item['answer']}")
        help_messages[chat_id] = [msg.message_id]

    elif data == "ask_ai":
        chat_id = query.from_user.id
        user_state[chat_id] = "ask_ai"
        session = get_ai_session(chat_id)
        session["history"].clear()
        session["last_suggestions"] = []
        session["last_feedback"] = None
        await query.edit_message_text(
            "🤖 Привет! Расскажи, что тебе важно: бюджет, тип кузова, топливо, назначение. "
            "Если вопрос уже есть в разделе помощи, отвечу из базы знаний, иначе подберу варианты и смогу показать фото. "
            "Напиши 'стоп', чтобы вернуться в меню."
        )

def main():
    init_db()
    init_help_db()
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
