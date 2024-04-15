from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import telebot
from telebot import types
import os
from secrets_1 import TOKEN

# Проверка наличия файла базы данных и создание нового, если файл отсутствует
DB_PATH = 'users.db'
if not os.path.exists(DB_PATH):
    open(DB_PATH, 'a').close()

# Настройка базы данных
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, unique=True)
    first_name = Column(String)
    username = Column(String)
    task_index = Column(Integer, default=1)  # Начальный индекс задач
    tasks = relationship('Task', back_populates='user', cascade="all, delete-orphan")

class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    local_id = Column(Integer)  # Локальный ID для удобства пользователя
    text = Column(String)
    reminder_time = Column(DateTime, nullable=True)  # Время напоминания
    reminder_set = Column(Boolean, default=False)  # Флаг установленного напоминания
    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship('User', back_populates='tasks')

engine = create_engine(f'sqlite:///{DB_PATH}', echo=True)
Base.metadata.create_all(engine, checkfirst=True)  # Создание таблиц, если их нет
Session = sessionmaker(bind=engine)
session = Session()


bot = telebot.TeleBot(TOKEN)
expecting_task = {}

def create_keyboard():
    keyboard = types.ReplyKeyboardMarkup(row_width=2)
    commands = ['/new_task Новая задача', '/tasks Список задач', '/rmtasks Удалить все', '/rmtask Удалить задачу', '/help Помощь']
    buttons = [types.KeyboardButton(command) for command in commands]
    keyboard.add(*buttons)
    return keyboard

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    user = session.query(User).filter_by(chat_id=chat_id).first()
    if not user:
        new_user = User(chat_id=chat_id, first_name=message.chat.first_name, username=message.chat.username)
        session.add(new_user)
        session.commit()
        bot.reply_to(message, "Теперь ты зарегистрирован! Используй команды для управления задачами.", reply_markup=create_keyboard())
    else:
        bot.reply_to(message, "Ты уже зарегистрирован." + get_commands_list(), reply_markup=create_keyboard())

@bot.message_handler(commands=['help'])
def send_help(message):
    bot.reply_to(message, get_commands_list(), reply_markup=create_keyboard())

@bot.message_handler(commands=['new_task'])
def new_task(message):
    chat_id = message.chat.id
    user = session.query(User).filter_by(chat_id=chat_id).first()
    if user:
        expecting_task[chat_id] = True
        bot.reply_to(message, "Отправь мне текст задачи:", reply_markup=create_keyboard())
    else:
        bot.reply_to(message, "Вы не зарегистрированы в системе. Используйте /start для регистрации.", reply_markup=create_keyboard())

@bot.message_handler(func=lambda message: message.chat.id in expecting_task and expecting_task[message.chat.id])
def add_task(message):
    chat_id = message.chat.id
    user = session.query(User).filter_by(chat_id=chat_id).first()
    if user:
        new_task_text = message.text
        new_task = Task(text=new_task_text, user=user, local_id=user.task_index)
        session.add(new_task)
        session.commit()

        # Полностью обновляем нумерацию всех задач
        for index, task in enumerate(sorted(user.tasks, key=lambda x: x.local_id), start=1):
            task.local_id = index
        session.commit()

        user.task_index += 1  # Увеличиваем индекс следующей задачи
        del expecting_task[chat_id]
        bot.reply_to(message, f"Задача добавлена: {new_task_text}", reply_markup=create_keyboard())
    else:
        bot.reply_to(message, "Произошла ошибка, возможно, вы не зарегистрированы.", reply_markup=create_keyboard())

@bot.message_handler(commands=['tasks'])
def show_tasks(message):
    chat_id = message.chat.id
    user = session.query(User).filter_by(chat_id=chat_id).first()
    if user:
        tasks = user.tasks
        if tasks:
            reply = ""
            for task in tasks:
                reply += f"{task.local_id}. {task.text}\n"
        else:
            reply = "Список задач пуст."
        bot.reply_to(message, reply, reply_markup=create_keyboard())
    else:
        bot.reply_to(message, "Вы не зарегистрированы в системе.", reply_markup=create_keyboard())

@bot.message_handler(commands=['rmtasks'])
def remove_tasks(message):
    chat_id = message.chat.id
    user = session.query(User).filter_by(chat_id=chat_id).first()
    if user:
        bot.send_message(chat_id, "Вы уверены, что хотите удалить все ваши задачи? (ответьте '1' для подтверждения)", reply_markup=create_keyboard())
        bot.register_next_step_handler(message, process_task_removal_confirmation, user)
    else:
        bot.reply_to(message, "Вы не зарегистрированы в системе.", reply_markup=create_keyboard())

def process_task_removal_confirmation(message, user):
    if message.text == '1':
        user.tasks = []  # Удаляем все задачи пользователя
        user.task_index = 1  # Сброс индекса задач
        session.commit()
        bot.reply_to(message, "Все ваши задачи удалены.", reply_markup=create_keyboard())
    else:
        bot.reply_to(message, "Операция отменена.", reply_markup=create_keyboard())

@bot.message_handler(commands=['rmtask'])
def remove_task(message):
    chat_id = message.chat.id
    user = session.query(User).filter_by(chat_id=chat_id).first()
    if user:
        bot.send_message(chat_id, "Введите номер задачи для удаления:", reply_markup=create_keyboard())
        bot.register_next_step_handler(message, process_task_removal_input, user)
    else:
        bot.reply_to(message, "Вы не зарегистрированы в системе.", reply_markup=create_keyboard())

def process_task_removal_input(message, user):
    try:
        task_id = int(message.text)
        task = next((task for task in user.tasks if task.local_id == task_id), None)
        if task:
            session.delete(task)
            session.commit()
            # Обновляем номера всех оставшихся задач
            for index, task in enumerate(sorted(user.tasks, key=lambda x: x.local_id), start=1):
                task.local_id = index
            session.commit()
            bot.reply_to(message, f"Задача {task_id} удалена.", reply_markup=create_keyboard())
        else:
            bot.reply_to(message, f"Задача с номером {task_id} не найдена.", reply_markup=create_keyboard())
    except ValueError:
        bot.reply_to(message, "Неправильный формат номера задачи. Пожалуйста, введите число.", reply_markup=create_keyboard())

@bot.message_handler(func=lambda message: True)
def handle_unregistered_command(message):
    bot.reply_to(message, "Неправильная команда. " + get_commands_list(), reply_markup=create_keyboard())

def get_commands_list():
    return "Доступные команды:\n/new_task - Новая задача\n/tasks - Список задач\n/rmtasks - Удалить все\n/rmtask - Удалить задачу\n/help - Помощь"

bot.polling()
