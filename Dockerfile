FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Use the absolute path /models to match MODEL_CACHE_PATH in sync_equity.py
RUN mkdir -p /models
RUN python app/model_cache.py

# CMD ["python", "app/liaison_bot.py"]