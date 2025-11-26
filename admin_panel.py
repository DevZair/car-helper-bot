from __future__ import annotations

import sys
import sqlite3
from pathlib import Path
from typing import Optional

from PyQt5 import uic
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QDialog,
    QHeaderView,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QWidget,
)

from config import ADMIN_LOGIN, ADMIN_PASSWORD


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UI_DIR = BASE_DIR / "ui"
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
            liked INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
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
        """
    )
    conn.commit()
    _ensure_column(conn, "feedback", "created_at", "TEXT", "CURRENT_TIMESTAMP")
    _ensure_column(conn, "ai_dialogs", "prompt", "TEXT")
    _ensure_column(conn, "ai_dialogs", "status", "TEXT", "'ok'")
    _ensure_column(conn, "ai_dialogs", "error", "TEXT")
    _ensure_column(conn, "ai_dialogs", "created_at", "TEXT", "CURRENT_TIMESTAMP")
    cur.execute("UPDATE ai_dialogs SET status = COALESCE(status, 'ok')")
    cur.execute("UPDATE ai_dialogs SET prompt = question WHERE prompt IS NULL")
    conn.commit()
    conn.close()


class AdminLoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        uic.loadUi(str(UI_DIR / "login_dialog.ui"), self)
        self.button_box.accepted.connect(self.handle_login)
        self.button_box.rejected.connect(self.reject)

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
        uic.loadUi(str(UI_DIR / "car_tab.ui"), self)
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

        self.add_button.clicked.connect(self.add_car)
        self.update_button.clicked.connect(self.update_car)
        self.delete_button.clicked.connect(self.delete_car)
        self.clear_button.clicked.connect(self.clear_form)
        self.refresh_button.clicked.connect(self.load_cars)

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
        self._setup_ui()

        if data:
            self.key_edit.setText(data.get("key", ""))
            self.label_edit.setText(data.get("label", ""))
            self.button_edit.setText(data.get("button", ""))
            self.sort_spin.setValue(data.get("sort_index", 0))

    def _setup_ui(self):
        uic.loadUi(str(UI_DIR / "category_dialog.ui"), self)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

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
        self._setup_ui()

        if data:
            self.question_edit.setText(data.get("question", ""))
            self.answer_edit.setPlainText(data.get("answer", ""))
            self.sort_spin.setValue(data.get("sort_index", 0))

    def _setup_ui(self):
        uic.loadUi(str(UI_DIR / "question_dialog.ui"), self)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

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
        uic.loadUi(str(UI_DIR / "user_tab.ui"), self)
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

        self.add_btn.clicked.connect(self.add_user)
        self.update_btn.clicked.connect(self.update_user)
        self.delete_btn.clicked.connect(self.delete_user)
        self.clear_btn.clicked.connect(self.clear_form)
        self.refresh_btn.clicked.connect(self.load_users)

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
        uic.loadUi(str(UI_DIR / "qa_tab.ui"), self)
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

        self.add_btn.clicked.connect(self.add_entry)
        self.update_btn.clicked.connect(self.update_entry)
        self.delete_btn.clicked.connect(self.delete_entry)
        self.clear_btn.clicked.connect(self.clear_form)
        self.refresh_btn.clicked.connect(self.load_entries)

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


class AIDialogsTab(QWidget):
    headers = ["ID", "User ID", "Вопрос", "Ответ", "Статус", "Дата/время"]

    def __init__(self):
        super().__init__()
        self.current_search: str = ""
        self._setup_ui()
        self.load_dialogs()

    def _setup_ui(self):
        uic.loadUi(str(UI_DIR / "dialogs_tab.ui"), self)
        self.table.setColumnCount(len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self.populate_details)

        self.search_btn.clicked.connect(self.apply_search)
        self.reset_btn.clicked.connect(self.reset_search)
        self.refresh_btn.clicked.connect(self.load_dialogs)
        self.save_btn.clicked.connect(self.add_dialog)

    def apply_search(self):
        self.current_search = self.search_input.text().strip()
        self.load_dialogs()

    def reset_search(self):
        self.search_input.clear()
        self.current_search = ""
        self.load_dialogs()

    def load_dialogs(self):
        conn = sqlite3.connect(QUESTIONS_DB_PATH)
        cur = conn.cursor()
        query = """
        SELECT id, user_id, question, answer, status, created_at, prompt, error
        FROM ai_dialogs
        """
        params = []
        if self.current_search:
            query += " WHERE question LIKE ?"
            params.append(f"%{self.current_search}%")
        query += " ORDER BY COALESCE(created_at, '') DESC, id DESC"
        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()

        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            prompt_value = row[6] if len(row) > 6 else ""
            error_value = row[7] if len(row) > 7 else ""
            for col_idx in range(len(self.headers)):
                value = row[col_idx] if col_idx < len(row) else ""
                raw_value = "" if value is None else str(value)
                display = raw_value
                if col_idx in (2, 3) and len(display) > 60:
                    display = display[:57] + "..."
                item = QTableWidgetItem(display)
                if col_idx == 0:
                    item.setData(Qt.UserRole, row[0])
                if col_idx in (2, 3):
                    item.setData(Qt.UserRole + 1, raw_value)
                if col_idx == 0:
                    item.setData(Qt.UserRole + 2, prompt_value)  # prompt
                    item.setData(Qt.UserRole + 3, error_value)  # error
                self.table.setItem(row_idx, col_idx, item)
        self.table.resizeRowsToContents()
        self.table.clearSelection()
        self.full_question.clear()
        self.full_answer.clear()
        self.full_prompt.clear()

    def populate_details(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        question_item = self.table.item(row, 2)
        answer_item = self.table.item(row, 3)
        id_item = self.table.item(row, 0)
        question_text = ""
        answer_text = ""
        prompt_text = ""
        if question_item:
            question_text = question_item.data(Qt.UserRole + 1) or question_item.text()
        if answer_item:
            answer_text = answer_item.data(Qt.UserRole + 1) or answer_item.text()
        if id_item:
            prompt_text = id_item.data(Qt.UserRole + 2) or ""
            error_text = id_item.data(Qt.UserRole + 3)
            if error_text:
                prompt_text = f"{prompt_text}\n\n---\nОшибка: {error_text}"
        if not prompt_text:
            prompt_text = "Промпт не сохранён (старый диалог)"
        self.full_question.setPlainText(question_text)
        self.full_answer.setPlainText(answer_text)
        self.full_prompt.setPlainText(prompt_text)

    def add_dialog(self):
        question = self.new_question.toPlainText().strip()
        answer = self.new_answer.toPlainText().strip()
        if not question or not answer:
            QMessageBox.warning(self, "Недостаточно данных", "Нужны и вопрос, и ответ.")
            return
        user_id_text = self.new_user_id.text().strip()
        user_id = None
        if user_id_text:
            try:
                user_id = int(user_id_text)
            except ValueError:
                QMessageBox.warning(self, "Некорректный User ID", "User ID должен быть числом.")
                return
        conn = sqlite3.connect(QUESTIONS_DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO ai_dialogs (user_id, question, answer, prompt, status, created_at)
            VALUES (?, ?, ?, ?, 'manual', CURRENT_TIMESTAMP)
            """,
            (user_id, question, answer, question),
        )
        conn.commit()
        conn.close()
        QMessageBox.information(self, "Готово", "Диалог добавлен.")
        self.new_question.clear()
        self.new_answer.clear()
        self.new_user_id.clear()
        self.load_dialogs()


class AIFeedbackTab(QWidget):
    headers = ["ID", "User ID", "Вопрос", "Ответ", "Оценка", "Дата/время"]

    def __init__(self):
        super().__init__()
        self.current_filter: Optional[int] = None
        self.current_feedback_id: Optional[int] = None
        self._setup_ui()
        self.load_feedback()

    def _setup_ui(self):
        uic.loadUi(str(UI_DIR / "feedback_tab.ui"), self)
        self.table.setColumnCount(len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self.populate_details)

        self.liked_btn.clicked.connect(lambda: self.apply_filter(1))
        self.disliked_btn.clicked.connect(lambda: self.apply_filter(0))
        self.all_btn.clicked.connect(lambda: self.apply_filter(None))
        self.refresh_btn.clicked.connect(self.load_feedback)
        self.toggle_button.clicked.connect(self.toggle_feedback)

    def apply_filter(self, value: Optional[int]):
        self.current_filter = value
        self.load_feedback()

    def load_feedback(self):
        conn = sqlite3.connect(QUESTIONS_DB_PATH)
        cur = conn.cursor()
        query = "SELECT id, user_id, question, answer, liked, created_at FROM feedback"
        params = []
        if self.current_filter is not None:
            query += " WHERE liked = ?"
            params.append(self.current_filter)
        query += " ORDER BY COALESCE(created_at, '') DESC, id DESC"
        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()

        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(row):
                if col_idx == 4:
                    liked = 1 if value else 0
                    text = "👍" if liked else "👎"
                    item = QTableWidgetItem(text)
                    color = QColor("green") if liked else QColor("red")
                    item.setForeground(color)
                    item.setData(Qt.UserRole + 2, liked)
                else:
                    raw_value = "" if value is None else str(value)
                    display = raw_value
                    if col_idx in (2, 3) and len(display) > 60:
                        display = display[:57] + "..."
                    item = QTableWidgetItem(display)
                    if col_idx in (2, 3):
                        item.setData(Qt.UserRole + 1, raw_value)
                if col_idx == 0:
                    item.setData(Qt.UserRole, row[0])
                self.table.setItem(row_idx, col_idx, item)
        self.table.resizeRowsToContents()
        self.table.clearSelection()
        self.current_feedback_id = None
        self.full_feedback_question.clear()
        self.full_feedback_answer.clear()

    def populate_details(self):
        selected = self.table.selectedItems()
        if not selected:
            self.current_feedback_id = None
            return
        row = selected[0].row()
        id_item = self.table.item(row, 0)
        if not id_item:
            self.current_feedback_id = None
            return
        raw_id = id_item.data(Qt.UserRole) or id_item.text()
        try:
            self.current_feedback_id = int(raw_id)
        except (TypeError, ValueError):
            self.current_feedback_id = None
            return

        def _text(col):
            cell = self.table.item(row, col)
            if not cell:
                return ""
            return cell.data(Qt.UserRole + 1) or cell.text()

        self.full_feedback_question.setPlainText(_text(2))
        self.full_feedback_answer.setPlainText(_text(3))

    def toggle_feedback(self):
        if self.current_feedback_id is None:
            QMessageBox.information(self, "Не выбрано", "Выберите запись для изменения.")
            return
        conn = sqlite3.connect(QUESTIONS_DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT liked FROM feedback WHERE id = ?", (self.current_feedback_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            QMessageBox.warning(self, "Ошибка", "Запись не найдена.")
            return
        current = 1 if row[0] else 0
        new_value = 0 if current else 1
        cur.execute(
            "UPDATE feedback SET liked = ? WHERE id = ?",
            (new_value, self.current_feedback_id),
        )
        conn.commit()
        conn.close()
        self.load_feedback()
class HelpAdminTab(QWidget):
    question_headers = ["ID", "Вопрос", "Ответ", "Сортировка"]

    def __init__(self):
        super().__init__()
        self.current_category: Optional[dict] = None
        self._setup_ui()
        self.load_categories()

    def _setup_ui(self):
        uic.loadUi(str(UI_DIR / "help_tab.ui"), self)
        self.category_list.itemSelectionChanged.connect(self.on_category_selected)
        self.questions_table.setColumnCount(len(self.question_headers))
        self.questions_table.setHorizontalHeaderLabels(self.question_headers)
        self.questions_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.questions_table.setSelectionMode(QTableWidget.SingleSelection)
        self.questions_table.setEditTriggers(QTableWidget.NoEditTriggers)
        header = self.questions_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.questions_table.verticalHeader().setVisible(False)
        self.splitter.setSizes([250, 600])

        self.add_cat_btn.clicked.connect(self.add_category)
        self.edit_cat_btn.clicked.connect(self.edit_category)
        self.delete_cat_btn.clicked.connect(self.delete_category)
        self.add_q_btn.clicked.connect(self.add_question)
        self.edit_q_btn.clicked.connect(self.edit_question)
        self.delete_q_btn.clicked.connect(self.delete_question)

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
        self.tabs = QTabWidget()
        self.car_tab = CarAdminTab()
        self.help_tab = HelpAdminTab()
        self.users_tab = UserAdminTab()
        self.qa_tab = QAAdminTab()
        self.dialogs_tab = AIDialogsTab()
        self.ai_feedback_tab = AIFeedbackTab()
        self.tabs.addTab(self.car_tab, "Авто")
        self.tabs.addTab(self.help_tab, "Помощь / FAQ")
        self.tabs.addTab(self.users_tab, "Пользователи")
        self.tabs.addTab(self.qa_tab, "База ответов")
        self.tabs.addTab(self.dialogs_tab, "Диалоги с ИИ")
        self.tabs.addTab(self.ai_feedback_tab, "Оценки ответов ИИ")
        self.setCentralWidget(self.tabs)
        self.resize(1200, 800)
        self._setup_menu()

    def _setup_menu(self):
        session_menu = self.menuBar().addMenu("Сессия")
        logout_action = QAction("Выйти", self)
        logout_action.triggered.connect(self._handle_logout)
        session_menu.addAction(logout_action)

        sections_menu = self.menuBar().addMenu("Разделы")
        dialogs_action = QAction("Диалоги с ИИ", self)
        dialogs_action.triggered.connect(lambda: self._open_tab(self.dialogs_tab))
        feedback_action = QAction("Оценки ответов ИИ", self)
        feedback_action.triggered.connect(lambda: self._open_tab(self.ai_feedback_tab))
        sections_menu.addAction(dialogs_action)
        sections_menu.addAction(feedback_action)

    def _handle_logout(self):
        if self.logout_callback:
            self.logout_callback()

    def _open_tab(self, widget: QWidget):
        index = self.tabs.indexOf(widget)
        if index != -1:
            self.tabs.setCurrentIndex(index)


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
