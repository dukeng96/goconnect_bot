from typing import Dict, Any, List
from message_config import TICKET_PREVIEW_HEADER, TICKET_PREVIEW_FOOTER
import re

def html_escape(s: str) -> str:
    if s is None:
        return ""
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))

def fmt_attachments(att: List[Dict[str, str]]) -> str:
    if not att:
        return "<i>Không</i>"
    parts = []
    for i, a in enumerate(att, 1):
        url = a.get("url"); name = html_escape(a.get("name", f"tệp {i}"))
        parts.append(f"• <a href=\"{url}\">{name}</a>" if url else f"• {name}")
    return "\n".join(parts)

def fmt_notes(notes: list[dict] | None, limit: int = 3) -> str:
    if not notes:
        return "<i>Không</i>"
    last = notes[-limit:]
    lines = []
    for n in last:
        who = html_escape(n.get('author', 'user'))
        content = html_escape((n.get('content') or '').strip())
        if content:
            lines.append(f"• <b>{who}</b>: {content}")
    return "\n".join(lines) if lines else "<i>Không</i>"

def ticket_preview_text(t: Dict[str, Any]) -> str:
    meta = t.get('meta', {})
    attachments = fmt_attachments(t.get('attachments', []))
    notes = fmt_notes(t.get('notes', []))
    base = TICKET_PREVIEW_HEADER.format(
        ticket_id=t['id'],
        text=html_escape(t.get('text','')),     # <-- escape
        platform=html_escape(meta.get('platform','unknown')),
        os=html_escape(meta.get('os','unknown')),
        app_version=html_escape(meta.get('app_version','unknown')),
        attachments=attachments
    )
    notes_block = "\n<b>Ghi chú bổ sung:</b>\n" + notes + "\n"
    return base + notes_block + TICKET_PREVIEW_FOOTER

def html_escape_basic(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def rag_markdown_to_html(s: str) -> str:
    s = html_escape_basic(s)
    # convert **bold** -> <b>bold</b>
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    return s
