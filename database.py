import sqlite3

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
    conn = sqlite3.connect("data/questions.db")
    cur = conn.cursor()
    cur.execute("INSERT INTO users (name, age, city, chat_id) VALUES (?, ?, ?, ?)", (name, age, city, chat_id))
    conn.commit()
    conn.close()


def save_feedback(question, answer, user_id, liked):
    conn = sqlite3.connect("data/questions.db")
    cur = conn.cursor()
    cur.execute("INSERT INTO feedback (question, answer, user_id, liked) VALUES (?, ?, ?, ?)",
                (question, answer, user_id, liked))
    conn.commit()
    conn.close()