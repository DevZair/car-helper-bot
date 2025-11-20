"""
PyQt5 based admin panel to manage bot data without touching SQL manually.
Provides two tabs:
1. Авто: CRUD for vehicles in data/cars.db.
2. Помощь/FAQ: CRUD for help categories/questions in data/help.db.
"""

from __future__ import annotations

import sys
import sqlite3
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import ADMIN_LOGIN, ADMIN_PASSWORD


DATA_DIR = Path("data")
CARS_DB_PATH = DATA_DIR / "cars.db"
HELP_DB_PATH = DATA_DIR / "help.db"
QUESTIONS_DB_PATH = DATA_DIR / "questions.db"


def ensure_car_schema():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CARS_DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
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
        """
    )
    conn.commit()
    conn.close()


def ensure_help_schema():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(HELP_DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS help_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            label TEXT NOT NULL,
            button TEXT NOT NULL,
            sort_index INTEGER DEFAULT 0
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS help_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            sort_index INTEGER DEFAULT 0,
            FOREIGN KEY (category_id) REFERENCES help_categories(id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()
    conn.close()


def ensure_questions_schema():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(QUESTIONS_DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS qa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT,
            answer TEXT,
            type TEXT,
            reaction TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            age INTEGER,
            city TEXT,
            chat_id INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT,
            answer TEXT,
            user_id INTEGER,
            liked INTEGER
        )
        """
    )
    conn.commit()
    conn.close()


class AdminLoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Вход в админ-панель")
        layout = QVBoxLayout(self)

        info = QLabel("Введите логин и пароль, чтобы продолжить.")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        self.login_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        form.addRow("Логин:", self.login_edit)
        form.addRow("Пароль:", self.password_edit)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: red;")
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.handle_login)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def handle_login(self):
        login = self.login_edit.text().strip()
        password = self.password_edit.text()
        if not login or not password:
            self.error_label.setText("Укажите логин и пароль.")
            return
        if login != ADMIN_LOGIN or password != ADMIN_PASSWORD:
            self.error_label.setText("Неверные данные для входа.")
            self.password_edit.clear()
            return
        self.accept()


class CarAdminTab(QWidget):
    headers = [
        "ID",
        "Категория",
        "Бренд",
        "Модель",
        "Цена",
        "Описание",
        "Изображение",
        "Характеристики",
        "Акция",
    ]

    def __init__(self):
        super().__init__()
        self.current_car_id: Optional[int] = None
        self._setup_ui()
        self.load_cars()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self.populate_form_from_selection)
        layout.addWidget(self.table, stretch=1)

        form_layout = QFormLayout()
        self.category_input = QComboBox()
        self.category_input.setEditable(True)
        self.category_input.addItems(
            [
                "Легковой",
                "Кроссовер",
                "Грузовой",
                "Электромобили",
                "Гибриды",
            ]
        )
        self.brand_input = QLineEdit()
        self.model_input = QLineEdit()
        self.price_input = QLineEdit()
        self.description_input = QPlainTextEdit()
        self.description_input.setPlaceholderText("Короткое описание автомобиля")
        self.image_input = QLineEdit()
        self.image_input.setPlaceholderText("Например: camry.jpg")
        self.specs_input = QPlainTextEdit()
        self.specs_input.setPlaceholderText("Ключевые характеристики, которые видит пользователь")
        self.discount_checkbox = QCheckBox("Акционный автомобиль")

        form_layout.addRow("Категория:", self.category_input)
        form_layout.addRow("Бренд:", self.brand_input)
        form_layout.addRow("Модель:", self.model_input)
        form_layout.addRow("Цена:", self.price_input)
        form_layout.addRow("Описание:", self.description_input)
        form_layout.addRow("Файл изображения:", self.image_input)
        form_layout.addRow("Характеристики:", self.specs_input)
        form_layout.addRow("", self.discount_checkbox)

        form_container = QWidget()
        form_container.setLayout(form_layout)
        form_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addWidget(form_container)

        button_row = QHBoxLayout()
        self.add_button = QPushButton("Добавить")
        self.update_button = QPushButton("Сохранить изменения")
        self.delete_button = QPushButton("Удалить")
        self.clear_button = QPushButton("Очистить форму")
        self.refresh_button = QPushButton("Обновить список")

        self.add_button.clicked.connect(self.add_car)
        self.update_button.clicked.connect(self.update_car)
        self.delete_button.clicked.connect(self.delete_car)
        self.clear_button.clicked.connect(self.clear_form)
        self.refresh_button.clicked.connect(self.load_cars)

        button_row.addWidget(self.add_button)
        button_row.addWidget(self.update_button)
        button_row.addWidget(self.delete_button)
        button_row.addWidget(self.clear_button)
        button_row.addWidget(self.refresh_button)
        layout.addLayout(button_row)

    def load_cars(self):
        conn = sqlite3.connect(CARS_DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, category, brand, model, price, description, image, specs, is_discounted
            FROM cars
            ORDER BY category, brand, model
            """
        )
        rows = cur.fetchall()
        conn.close()

        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(row):
                if col_idx == 8:
                    display = "Да" if value else "Нет"
                else:
                    display = value if value is not None else ""
                item = QTableWidgetItem(display)
                if col_idx == 0:
                    item.setData(Qt.UserRole, value)
                self.table.setItem(row_idx, col_idx, item)

        self.table.resizeRowsToContents()
        self.current_car_id = None
        self.table.clearSelection()
        self.clear_form(keep_selection=True)

    def _get_form_data(self) -> Optional[dict]:
        category = self.category_input.currentText().strip()
        brand = self.brand_input.text().strip()
        model = self.model_input.text().strip()

        if not all([category, brand, model]):
            QMessageBox.warning(self, "Недостаточно данных", "Категория, бренд и модель обязательны.")
            return None

        return {
            "category": category,
            "brand": brand,
            "model": model,
            "price": self.price_input.text().strip(),
            "description": self.description_input.toPlainText().strip(),
            "image": self.image_input.text().strip(),
            "specs": self.specs_input.toPlainText().strip(),
            "is_discounted": 1 if self.discount_checkbox.isChecked() else 0,
        }

    def add_car(self):
        data = self._get_form_data()
        if not data:
            return

        conn = sqlite3.connect(CARS_DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO cars (category, brand, model, price, description, image, specs, is_discounted)
            VALUES (:category, :brand, :model, :price, :description, :image, :specs, :is_discounted)
            """,
            data,
        )
        conn.commit()
        conn.close()
        QMessageBox.information(self, "Готово", "Автомобиль добавлен.")
        self.load_cars()

    def update_car(self):
        if self.current_car_id is None:
            QMessageBox.information(self, "Не выбрано", "Выберите запись для обновления.")
            return

        data = self._get_form_data()
        if not data:
            return
        data["id"] = self.current_car_id

        conn = sqlite3.connect(CARS_DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE cars
            SET category = :category,
                brand = :brand,
                model = :model,
                price = :price,
                description = :description,
                image = :image,
                specs = :specs,
                is_discounted = :is_discounted
            WHERE id = :id
            """,
            data,
        )
        conn.commit()
        conn.close()
        QMessageBox.information(self, "Сохранено", "Изменения применены.")
        self.load_cars()

    def delete_car(self):
        if self.current_car_id is None:
            QMessageBox.information(self, "Не выбрано", "Сначала выделите автомобиль.")
            return

        confirm = QMessageBox.question(
            self,
            "Удалить запись",
            "Удалить выбранный автомобиль?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        conn = sqlite3.connect(CARS_DB_PATH)
        cur = conn.cursor()
        cur.execute("DELETE FROM cars WHERE id = ?", (self.current_car_id,))
        conn.commit()
        conn.close()
        self.load_cars()

    def populate_form_from_selection(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        car_id_item = self.table.item(row, 0)
        if car_id_item is None:
            self.current_car_id = None
            return

        raw_id = car_id_item.data(Qt.UserRole)
        if raw_id is None:
            text = (car_id_item.text() or "").strip()
            if not text:
                self.current_car_id = None
                return
            raw_id = text
        try:
            self.current_car_id = int(raw_id)
        except ValueError:
            QMessageBox.warning(self, "Ошибка ID", "Не удалось определить идентификатор записи.")
            self.current_car_id = None
            return

        def _text(col):
            item = self.table.item(row, col)
            return item.text() if item else ""

        self.category_input.setCurrentText(_text(1))
        self.brand_input.setText(_text(2))
        self.model_input.setText(_text(3))
        self.price_input.setText(_text(4))
        self.description_input.setPlainText(_text(5))
        self.image_input.setText(_text(6))
        self.specs_input.setPlainText(_text(7))
        self.discount_checkbox.setChecked(_text(8) == "Да")

    def clear_form(self, keep_selection: bool = False):
        self.category_input.setCurrentText("")
        self.brand_input.clear()
        self.model_input.clear()
        self.price_input.clear()
        self.description_input.clear()
        self.image_input.clear()
        self.specs_input.clear()
        self.discount_checkbox.setChecked(False)
        if not keep_selection:
            self.current_car_id = None
            self.table.clearSelection()


class CategoryDialog(QDialog):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.setWindowTitle("Категория помощи")
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.key_edit = QLineEdit()
        self.label_edit = QLineEdit()
        self.button_edit = QLineEdit()
        self.sort_spin = QSpinBox()
        self.sort_spin.setRange(0, 10_000)

        if data:
            self.key_edit.setText(data.get("key", ""))
            self.label_edit.setText(data.get("label", ""))
            self.button_edit.setText(data.get("button", ""))
            self.sort_spin.setValue(data.get("sort_index", 0))

        form.addRow("Ключ:", self.key_edit)
        form.addRow("Заголовок:", self.label_edit)
        form.addRow("Кнопка:", self.button_edit)
        form.addRow("Сортировка:", self.sort_spin)
        layout.addLayout(form)

        info_label = QLabel("Ключ используется в callback_data. Должен быть уникальным.")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self):
        key = self.key_edit.text().strip()
        label = self.label_edit.text().strip()
        button = self.button_edit.text().strip()
        if not all([key, label, button]):
            QMessageBox.warning(self, "Не заполнено", "Ключ, заголовок и текст кнопки обязательны.")
            return None
        return {
            "key": key,
            "label": label,
            "button": button,
            "sort_index": self.sort_spin.value(),
        }


class QuestionDialog(QDialog):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.setWindowTitle("Вопрос раздела")
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.question_edit = QLineEdit()
        self.answer_edit = QPlainTextEdit()
        self.sort_spin = QSpinBox()
        self.sort_spin.setRange(0, 10_000)

        if data:
            self.question_edit.setText(data.get("question", ""))
            self.answer_edit.setPlainText(data.get("answer", ""))
            self.sort_spin.setValue(data.get("sort_index", 0))

        form.addRow("Вопрос:", self.question_edit)
        form.addRow("Ответ:", self.answer_edit)
        form.addRow("Сортировка:", self.sort_spin)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self):
        question = self.question_edit.text().strip()
        answer = self.answer_edit.toPlainText().strip()
        if not all([question, answer]):
            QMessageBox.warning(self, "Не заполнено", "Вопрос и ответ обязательны.")
            return None
        return {
            "question": question,
            "answer": answer,
            "sort_index": self.sort_spin.value(),
        }


class UserAdminTab(QWidget):
    headers = ["ID", "Имя", "Возраст", "Город", "Chat ID"]

    def __init__(self):
        super().__init__()
        self.current_user_id: Optional[int] = None
        self._setup_ui()
        self.load_users()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self.populate_form_from_selection)
        layout.addWidget(self.table, stretch=1)

        form = QFormLayout()
        self.name_input = QLineEdit()
        self.age_input = QSpinBox()
        self.age_input.setRange(0, 120)
        self.city_input = QLineEdit()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("ID пользователя в Telegram")
        form.addRow("Имя:", self.name_input)
        form.addRow("Возраст:", self.age_input)
        form.addRow("Город:", self.city_input)
        form.addRow("Chat ID:", self.chat_input)
        form_container = QWidget()
        form_container.setLayout(form)
        layout.addWidget(form_container)

        button_row = QHBoxLayout()
        add_btn = QPushButton("Добавить")
        update_btn = QPushButton("Сохранить изменения")
        delete_btn = QPushButton("Удалить")
        clear_btn = QPushButton("Очистить форму")
        refresh_btn = QPushButton("Обновить список")

        add_btn.clicked.connect(self.add_user)
        update_btn.clicked.connect(self.update_user)
        delete_btn.clicked.connect(self.delete_user)
        clear_btn.clicked.connect(self.clear_form)
        refresh_btn.clicked.connect(self.load_users)

        for btn in (add_btn, update_btn, delete_btn, clear_btn, refresh_btn):
            button_row.addWidget(btn)
        layout.addLayout(button_row)

    def load_users(self):
        conn = sqlite3.connect(QUESTIONS_DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT id, name, age, city, chat_id FROM users ORDER BY id DESC")
        rows = cur.fetchall()
        conn.close()

        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(row):
                display = "" if value is None else str(value)
                item = QTableWidgetItem(display)
                if col_idx == 0:
                    item.setData(Qt.UserRole, value)
                self.table.setItem(row_idx, col_idx, item)
        self.table.resizeRowsToContents()
        self.current_user_id = None
        self.table.clearSelection()
        self.clear_form(keep_selection=True)

    def _get_form_data(self) -> Optional[dict]:
        name = self.name_input.text().strip()
        city = self.city_input.text().strip()
        chat_id_text = self.chat_input.text().strip()
        if not name or not chat_id_text:
            QMessageBox.warning(self, "Недостаточно данных", "Имя и Chat ID обязательны.")
            return None
        try:
            chat_id = int(chat_id_text)
        except ValueError:
            QMessageBox.warning(self, "Некорректный Chat ID", "Chat ID должен быть числом.")
            return None
        return {
            "name": name,
            "age": self.age_input.value(),
            "city": city,
            "chat_id": chat_id,
        }

    def add_user(self):
        data = self._get_form_data()
        if not data:
            return
        conn = sqlite3.connect(QUESTIONS_DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (name, age, city, chat_id)
            VALUES (:name, :age, :city, :chat_id)
            """,
            data,
        )
        conn.commit()
        conn.close()
        QMessageBox.information(self, "Готово", "Пользователь добавлен.")
        self.load_users()

    def update_user(self):
        if self.current_user_id is None:
            QMessageBox.information(self, "Не выбрано", "Выберите пользователя для редактирования.")
            return
        data = self._get_form_data()
        if not data:
            return
        data["id"] = self.current_user_id

        conn = sqlite3.connect(QUESTIONS_DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE users
            SET name = :name, age = :age, city = :city, chat_id = :chat_id
            WHERE id = :id
            """,
            data,
        )
        conn.commit()
        conn.close()
        QMessageBox.information(self, "Сохранено", "Пользователь обновлён.")
        self.load_users()

    def delete_user(self):
        if self.current_user_id is None:
            QMessageBox.information(self, "Не выбрано", "Сначала выберите пользователя.")
            return
        confirm = QMessageBox.question(
            self,
            "Удалить пользователя",
            "Удалить выбранную запись?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        conn = sqlite3.connect(QUESTIONS_DB_PATH)
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id = ?", (self.current_user_id,))
        conn.commit()
        conn.close()
        self.load_users()

    def populate_form_from_selection(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        item = self.table.item(row, 0)
        if not item:
            self.current_user_id = None
            return
        raw_id = item.data(Qt.UserRole) or item.text()
        try:
            self.current_user_id = int(raw_id)
        except (TypeError, ValueError):
            self.current_user_id = None
            QMessageBox.warning(self, "Ошибка ID", "Невозможно определить ID пользователя.")
            return

        def _text(col):
            cell = self.table.item(row, col)
            return cell.text() if cell else ""

        self.name_input.setText(_text(1))
        age_text = _text(2)
        self.age_input.setValue(int(age_text) if age_text.isdigit() else 0)
        self.city_input.setText(_text(3))
        self.chat_input.setText(_text(4))

    def clear_form(self, keep_selection: bool = False):
        self.name_input.clear()
        self.age_input.setValue(0)
        self.city_input.clear()
        self.chat_input.clear()
        if not keep_selection:
            self.current_user_id = None
            self.table.clearSelection()


class QAAdminTab(QWidget):
    headers = ["ID", "Вопрос", "Ответ", "Тип", "Реакция"]

    def __init__(self):
        super().__init__()
        self.current_entry_id: Optional[int] = None
        self._setup_ui()
        self.load_entries()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self.populate_form_from_selection)
        layout.addWidget(self.table, stretch=1)

        form = QFormLayout()
        self.question_input = QLineEdit()
        self.answer_input = QPlainTextEdit()
        self.type_input = QLineEdit()
        self.reaction_input = QLineEdit()
        form.addRow("Вопрос:", self.question_input)
        form.addRow("Ответ:", self.answer_input)
        form.addRow("Тип:", self.type_input)
        form.addRow("Реакция (emoji):", self.reaction_input)
        layout.addLayout(form)

        button_row = QHBoxLayout()
        add_btn = QPushButton("Добавить")
        update_btn = QPushButton("Сохранить изменения")
        delete_btn = QPushButton("Удалить")
        clear_btn = QPushButton("Очистить форму")
        refresh_btn = QPushButton("Обновить список")
        add_btn.clicked.connect(self.add_entry)
        update_btn.clicked.connect(self.update_entry)
        delete_btn.clicked.connect(self.delete_entry)
        clear_btn.clicked.connect(self.clear_form)
        refresh_btn.clicked.connect(self.load_entries)
        for btn in (add_btn, update_btn, delete_btn, clear_btn, refresh_btn):
            button_row.addWidget(btn)
        layout.addLayout(button_row)

    def load_entries(self):
        conn = sqlite3.connect(QUESTIONS_DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT id, question, answer, type, reaction FROM qa ORDER BY id DESC")
        rows = cur.fetchall()
        conn.close()

        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(row):
                display = "" if value is None else str(value)
                item = QTableWidgetItem(display)
                if col_idx == 0:
                    item.setData(Qt.UserRole, value)
                self.table.setItem(row_idx, col_idx, item)
        self.table.resizeRowsToContents()
        self.current_entry_id = None
        self.table.clearSelection()
        self.clear_form(keep_selection=True)

    def _get_form_data(self) -> Optional[dict]:
        question = self.question_input.text().strip()
        answer = self.answer_input.toPlainText().strip()
        if not question or not answer:
            QMessageBox.warning(self, "Недостаточно данных", "Вопрос и ответ обязательны.")
            return None
        return {
            "question": question,
            "answer": answer,
            "type": self.type_input.text().strip(),
            "reaction": self.reaction_input.text().strip(),
        }

    def add_entry(self):
        data = self._get_form_data()
        if not data:
            return
        conn = sqlite3.connect(QUESTIONS_DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO qa (question, answer, type, reaction)
            VALUES (:question, :answer, :type, :reaction)
            """,
            data,
        )
        conn.commit()
        conn.close()
        QMessageBox.information(self, "Готово", "Вопрос добавлен.")
        self.load_entries()

    def update_entry(self):
        if self.current_entry_id is None:
            QMessageBox.information(self, "Не выбрано", "Выберите запись для изменения.")
            return
        data = self._get_form_data()
        if not data:
            return
        data["id"] = self.current_entry_id
        conn = sqlite3.connect(QUESTIONS_DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE qa
            SET question = :question,
                answer = :answer,
                type = :type,
                reaction = :reaction
            WHERE id = :id
            """,
            data,
        )
        conn.commit()
        conn.close()
        QMessageBox.information(self, "Сохранено", "Запись обновлена.")
        self.load_entries()

    def delete_entry(self):
        if self.current_entry_id is None:
            QMessageBox.information(self, "Не выбрано", "Сначала выберите запись.")
            return
        confirm = QMessageBox.question(
            self,
            "Удалить вопрос",
            "Удалить выбранную запись из базы ответов?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        conn = sqlite3.connect(QUESTIONS_DB_PATH)
        cur = conn.cursor()
        cur.execute("DELETE FROM qa WHERE id = ?", (self.current_entry_id,))
        conn.commit()
        conn.close()
        self.load_entries()

    def populate_form_from_selection(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        item = self.table.item(row, 0)
        if not item:
            self.current_entry_id = None
            return
        raw_id = item.data(Qt.UserRole) or item.text()
        try:
            self.current_entry_id = int(raw_id)
        except (TypeError, ValueError):
            QMessageBox.warning(self, "Ошибка ID", "Не удалось определить ID записи.")
            self.current_entry_id = None
            return

        def _text(col):
            cell = self.table.item(row, col)
            return cell.text() if cell else ""

        self.question_input.setText(_text(1))
        self.answer_input.setPlainText(_text(2))
        self.type_input.setText(_text(3))
        self.reaction_input.setText(_text(4))

    def clear_form(self, keep_selection: bool = False):
        self.question_input.clear()
        self.answer_input.clear()
        self.type_input.clear()
        self.reaction_input.clear()
        if not keep_selection:
            self.current_entry_id = None
            self.table.clearSelection()

class HelpAdminTab(QWidget):
    question_headers = ["ID", "Вопрос", "Ответ", "Сортировка"]

    def __init__(self):
        super().__init__()
        self.current_category: Optional[dict] = None
        self._setup_ui()
        self.load_categories()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        splitter = QSplitter()
        layout.addWidget(splitter)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        self.category_list = QListWidget()
        self.category_list.itemSelectionChanged.connect(self.on_category_selected)
        left_layout.addWidget(QLabel("Разделы помощи"))
        left_layout.addWidget(self.category_list, stretch=1)

        cat_button_row = QHBoxLayout()
        add_cat_btn = QPushButton("Добавить")
        edit_cat_btn = QPushButton("Изменить")
        delete_cat_btn = QPushButton("Удалить")
        add_cat_btn.clicked.connect(self.add_category)
        edit_cat_btn.clicked.connect(self.edit_category)
        delete_cat_btn.clicked.connect(self.delete_category)
        cat_button_row.addWidget(add_cat_btn)
        cat_button_row.addWidget(edit_cat_btn)
        cat_button_row.addWidget(delete_cat_btn)
        left_layout.addLayout(cat_button_row)

        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(QLabel("Вопросы выбранного раздела"))

        self.questions_table = QTableWidget()
        self.questions_table.setColumnCount(len(self.question_headers))
        self.questions_table.setHorizontalHeaderLabels(self.question_headers)
        self.questions_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.questions_table.setSelectionMode(QTableWidget.SingleSelection)
        self.questions_table.setEditTriggers(QTableWidget.NoEditTriggers)
        header = self.questions_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.questions_table.verticalHeader().setVisible(False)
        right_layout.addWidget(self.questions_table, stretch=1)

        q_button_row = QHBoxLayout()
        add_q_btn = QPushButton("Добавить вопрос")
        edit_q_btn = QPushButton("Изменить")
        delete_q_btn = QPushButton("Удалить")
        add_q_btn.clicked.connect(self.add_question)
        edit_q_btn.clicked.connect(self.edit_question)
        delete_q_btn.clicked.connect(self.delete_question)
        q_button_row.addWidget(add_q_btn)
        q_button_row.addWidget(edit_q_btn)
        q_button_row.addWidget(delete_q_btn)
        right_layout.addLayout(q_button_row)

        splitter.addWidget(right_panel)
        splitter.setSizes([250, 600])

    def load_categories(self):
        conn = sqlite3.connect(HELP_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT id, key, label, button, sort_index FROM help_categories ORDER BY sort_index, id"
        )
        rows = cur.fetchall()
        conn.close()

        self.category_list.clear()
        for row in rows:
            text = f"{row['label']} ({row['key']})"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, dict(row))
            self.category_list.addItem(item)

        self.current_category = None
        if rows:
            self.category_list.setCurrentRow(0)
        else:
            self.questions_table.setRowCount(0)

    def _selected_category(self) -> Optional[dict]:
        selected = self.category_list.currentItem()
        if not selected:
            QMessageBox.information(self, "Не выбрано", "Сначала выберите раздел.")
            return None
        return selected.data(Qt.UserRole)

    def add_category(self):
        dialog = CategoryDialog(self)
        if dialog.exec_() != QDialog.Accepted:
            return
        data = dialog.get_data()
        if not data:
            return

        conn = sqlite3.connect(HELP_DB_PATH)
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO help_categories (key, label, button, sort_index)
                VALUES (:key, :label, :button, :sort_index)
                """,
                data,
            )
            conn.commit()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Ошибка", "Категория с таким ключом уже существует.")
        finally:
            conn.close()
        self.load_categories()

    def edit_category(self):
        category = self._selected_category()
        if not category:
            return

        dialog = CategoryDialog(self, category)
        if dialog.exec_() != QDialog.Accepted:
            return
        data = dialog.get_data()
        if not data:
            return
        data["id"] = category["id"]

        conn = sqlite3.connect(HELP_DB_PATH)
        cur = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE help_categories
                SET key = :key, label = :label, button = :button, sort_index = :sort_index
                WHERE id = :id
                """,
                data,
            )
            conn.commit()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Ошибка", "Категория с таким ключом уже существует.")
        finally:
            conn.close()
        self.load_categories()

    def delete_category(self):
        category = self._selected_category()
        if not category:
            return

        confirm = QMessageBox.question(
            self,
            "Удалить раздел",
            "Удалить выбранную категорию и все её вопросы?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        conn = sqlite3.connect(HELP_DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()
        cur.execute("DELETE FROM help_categories WHERE id = ?", (category["id"],))
        conn.commit()
        conn.close()
        self.load_categories()

    def on_category_selected(self):
        item = self.category_list.currentItem()
        if not item:
            self.current_category = None
            self.questions_table.setRowCount(0)
            return
        self.current_category = item.data(Qt.UserRole)
        self.load_questions()

    def load_questions(self):
        if not self.current_category:
            return

        conn = sqlite3.connect(HELP_DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, question, answer, sort_index
            FROM help_questions
            WHERE category_id = ?
            ORDER BY sort_index, id
            """,
            (self.current_category["id"],),
        )
        rows = cur.fetchall()
        conn.close()

        self.questions_table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(row):
                display = str(value) if value is not None else ""
                self.questions_table.setItem(row_idx, col_idx, QTableWidgetItem(display))
        self.questions_table.resizeRowsToContents()

    def _selected_question(self) -> Optional[int]:
        selected = self.questions_table.selectedItems()
        if not selected:
            QMessageBox.information(self, "Не выбрано", "Выберите вопрос из таблицы.")
            return None
        row = selected[0].row()
        return int(self.questions_table.item(row, 0).text())

    def add_question(self):
        if not self.current_category:
            QMessageBox.information(self, "Нет раздела", "Сначала выберите категорию.")
            return

        dialog = QuestionDialog(self)
        if dialog.exec_() != QDialog.Accepted:
            return
        data = dialog.get_data()
        if not data:
            return

        data["category_id"] = self.current_category["id"]

        conn = sqlite3.connect(HELP_DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO help_questions (category_id, question, answer, sort_index)
            VALUES (:category_id, :question, :answer, :sort_index)
            """,
            data,
        )
        conn.commit()
        conn.close()
        self.load_questions()

    def edit_question(self):
        question_id = self._selected_question()
        if not question_id:
            return

        conn = sqlite3.connect(HELP_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT id, question, answer, sort_index FROM help_questions WHERE id = ?",
            (question_id,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            QMessageBox.warning(self, "Ошибка", "Не удалось найти запись.")
            return

        dialog = QuestionDialog(self, dict(row))
        if dialog.exec_() != QDialog.Accepted:
            return
        data = dialog.get_data()
        if not data:
            return
        data["id"] = question_id

        conn = sqlite3.connect(HELP_DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE help_questions
            SET question = :question, answer = :answer, sort_index = :sort_index
            WHERE id = :id
            """,
            data,
        )
        conn.commit()
        conn.close()
        self.load_questions()

    def delete_question(self):
        question_id = self._selected_question()
        if not question_id:
            return

        confirm = QMessageBox.question(
            self,
            "Удалить вопрос",
            "Удалить выбранный вопрос?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        conn = sqlite3.connect(HELP_DB_PATH)
        cur = conn.cursor()
        cur.execute("DELETE FROM help_questions WHERE id = ?", (question_id,))
        conn.commit()
        conn.close()
        self.load_questions()


class AdminWindow(QMainWindow):
    def __init__(self, logout_callback=None):
        super().__init__()
        self.logout_callback = logout_callback
        self.setWindowTitle("Car Helper Admin")
        tabs = QTabWidget()
        tabs.addTab(CarAdminTab(), "Авто")
        tabs.addTab(HelpAdminTab(), "Помощь / FAQ")
        tabs.addTab(UserAdminTab(), "Пользователи")
        tabs.addTab(QAAdminTab(), "База ответов")
        self.setCentralWidget(tabs)
        self.resize(1200, 800)
        self._setup_menu()

    def _setup_menu(self):
        menu = self.menuBar().addMenu("Сессия")
        logout_action = QAction("Выйти", self)
        logout_action.triggered.connect(self._handle_logout)
        menu.addAction(logout_action)

    def _handle_logout(self):
        if self.logout_callback:
            self.logout_callback()


def main():
    ensure_car_schema()
    ensure_help_schema()
    ensure_questions_schema()
    app = QApplication(sys.argv)

    login_dialog = AdminLoginDialog()
    if login_dialog.exec_() != QDialog.Accepted:
        return

    window_holder = {}

    def handle_logout():
        window = window_holder.get("window")
        if not window:
            return
        window.hide()
        dialog = AdminLoginDialog(window)
        if dialog.exec_() == QDialog.Accepted:
            window.show()
        else:
            window.close()
            app.quit()

    window = AdminWindow(logout_callback=handle_logout)
    window_holder["window"] = window
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
