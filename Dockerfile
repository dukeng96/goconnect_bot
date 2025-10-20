FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=UTC

# System deps (SSL, ca-certs, curl) + build basics nếu cần compile nhẹ
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl tzdata build-essential \
    && rm -rf /var/lib/apt/lists/*

# App dir
WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt
COPY bot.py config.py db.py handler.py llm.py storage.py formatting.py message_config.py /app/

# Non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Entry
CMD ["python", "bot.py"]