import os
import sqlite3
from typing import Optional

def init_cars_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect("data/cars.db")
    cur = conn.cursor()

    # Добавляем новое поле specs и is_discounted
    cur.execute("""
    CREATE TABLE IF NOT EXISTS cars (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT,
        brand TEXT,
        model TEXT,
        price TEXT,
        description TEXT,
        image TEXT,
        specs TEXT,
        is_discounted INTEGER DEFAULT 0
    )
    """)

    cur.execute("SELECT COUNT(*) FROM cars")
    count = cur.fetchone()[0]

    if count == 0:
        cars = [
            ("Легковой", "Toyota", "Camry 50", "12 000 000 ₸",
             "Комфортный седан с надёжным двигателем.", "camry.jpg",
             "Двигатель: 2.5 л, 181 л.с. | КПП: Автомат | Привод: Передний | Расход: 8.2 л/100 км", 1),

            ("Легковой", "Hyundai", "Elantra", "10 500 000 ₸",
             "Экономичный седан с современным дизайном.", "elantra.jpg",
             "Двигатель: 1.6 л, 128 л.с. | КПП: Автомат | Привод: Передний | Расход: 7.1 л/100 км", 0),

            ("Кроссовер", "Kia", "Sportage", "15 800 000 ₸",
             "Полный привод, отличная проходимость.", "sportage.jpg",
             "Двигатель: 2.0 л, 150 л.с. | КПП: Автомат | Привод: Полный | Расход: 9.5 л/100 км", 1),

            ("Кроссовер", "Toyota", "RAV4", "17 200 000 ₸",
             "Надёжный кроссовер для города и трассы.", "rav4.jpg",
             "Двигатель: 2.0 л, 173 л.с. | КПП: Вариатор | Привод: Полный | Расход: 8.4 л/100 км", 0),

            ("Грузовой", "Isuzu", "NQR 75", "22 000 000 ₸",
             "Легендарный грузовик для перевозок до 5 тонн.", "isuzu.jpg",
             "Двигатель: 5.2 л дизель | Мощность: 155 л.с. | КПП: Механика | Грузоподъёмность: 5 тонн", 0),

            ("Грузовой", "MAN", "TGS 26.440", "55 000 000 ₸",
             "Мощный тягач для дальних перевозок.", "man.jpg",
             "Двигатель: 10.5 л дизель | Мощность: 440 л.с. | КПП: Автомат | Тягач: 26 тонн", 1),
        ]

        cur.executemany("""
            INSERT INTO cars (category, brand, model, price, description, image, specs, is_discounted)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, cars)
        print("✅ cars.db создана и заполнена с флагом акций (is_discounted).")
    else:
        print("ℹ️ cars.db уже содержит данные.")

    conn.commit()
    conn.close()


def get_cars_by_category(category: str):
    conn = sqlite3.connect("data/cars.db")
    cur = conn.cursor()
    cur.execute("SELECT brand, model, price, description, image, specs FROM cars WHERE category = ?", (category,))
    result = cur.fetchall()
    conn.close()
    return result


def get_discounted_cars():
    conn = sqlite3.connect("data/cars.db")
    cur = conn.cursor()
    cur.execute("SELECT brand, model, price, description, image, specs FROM cars WHERE is_discounted = 1")
    result = cur.fetchall()
    conn.close()
    return result


def get_cars_by_filters(brand: Optional[str] = None, model: Optional[str] = None):
    conn = sqlite3.connect("data/cars.db")
    cur = conn.cursor()

    query = "SELECT brand, model, price, description, image, specs FROM cars WHERE 1 = 1"
    params = []

    if brand:
        query += " AND LOWER(brand) LIKE LOWER(?)"
        params.append(f"%{brand}%")

    if model:
        query += " AND LOWER(model) LIKE LOWER(?)"
        params.append(f"%{model}%")

    cur.execute(query, params)
    result = cur.fetchall()
    conn.close()
    return result
