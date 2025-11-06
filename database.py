import sqlite3
from pathlib import Path

QUESTIONS_DB_PATH = Path("data/questions.db")
HELP_DB_PATH = Path("data/help.db")


def _connect():
    conn = sqlite3.connect(QUESTIONS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _help_connect():
    conn = sqlite3.connect(HELP_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = sqlite3.connect(QUESTIONS_DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS qa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT,
        answer TEXT,
        type TEXT,
        reaction TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        age INTEGER,
        city TEXT,
        chat_id INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT,
        answer TEXT,
        user_id INTEGER,
        liked INTEGER
    )
    """)

    conn.commit()
    conn.close()


def init_help_db():
    HELP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(HELP_DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS help_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE NOT NULL,
        label TEXT NOT NULL,
        button TEXT NOT NULL,
        sort_index INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS help_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id INTEGER NOT NULL,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        sort_index INTEGER DEFAULT 0,
        FOREIGN KEY (category_id) REFERENCES help_categories(id) ON DELETE CASCADE
    )
    """)

    conn.commit()
    conn.close()


def get_answer(question: str):
    term = (question or "").strip()
    if not term:
        return None

    lookup = term.casefold()

    conn = _help_connect()
    cur = conn.cursor()
    cur.execute("SELECT question, answer FROM help_questions")
    rows = cur.fetchall()
    conn.close()

    for row in rows:
        if row["question"].strip().casefold() == lookup:
            return row

    for row in rows:
        if lookup in row["question"].strip().casefold():
            return row

    return None


def save_user(name, age, city, chat_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE chat_id = ?", (chat_id,))
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE users SET name = ?, age = ?, city = ? WHERE chat_id = ?",
            (name, age, city, chat_id)
        )
        user_id = row["id"]
    else:
        cur.execute(
            "INSERT INTO users (name, age, city, chat_id) VALUES (?, ?, ?, ?)",
            (name, age, city, chat_id)
        )
        user_id = cur.lastrowid
    conn.commit()
    conn.close()
    return user_id


def get_user_by_chat_id(chat_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT id, name, age, city, chat_id FROM users WHERE chat_id = ?", (chat_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def save_feedback(question, answer, user_id, liked):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO feedback (question, answer, user_id, liked) VALUES (?, ?, ?, ?)",
        (question, answer, user_id, liked),
    )
    conn.commit()
    conn.close()


def get_help_sections():
    conn = _help_connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, key, label, button FROM help_categories ORDER BY sort_index, id"
    )
    categories = []
    for category in cur.fetchall():
        cur.execute(
            "SELECT question, answer FROM help_questions WHERE category_id = ? ORDER BY sort_index, id",
            (category["id"],),
        )
        questions = [{"question": row["question"], "answer": row["answer"]} for row in cur.fetchall()]
        categories.append({
            "key": category["key"],
            "label": category["label"],
            "button": category["button"],
            "questions": questions,
        })
    conn.close()
    return categories


def get_help_section_by_key(key: str):
    if not key:
        return None

    conn = _help_connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, key, label, button FROM help_categories WHERE key = ?",
        (key,),
    )
    category = cur.fetchone()
    if not category:
        conn.close()
        return None

    cur.execute(
        "SELECT question, answer FROM help_questions WHERE category_id = ? ORDER BY sort_index, id",
        (category["id"],),
    )
    questions = [{"question": row["question"], "answer": row["answer"]} for row in cur.fetchall()]
    conn.close()
    return {
        "key": category["key"],
        "label": category["label"],
        "button": category["button"],
        "questions": questions,
    }
