import os, logging
from dotenv import load_dotenv

load_dotenv()

# Logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("goconnect_bot")
logging.getLogger("pymongo").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Telegram
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8265574317:AAH1xM9V9GSjesgBaSqmUvWXf96FaEDEtZc')
INCIDENT_GROUP_ID = int(os.getenv('INCIDENT_GROUP_ID', '-1002725362613'))

# LLM / RAG
LLM_URL = os.getenv('LLM_URL', 'http://10.165.24.200:30424/query')
RAG_URL = os.getenv('RAG_URL', 'http://10.159.19.9:31838/botproxy/action')
RAG_BOT_ID = os.getenv('RAG_BOT_ID', "6df02010-a8d1-11f0-b308-c9a56fc30658")

# Mongo
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
MONGO_DB = os.getenv('MONGO_DB', 'goconnect_bot')

# MinIO
MINIO_SERVICE_URL = os.getenv('MINIO_SERVICE_URL', 'https://voice-storage.vnpt.vn')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'texttospeech')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'Text2speechVnptAI@2024')
MINIO_FOLDER_NAME = os.getenv('MINIO_FOLDER_NAME', 'goconnect')  # bucket
MINIO_PUBLIC_HOST = os.getenv('MINIO_PUBLIC_HOST', MINIO_SERVICE_URL)
MINIO_EXPIRE_TIME = int(os.getenv('MINIO_EXPIRE_TIME', '168')) * 3600  # hours → seconds

REQUIRED_ENV = [TOKEN, INCIDENT_GROUP_ID, LLM_URL, RAG_URL, RAG_BOT_ID, MONGODB_URI]