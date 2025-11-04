import sqlite3

def _connect():
    conn = sqlite3.connect("data/questions.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = sqlite3.connect("data/questions.db")
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


def get_answer(question: str):
    conn = sqlite3.connect("data/questions.db")
    cur = conn.cursor()
    cur.execute("SELECT answer, reaction FROM qa WHERE question LIKE ?", (f"%{question}%",))
    row = cur.fetchone()
    conn.close()
    return row


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
    conn = sqlite3.connect("data/questions.db")
    cur = conn.cursor()
    cur.execute("INSERT INTO feedback (question, answer, user_id, liked) VALUES (?, ?, ?, ?)",
                (question, answer, user_id, liked))
    conn.commit()
    conn.close()
