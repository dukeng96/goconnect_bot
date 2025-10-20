# GoConnect Telegram Incident Assistant

This guide focuses on **deploying and running** the service.

## 1) Requirements
- **Python 3.11+** (or Docker)
- **MongoDB** reachable from the bot
- (Optional) **MinIO/S3** for attachments
- **Telegram** bot token + a **technical group** chat ID

## 2) Environment Variables
Create a `.env` file next to the code (or pass via Docker):
```
TELEGRAM_BOT_TOKEN=xxxxx
INCIDENT_GROUP_ID=-1001234567890

LLM_URL=http://10.165.24.200:30424/query
RAG_URL=http://10.159.19.9:31838/botproxy/action
RAG_BOT_ID=6df02010-a8d1-11f0-b308-c9a56fc30658

MONGODB_URI=mongodb://mongo:27017
MONGO_DB=goconnect_bot

# Optional MinIO (leave blank to disable uploads)
MINIO_SERVICE_URL=
MINIO_ACCESS_KEY=
MINIO_SECRET_KEY=
MINIO_FOLDER_NAME=
MINIO_PUBLIC_HOST=
MINIO_EXPIRE_TIME=168

LOG_LEVEL=INFO
```

> **How to get `INCIDENT_GROUP_ID`:** add your bot into the target Telegram group, send any message, then use a helper tool (or Bot API `getUpdates`) to read the `chat.id` (usually negative, e.g. `-100...`).

## 3) Run Locally (Python)
```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Load env (Linux/Mac)
export $(grep -v '^#' .env | xargs)

python bot.py
```

## 4) Run with Docker
Build once:
```bash
docker build -t goconnect-bot:latest .
```

Run:
```bash
docker run --rm -it   --name goconnect-bot   --env-file .env   goconnect-bot:latest
```
