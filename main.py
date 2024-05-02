import telebot
from telebot import types
import datetime
import time
import threading
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
import os

# Получаем значение переменной среды TELEGRAM_TOKEN

# Настройка базы данных
engine = create_engine('sqlite:///bot.db')
Base = declarative_base()

# Определение таблицы пользователей
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, unique=True)
    tasks = relationship("Task", back_populates="user")

# Определение таблицы задач
class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    text = Column(String)
    reminder_time = Column(DateTime, nullable=True)
    reminder_set = Column(Boolean, default=False)
    reminder_sent = Column(Boolean, default=False)
    user = relationship("User", back_populates="tasks")

# Создание таблиц, если они еще не существуют
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

# Настройка бота
TOKEN = os.environ.get('TELEGRAM_TOKEN')
bot = telebot.TeleBot(TOKEN)


def create_keyboard():
    keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    buttons = ["Новая задача", "Список задач", "Удалить все", "Удалить задачу", "Помощь", "Установить время"]
    keyboard.add(*buttons)
    return keyboard

def ensure_user_registered(message):
    chat_id = message.chat.id
    user = session.query(User).filter_by(chat_id=chat_id).first()
    if not user:
        user = User(chat_id=chat_id)
        session.add(user)
        session.commit()
    return user

@bot.message_handler(func=lambda message: True)
def handle_commands(message):
    user = ensure_user_registered(message)
    text = message.text
    if text == "Новая задача":
        new_task(message)
    elif text == "Список задач":
        list_tasks(message)
    elif text == "Удалить все":
        confirm_removal_all(message)
    elif text == "Удалить задачу":
        delete_task(message)
    elif text == "Установить время":
        set_time(message)
    elif text == "Помощь":
        bot.send_message(message.chat.id, "Это бот для управления задачами и установки напоминаний. Используйте интерактивную клавиатуру для управления задачами.", reply_markup=create_keyboard())
    else:
        bot.send_message(message.chat.id, "Неизвестная команда, используйте клавиатуру.", reply_markup=create_keyboard())

def new_task(message):
    msg = bot.send_message(message.chat.id, "Введите текст задачи:")
    bot.register_next_step_handler(msg, add_task)

def add_task(message):
    chat_id = message.chat.id
    user = session.query(User).filter_by(chat_id=chat_id).first()
    new_task = Task(text=message.text, user=user)
    session.add(new_task)
    session.commit()
    bot.send_message(chat_id, "Задача добавлена!", reply_markup=create_keyboard())

def list_tasks(message):
    chat_id = message.chat.id
    user = session.query(User).filter_by(chat_id=chat_id).first()
    if user.tasks:
        response = ''
        for idx, task in enumerate(user.tasks):
            if task.reminder_set:
                reminder_time = task.reminder_time.strftime('%Y-%m-%d %H:%M')
                response += f"{idx + 1}. {task.text} (Когда: {reminder_time})\n"
            else:
                response += f"{idx + 1}. {task.text}\n"
        bot.send_message(chat_id, f"Ваши задачи:\n{response}", reply_markup=create_keyboard())
    else:
        bot.send_message(chat_id, "У вас пока нет задач.", reply_markup=create_keyboard())

def confirm_removal_all(message):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("Да, удалить все", callback_data="confirm_delete_all"))
    keyboard.add(types.InlineKeyboardButton("Нет, оставить", callback_data="cancel_delete_all"))
    bot.send_message(message.chat.id, "Вы уверены, что хотите удалить все задачи?", reply_markup=keyboard)

def delete_task(message):
    chat_id = message.chat.id
    user = session.query(User).filter_by(chat_id=chat_id).first()
    if not user.tasks:
        bot.send_message(chat_id, "У вас нет задач для удаления.")
        return
    keyboard = types.InlineKeyboardMarkup()
    for idx, task in enumerate(user.tasks):
        button = types.InlineKeyboardButton(task.text, callback_data=f'delete_task_{task.id}')
        keyboard.add(button)
    bot.send_message(chat_id, "Выберите задачу для удаления:", reply_markup=keyboard)

def set_time(message):
    chat_id = message.chat.id
    user = session.query(User).filter_by(chat_id=chat_id).first()
    if not user.tasks:
        bot.send_message(chat_id, "У вас нет задач для установки времени.")
        return
    keyboard = types.InlineKeyboardMarkup()
    for idx, task in enumerate(user.tasks):
        button = types.InlineKeyboardButton(task.text, callback_data=f'set_time_{task.id}')
        keyboard.add(button)
    bot.send_message(chat_id, "Выберите задачу для установки времени:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    data = call.data
    if data == "confirm_delete_all":
        delete_all_tasks(call.message)
        bot.answer_callback_query(call.id, "Все задачи удалены")
    elif data == "cancel_delete_all":
        bot.answer_callback_query(call.id, "Удаление отменено")
        bot.edit_message_text("Удаление всех задач отменено.", call.message.chat.id, call.message.message_id)
    elif data.startswith('delete_task_'):
        task_id = int(data.split('_')[-1])
        delete_specific_task(call, task_id)
    elif data.startswith('set_time_'):
        task_id = int(data.split('_')[-1])
        request_time(call, task_id)

def delete_specific_task(call, task_id):
    task = session.query(Task).filter_by(id=task_id).first()
    if task:
        session.delete(task)
        session.commit()
        bot.answer_callback_query(call.id, "Задача удалена")
        list_tasks(call.message)
    else:
        bot.answer_callback_query(call.id, "Задача не найдена")

def request_time(call, task_id):
    msg = bot.send_message(call.message.chat.id, "Введите время для задачи в формате ГГГГ-ММ-ДД ЧЧ:ММ:")
    bot.register_next_step_handler(msg, lambda message: set_reminder_time(message, task_id))

def set_reminder_time(message, task_id):
    try:
        reminder_time = datetime.datetime.strptime(message.text, '%Y-%m-%d %H:%M')
        if reminder_time < datetime.datetime.now():
            bot.send_message(message.chat.id, "Нельзя установить время в прошлом. Пожалуйста, введите корректное время.")
            return
        task = session.query(Task).filter_by(id=task_id).first()
        if task:
            task.reminder_time = reminder_time
            task.reminder_set = True
            task.reminder_sent = False
            session.commit()
            bot.send_message(message.chat.id, "Время установлено.")
            list_tasks(message)
        else:
            bot.send_message(message.chat.id, "Задача не найдена.")
    except ValueError:
        bot.send_message(message.chat.id, "Неправильный формат времени. Используйте формат ГГГГ-ММ-ДД ЧЧ:ММ.")

def delete_all_tasks(message):
    chat_id = message.chat.id
    user = session.query(User).filter_by(chat_id=chat_id).first()
    for task in user.tasks:
        session.delete(task)
    session.commit()
    bot.send_message(chat_id, "Все задачи удалены.", reply_markup=create_keyboard())

def periodic_notification_check():
    while True:
        now = datetime.datetime.now()
        tasks_to_notify = session.query(Task).filter(Task.reminder_set == True, Task.reminder_sent == False, Task.reminder_time <= now).all()
        for task in tasks_to_notify:
            if task.reminder_time + datetime.timedelta(minutes=2) > now:
                bot.send_message(task.user.chat_id, f"Напоминание: {task.text}")
                task.reminder_sent = True
                session.commit()
        time.sleep(60)

if __name__ == "__main__":
    print("Tasks tg bot v1.0 is started")
    notification_thread = threading.Thread(target=periodic_notification_check)
    notification_thread.start()
    try:
        bot.polling()
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        time.sleep(10)