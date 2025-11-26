import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
QUESTIONS_DB_PATH = DATA_DIR / "questions.db"
HELP_DB_PATH = DATA_DIR / "help.db"


def _connect():
    conn = sqlite3.connect(QUESTIONS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _help_connect():
    conn = sqlite3.connect(HELP_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn, table: str, column: str, ddl: str, fill_expression: str | None = None):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cur.fetchall()}
    if column not in existing:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        conn.commit()
        if fill_expression:
            cur.execute(
                f"UPDATE {table} SET {column} = {fill_expression} WHERE {column} IS NULL"
            )
            conn.commit()


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
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
    CREATE TABLE IF NOT EXISTS ai_dialogs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        prompt TEXT,
        status TEXT DEFAULT 'ok',
        error TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    _ensure_column(conn, "ai_dialogs", "prompt", "TEXT")
    _ensure_column(conn, "ai_dialogs", "status", "TEXT", "'ok'")
    _ensure_column(conn, "ai_dialogs", "error", "TEXT")
    _ensure_column(conn, "ai_dialogs", "created_at", "TEXT", "CURRENT_TIMESTAMP")
    cur.execute("UPDATE ai_dialogs SET status = COALESCE(status, 'ok')")
    cur.execute("UPDATE ai_dialogs SET prompt = question WHERE prompt IS NULL")

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
        liked INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
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
        "INSERT INTO feedback (question, answer, user_id, liked, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
        (question, answer, user_id, liked),
    )
    conn.commit()
    conn.close()


def save_ai_dialog(question: str, answer: str, user_id: int | None, *, prompt: str | None = None, status: str | None = None, error: str | None = None):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO ai_dialogs (user_id, question, answer, prompt, status, error, created_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (user_id, question, answer, prompt, status, error),
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
