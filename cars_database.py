import os
import sqlite3
from typing import Optional

def init_cars_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect("data/cars.db")
    cur = conn.cursor()

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

    cars = [
        ("Легковой", "Toyota", "Camry 50", "12 000 000 ₸",
         "Комфортный седан с надёжным двигателем.", "camry.jpg",
         "Двигатель: 2.5 л, 181 л.с. | КПП: Автомат | Привод: Передний | Расход: 8.2 л/100 км", 1),

        ("Легковой", "Hyundai", "Elantra", "10 500 000 ₸",
         "Экономичный седан с современным дизайном.", "elantra.jpg",
         "Двигатель: 1.6 л, 128 л.с. | КПП: Автомат | Привод: Передний | Расход: 7.1 л/100 км", 0),

        ("Легковой", "Honda", "Accord", "13 400 000 ₸",
         "Просторный седан бизнес-класса с богатой комплектацией.", "accord.jpg",
         "Двигатель: 2.0 л, 190 л.с. | КПП: Вариатор | Привод: Передний | Расход: 7.4 л/100 км", 0),

        ("Легковой", "Mazda", "6", "11 800 000 ₸",
         "Динамичный седан с акцентом на управляемость.", "mazda6.jpg",
         "Двигатель: 2.5 л, 194 л.с. | КПП: Автомат | Привод: Передний | Расход: 7.8 л/100 км", 1),

        ("Кроссовер", "Kia", "Sportage", "15 800 000 ₸",
         "Полный привод, отличная проходимость.", "sportage.jpg",
         "Двигатель: 2.0 л, 150 л.с. | КПП: Автомат | Привод: Полный | Расход: 9.5 л/100 км", 1),

        ("Кроссовер", "Toyota", "RAV4", "17 200 000 ₸",
         "Надёжный кроссовер для города и трассы.", "rav4.jpg",
         "Двигатель: 2.0 л, 173 л.с. | КПП: Вариатор | Привод: Полный | Расход: 8.4 л/100 км", 0),

        ("Кроссовер", "Nissan", "X-Trail", "16 300 000 ₸",
         "Практичный кроссовер с просторным салоном.", "xtrail.jpg",
         "Двигатель: 2.5 л, 171 л.с. | КПП: Вариатор | Привод: Полный | Расход: 8.7 л/100 км", 0),

        ("Кроссовер", "Mazda", "CX-5", "18 100 000 ₸",
         "Стильный кроссовер с премиальной отделкой.", "cx5.jpg",
         "Двигатель: 2.5 л, 194 л.с. | КПП: Автомат | Привод: Полный | Расход: 8.9 л/100 км", 1),

        ("Грузовой", "Isuzu", "NQR 75", "22 000 000 ₸",
         "Легендарный грузовик для перевозок до 5 тонн.", "isuzu.jpg",
         "Двигатель: 5.2 л дизель | Мощность: 155 л.с. | КПП: Механика | Грузоподъёмность: 5 тонн", 0),

        ("Грузовой", "MAN", "TGS 26.440", "55 000 000 ₸",
         "Мощный тягач для дальних перевозок.", "man.jpg",
         "Двигатель: 10.5 л дизель | Мощность: 440 л.с. | КПП: Автомат | Тягач: 26 тонн", 1),

        ("Грузовой", "Mercedes-Benz", "Actros 1845", "62 000 000 ₸",
         "Тягач премиум-класса с экономичным расходом топлива.", "actros.jpg",
         "Двигатель: 12.8 л дизель | Мощность: 450 л.с. | КПП: Автомат | Тягач: 18 тонн", 0),

        ("Грузовой", "Volvo", "FH16", "68 500 000 ₸",
         "Флагманский тягач с высоким уровнем безопасности.", "volvofh16.jpg",
         "Двигатель: 16.1 л дизель | Мощность: 550 л.с. | КПП: Автомат | Тягач: 26 тонн", 1),

        ("Электромобили", "Tesla", "Model 3", "24 500 000 ₸",
         "Популярный электроседан с автопилотом и быстрым разгоном.", "tesla_model3.jpg",
         "Батарея: 75 кВт·ч | Пробег: 491 км | Привод: Полный | Разгон 0-100: 4.4 с", 1),

        ("Электромобили", "Tesla", "Model Y", "27 800 000 ₸",
         "Компактный электрический кроссовер с большим запасом хода.", "tesla_modely.jpg",
         "Батарея: 75 кВт·ч | Пробег: 505 км | Привод: Полный | Разгон 0-100: 5.0 с", 0),

        ("Электромобили", "Mercedes-Benz", "EQC", "35 600 000 ₸",
         "Премиальный электрический SUV с комфортным салоном.", "mercedes_eqc.jpg",
         "Батарея: 80 кВт·ч | Пробег: 414 км | Привод: Полный | Разгон 0-100: 5.1 с", 0),

        ("Электромобили", "BYD", "Han EV", "21 900 000 ₸",
         "Электроседан бизнес-класса с богатым оснащением.", "byd_han.jpg",
         "Батарея: 85 кВт·ч | Пробег: 521 км | Привод: Полный | Разгон 0-100: 3.9 с", 1),

        ("Гибриды", "Li Auto", "L9", "32 400 000 ₸",
         "Полноразмерный гибридный SUV с увеличенным запасом хода.", "li_l9.jpg",
         "Двигатель: 1.5 л гибрид | Суммарная мощность: 449 л.с. | Пробег: 1100 км | Привод: Полный", 1),

        ("Гибриды", "Toyota", "Prius", "14 200 000 ₸",
         "Экономичный гибридный хэтчбек для города.", "toyota_prius.jpg",
         "Двигатель: 1.8 л гибрид | Мощность: 122 л.с. | Привод: Передний | Расход: 4.0 л/100 км", 0),

        ("Гибриды", "Toyota", "Highlander Hybrid", "24 800 000 ₸",
         "Семейный кроссовер с гибридной установкой и полным приводом.", "toyota_highlander_hybrid.jpg",
         "Двигатель: 2.5 л гибрид | Мощность: 243 л.с. | Привод: Полный | Расход: 7.0 л/100 км", 0),

        ("Гибриды", "Honda", "CR-V Hybrid", "19 600 000 ₸",
         "Гибридный кроссовер с просторным салоном и экономичным расходом.", "honda_crv_hybrid.jpg",
         "Двигатель: 2.0 л гибрид | Мощность: 215 л.с. | Привод: Полный | Расход: 6.5 л/100 км", 1),
    ]

    cur.execute("SELECT COUNT(*) FROM cars")
    existing_count = cur.fetchone()[0]

    inserted = 0
    for car in cars:
        _, brand, model, *_ = car
        cur.execute("SELECT 1 FROM cars WHERE brand = ? AND model = ?", (brand, model))
        if cur.fetchone():
            continue
        cur.execute("""
            INSERT INTO cars (category, brand, model, price, description, image, specs, is_discounted)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, car)
        inserted += 1

    if existing_count == 0 and inserted == len(cars):
        print("✅ cars.db создана и заполнена с флагом акций (is_discounted).")
    elif inserted > 0:
        print(f"➕ Добавлено {inserted} новых автомобилей в cars.db.")
    else:
        print("ℹ️ cars.db уже содержит актуальные данные.")

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


def get_all_cars():
    conn = sqlite3.connect("data/cars.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT category, brand, model, price, description, image, specs
        FROM cars
        ORDER BY category, brand, model
    """)
    result = cur.fetchall()
    conn.close()
    return result
