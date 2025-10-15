from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pymongo import MongoClient, ReturnDocument
from config import logger, MONGODB_URI, MONGO_DB

# Init
logger.info("Connecting to MongoDB... %s", MONGODB_URI)
client = MongoClient(MONGODB_URI)
db = client[MONGO_DB]
col_tickets = db['tickets']
col_events = db['events']
col_users = db['users']
col_tickets.create_index('id', unique=True)
col_tickets.create_index([('user_id', 1), ('created_at', -1)])
col_events.create_index([('ticket_id', 1), ('at', -1)])
col_users.create_index('telegram_id', unique=True)

# CRUD helpers

def now_iso() -> str:
    return datetime.utcnow().isoformat()

def create_ticket(doc: Dict[str, Any]) -> None:
    col_tickets.insert_one(doc)

def add_event(tid: str, actor: str, action: str, note: str = '') -> None:
    col_events.insert_one({
        'ticket_id': tid, 'actor': actor, 'action': action, 'note': note, 'at': now_iso()
    })

def set_status(tid: str, status: str) -> None:
    col_tickets.find_one_and_update({'id': tid}, {'$set': {'status': status, 'updated_at': now_iso()}},
                                    return_document=ReturnDocument.AFTER)

def update_meta(tid: str, meta: Dict[str, str]) -> None:
    col_tickets.find_one_and_update({'id': tid}, {'$set': {**{f"meta.{k}": v for k, v in meta.items()}, 'updated_at': now_iso()}},
                                    return_document=ReturnDocument.AFTER)

def add_attachment(tid: str, att: Dict[str, str]) -> None:
    col_tickets.find_one_and_update({'id': tid}, {'$push': {'attachments': att}, '$set': {'updated_at': now_iso()}},
                                    return_document=ReturnDocument.AFTER)

def upsert_user(user_id: int, username: str, full_name: str) -> None:
    col_users.update_one({'telegram_id': user_id}, {'$set': {
        'telegram_id': user_id, 'username': username, 'full_name': full_name, 'last_seen': now_iso()
    }}, upsert=True)

def latest_open_draft(user_id: int) -> Optional[Dict[str, Any]]:
    d = col_tickets.find_one({'user_id': user_id, 'status': {'$in': ['DRAFT','UPDATING']}}, sort=[('created_at', -1)])
    if not d: return None
    try:
        created = datetime.fromisoformat(d['created_at'])
        if datetime.utcnow() - created > timedelta(minutes=10):
            set_status(d['id'], 'CANCELLED')
            return None
    except Exception:
        pass
    return d

def reset_user_flow(user_id: int):
    col_tickets.update_many({ 'user_id': user_id, 'status': {'$in': ['DRAFT','UPDATING']} },
                            { '$set': {'status': 'CANCELLED', 'updated_at': now_iso()} })