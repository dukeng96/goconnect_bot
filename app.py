import os, re, json, requests, logging
from datetime import datetime
from uuid import uuid4
from typing import Dict, Any
from pymongo import MongoClient, ReturnDocument
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# =========================
# Logging
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("goconnect_bot")
logging.getLogger("pymongo").setLevel(logging.WARNING)

# =========================
# ENV & CONFIG
# =========================
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8265574317:AAH1xM9V9GSjesgBaSqmUvWXf96FaEDEtZc')
INCIDENT_GROUP_ID = int(os.getenv('INCIDENT_GROUP_ID', '-1002725362613'))
LLM_URL = os.getenv('LLM_URL', 'http://10.165.24.200:30424/query')
RAG_URL = os.getenv('RAG_URL', 'http://10.159.19.9:31838/botproxy/action')
RAG_BOT_ID = os.getenv('RAG_BOT_ID', "6df02010-a8d1-11f0-b308-c9a56fc30658")
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
MONGO_DB = os.getenv('MONGO_DB', 'goconnect_bot')

# === ALL MESSAGES HERE (no literals inside handlers) ===
MESSAGES: Dict[str, str] = {
    'start': (
        """
Dạ em là trợ lý GoConnect. Em có thể hướng dẫn anh/chị cách sử dụng GoConnect hoặc xử lý các sự cố, lỗi liên quan. Anh/chị cần em hỗ trợ gì ạ?
"""
    ),
    'help': (
        """
/start – giới thiệu
/help – trợ giúp

Cứ nhắn câu hỏi hoặc mô tả sự cố, em sẽ hỗ trợ ạ.
"""
    ),
    'soothing_received': (
        """
Dạ, em đã nhận yêu cầu và chuyển cho đội kĩ thuật kiểm tra ngay ạ.
"""
    ),
    'soothing_received_alt': (
        """
Dạ, em đã chuyển thông tin cho team kĩ thuật, team sẽ kiểm tra ngay và phản hồi anh sớm ạ.
"""
    ),
    'need_info_user': (
        """
Dạ để xử lý nhanh hơn, anh/chị cho em xin thêm thông tin: thiết bị, hệ điều hành, phiên bản app, bước tái hiện và ảnh/chụp màn hình ạ.
"""
    ),
    'fixed_user': (
        """
Anh/chị ơi, sự cố vừa rồi đã được đội xử lý xong. Anh/chị thử lại giúp em xem đã ổn chưa ạ. Em cảm ơn anh/chị!
"""
    ),
    'qna_busy': (
        """
Em xin lỗi, hệ thống hỏi đáp đang bận. Anh/chị vui lòng thử lại giúp em ạ.
"""
    ),
    'qna_not_found': (
        """
Em xin lỗi, hiện em chưa tìm được thông tin phù hợp trong kho kiến thức ạ.
"""
    ),
    'group_bug_template': (
        """
[BUG] {ticket_id}
Từ: @{username} ({user_id})
Nội dung: "{text}"
Thời điểm: {time_utc}
"""
    ),
    'group_ack_suffix': "",
    'group_need_suffix': "",
    'group_fix_suffix': (
        """


🟢 Đã khắc phục và đã nhắn lại người dùng.
"""
    ),
    # Externalized LLM classifier prompt
    'classifier_prompt': (
        """
Bạn là bộ phân loại tin nhắn cho trợ lý hỗ trợ GoConnect. Phân loại:
- BUG: người dùng mô tả sự cố/lỗi/không làm được.
- QNA: hỏi cách dùng/thông tin.
Chỉ trả JSON một dòng: {{"class": "BUG|QNA", "confidence": 0..1}}.
Văn bản: "{text}"
"""
    ),
}

BUG_KEYWORDS = [
    'lỗi','bug','không gửi','không vào','không nhận','đơ','treo','xoay xoay','failed','error',
    'không mở','không join','mất tiếng','không thấy','upload','gửi file','quay vòng','crash','đứng hình'
]

# =========================
# MongoDB setup
# =========================
logger.info("Connecting to MongoDB... %s", MONGODB_URI)
client = MongoClient(MONGODB_URI)
logger.info("Connected to MongoDB, db=%s", MONGO_DB)
db = client[MONGO_DB]
col_tickets = db['tickets']
col_events = db['events']
col_users = db['users']

# Indexes (idempotent)
col_tickets.create_index('id', unique=True)
col_tickets.create_index([('user_id', 1), ('created_at', -1)])
col_events.create_index([('ticket_id', 1), ('at', -1)])
col_users.create_index('telegram_id', unique=True)

# =========================
# Helpers
# =========================

def rule_is_bug(text: str) -> bool:
    t = (text or '').lower()
    hit = any(k in t for k in BUG_KEYWORDS)
    if hit:
        logger.info("Rule matched BUG keywords")
    return hit

def llm_classify(text: str) -> Dict[str, Any]:
    """Gọi LLM để phân loại BUG|QNA khi rule chưa chắc."""
    prompt = MESSAGES['classifier_prompt'].format(text=text)
    try:
        logger.info("Classifier: calling LLM")
        r = requests.post(LLM_URL, json={'query': prompt}, timeout=10)
        r.raise_for_status()
        resp = r.json().get('response','').strip()
        m = re.search(r'\{.*\}', resp)
        if m:
            result = json.loads(m.group(0))
            logger.info("Classifier result: %s", result)
            return result
        logger.warning("Classifier: JSON not found in response")
    except Exception:
        logger.exception("Classifier: exception while calling LLM")
    fallback = {'class': 'BUG' if rule_is_bug(text) else 'QNA', 'confidence': 0.51}
    logger.info("Classifier fallback: %s", fallback)
    return fallback
def rag_answer(telegram_id: int, text: str) -> str:
    payload = {
        'bot_id': RAG_BOT_ID,
        'sender_id': str(telegram_id),
        'logSTT_id': 'DTMF',
        'input_channel': 'telegram',
        'text': text
    }
    try:
        logger.info("RAG: calling backend for sender=%s", telegram_id)
        r = requests.post(RAG_URL, json=payload, timeout=20)
        r.raise_for_status()
        j = r.json()
        cards = j.get('card_data') or []
        if cards:
            logger.info("RAG: got card_data with %d item(s)", len(cards))
            return cards[0].get('text') or MESSAGES['qna_not_found']
        logger.warning("RAG: empty card_data")
    except Exception:
        logger.exception("RAG: exception while calling backend")
        return MESSAGES['qna_busy']
    return MESSAGES['qna_not_found']

# Ticket helpers (Mongo)

def new_ticket_id() -> str:
    return f"GC-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid4())[:4].upper()}"

def create_ticket(user_id: int, chat_id: int, src_message_id: int, text: str,
                  priority: str = 'P3', khl_tag: str | None = None) -> str:
    tid = new_ticket_id()
    now = datetime.utcnow().isoformat()
    logger.info("DB: create_ticket for user=%s chat=%s", user_id, chat_id)
    col_tickets.insert_one({
        'id': tid,
        'user_id': user_id,
        'chat_id': chat_id,
        'src_message_id': src_message_id,
        'text': text,
        'status': 'NEW',
        'priority': priority,
        'khl_tag': khl_tag,
        'created_at': now,
        'updated_at': now,
    })
    return tid

def add_event(tid: str, actor: str, action: str, note: str = '') -> None:
    logger.info("DB: add_event %s %s", action, tid)
    col_events.insert_one({
        'ticket_id': tid,
        'actor': actor,
        'action': action,
        'note': note,
        'at': datetime.utcnow().isoformat()
    })

def set_status(tid: str, status: str) -> None:
    logger.info("DB: set_status %s -> %s", tid, status)
    col_tickets.find_one_and_update(
        {'id': tid},
        {'$set': {'status': status, 'updated_at': datetime.utcnow().isoformat()}},
        return_document=ReturnDocument.AFTER
    )

# =========================
# Telegram handlers (no hard-coded messages)
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("/start from %s", update.effective_user.id if update.effective_user else None)
    await update.message.reply_text(MESSAGES['start'])

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("/help from %s", update.effective_user.id if update.effective_user else None)
    await update.message.reply_text(MESSAGES['help'])

async def forward_to_group(context: ContextTypes.DEFAULT_TYPE, tid: str, src_msg: str, user, chat_id: int, message_id: int):
    kb = InlineKeyboardMarkup([[ 
        InlineKeyboardButton("Đã khắc phục", callback_data=f"fix:{tid}")
    ]])
    text = MESSAGES['group_bug_template'].format(
        ticket_id=tid,
        username=(user.username or 'user'),
        user_id=user.id,
        text=src_msg,
        time_utc=datetime.utcnow().strftime('%H:%M:%S UTC')
    )
    logger.info("Forwarded ticket %s to INCIDENT_GROUP_ID=%s", tid, INCIDENT_GROUP_ID)
    await context.bot.send_message(chat_id=INCIDENT_GROUP_ID, text=text, reply_markup=kb)

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Callback received: %s", update.callback_query.data if update.callback_query else None)
    q = update.callback_query
    await q.answer()
    action, tid = q.data.split(':', 1)
    actor = q.from_user.username or str(q.from_user.id)

    if action == 'fix':
        logger.info("Action FIX for %s by %s", tid, actor)
        set_status(tid, 'FIXED'); add_event(tid, actor, 'fix')
        row = col_tickets.find_one({'id': tid}, {'chat_id': 1})
        if row:
            await context.bot.send_message(chat_id=row['chat_id'], text=MESSAGES['fixed_user'])
        await q.edit_message_text(q.message.text + MESSAGES['group_fix_suffix'])

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("on_message: chat=%s user=%s", update.effective_chat.id if update.effective_chat else None, update.effective_user.id if update.effective_user else None)
    msg = update.effective_message
    user = msg.from_user
    text = msg.text or msg.caption or ''

    # Upsert user
    col_users.update_one(
        {'telegram_id': user.id},
        {'$set': {
            'telegram_id': user.id,
            'username': user.username,
            'full_name': user.full_name,
            'last_seen': datetime.utcnow().isoformat()
        }}, upsert=True
    )

    # 1) Bug theo rule → soothing + forward ngay
    if rule_is_bug(text):
        tid = create_ticket(user.id, msg.chat_id, msg.id, text)
        await msg.reply_text(MESSAGES['soothing_received'])
        await forward_to_group(context, tid, text, user, msg.chat_id, msg.id)
        return

    # 2) Không chắc → gọi LLM phân loại
    cls = llm_classify(text)
    if cls.get('class') == 'BUG' and cls.get('confidence', 0) >= 0.6:
        tid = create_ticket(user.id, msg.chat_id, msg.id, text)
        await msg.reply_text(MESSAGES['soothing_received_alt'])
        await forward_to_group(context, tid, text, user, msg.chat_id, msg.id)
        return

    # 3) QnA → RAG
    answer = rag_answer(user.id, text)
    await msg.reply_text(answer)

# =========================
# Bootstrap
# =========================
if __name__ == '__main__':
    REQUIRED = [TOKEN, INCIDENT_GROUP_ID, LLM_URL, RAG_URL, RAG_BOT_ID, MONGODB_URI]
    if any(v in (None, '', 0) for v in REQUIRED):
        raise SystemExit('Thiếu ENV: TELEGRAM_BOT_TOKEN, INCIDENT_GROUP_ID, LLM_URL, RAG_URL, RAG_BOT_ID, MONGODB_URI')

    app = ApplicationBuilder().token(TOKEN).build()

    # Global error handler
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.exception("Unhandled exception in PTB handler", exc_info=context.error)

    app.add_error_handler(error_handler)
    logger.info("Bot starting polling...")
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_cmd))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, on_message))
    app.run_polling(drop_pending_updates=True)