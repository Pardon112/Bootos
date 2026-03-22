FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем bot.py (а не yandex_bot.py)
COPY bot.py .

RUN mkdir -p /app/data/yandex_screenshots

CMD ["python", "bot.py"]
