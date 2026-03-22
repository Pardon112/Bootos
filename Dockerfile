FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY yandex_bot.py bot.py

RUN mkdir -p /app/data/yandex_screenshots

CMD ["python", "bot.py"]
