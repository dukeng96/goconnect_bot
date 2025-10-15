import re, json, requests
from typing import Dict, Any
from config import logger, LLM_URL, RAG_URL, RAG_BOT_ID
from messages_config import CLASSIFIER_PROMPT, ENTITY_PROMPT, QNA_BUSY, QNA_NOT_FOUND


def _call_llm(prompt: str) -> str:
    try:
        r = requests.post(LLM_URL, json={'query': prompt}, timeout=15)
        r.raise_for_status()
        return r.json().get('response', '')
    except Exception:
        logger.exception("LLM call failed")
        return ''


def classify(text: str) -> Dict[str, Any]:
    prompt = CLASSIFIER_PROMPT.format(text=text)
    resp = _call_llm(prompt).strip()
    m = re.search(r'\{.*\}', resp)
    if m:
        try:
            result = json.loads(m.group(0))
            logger.info("Classifier: %s", result)
            return result
        except Exception:
            logger.exception("Classifier JSON parse error")
    return {'class': 'QNA', 'confidence': 0.5}


def extract_entities(text: str) -> Dict[str, str]:
    default = {"platform": "unknown", "os": "unknown", "device_model": "unknown", "app_version": "unknown"}
    prompt = ENTITY_PROMPT.format(text=text)
    resp = _call_llm(prompt).strip()
    if not resp:
        return default
    m = re.search(r'\{.*\}', resp)
    if not m:
        return default
    try:
        data = json.loads(m.group(0))
        return {k: str(data.get(k, default[k])) for k in default.keys()}
    except Exception:
        logger.exception("Entity JSON parse error")
        return default


def rag_answer(telegram_id: int, text: str) -> str:
    payload = { 'bot_id': RAG_BOT_ID, 'sender_id': str(telegram_id), 'logSTT_id': 'DTMF', 'input_channel': 'telegram', 'text': text }
    try:
        logger.info("RAG: calling backend for sender=%s", telegram_id)
        r = requests.post(RAG_URL, json=payload, timeout=20)
        r.raise_for_status()
        j = r.json(); cards = j.get('card_data') or []
        if cards:
            return cards[0].get('text') or QNA_NOT_FOUND
    except Exception:
        logger.exception("RAG call failed")
        return QNA_BUSY
    return QNA_NOT_FOUND