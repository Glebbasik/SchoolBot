import telebot
from telebot import types
from telebot import apihelper
import sqlite3
import re
import time 
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
from threading import Lock
import requests
from bs4 import BeautifulSoup as BS
from pathlib import Path
#*Тут все библиотеки*#

file_path = os.path.abspath(__file__)
current_dir = os.path.dirname(file_path)
env_path = os.path.join(current_dir, 'bot.env')

load_dotenv(env_path)
bot = telebot.TeleBot(os.getenv("TOKEN"))
apihelper.delete_webhook(bot.token)
db_lock = Lock()
conn = sqlite3.connect('BD_for_telegram_bot.db', check_same_thread=False)
cur = conn.cursor()
cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        password TEXT,
        class_number TEXT,
        class_letter TEXT)
''')
conn.commit()

cur.execute('''
    CREATE TABLE IF NOT EXISTS anonymous_questions (
        question_id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user_id INTEGER,
        to_teacher_id INTEGER,
        question_text TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        is_answered BOOLEAN DEFAULT 0,
        answer_text TEXT
    )
''')
conn.commit()

cur.execute('''
    CREATE TABLE IF NOT EXISTS elschool_data (
    user_id INTEGER PRIMARY KEY,
    login_user TEXT,
    password_user TEXT
    )
''')

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Ловим даже DEBUG сообщения

#Папка для логов
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# Форматирование (общее для всех обработчиков)
formatter = logging.Formatter(
    '%(asctime)s\n--- %(levelname)s ----\n%(message)s',
    datefmt='%Y/%m/%d %H:%M:%S'
)

# 1. Обработчик для консоли (только INFO и выше)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

# 2. Обработчик для файла (DEBUG и выше + ротация логов)
file_handler = logging.FileHandler(
    filename=log_dir / "app.log",
    encoding='utf-8'
)
file_handler.setLevel(logging.DEBUG)  # В файл пишем всё
file_handler.setFormatter(formatter)

# Добавляем оба обработчика
logger.addHandler(console_handler)
logger.addHandler(file_handler)

#*Глобальные переменные
user_states = {}
search_data = {}
photo_calendar_dct = {
    'photo': None,
    'text': None
}
adminusers_insert_dct = {
    'user_id': None,
    'username': None,
    'password':None,
    'class_number': None,
    'class_letter': None
}

def check_registration(func):
    def wrapper(message):
        user_id = message.from_user.id
        with db_lock:
            cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user_data = cur.fetchone()
        if user_data is None or user_data[3] is None or user_data[4] is None:
            bot.send_message(message.chat.id, "<b>Пожалуйста, зарегистрируйтесь с помощью команды /start</b>", parse_mode="HTML")
            return
        return func(message)
    return wrapper

def is_teacher(user_id):
    with db_lock:
        cur.execute("SELECT class_number FROM users WHERE user_id = ?", (user_id,))
        result = cur.fetchone()
    if result and '_id' in result[0]:
        return True
    return False

#Команда /start   
@bot.message_handler(commands=['start'])
def main_start(message):
    user_id = message.from_user.id
    hour = datetime.now().hour
    stiker_day = "CAACAgIAAxkBAAEOHYxn8kxlp5bYBtPFWysqWJfvY6s08AAChwIAAladvQpC7XQrQFfQkDYE"
    stiker_evening = "CAACAgIAAxkBAAENsl5n3uJz91ELhaAbvdExcighKaLHVQADKwACXTlgSeFvhT8xkv9ENgQ"
    stiker_night = "CAACAgIAAxkBAAENslJn3uIeXXiUIm0gigSgk0wehvvrfQACTyMAAtAZMEgpYDBIIoBMvTYE"
    stiker_morning = "CAACAgIAAxkBAAEN0n9n5D7j7cx0oCTQgnooixX3UtWHXAACIQ0AAiWx6UpCBrcao52KeDYE"
    with db_lock:
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user_data = cur.fetchone()

    if user_data:
        if user_data[3] != None and user_data[4] != None: 
            if 6 <= hour < 12:
                bot.send_message(message.chat.id, f"<b>Утро доброе! 🌅 {message.from_user.first_name}</b>", parse_mode="HTML")
                bot.send_sticker(message.chat.id, stiker_morning)
            elif 12 <= hour < 18:
                bot.send_message(message.chat.id, f"<b>Доброго дня! 🌞 {message.from_user.first_name}</b>", parse_mode="HTML")
                bot.send_sticker(message.chat.id, stiker_day)
            elif 18 <= hour <= 23:
                bot.send_message(message.chat.id, f"<b>Добрый вечер! 🌙 {message.from_user.first_name}</b>", parse_mode="HTML")
                bot.send_sticker(message.chat.id, stiker_evening)
            else:
                bot.send_message(message.chat.id, f"<b>Доброй ночи! 🌙 {message.from_user.first_name}</b>", parse_mode="HTML")
                bot.send_sticker(message.chat.id, stiker_night)
        else:
            bot.send_message(message.chat.id, "<b>Пройдите регистрацию до конца😤</b>", parse_mode="HTML")
            register_class_id(message=message, accepted_message_id=None)
    else:
        bot.send_message(message.chat.id, f"<b>Добро пожаловать {message.from_user.first_name}!</b>✨\n"
                                        "<b>Пройдите регистрацию🥰</b>", parse_mode="HTML")
        bot.send_sticker(message.chat.id, stiker_day)
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_1 = types.InlineKeyboardButton('Войти как ученик', callback_data='study_user')
        btn_2 = types.InlineKeyboardButton('Войти как учитель', callback_data='teacher_user')
        markup.add(btn_1, btn_2)
        bot.send_message(message.chat.id, "<b>Давайте начнём! Как вы хотите войти?</b>", reply_markup=markup, parse_mode="HTML")
# Регистрация учащегося 
@bot.callback_query_handler(func=lambda call: call.data == 'study_user')
def handle_button(call):
    default_bull = 'student'
    try:
        bot.answer_callback_query(call.id)
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.delete_message(call.message.chat.id, call.message.message_id-1)
        bot.delete_message(call.message.chat.id, call.message.message_id-2)
        # Для учеников сразу переходим к выбору класса без пароля
        user_id = call.from_user.id
        with db_lock:
            cur.execute("INSERT INTO users (user_id, username, password, class_number, class_letter) VALUES (?, ?, ?, ?, ?)", 
                    (user_id, call.from_user.first_name, default_bull, None, None))
            conn.commit()
        register_class_id(call.message)
    except Exception as exp:
        logger.error(exp)

def register_class_id(message):
    wait_message = bot.send_message(message.chat.id, "<b>Подождите секунду...</b>", parse_mode="HTML")
    
    time.sleep(2)
    
    try:
        bot.delete_message(message.chat.id, wait_message.message_id)  # Удаляем "Подождите секунду..."
    except Exception as e:
        logger.error(e)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_1 = types.InlineKeyboardButton("5 класс🔹", callback_data="class_5")
    btn_2 = types.InlineKeyboardButton("6 класс🔹", callback_data="class_6")
    btn_3 = types.InlineKeyboardButton("7 класс🔹", callback_data="class_7")
    btn_4 = types.InlineKeyboardButton("8 класс🔹", callback_data="class_8")
    btn_5 = types.InlineKeyboardButton("9 класс🔹", callback_data="class_9")
    btn_6 = types.InlineKeyboardButton("10 класс🔹", callback_data="class_10")
    btn_7 = types.InlineKeyboardButton("11 класс🔹", callback_data="class_11")
    markup.add(btn_1, btn_2, btn_3, btn_4, btn_5, btn_6, btn_7)
    bot.send_message(message.chat.id, "<b>Пожалуйста, укажите, в каком классе вы учитесь😉</b>", parse_mode="HTML", reply_markup=markup)

#Регистрация учителя
@bot.callback_query_handler(func=lambda call: call.data == 'teacher_user')
def handle_button_teacher(call):
    try:
        bot.answer_callback_query(call.id)
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.delete_message(call.message.chat.id, call.message.message_id-1)
        bot.delete_message(call.message.chat.id, call.message.message_id-2)
        reg_new_teacher(call.message)
    except Exception as exp:
        logger.error(e)
def reg_new_teacher(message):
    try:
        bot.send_message(message.chat.id, "<b>Пожалуйста, введите ваш универсальный ID😀:</b>", parse_mode="HTML")
        bot.register_next_step_handler(message, lambda msg: password_new_teacher(msg))
    except Exception:
        logger.error(e)
def password_new_teacher(message):
    password = message.text.strip()
    user_id = message.from_user.id
    password_teachers = {
    5: {"А": "a7b3c9d2e1", "Б": "f4g6h8j0k5", "В": "l2m4n6p8q0", "Г": "xk8d3m9p2q", "Д": "r1s3t5u7v9"},
    6: {"А": "w2x4y6z8a0", "Б": "b3c5d7e9f1", "В": "g4h6j8k0l2", "Г": "m5n7p9q1r3"},
    7: {"А": "s6t8u0v2w4", "Б": "x7y9z1a3b5", "В": "c8d0e2f4g7", "Г": "h9j1k3l5m8"},
    8: {"А": "n0p2q4r6s9", "Б": "t3u5v7w9x1", "В": "y4z6a8b0c2", "Г": "d5e7f9g1h3"},
    9: {"А": "i6j8k0l2m4", "Б": "n7o9p1q3r5", "В": "s8t0u2v4w6", "Г": "x9y1z3a5b7"},
    10: {"А": "c8d0e2f4g6", "Б": "h9j1k3l5m7"},
    11: {"А": "n0p2q4r6s8", "Б": "t3u5v7w9x9"}
    }
    with db_lock:
        cur.execute("""
            SELECT user_id FROM users 
            WHERE password = ?
            """, (password,))
        existing_teacher = cur.fetchone()
    
    found = any(
        password in class_letters.values()
        for class_letters in password_teachers.values()
    )

    if existing_teacher and found:
        bot.send_message(
            chat_id=message.chat.id,
            text="<b>❌ Учитель с таким id уже зарегистрирован! ❌</b>\n"
            "<b>Если это ошибка, обратитесь к администратору</b>",
            parse_mode='HTML'
        )
        return
    result = next(((n, l) for n, letters in password_teachers.items() 
            for l, p in letters.items() if p == password), None)
    
    if password in ("/start", "/clear", "/help", "/reference", "/exit", "/calendar", "/support", '/ask_anon', '/my_questions', '/send_class', '/del_user_elschool', '/elschool_marks'):
        bot.send_message(message.chat.id, "<b>Ой, кажется, вы прервали регистрацию. Давайте попробуем ещё раз /start😊</b>", parse_mode="HTML")
        return
    elif result is not None:
        try:
            class_number, class_letter = result
            with db_lock:
                cur.execute("INSERT INTO users (user_id, username, password, class_number, class_letter) VALUES (?, ?, ?, ?, ?)", (user_id, message.from_user.first_name, password, f"{class_number}_id", class_letter))
                conn.commit()
            register_class_teacher(message=message)
        except Exception:
            logger.error(e)
    else:
        bot.send_sticker(message.chat.id, "CAACAgIAAxkBAAENs7Fn3xUuEgn_WhAFdrvFP5oAAR9kmw4AAr0cAAJHONBKJuWKeGhBF-02BA")
        time.sleep(1)
        bot.send_message(message.chat.id, "<b>❌Неверный ID❌</b>"
                                        "Попробуйте снова😉", parse_mode="HTML")
        bot.register_next_step_handler(message, lambda msg: password_new_teacher(msg))


def register_class_teacher(message):
    wait_message = bot.send_message(message.chat.id, "<b>Подождите секунду...</b>", parse_mode="HTML")
    
    time.sleep(2)
    
    try:
        bot.delete_message(message.chat.id, wait_message.message_id)  # Удаляем "Подождите секунду..."
        bot.send_message(message.chat.id, '<b>Вы успешно вошли как учитель😀</b>', parse_mode="HTML")
        with db_lock:
            cur.execute("SELECT * FROM users WHERE user_id = ?", (message.from_user.id,))
            list_user = cur.fetchone()
        logger.info(f"Учитель зарегистрировался: {list_user}")
    except Exception:
        logger.error(e)

@bot.callback_query_handler(func=lambda call: call.data == "class_5")
def class_5_call(call):
    bot.answer_callback_query(call.id)
    with db_lock:
        cur.execute("UPDATE users SET class_number = ? WHERE user_id = ?", ('5', call.from_user.id))
        conn.commit()
    markup = types.InlineKeyboardMarkup(row_width=2)
    but_1 = types.InlineKeyboardButton("А🔹", callback_data="class_a")
    but_2 = types.InlineKeyboardButton("Б🔹", callback_data="class_b")
    but_3 = types.InlineKeyboardButton("В🔹", callback_data="class_v")
    but_4 = types.InlineKeyboardButton("Г🔹", callback_data="class_g")
    but_5 = types.InlineKeyboardButton("Д🔹", callback_data="class_d")
    back_btn = types.InlineKeyboardButton("Вернуться назад🔄", callback_data="back_button")
    markup.add(but_1, but_2, but_3, but_4, but_5)
    markup.add(back_btn)

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Отлично, теперь выберите букву вашего класса:</b>",
        parse_mode="HTML",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "class_6")
def class_5_call(call):
    bot.answer_callback_query(call.id)
    with db_lock:
        cur.execute("UPDATE users SET class_number = ? WHERE user_id = ?", ('6', call.from_user.id))
        conn.commit()
    markup = types.InlineKeyboardMarkup(row_width=2)
    but_1 = types.InlineKeyboardButton("А🔹", callback_data="class_a")
    but_2 = types.InlineKeyboardButton("Б🔹", callback_data="class_b")
    but_3 = types.InlineKeyboardButton("В🔹", callback_data="class_v")
    but_4 = types.InlineKeyboardButton("Г🔹", callback_data="class_g")
    back_btn = types.InlineKeyboardButton("Вернуться назад🔄", callback_data="back_button")
    markup.add(but_1, but_2, but_3, but_4)
    markup.add(back_btn)

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Отлично, теперь выберите букву вашего класса:</b>",
        parse_mode="HTML",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "class_7")
def class_5_call(call):
    bot.answer_callback_query(call.id)
    with db_lock:
        cur.execute("UPDATE users SET class_number = ? WHERE user_id = ?", ('7', call.from_user.id))
        conn.commit()
    markup = types.InlineKeyboardMarkup(row_width=2)
    but_1 = types.InlineKeyboardButton("А🔹", callback_data="class_a")
    but_2 = types.InlineKeyboardButton("Б🔹", callback_data="class_b")
    but_3 = types.InlineKeyboardButton("В🔹", callback_data="class_v")
    but_4 = types.InlineKeyboardButton("Г🔹", callback_data="class_g")
    back_btn = types.InlineKeyboardButton("Вернуться назад🔄", callback_data="back_button")
    markup.add(but_1, but_2, but_3, but_4)
    markup.add(back_btn)

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Отлично, теперь выберите букву вашего класса:</b>",
        parse_mode="HTML",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "class_8")
def class_5_call(call):
    bot.answer_callback_query(call.id)
    with db_lock:
        cur.execute("UPDATE users SET class_number = ? WHERE user_id = ?", ('8', call.from_user.id))
        conn.commit()
    markup = types.InlineKeyboardMarkup(row_width=2)
    but_1 = types.InlineKeyboardButton("А🔹", callback_data="class_a")
    but_2 = types.InlineKeyboardButton("Б🔹", callback_data="class_b")
    but_3 = types.InlineKeyboardButton("В🔹", callback_data="class_v")
    but_4 = types.InlineKeyboardButton("Г🔹", callback_data="class_g")
    back_btn = types.InlineKeyboardButton("Вернуться назад🔄", callback_data="back_button")
    markup.add(but_1, but_2, but_3, but_4)
    markup.add(back_btn)

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Отлично, теперь выберите букву вашего класса:</b>",
        parse_mode="HTML",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "class_9")
def class_5_call(call):
    bot.answer_callback_query(call.id)
    with db_lock:
        cur.execute("UPDATE users SET class_number = ? WHERE user_id = ?", ('9', call.from_user.id))
        conn.commit()
    markup = types.InlineKeyboardMarkup(row_width=2)
    but_1 = types.InlineKeyboardButton("А🔹", callback_data="class_a")
    but_2 = types.InlineKeyboardButton("Б🔹", callback_data="class_b")
    but_3 = types.InlineKeyboardButton("В🔹", callback_data="class_v")
    but_4 = types.InlineKeyboardButton("Г🔹", callback_data="class_g")
    back_btn = types.InlineKeyboardButton("Вернуться назад🔄", callback_data="back_button")
    markup.add(but_1, but_2, but_3, but_4)
    markup.add(back_btn)

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Отлично, теперь выберите букву вашего класса:</b>",
        parse_mode="HTML",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "class_10")
def class_5_call(call):
    bot.answer_callback_query(call.id)
    with db_lock:
        cur.execute("UPDATE users SET class_number = ? WHERE user_id = ?", ('10', call.from_user.id))
        conn.commit()
    markup = types.InlineKeyboardMarkup(row_width=2)
    but_1 = types.InlineKeyboardButton("А🔹", callback_data="class_a")
    but_2 = types.InlineKeyboardButton("Б🔹", callback_data="class_b")
    back_btn = types.InlineKeyboardButton("Вернуться назад🔄", callback_data="back_button")
    markup.add(but_1, but_2)
    markup.add(back_btn)

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Отлично, теперь выберите букву вашего класса:</b>",
        parse_mode="HTML",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "class_11")
def class_5_call(call):
    bot.answer_callback_query(call.id)
    with db_lock:
        cur.execute("UPDATE users SET class_number = ? WHERE user_id = ?", ('11', call.from_user.id))
        conn.commit()
    markup = types.InlineKeyboardMarkup(row_width=2)
    but_1 = types.InlineKeyboardButton("А🔹", callback_data="class_a")
    but_2 = types.InlineKeyboardButton("Б🔹", callback_data="class_b")
    back_btn = types.InlineKeyboardButton("Вернуться назад🔄", callback_data="back_button")
    markup.add(but_1, but_2)
    markup.add(back_btn)

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Отлично, теперь выберите букву вашего класса:</b>",
        parse_mode="HTML",
        reply_markup=markup
    )






@bot.callback_query_handler(func=lambda call: call.data == "class_a")
def call_class_a(call):
    bot.answer_callback_query(call.id)
    with db_lock:
        cur.execute("UPDATE users SET class_letter = ? WHERE user_id = ?", ('А', call.from_user.id))
        conn.commit()
    user_id = call.from_user.id
    with db_lock:
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user_data = cur.fetchone()
    logger.info(f"Пользователь зарегистрирован: {user_data}")
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Отлично, регистрация прошла успешно😊</b>",
        parse_mode="HTML"
    )
@bot.callback_query_handler(func=lambda call: call.data == "class_b")
def call_class_a(call):
    bot.answer_callback_query(call.id)
    with db_lock:
        cur.execute("UPDATE users SET class_letter = ? WHERE user_id = ?", ('Б', call.from_user.id))
        conn.commit()
    user_id = call.from_user.id
    with db_lock:
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user_data = cur.fetchone()
    logger.info(f"Пользователь зарегистрирован: {user_data}")
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Отлично, регистрация прошла успешно😊</b>",
        parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data == "class_v")
def call_class_a(call):
    bot.answer_callback_query(call.id)
    with db_lock:
        cur.execute("UPDATE users SET class_letter = ? WHERE user_id = ?", ('В', call.from_user.id))
        conn.commit()
    user_id = call.from_user.id
    with db_lock:
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user_data = cur.fetchone()
    logger.info(f"Пользователь зарегистрирован: {user_data}")
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Отлично, регистрация прошла успешно😊</b>",
        parse_mode="HTML"
    )
    
@bot.callback_query_handler(func=lambda call: call.data == "class_g")
def call_class_a(call):
    bot.answer_callback_query(call.id)
    with db_lock:
        cur.execute("UPDATE users SET class_letter = ? WHERE user_id = ?", ('Г', call.from_user.id))
        conn.commit()
    user_id = call.from_user.id
    with db_lock:
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user_data = cur.fetchone()
    logger.info(f"Пользователь зарегистрирован: {user_data}")
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Отлично, регистрация прошла успешно😊</b>",
        parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data == "class_d")
def call_class_a(call):
    bot.answer_callback_query(call.id)
    with db_lock:
        cur.execute("UPDATE users SET class_letter = ? WHERE user_id = ?", ('Д', call.from_user.id))
        conn.commit()
    user_id = call.from_user.id
    with db_lock:
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user_data = cur.fetchone()
    logger.info(f"Пользователь зарегистрирован: {user_data}")
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Отлично, регистрация прошла успешно😊</b>",
        parse_mode="HTML"
    )



@bot.callback_query_handler(func=lambda call: call.data == "back_button")
def back_class_button(call):
    bot.answer_callback_query(call.id)
    with db_lock:
        cur.execute("UPDATE users SET class_number = ? WHERE user_id = ?", (None, call.from_user.id))
        conn.commit()
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_1 = types.InlineKeyboardButton("5 класс🔹", callback_data="class_5")
    btn_2 = types.InlineKeyboardButton("6 класс🔹", callback_data="class_6")
    btn_3 = types.InlineKeyboardButton("7 класс🔹", callback_data="class_7")
    btn_4 = types.InlineKeyboardButton("8 класс🔹", callback_data="class_8")
    btn_5 = types.InlineKeyboardButton("9 класс🔹", callback_data="class_9")
    btn_6 = types.InlineKeyboardButton("10 класс🔹", callback_data="class_10")
    btn_7 = types.InlineKeyboardButton("11 класс🔹", callback_data="class_11")
    markup.add(btn_1, btn_2, btn_3, btn_4, btn_5, btn_6, btn_7)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Пожалуйста, укажите, в каком классе вы учитесь😉</b>",
        parse_mode="HTML",
        reply_markup=markup
    )


@bot.message_handler(commands=['clear'])
@check_registration
def clear(message):
    chat_id = message.chat.id
    user_message_id = message.message_id  # ID сообщения пользователя

    try:
        for message_id in range(user_message_id, user_message_id - 30, -1):
            try:
                bot.delete_message(chat_id, message_id)
            except:
                pass  # Игнорируем ошибки, если сообщение уже удалено
    except Exception as e:
        logger.error(e)
        bot.send_message(chat_id, f"<b>Ошибка при очистке чата: {e}</b>", parse_mode='HTML')

@bot.message_handler(commands=['reference'])
@check_registration
def send_subject_choice(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    btn_math = types.InlineKeyboardButton('Математика🔢', callback_data='math')
    btn_physics = types.InlineKeyboardButton('Физика🚗', callback_data='physics')
    btn_russian = types.InlineKeyboardButton('Русский язык📒', callback_data='russian')
    btn_informatics = types.InlineKeyboardButton('Информатика💻', callback_data='informatics')
    btn_english = types.InlineKeyboardButton('Английский язык🗽', callback_data='english')
    btn_chemistry = types.InlineKeyboardButton('Химия🧪', callback_data='chemistry')
    btn_biology = types.InlineKeyboardButton('Биология🌼', callback_data='biology')
    btn_literature = types.InlineKeyboardButton('Литература📚', callback_data='literature')
    btn_history = types.InlineKeyboardButton('История🎭', callback_data='history')
    btn_social_studies = types.InlineKeyboardButton('Обществознание📕', callback_data='social_studies')

    markup.add(btn_math, btn_physics, btn_russian, btn_informatics, btn_english, btn_chemistry, btn_biology, btn_literature, btn_history, btn_social_studies)

    bot.send_message(message.chat.id, "<b>Выберите предмет, который вас интересует:</b>", reply_markup=markup, parse_mode='HTML')

@bot.message_handler(commands=['send_class'])
def func_sendimage_class(message):
    with db_lock:
        cur.execute("SELECT * FROM users WHERE user_id = ?", (message.from_user.id,))
        user_lst = cur.fetchone()
    if '_id' in user_lst[3]: 
        stiker = 'CAACAgIAAxkBAAEOHYpn8kvZrCgNpVs3ks0H6t8k0QR-kgACeAIAAladvQr8ugi1kX0cDDYE'
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_1 = types.InlineKeyboardButton('Изображение🖼', callback_data='image_teacher')
        btn_2 = types.InlineKeyboardButton('Текст⌨', callback_data='text_teacher')
        markup.add(btn_1, btn_2)
        bot.send_sticker(message.chat.id, stiker)
        bot.send_message(message.chat.id, '<b>Выберите формат сообщения, который хотите отправить своему классу☺</b>', reply_markup=markup, parse_mode='HTML')
    else:
        bot.send_message(message.chat.id, '<b>Упс! Я бы с радостью выполнил команду, но мои инструкции разрешают это только учителям.😄\n'
                        'Если вам нужна помощь, напишите /help — я с радостью подскажу!</b>', parse_mode='HTML')
        return
@bot.message_handler(content_types=['photo'])
def handle_teacher_image(message):
    # Обработчик изображений с возможностью добавления текста
    user_id = message.from_user.id
    if user_states.get(user_id, {}).get('state') == 'waiting_for_image':
        try:
            # Сохраняем изображение и ждем текст
            image_file_id = message.photo[-1].file_id
            user_states[user_id] = {
                'state': 'waiting_for_caption',
                'image': image_file_id
            }
            
            bot.send_message(
                message.chat.id,
                "<b>📩 Изображение получено! Теперь введите текст подписи к изображению\n</b>"
                "<b>Или отправьте /skip чтобы отправить без текста</b>",
                reply_markup=types.ForceReply(selective=True),
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(e)
            bot.send_message(message.chat.id, "<b>❌ Не удалось обработать изображение</b>", parse_mode='HTML')
            user_states[user_id] = None
    elif user_states.get(user_id, {}).get('state') == 'waiting_for_caption':
        # Это не должно происходить, но на всякий случай
        bot.send_message(message.chat.id, "<b>ℹ️ Сначала отправьте изображение</b>", parse_mode='HTML')
    else:
        return

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'waiting_for_caption')
def handle_image_caption(message):
    # Обработчик текста подписи к изображению
    user_id = message.from_user.id
    user_data = user_states.get(user_id, {})
    
    if message.text == '/skip':
        caption = None
    else:
        caption = message.text
    
    try:
        image_all_teacher_people(
            message=message,
            message_image=user_data['image'],
            caption=caption
        )
    except Exception as e:
        logger.error(e)
        bot.send_message(message.chat.id, "<b>❌ Не удалось отправить сообщение</b>", parse_mode='HTML')
    finally:
        user_states[user_id] = None  # Сбрасываем состояние

def image_all_teacher_people(message, message_image, caption=None):
    try:
        # Получаем данные текущего пользователя
        with db_lock:
            cur.execute("SELECT class_number, class_letter FROM users WHERE user_id = ?", 
                    (message.from_user.id,))
            teacher_data = cur.fetchone()
        if len(teacher_data[0]) == 4:
            class_number = teacher_data[0][:1]
            class_letter = teacher_data[1]
        else:
            class_number = teacher_data[0][:2]
            class_letter = teacher_data[1]

        # Получаем всех учеников
        with db_lock:
            cur.execute("""
                SELECT user_id FROM users 
                WHERE class_number = ? AND class_letter = ? AND user_id != ?
                """, (class_number, class_letter, message.from_user.id))
            students = cur.fetchall()

        if not students:
            bot.send_message(message.chat.id, "<b>ℹ️ В вашем классе нет других пользователей</b>", parse_mode='HTML')
            return

        # Отправляем всем ученикам
        success_count = 0
        for student in students:
            try:
                bot.send_message(student[0], '<b>Вам пришло сообщение от вашего классного руководителя✉</b>', parse_mode='HTML')
                bot.send_photo(
                    student[0],
                    message_image,
                    caption=caption if caption else "📩 Сообщение от классного руководителя"
                )
                success_count += 1
            except Exception as e:
                logger.error(e)
        # Отчет учителю
        bot.send_message(
            message.chat.id,
            f"<b>✅ Материал отправлен {success_count} из {len(students)} учеников\n</b>"
            f"<b>Текст подписи: {caption if caption else 'без текста'}</b>",
            parse_mode='HTML'
        )

    except Exception as e:
        logger.error(e)
        bot.send_message(message.chat.id, "<b>❌ Произошла ошибка при отправке</b>", parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data == 'image_teacher')
def callfunc_image_teacher(call):
    # Отправка изображения
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    user_states[user_id] = {
        'state': 'waiting_for_image'
    }
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>📩 Отлично! Прикрепите изображение для отправки классу.</b>",
        parse_mode="HTML"
    )


@bot.callback_query_handler(func=lambda call: call.data == 'text_teacher')
def func_teacher_send_text(call):
    bot.answer_callback_query(call.id)
    
    msg = bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>🌟 Отлично! Просто введите текст — и ваши ученики мгновенно получат сообщение!</b>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_teacher_text)

def process_teacher_text(message):
    try:
        teacher_text = message.text
        teacher_id = message.from_user.id
        if teacher_text in ("/start", "/clear", "/help", "/reference", "/exit", "/calendar", "/support", '/ask_anon', '/my_questions', '/send_class', '/del_user_elschool', '/elschool_marks'):
            bot.send_message(message.chat.id, '<b>Ошибка при обработке текста❌</b>', parse_mode='HTML')
            return
        if not teacher_text.strip():
            bot.send_message(message.chat.id, "<b>❌ Текст сообщения не может быть пустым</b>", parse_mode='HTML')
            return
        with db_lock:
            cur.execute("SELECT class_number, class_letter FROM users WHERE user_id = ?", (teacher_id,))
            teacher_data = cur.fetchone()
        
        if len(teacher_data[0]) == 4:
            class_number = teacher_data[0][:1]
            class_letter = teacher_data[1]
        else:
            class_number = teacher_data[0][:2]
            class_letter = teacher_data[1]

        # Получаем всех учеников
        with db_lock:
            cur.execute("""
                SELECT user_id FROM users 
                WHERE class_number = ? AND class_letter = ? AND user_id != ?
                """, (class_number, class_letter, teacher_id))
            students = cur.fetchall()

        if not students:
            bot.send_message(message.chat.id, "<b>ℹ️ В вашем классе нет других пользователей</b>", parse_mode='HTML')
            return
        confirmation_markup = types.InlineKeyboardMarkup(row_width=2)
        confirmation_markup.add(
                types.InlineKeyboardButton("✅ Отправить", callback_data=f"confirm_send:{message.message_id}"),
                types.InlineKeyboardButton("❌ Отменить", callback_data="cancel_send")
            )

        bot.send_message(
                chat_id=message.chat.id,
                text=f"<b>Пожалуйста подтвердите рассылку:\n Получателей в вашем классе: {len(students)}</b>",
                reply_markup=confirmation_markup,
                parse_mode="HTML"
            )
            
            # Сохраняем данные для подтверждения
        user_states[teacher_id] = {
                'text': teacher_text,
                'students': students,
                'original_message': message.message_id
            }
            
    except Exception as e:
        logger.error(e)
        bot.send_message(message.chat.id, "<b>❌ Произошла ошибка при обработке запроса</b>", parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_send:'))
def handle_confirmation(call):
    try:
        bot.answer_callback_query(call.id)
        
        # Извлекаем ID оригинального сообщения
        original_msg_id = int(call.data.split(':')[1])
        teacher_id = call.from_user.id
        
        # Получаем сохраненные данные
        teacher_data = user_states.get(teacher_id)
        if not teacher_data:
            bot.send_message(call.message.chat.id, "<b>❌ Данные для рассылки не найдены или устарели</b>", parse_mode='HTML')
            return
            
        teacher_text = teacher_data['text']
        students = teacher_data['students']
        
        # Удаляем сообщение с подтверждением
        bot.delete_message(call.message.chat.id, call.message.message_id)
        
        # Отправляем уведомление о начале рассылки
        progress_msg = bot.send_message(
            call.message.chat.id,
            f"<b>⏳ Начинаем рассылку для {len(students)} получателей...</b>",
            parse_mode='HTML'
        )
        
        # Рассылка сообщения
        success = 0
        failed = 0
        failed_users = []
        
        for student in students:
            try:
                student_id = student[0]
                bot.send_message(
                    chat_id=student_id,
                    text=f"<b>📩 Сообщение от классного руководителя\n\n{teacher_text}</b>",
                    parse_mode='HTML'
                )
                success += 1
                # Небольшая задержка, чтобы не превысить лимиты Telegram
                time.sleep(0.1)
            except Exception as e:
                failed += 1
                failed_users.append(student_id)
                logger.error(e)
        
        # Формируем отчет
        report = (
            f"✅ Рассылка завершена!\n\n"
            f"Успешно отправлено: {success}\n"
            f"Не удалось отправить: {failed}\n\n"
            f"Текст сообщения:\n{teacher_text}"
        )
        
        if failed > 0:
            report += f"Не удалось отправить следующим пользователям: {', '.join(map(str, failed_users))}"
        
        # Отправляем отчет и удаляем сообщение о прогрессе
        bot.delete_message(call.message.chat.id, progress_msg.message_id)
        bot.send_message(call.message.chat.id, f'<b>{report}</b>', parse_mode='HTML')
        
        # Очищаем сохраненные данные
        del user_states[teacher_id]
        
    except Exception as e:
        logging.error(f"Error in handle_confirmation: {e}")
        bot.send_message(call.message.chat.id, "<b>❌ Произошла ошибка при выполнении рассылки</b>", parse_mode='HTML')


@bot.message_handler(commands=["calendar"])
@check_registration
def calendar_func(message):
    photo_calendar = photo_calendar_dct["photo"]
    text_calendar = photo_calendar_dct['text'] 
    try:
        if photo_calendar is not None:
            bot.send_message(message.chat.id, f'<b>{text_calendar}</b>', parse_mode='HTML')
            bot.send_photo(message.chat.id, photo_calendar)
        else:
            bot.send_message(message.chat.id, '<b>Простите, но админ ещё не выложил ваше школьное расписание😄</b>', parse_mode='HTML')

    except Exception as e:
        logger.error(e)

@bot.message_handler(commands=['reg_calendar'])
def reg_calendar_func_calendar(message):
    if message.from_user.id == int(os.getenv("ADMIN_ID")):
        try:
            bot.send_message(message.chat.id, '<b>Пришлите изображение для расписания😀</b>', parse_mode='HTML')
            bot.register_next_step_handler(message, next_reg_calendar_func)
        except Exception as e:
            logger.error(e)
    else:
        bot.send_message(message.chat.id, '<b>У вас нет прав для выполнения этой команды😔</b>', parse_mode='HTML')
def next_reg_calendar_func(message):
    global photo_calendar_dct
    photo_message = message.photo[-1].file_id
    photo_calendar_dct['photo'] = photo_message
    bot.send_message(message.chat.id, 'Отлично! Теперь отправьте текст для расписания😊')
    bot.register_next_step_handler(message, next2_reg_calendar_func)
def next2_reg_calendar_func(message):
    photo_calendar_dct['text'] = message.text
    bot.send_message(message.chat.id, 'Расписание успешно обновилось✔')

@bot.message_handler(commands=['set_new_user'])
def func_set_new_user(message):
    bot.send_message(message.chat.id, '<b>Введите id ползователя которого хотите зарегистрировать😉</b>', parse_mode='HTML')
    bot.register_next_step_handler(message, user_func_set_new_user)

def user_func_set_new_user(message):
    pattern = r'^\d+$'
    if re.match(pattern, message.text):
        try:
            adminusers_insert_dct['user_id'] = int(message.text)
        except Exception as e:
            logger.error(e)
            bot.send_message(message.chat.id, '<b>Ошибка при обработке текста❌</b>', parse_mode='HTML')
            return
        bot.send_message(message.chat.id, '<b>Отлично! Теперь введите username пользователя☺</b>', parse_mode='HTML')
        bot.register_next_step_handler(message, username_func_set_new_user)
    else:
        bot.send_message(message.chat.id, '<b>Ошибка при обработке текста❌</b>', parse_mode='HTML')
        return
def username_func_set_new_user(message):
    try:
        adminusers_insert_dct['username'] = message.text
    except Exception as e:
        logger.error(e)
        bot.send_message(message.chat.id, '<b>Ошибка при обработке текста❌</b>', parse_mode='HTML')
        return
    bot.send_message(message.chat.id, '<b>Успешно! Теперь введите номер и букву класса</b>', parse_mode='HTML')
    bot.register_next_step_handler(message, class_func_set_new_user)

def class_func_set_new_user(message):
    pattern = r'^([5-9]|10|11) [АБВГД]$'
    if re.match(pattern, message.text):
        mas_class = message.text.split(' ')
        adminusers_insert_dct['class_number'] = mas_class[0] 
        adminusers_insert_dct['class_letter'] = mas_class[1]
        try:
            password = 'student'
            user_id = adminusers_insert_dct['user_id']
            username = adminusers_insert_dct['username']
            class_number = adminusers_insert_dct['class_number']
            class_letter = adminusers_insert_dct['class_letter']
            with db_lock:
                cur.execute("INSERT INTO users (user_id, username, password, class_number, class_letter) VALUES (?, ?, ?, ?, ?)", 
                        (user_id, username, password, class_number, class_letter))
                conn.commit()
        except Exception as e:
            logger.error(e)
            bot.send_message(message.chat.id, '<b>Не удалось добавить пользователя в базу данных❌</b>', parse_mode='HTML')
        user_info_cort =(user_id, username, password, class_number, class_letter)
        bot.send_message(message.chat.id, '<b>Вы успешно добавили нового пользователя❤</b>', parse_mode='HTML')
        logger.info(f"Пользователь зарегистрирован: {user_info_cort}")
        bot.send_message(user_id, '<b>Добро пожаловать в SchoolBot😉\nИспользуйте команду /help, чтобы узнать ваши возможнсти</b>', parse_mode='HTML')
    else:
        bot.send_message(message.chat.id, '<b>Ошибка при обработке текста❌</b>', parse_mode='HTML')
        return

def notify_all_users(message_text):
    stiker_id = "CAACAgIAAxkBAAEN0n9n5D7j7cx0oCTQgnooixX3UtWHXAACIQ0AAiWx6UpCBrcao52KeDYE"
    with db_lock:
        cur.execute("SELECT user_id FROM users")
        all_users = cur.fetchall()
    for user in all_users:
        try:
            bot.send_sticker(user[0], sticker=stiker_id)
            bot.send_message(user[0], message_text, parse_mode="HTML")
        except Exception as e:
            logger.error(e)
@bot.message_handler(commands=['del_user'])
def func_del_user(message):
    bot.send_message(message.chat.id, '<b>Введите id пользователя, которого хотите удалить из базы данных🔵\nЧтобы отменить дейстивие введите команду /back</b>', parse_mode="HTML")
    bot.register_next_step_handler(message, select_func_del_user)
def select_func_del_user(message):
    text = message.text
    if text == '/back':
        bot.send_message(message.chat.id, '<b>Удаление отменено! ✅</b>', parse_mode="HTML")
        return
    else:
        next_func_del_user(message=message, text=text)
def next_func_del_user(message, text):
    user_id = text
    try:
        
        with db_lock:
            cur.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            data_user = cur.fetchone()
        with db_lock:
            cur.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
            conn.commit()
    except Exception as e:
        logger.error(e)
        bot.send_message(message.chat.id, '<b>Ошибка при обработке запроса❌\nПопробуйте снова</b>', parse_mode="HTML")
        return
    bot.send_message(message.chat.id, '<b>Вы успешно удалили пользователя из базы данных✔</b>', parse_mode="HTML")
    logger.info(f'Пользователь {data_user} был удален')

@bot.message_handler(commands=['notify_schedule'])
def update_schedule(message):
    if message.from_user.id == int(os.getenv("ADMIN_ID")): #Это мой ID  
        notify_all_users("<b>Расписание было обновлено! Проверьте его с помощью команды /calendar</b>")
        logger.info("Расписание обновлено и уведомления отправлены")
    else:
        bot.send_message(message.chat.id, "<b>У вас нет прав для выполнения этой команды</b>", parse_mode="HTML")



@bot.callback_query_handler(func=lambda call: call.data == "math")
def call_math_query(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    button = types.InlineKeyboardButton("Прототипы вариантов", url="https://examer.ru/ege_po_matematike/teoriya")
    button2 = types.InlineKeyboardButton("Канал со всем материалом", url="https://t.me/pif112")
    button_back = types.InlineKeyboardButton("Вернуться назад🔄", callback_data="back_to_subjects")
    markup.add(button, button2)
    markup.add(button_back)

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Ниже представлены материалы, которые помогут подготовиться к математике🔢</b>",
        parse_mode="HTML",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data == "physics")
def call_physics_query(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    button = types.InlineKeyboardButton("Перейти👆", url="https://yandex.ru/tutor/subject/?subject_id=4")
    button_back = types.InlineKeyboardButton("Вернуться назад🔄", callback_data="back_to_subjects")
    markup.add(button)
    markup.add(button_back)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Нажмите на кнопку ниже, чтобы перейти на сайт с полезной теорией для подготовки к экзамену по физике🚗</b>",
        parse_mode="HTML",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "russian")
def call_russian_query(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    button = types.InlineKeyboardButton("Перейти👆", url="https://yandex.ru/tutor/subject/?subject_id=3")
    button_back = types.InlineKeyboardButton("Вернуться назад🔄", callback_data="back_to_subjects")
    markup.add(button)
    markup.add(button_back)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Нажмите на кнопку ниже, чтобы перейти на сайт с полезной теорией для подготовки к экзамену по русскому языку📒</b>",
        parse_mode="HTML",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "informatics")
def call_informatics_query(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    button = types.InlineKeyboardButton("Перейти👆", url="https://education.yandex.ru/ege?utm_source=repetitor")
    button_back = types.InlineKeyboardButton("Вернуться назад🔄", callback_data="back_to_subjects")
    markup.add(button)
    markup.add(button_back)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Нажмите на кнопку ниже, чтобы перейти на сайт с полезной теорией для подготовки к экзамену по информатике💻</b>",
        parse_mode="HTML",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "english")
def call_english_query(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    button = types.InlineKeyboardButton("Перейти👆", url="https://yandex.ru/tutor/subject/?subject_id=12")
    button_back = types.InlineKeyboardButton("Вернуться назад🔄", callback_data="back_to_subjects")
    markup.add(button)
    markup.add(button_back)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Нажмите на кнопку ниже, чтобы перейти на сайт с полезной теорией для подготовки к экзамену по английскому языку🗽</b>",
        parse_mode="HTML",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "chemistry")
def call_chemistry_query(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    button = types.InlineKeyboardButton("Перейти👆", url="https://chemege.ru/")
    button_back = types.InlineKeyboardButton("Вернуться назад🔄", callback_data="back_to_subjects")
    markup.add(button)
    markup.add(button_back)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Нажмите на кнопку ниже, чтобы перейти на сайт с полезной теорией для подготовки к экзамену по химии🧪</b>",
        parse_mode="HTML",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "biology")
def call_biology_query(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    button = types.InlineKeyboardButton("Перейти👆", url="https://yandex.ru/tutor/subject/?subject_id=8")
    button_back = types.InlineKeyboardButton("Вернуться назад🔄", callback_data="back_to_subjects")
    markup.add(button)
    markup.add(button_back)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Нажмите на кнопку ниже, чтобы перейти на сайт с полезной теорией для подготовки к экзамену по биологии🌼</b>",
        parse_mode="HTML",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "literature")
def call_literature_query(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    button = types.InlineKeyboardButton("Перейти👆", url="https://yandex.ru/tutor/subject/?subject_id=5")
    button_back = types.InlineKeyboardButton("Вернуться назад🔄", callback_data="back_to_subjects")
    markup.add(button)
    markup.add(button_back)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Нажмите на кнопку ниже, чтобы перейти на сайт с полезной теорией для подготовки к экзамену по литературе📚</b>",
        parse_mode="HTML",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "history")
def call_history_query(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    button = types.InlineKeyboardButton("Перейти👆", url="https://yandex.ru/tutor/subject/?subject_id=10")
    button_back = types.InlineKeyboardButton("Вернуться назад🔄", callback_data="back_to_subjects")
    markup.add(button)
    markup.add(button_back)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Нажмите на кнопку ниже, чтобы перейти на сайт с полезной теорией для подготовки к экзамену по истории🎭</b>",
        parse_mode="HTML",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "social_studies")
def call_social_studies_query(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    button = types.InlineKeyboardButton("Перейти👆", url="https://yandex.ru/tutor/subject/?subject_id=11")
    button_back = types.InlineKeyboardButton("Вернуться назад🔄", callback_data="back_to_subjects")
    markup.add(button)
    markup.add(button_back)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Нажмите на кнопку ниже, чтобы перейти на сайт с полезной теорией для подготовки к экзамену по обществознанию📕</b>",
        parse_mode="HTML",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data == "back_to_subjects")
def back_to_subjects(call):

    bot.answer_callback_query(call.id)

    markup = types.InlineKeyboardMarkup(row_width=2)
    
    btn_math = types.InlineKeyboardButton("Математика🔢", callback_data="math")
    btn_physics = types.InlineKeyboardButton("Физика🚗", callback_data="physics")
    btn_social_studies = types.InlineKeyboardButton("Обществознание📕", callback_data="social_studies")
    btn_history = types.InlineKeyboardButton("История🎭", callback_data="history")
    btn_literature = types.InlineKeyboardButton("Литература📚", callback_data="literature")
    btn_biology = types.InlineKeyboardButton("Биология🌼", callback_data="biology")
    btn_chemistry = types.InlineKeyboardButton("Химия🧪", callback_data="chemistry")
    btn_english = types.InlineKeyboardButton("Английский язык🗽", callback_data="english")
    btn_informatics = types.InlineKeyboardButton("Информатика💻", callback_data="informatics")
    btn_russian = types.InlineKeyboardButton("Русский язык📒", callback_data="russian")
    
    markup.add(
        btn_math, btn_physics, btn_social_studies, btn_history,
        btn_literature, btn_biology, btn_chemistry, btn_english,
        btn_informatics, btn_russian
    )

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Выберите предмет, который вас интересует:</b>",
        parse_mode="HTML",
        reply_markup=markup
    )



@bot.message_handler(commands=['list_users'])
def users_list_func(message):
    with db_lock:
        cur.execute("SELECT user_id, username, class_number, class_letter FROM users")
        list_users = cur.fetchall()

    if message.from_user.id == int(os.getenv("ADMIN_ID")):  # Проверка ID админа
        if not list_users:
            bot.send_message(message.chat.id, "<b>В базе данных нет зарегистрированных пользователей</b>", parse_mode="HTML")
            return
            
        user_list_message = "<b>Список зарегистрированных пользователей:</b>\n"
        for i, user in enumerate(list_users, start=1):
            user_id, username, class_num, class_letter = user
            username_display = f"{username}"
            class_info = f"{class_num}{class_letter}" if class_num and class_letter else "класс не указан"
            
            user_list_message += (
                f"{i}. ID: {user_id}\n"
                f"   Имя: {username_display}\n"
                f"   Класс: {class_info}\n\n"
            )
        
        bot.send_message(message.chat.id, f'<b>{user_list_message}</b>', parse_mode="HTML")
        logger.info("Админ бота только что посмотрел список зарегистрированных пользователей")
    else:
        bot.send_message(message.chat.id, "<b>У вас нет прав для выполнения этой команды</b>", parse_mode="HTML")

#Проверка существует ли пользователь
def is_user_registered(user_id):
    with db_lock:
        cur.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        result = cur.fetchone()
    if result is None:
        return False
    else:
        user_id, username, password, class_number, class_letter = result
        return user_id is not None and username is not None and password is not None and class_number is not None and class_letter is not None

# Удаление пользователя (выход)
def logout_user(user_id):
    with db_lock:
        cur.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        conn.commit()

# Команда /exit
@bot.message_handler(commands=['exit'])
@check_registration
def handle_exit(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_1 = types.InlineKeyboardButton("Удалить🗑", callback_data="delete_ak")
    btn_2 = types.InlineKeyboardButton("Назад🔄", callback_data="back_to_ak")
    markup.add(btn_1, btn_2)
    user_id = message.from_user.id 
    if is_user_registered(user_id):
        bot.send_message(message.chat.id, "<b>Вы собираетесь удалить аккаунт. Все ваши данные будут безвозвратно удалены. Подтвердите, пожалуйста, это действие.</b>", reply_markup=markup, parse_mode="HTML")
    else:
        bot.send_message(message.chat.id, "<b>❌Вы еще не зарегистрированы</b>", parse_mode="HTML") 


@bot.callback_query_handler(func=lambda call: call.data == 'delete_ak')
def delete_ak_func(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    with db_lock:
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        name = cur.fetchone()
    logout_user(user_id=user_id)
    logger.info(f"Пользователь с именем {name[1]} удалил аккаунт")
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Вы успешно удалили свой аккаунт</b>",
        parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_ak')
def back_to_ak_func(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>❌Действие отменено</b>",
        parse_mode="HTML"
    )

@bot.message_handler(commands=['support'])
def support_func(message):
    stiker = 'CAACAgIAAxkBAAEOTtNn-2p-u2EekVrh23Xeelu3bn08_gAC_xsAAtdYaUg5zhOM-zad9zYE'
    bot.send_sticker(
        chat_id=message.chat.id,
        sticker=stiker
    )

    bot.send_message(
        chat_id=message.chat.id,
        text='<b>Расскажите, пожалуйста, о возникшей сложности</b>\n\n'
                '<b>Мы сделаем всё возможное, чтобы помочь вам как можно скорее.</b>',
        parse_mode='HTML'
    )
    bot.register_next_step_handler(message, support_func_2)
def support_func_2(message):
    text_support = message.text
    admin_chat_id = int(os.getenv("ADMIN_ID"))
    try:
        if text_support in ("/start", "/clear", "/help", "/reference", "/exit", "/calendar", "/support", '/ask_anon', '/my_questions', '/send_class', '/del_user_elschool', '/elschool_marks'):
            bot.send_message(message.chat.id, '<b>Ой, что-то пошло не так!\nПожалуйста, проверьте правильность ввода и отправьте запрос заново</b>', parse_mode='HTML')
        else:
            bot.send_message(message.chat.id, '<b>Сообщение доставлено!\n</b>'
                            '<b>Администратор уже в курсе и скоро с вами свяжется. Спасибо!</b>', parse_mode='HTML')
            bot.send_message(
                chat_id=admin_chat_id,
                text=f'<b>📩 Сообщение от пользователя {message.from_user.first_name}\n\n</b>'
                    f'<b>ID пользователя: {message.chat.id}</b>\n'
                    f'<b>Текст сообщения: {text_support}</b>',
                parse_mode='HTML'
            )
            
    except Exception as e:
        logger.error(e)

@bot.message_handler(commands=['support_answer'])
def support_answer_func(message):
    try:
        if message.from_user.id == int(os.getenv("ADMIN_ID")):
            bot.send_message(
                chat_id=message.chat.id,
                text='<b>Добро пожаловать админ\n\n</b>'
                    '<b>Введите id пользователя которому хотите отправить сообщение</b>',
                parse_mode='HTML'
            )
            bot.register_next_step_handler(message, support_answer_func_2)
        else:
            bot.send_message(
                chat_id=message.chat.id,
                text='<b>У вас нет прав для выполнения этой команды😔</b>',
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(e)

def support_answer_func_2(message):
    try:
        admin_send_user = int(message.text)
        bot.send_message(
            chat_id=message.chat.id,
            text='<b>Отлично!\n\nТеперь отправьте сообщение которое хотите отправить пользователю</b>',
            parse_mode='HTML'
        )
        bot.register_next_step_handler(
            message,
            lambda msg: support_answer_func_3(message=msg, user_id=admin_send_user)
        )
    except Exception as e:
        bot.reply_to(message, '❌Ошибка при обработке текста')
        logger.error(e)

def support_answer_func_3(message, user_id):
    try:
        bot.send_message(
            chat_id=user_id,
            text=f"<b>📩 Сообщение от администратора:\n\n{message.text}</b>",
            parse_mode='HTML'
        )
        bot.reply_to(message, "✔ Сообщение отправлено!")
    except Exception as e:
        bot.reply_to(message, "❌Ошибка при отправке сообщения")
        logger.error(e)
@bot.message_handler(commands=['help'])
@check_registration
def main_help(message):
    user_id = message.from_user.id
    
    if user_id == int(os.getenv("ADMIN_ID")):
        help_text = """
    <b>Доступные команды для админа:</b>

    /start - Начать работу с ботом✨
    /clear - Очистить переписку🧹
    /help - Помощь и инструкции📚
    /reference - Учебные материалы🔍
    /calendar - Мое расписание📅
    /reg_calendar - Обновить школьное расписание🟢
    /support - Служба поддержки🆘
    /send_class - Отправить сообщение классу📩
    /my_questions - посмотреть ваши анонимные сообщения📨
    /elschool_marks - Узнать свои оценки📃
    /del_user_elschool - Удалить сохраненный аккаунт🗑
    /ask_anon - отправить анонимное сообщение учителю✉
    /exit - Выйти из системы🚪
    /set_new_user - Добавить нового учащегося➕
    /del_user - Удалить пользователя🗑
    /list_users - Просмотр списка пользователей👥 
    /notify_schedule - Рассылка уведомлений🔔 
    /support_answer - Ответы на обращения💬 
    """
    elif is_teacher(user_id):
        # Команды для учителей
        help_text = """
    <b>Доступные команды для учителей:</b>

    /start - Начать работу с ботом✨
    /clear - Очистить переписку🧹
    /help - Помощь и инструкции📚
    /reference - Учебные материалы🔍
    /calendar - Мое расписание📅
    /support - Служба поддержки🆘
    /send_class - Отправить сообщение классу📩
    /my_questions - посмотреть ваши анонимные сообщения📨
    /exit - Выйти из системы🚪
    """
    else:
        # Команды для учеников
        help_text = """
    <b>Доступные команды для учеников:</b>

    /start - Начать работу с ботом✨
    /clear - Очистить переписку🧹
    /help - Помощь и инструкции📚
    /reference - Учебные материалы🔍
    /calendar - Мое расписание📅
    /support - Служба поддержки🆘
    /elschool_marks - Узнать свои оценки📃
    /del_user_elschool - Удалить сохраненный аккаунт🗑
    /ask_anon - отправить анонимное сообщение учителю✉
    /exit - Выйти из системы🚪
    """
    bot.send_message(message.chat.id, help_text, parse_mode="HTML")


# Команда для отправки анонимного вопроса
@bot.message_handler(commands=['ask_anon'])
@check_registration
def ask_anon_question(message):
    if is_teacher(message.from_user.id):
        bot.send_message(message.chat.id, "<b>Эта функция доступна только ученикам.</b>", parse_mode="HTML")
        return
    
    # Получаем список учителей
    with db_lock:
        cur.execute("SELECT user_id, username FROM users WHERE class_number LIKE '%/_id' ESCAPE '/'")
        teachers = cur.fetchall()
    
    if not teachers:
        bot.send_message(message.chat.id, "<b>В системе нет зарегистрированных учителей.</b>", parse_mode="HTML")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for teacher in teachers:
        btn = types.InlineKeyboardButton(
            f"{teacher[1]}", 
            callback_data=f"select_teacher_{teacher[0]}"
        )
        markup.add(btn)
    
    bot.send_message(
        message.chat.id, 
        "<b>Выберите учителя, которому хотите отправить сообщение:</b>", 
        reply_markup=markup, 
        parse_mode="HTML"
    )

# Обработчик выбора учителя
@bot.callback_query_handler(func=lambda call: call.data.startswith('select_teacher_'))
def select_teacher(call):
    bot.answer_callback_query(call.id)
    teacher_id = int(call.data.split('_')[2])
    user_states[call.from_user.id] = {
        'state': 'waiting_anon_question',
        'teacher_id': teacher_id
    }
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Напишите ваш вопрос, и мы отправим его вашему учителю\n\nВопрос будет отправлен анонимно😉</b>",
        parse_mode="HTML"
    )

# Обработчик текста вопроса
@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'waiting_anon_question')
def process_anon_question(message):
    user_data = user_states[message.from_user.id]
    teacher_id = user_data['teacher_id']
    question_text = message.text
    
    # Сохраняем вопрос в базу
    with db_lock:
        cur.execute(
            "INSERT INTO anonymous_questions (from_user_id, to_teacher_id, question_text) VALUES (?, ?, ?)",
            (message.from_user.id, teacher_id, question_text)
        )
        conn.commit()
    
    # Отправляем уведомление учителю
    try:
        bot.send_message(
            teacher_id,
            f"<b>📨 У вас новое анонимное сообщение:</b>\n\n{question_text}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Не удалось отправить вопрос учителю: {e}")
    
    bot.send_message(
        message.chat.id,
        "<b>Ваше сообщение отправлено! Учитель уже получил ваше сообщение😊</b>",
        parse_mode="HTML"
    )
    
    user_states.pop(message.from_user.id, None)

# Команда для учителей - просмотр вопросов
@bot.message_handler(commands=['my_questions'])
def show_questions(message):
    if not is_teacher(message.from_user.id):
        bot.send_message(message.chat.id, "<b>Эта команда доступна только учителям.</b>", parse_mode="HTML")
        return
    with db_lock:
        cur.execute("""
            SELECT question_id, question_text, timestamp 
            FROM anonymous_questions 
            WHERE to_teacher_id = ? AND is_answered = 0
            ORDER BY timestamp DESC
        """, (message.from_user.id,))
        
        questions = cur.fetchall()
    
    if not questions:
        bot.send_message(message.chat.id, "<b>У вас нет новых сообщений</b>", parse_mode="HTML")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for number, q in enumerate(questions):
        btn = types.InlineKeyboardButton(
            f"Вопрос 🔹{number + 1} ({q[2][:10]})",
            callback_data=f"view_question_{q[0]}_{number + 1}"
        )
        markup.add(btn)
    
    bot.send_message(
        message.chat.id,
        "<b>У вас есть непрочитанные сообщения:</b>",
        reply_markup=markup,
        parse_mode="HTML"
    )

# Просмотр конкретного вопроса
@bot.callback_query_handler(func=lambda call: call.data.startswith('view_question_'))
def view_question(call):
    question_id = int(call.data.split('_')[2])
    question_number = int(call.data.split('_')[3])
    with db_lock:
        cur.execute("""
            SELECT question_text, timestamp 
            FROM anonymous_questions 
            WHERE question_id = ?
        """, (question_id,))
        
        question = cur.fetchone()
    
    if not question:
        bot.answer_callback_query(call.id, "Вопрос не найден")
        return
    
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    answer_btn = types.InlineKeyboardButton(
        "Ответить ✏️", 
        callback_data=f"answer_question_{question_id}"
    )
    markup.add(answer_btn)

    date_time_str = question[1][:16]

    dt = datetime.strptime(date_time_str, '%Y-%m-%d %H:%M')

    new_dt = dt + timedelta(hours=5)

    new_date_time_str = new_dt.strftime('%Y-%m-%d %H:%M')

    bot.edit_message_text( 
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"<b>Вопрос 🔹{question_number}:</b>\n\n{question[0]}\n\n<i>{new_date_time_str}</i>",
        reply_markup=markup,
        parse_mode="HTML"
    )

# Ответ на вопрос
@bot.callback_query_handler(func=lambda call: call.data.startswith('answer_question_'))
def answer_question(call):
    bot.answer_callback_query(call.id)

    question_id = int(call.data.split('_')[2])
    user_states[call.from_user.id] = {
        'state': 'waiting_answer',
        'question_id': question_id
    }
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Напишите ваш ответ на это сообщение:</b>",
        parse_mode="HTML"
    )

# Обработчик ответа
@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'waiting_answer')
def process_answer(message):
    user_data = user_states[message.from_user.id]
    question_id = user_data['question_id']
    answer_text = message.text
    
    # Получаем информацию о вопросе
    with db_lock:
        cur.execute("""
            SELECT from_user_id, question_text 
            FROM anonymous_questions 
            WHERE question_id = ?
        """, (question_id,))
        
        question = cur.fetchone()
    
    if not question:
        bot.send_message(message.chat.id, "<b>Вопрос не найден.</b>", parse_mode="HTML")
        user_states.pop(message.from_user.id, None)
        return
    
    # Обновляем запись в базе
    with db_lock:
        cur.execute("""
            UPDATE anonymous_questions 
            SET is_answered = 1, answer_text = ? 
            WHERE question_id = ?
        """, (answer_text, question_id))
        conn.commit()
    
    # Отправляем ответ ученику
    try:
        bot.send_message(
            question[0],
            f"<b>📩 Ответ на ваш анонимный вопрос:</b>\n\n"
            f"<b>Ваш вопрос: {question[1]}</b>\n\n"
            f"<b>Ответ: {answer_text}</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Не удалось отправить ответ ученику: {e}")
    
    bot.send_message(
        message.chat.id,
        "<b>Ваш ответ был отправлен ученику!</b>",
        parse_mode="HTML"
    )
    
    user_states.pop(message.from_user.id, None)
@bot.message_handler(commands=['elschool_marks'])
@check_registration
def elschool_marks_function(message):
    if is_teacher(message.from_user.id):
        bot.send_message(
            chat_id=message.chat.id,
            text='<b>Эта команда доступна только ученикам😊</b>',
            parse_mode='HTML'
            )
        return
    with db_lock:
        cur.execute('SELECT * FROM elschool_data WHERE user_id = ?', (message.from_user.id,))
        user_info = cur.fetchone()
    if not user_info:
        bot.send_message(
            chat_id=message.chat.id,
            text='<b>Добро пожаловать с помощью этой команды вы можете узнавать свои оценки из электронного журнала elshool✨\n\nВведите логин от вашего электронного дневника✍</b>',
            parse_mode='HTML'
            )
        bot.register_next_step_handler(message, register_login_elschool)
    else:
        if message.from_user.id in search_data:
            del search_data[message.from_user.id]

        mes_mark = bot.send_message(
            chat_id=message.chat.id,
            text='<b>🔄Подождите немного, запрос обрабатывается...</b>',
            parse_mode='HTML'
            )
        with db_lock:
            cur.execute('SELECT * FROM elschool_data WHERE user_id = ?', (message.from_user.id,))
        user_info = cur.fetchone()
        user_data = {
            'login': user_info[1],
            'password': user_info[2]
        }
        username = user_info[0]
        login_url = 'https://elschool.ru/Logon/Index'
        session = requests.Session()
        headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        try:
            #1 Вход пользователя
            login_response = session.post(login_url, data=user_data, headers=headers)
            login_response.raise_for_status()

            # 2. Проверяем, куда нас перенаправило после авторизации
            if login_response.history:
                logger.info(f"Перенаправление после входа на: {login_response.url}")
            
            # 3. Получаем главную страницу личного кабинета
            cabinet_response = session.get(login_response.url, headers=headers)
            cabinet_soup = BS(cabinet_response.text, 'html.parser')
            
            # 4. Ищем ссылку на страницу с оценками
            grades_link = cabinet_soup.find('a', href=re.compile(r'/users/diaries'))
            if grades_link:
                grades_url = grades_link['href']
                if not grades_url.startswith('http'):
                    grades_url = f"https://elschool.ru{grades_link['href']}"
                logger.info(f"Найдена ссылка на оценки: {grades_url}")
            else:
                logger.error("Не удалось найти ссылку на страницу с оценками")
            
            
            cabinet_response_2 = session.get(grades_url, headers=headers)
            cabinet_response_2.raise_for_status()

            cabinet_soup_2 = BS(cabinet_response_2.text, 'html.parser')

            grades_link_2 = cabinet_soup_2.find('a', string=lambda x: x and 'табель' == x.lower())

            if grades_link_2:
                grades_url_2 = grades_link_2['href']
                if not grades_url_2.startswith('http'):
                    grades_url_2 = f'https://elschool.ru/users/diaries/{grades_link_2['href']}'
                logger.info(f"Найдена ссылка на оценки: {grades_url_2}")
            else:
                logger.error('Не удалось найти ссылку на страницу с оценками')

            response = session.get(grades_url_2, headers=headers)
            response.raise_for_status()


            soup = BS(response.text, 'html.parser')

            subject_rows = soup.find_all('tr', attrs={'lesson': True})

            if not subject_rows:
                logger.info("Не найдено ни одного предмета. Проверьте HTML-структуру.")
            
            # Определяем количество периодов по количеству столбцов с оценками
            first_row = subject_rows[0]
            grade_columns = first_row.find_all('td', class_=lambda x: x and 'grades-marks' in x)
            num_periods = len(grade_columns)
            
            # Инициализация структуры данных
            if username not in search_data:
                search_data[username] = {str(i): {} for i in range(1, num_periods + 1)}
            
            for row in subject_rows:
                subject_element = row.find('td', class_='grades-lesson')
                if not subject_element:
                    continue
            
                subject = subject_element.text.strip()
                grade_cells = row.find_all('td', class_=lambda x: x and 'grades-marks' in x)
                
                for period_num, grade_cell in enumerate(grade_cells, 1):
                    current_period = str(period_num)
                    
                    # Проверка на случай расхождений в количестве столбцов
                    if current_period not in search_data[username]:
                        logger.warning(f"Обнаружен избыточный оценочный период {current_period}")
                        continue
                        
                    if subject not in search_data[username][current_period]:
                        search_data[username][current_period][subject] = []
                    
                    marks = grade_cell.find_all('span', class_="mark-span")
                    if not marks:
                        # Удаляем предмет из периода, если оценок нет
                        if subject in search_data[username][current_period]:
                            del search_data[username][current_period][subject]
                        continue
                    
                    for mark in marks:
                        grade = mark.text.strip()
                        search_data[username][current_period][subject].append(grade)

            markup = types.InlineKeyboardMarkup(row_width=2)
            if num_periods == 2:
                btn_1 = types.InlineKeyboardButton("1️⃣ Первое полугодие", callback_data='first_half_year')
                btn_2 = types.InlineKeyboardButton("2️⃣ Второе полугодие", callback_data='second_half_year')
                markup.add(btn_1, btn_2) 
            else:
                btn_1 = types.InlineKeyboardButton("1️⃣Первая четверть", callback_data='first_half_year')
                btn_2 = types.InlineKeyboardButton("2️⃣Вторая четверть", callback_data='second_half_year')
                btn_3 = types.InlineKeyboardButton("3️⃣Третья четверть", callback_data='third_half_year')
                btn_4 = types.InlineKeyboardButton("4️⃣Четвертая четверть", callback_data='fourth_half_year')
                markup.add(btn_1, btn_2, btn_3, btn_4)

            bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=mes_mark.message_id,
            text=f'<b>📚 Выберите полугодие для просмотра оценок:</b>',
            parse_mode='HTML',
            reply_markup=markup
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при выполнении запроса: {e}")
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=mes_mark.message_id,
                text=f'<b>Ошибка при выполнении запроса на elschool</b>',
                parse_mode='HTML'
                )
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP ошибка: {e}")
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=mes_mark.message_id,
                text=f'<b>Ошибка при выполнении запроса на elschool</b>',
                parse_mode='HTML'
                )
        except requests.exceptions.ConnectionError:
            logger.error("Проблемы с соединением")
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=mes_mark.message_id,
                text=f'<b>Ошибка!\nПроблемы с соединением</b>',
                parse_mode='HTML'
                )
        except ValueError as e:
            logger.error(f"Ошибка данных: {e}")
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=mes_mark.message_id,
                text='<b>Ошибка данных</b>',
                parse_mode='HTML'
                )
        except Exception as e:
            logger.error(f"Произошла ошибка: {e}")
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=mes_mark.message_id,
                text='<b>Ошибка при попытке получить ваши оценки на elschool</b>',
                parse_mode='HTML'
                )
def register_login_elschool(message):
    login_user = message.text
    if login_user in ("/start", "/clear", "/help", "/reference", "/exit", "/calendar", "/support", '/ask_anon', '/my_questions', '/send_class', '/del_user_elschool', '/elschool_marks'):
        bot.send_message(message.chat.id, '<b>Ошибка при обработке текста❌</b>', parse_mode='HTML')
        return
    bot.send_message(
        chat_id=message.chat.id,
        text='<b>Отлично😃!\n\nТеперь введите ваш пароль от вашего электронного дневника</b>',
        parse_mode='HTML'
        )
    bot.register_next_step_handler(message, lambda msg: register_password_elschool(msg, login_user))

def register_password_elschool(message, login):
    login_url = 'https://elschool.ru/Logon/Index'

    session = requests.Session()

    headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    password_user = message.text
    user_data = {
        'login': login,
        'password': password_user
        }
    check_register = bot.send_message(
        chat_id=message.chat.id,
        text='<b>🔄Подождите немного, мы проверяем ваши данные...</b>',
        parse_mode='HTML'
        )
    try:
        login_response = session.post(login_url, data=user_data, headers=headers)
        login_response.raise_for_status()

        if login_response.history:
            logger.info(f"Перенаправление после входа на: {login_response.url}")

        cabinet_response = session.get(login_response.url, headers=headers)
        cabinet_soup = BS(cabinet_response.text, 'html.parser')
        
        grades_link = cabinet_soup.find('a', href=re.compile(r'/users/diaries'))
        if grades_link:
            grades_url = grades_link['href']
            if not grades_url.startswith('http'):
                grades_url = f"https://elschool.ru{grades_link['href']}"
            logger.info(f"Найдена ссылка на оценки: {grades_url}")
        else:
            logger.error("Не удалось найти ссылку на страницу с оценками")
            raise Exception("Ссылка на оценки не найдена в HTML-структуре")
        with db_lock:
            cur.execute(
                "INSERT INTO elschool_data (user_id, login_user, password_user) VALUES (?, ?, ?)",
                (message.from_user.id, login, password_user)
                )

            conn.commit()

        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=check_register.message_id,
            text='<b>✔Вы успешно зарегистрировались!\n\nЧтобы узнать свои оценки, воспользуйтесь командой\n/elschool_marks</b>',
            parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f'Ошибка при входе регистрации пользователя {e}')
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=check_register.message_id,
            text='<b>❌Ошибка при регистрации\nПопробуйте войти снова</b>',
            parse_mode='HTML'
            )
@bot.message_handler(commands=['del_user_elschool'])
def del_elschool_user_func(message):
    with db_lock:
        cur.execute('SELECT * FROM elschool_data WHERE user_id = ?', (message.from_user.id,))
    user_info = cur.fetchone()
    if not user_info:
        bot.send_message(
            chat_id=message.chat.id,
            text='<b>❌Вы еще не привязали аккаунт elschool</b>',
            parse_mode='HTML'
            )
    else:
        markup = types.InlineKeyboardMarkup(row_width=1)
        btn_1 = types.InlineKeyboardButton("Удалить🗑", callback_data="delete_el")
        btn_2 = types.InlineKeyboardButton("Назад🔄", callback_data="back_to_el")
        markup.add(btn_1, btn_2)
        bot.send_message(
            chat_id=message.chat.id,
            text='<b>Вы уверены, что хотите удалить привязанный аккаунт elschool</b>',
            parse_mode='HTML',
            reply_markup=markup
            )
@bot.callback_query_handler(func=lambda call: call.data == 'delete_el')
def delete_el_func(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    with db_lock:
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    name = cur.fetchone()
    with db_lock:
        cur.execute('DELETE FROM elschool_data WHERE user_id = ?', (user_id,))
        conn.commit()

    logger.info(f"Пользователь {name} отвязал аккаунт elschool")
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Вы успешно отвязали аккаунт elschool</b>",
        parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data == 'first_half_year' or call.data == 'second_half_year' or call.data == 'third_half_year' or call.data == 'fourth_half_year')
def send_marks_for_hight_class(call):
    try:
        bot.answer_callback_query(call.id)
        user_id = call.from_user.id
        markup = types.InlineKeyboardMarkup(row_width=2)

        if call.data == 'first_half_year':
            semester = '1'
        elif call.data == 'second_half_year':
            semester = '2'
        elif call.data == 'third_half_year':
            semester = '3'
        else:
            semester = '4'

        items = list(search_data[user_id][semester].items())

        # Группируем кнопки по 2 в строке
        for i in range(0, len(items), 2):
            row_buttons = []
            for number, item in enumerate(items[i:i+2], i):
                subject, mark = item
                mark_str = ''.join(mark)
                btn = types.InlineKeyboardButton(
                    text=f"🔹{subject}",
                    callback_data=f"sjk_{number}_{mark_str}_{semester}"
                )
                row_buttons.append(btn)
            markup.row(*row_buttons)

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="<b>📚 Выберите предмет, по которому хотите узнать оценки:</b>",
            parse_mode="HTML",
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Ошибка в send_marks_for_hight_class: {e}")
        bot.answer_callback_query(call.id, "⚠️ Произошла ошибка", show_alert=True)
@bot.callback_query_handler(func=lambda call: call.data.startswith('sjk'))
def send_mark_hight_class_func(call):
    try:
        bot.answer_callback_query(call.id)
        call_info = call.data.split('_')
        number = int(call_info[1])
        mark = call_info[2]
        semester = call_info[3]
        item = list(search_data[call.from_user.id].get(str(semester)).items())
        subject = item[number][0]
        if semester == '1':
            back_call = 'first_half_year'
        elif semester == '2':
            back_call = 'second_half_year'
        elif semester == '3':
            back_call = 'third_half_year'
        else:
            back_call = 'fourth_half_year'
        markup = types.InlineKeyboardMarkup(row_width=1)
        btn_1 = types.InlineKeyboardButton('🔢Средний балл', callback_data=f'avrgmrk_{number}_{mark}_{semester}')
        btn_2 = types.InlineKeyboardButton('🔄Назад', callback_data=back_call)
        markup.add(btn_1, btn_2)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"<b>📖 Предмет: {subject}\n⭐ Оценки: {mark}</b>",
            parse_mode="HTML",
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Ошибка в send_mark_hight_class_func: {e}")
        bot.answer_callback_query(call.id, "⚠️ Произошла ошибка", show_alert=True)
@bot.callback_query_handler(func=lambda call: call.data.startswith('avrgmrk'))
def average_mark_func(call):
    bot.answer_callback_query(call.id)
    call_info = call.data.split('_')
    number = int(call_info[1])
    mark = call_info[2]
    semester = call_info[3]
    item = list(search_data[call.from_user.id].get(str(semester)).items())
    subject = item[number][0]
    sum = 0
    for i in str(mark):
        sum += int(i)
    
    average = sum / len(str(mark))
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn = types.InlineKeyboardButton('🔄Назад', callback_data=f"sjk_{number}_{mark}_{semester}")
    markup.add(btn)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"<b>📖 Предмет: {subject}\n⭐ Средний балл: {str(average)[:4]}</b>",
        parse_mode="HTML",
        reply_markup=markup
            )
@bot.callback_query_handler(func=lambda call: call.data == 'back_to_el')
def back_to_el_func(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>❌Действие отменено</b>",
        parse_mode="HTML"
    )
@bot.message_handler()
def info_for_str(message):
    if type(message.text.lower()) == str:
        bot.send_message(message.chat.id, '<b>Упс, не понимаю что ты написал😥</b>', parse_mode='HTML')


while True:
    try:
        bot.polling(none_stop=True, skip_pending=True)
    except Exception as e:
        logger.error(e)
