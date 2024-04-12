from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import telebot
from secrets_1 import TOKEN

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
    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship('User', back_populates='tasks')

engine = create_engine('sqlite:///users.db', echo=True)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()


bot = telebot.TeleBot(TOKEN)
expecting_task = {}

def get_commands_list():
    return """
    Вот список доступных команд:
    /start - Регистрация в системе и приветственное сообщение
    /new_task - Добавить новую задачу
    /tasks - Показать все ваши задачи
    /rmtasks - Удалить все ваши задачи
    /rmtask - Удалить конкретную задачу по номеру
    /help - Показать этот список команд
    """

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    user = session.query(User).filter_by(chat_id=chat_id).first()
    if not user:
        new_user = User(chat_id=chat_id, first_name=message.chat.first_name, username=message.chat.username)
        session.add(new_user)
        session.commit()
        bot.reply_to(message, "Теперь ты зарегистрирован! Используй команды для управления задачами." + get_commands_list())
    else:
        bot.reply_to(message, "Ты уже зарегистрирован." + get_commands_list())

@bot.message_handler(commands=['help'])
def send_help(message):
    bot.reply_to(message, get_commands_list())

@bot.message_handler(commands=['new_task'])
def new_task(message):
    chat_id = message.chat.id
    user = session.query(User).filter_by(chat_id=chat_id).first()
    if user:
        expecting_task[chat_id] = True
        bot.reply_to(message, "Отправь мне текст задачи.")
    else:
        bot.reply_to(message, "Вы не зарегистрированы в системе. Используйте /start для регистрации.")

@bot.message_handler(func=lambda message: message.chat.id in expecting_task and expecting_task[message.chat.id])
def add_task(message):
    chat_id = message.chat.id
    user = session.query(User).filter_by(chat_id=chat_id).first()
    if user:
        new_task = Task(text=message.text, user=user, local_id=user.task_index)
        user.task_index += 1  # Увеличиваем индекс следующей задачи
        session.add(new_task)
        session.commit()
        del expecting_task[chat_id]
        bot.reply_to(message, f"Задача добавлена: {message.text}")
    else:
        bot.reply_to(message, "Произошла ошибка, возможно, вы не зарегистрированы.")

@bot.message_handler(commands=['tasks'])
def show_tasks(message):
    chat_id = message.chat.id
    user = session.query(User).filter_by(chat_id=chat_id).first()
    if user:
        tasks = user.tasks
        if tasks:
            reply = "\n".join([f"{task.local_id}. {task.text}" for task in tasks])
        else:
            reply = "Список задач пуст."
        bot.reply_to(message, reply)
    else:
        bot.reply_to(message, "Вы не зарегистрированы в системе.")

@bot.message_handler(commands=['rmtasks'])
def remove_tasks(message):
    chat_id = message.chat.id
    user = session.query(User).filter_by(chat_id=chat_id).first()
    if user:
        user.tasks = []  # Удаляем все задачи пользователя
        user.task_index = 1  # Сброс индекса задач
        session.commit()
        bot.reply_to(message, "Все задачи удалены.")
    else:
        bot.reply_to(message, "Вы не зарегистрированы в системе.")

@bot.message_handler(commands=['rmtask'])
def remove_task(message):
    chat_id = message.chat.id
    user = session.query(User).filter_by(chat_id=chat_id).first()
    if user:
        bot.send_message(chat_id, "Введите номер задачи для удаления:")
        bot.register_next_step_handler(message, process_task_removal, user)
    else:
        bot.reply_to(message, "Вы не зарегистрированы в системе.")

def process_task_removal(message, user):
    task_id = int(message.text)
    task = next((task for task in user.tasks if task.local_id == task_id), None)
    if task:
        session.delete(task)
        session.commit()
        bot.reply_to(message, f"Задача {task_id} удалена.")
    else:
        bot.reply_to(message, f"Задача с номером {task_id} не найдена.")

bot.polling()
