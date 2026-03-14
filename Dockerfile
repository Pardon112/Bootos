FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода бота
COPY bot.py .
COPY *.db /app/  # если есть существующая база данных

# Создание папки для скриншотов
RUN mkdir -p /app/screenshots

# Запуск бота
CMD ["python", "bot.py"]
