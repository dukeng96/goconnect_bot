from typing import Dict, Any, List
from message_config import TICKET_PREVIEW_HEADER, TICKET_PREVIEW_FOOTER


def fmt_attachments(att: List[Dict[str, str]]) -> str:
    if not att:
        return "<i>Không</i>"
    parts = []
    for i, a in enumerate(att, 1):
        url = a.get("url"); name = a.get("name", f"tệp {i}")
        parts.append(f"• <a href=\"{url}\">{name}</a>" if url else f"• {name}")
    return "".join(parts)


def ticket_preview_text(t: Dict[str, Any]) -> str:
    meta = t.get('meta', {})
    return (
        TICKET_PREVIEW_HEADER.format(
            ticket_id=t['id'], text=t.get('text',''),
            platform=meta.get('platform','unknown'), os=meta.get('os','unknown'), app_version=meta.get('app_version','unknown'),
            attachments=fmt_attachments(t.get('attachments', []))
        ) + TICKET_PREVIEW_FOOTER
    )