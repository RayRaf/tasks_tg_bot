# Используем официальный образ Python с Docker Hub
FROM python:3.10-slim

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Копируем файлы зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем файл main.py
COPY main.py .

# Команда для запуска main.py
CMD ["python", "main.py"]
