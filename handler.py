# handler.py
import io
from uuid import uuid4
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import logger, INCIDENT_GROUP_ID
from message_config import (
    START, HELP, SOOTHING_ASK_ENV, NEED_INFO_USER, FIXED_USER,
    GROUP_BUG_TEMPLATE, GROUP_FIX_SUFFIX, CANCELLED_USER
)
from db import (
    now_iso, create_ticket, add_event, set_status, update_meta, add_attachment,
    upsert_user, latest_open_draft, reset_user_flow, col_tickets
)
from llm import classify, extract_entities, rag_answer
from storage import upload_bytes, guess_content_type
from formatting import ticket_preview_text, fmt_attachments, html_escape, fmt_notes


def new_ticket_id() -> str:
    return f"GC-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid4())[:4].upper()}"


# ========== Commands ==========
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else None
    if uid:
        reset_user_flow(uid)
    await update.message.reply_text(START, parse_mode='HTML')

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP, parse_mode='HTML')

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else None
    if uid:
        reset_user_flow(uid)
    await update.message.reply_text(
        "Em đã đặt lại phiên làm việc. Anh/chị có thể bắt đầu câu hỏi mới ạ.",
        parse_mode='HTML'
    )


# ========== Internal ==========
async def _forward_to_group(context: ContextTypes.DEFAULT_TYPE, tid: str, src_msg: str, user, ticket_doc):
    meta = ticket_doc.get('meta', {})
    text = GROUP_BUG_TEMPLATE.format(
        ticket_id=tid,
        username=(user.username or 'user'),
        user_id=user.id,
        text=html_escape(src_msg),
        platform=meta.get('platform','unknown'),
        os=meta.get('os','unknown'),
        app_version=meta.get('app_version','unknown'),
        attachments=fmt_attachments(ticket_doc.get('attachments', [])),
        notes=fmt_notes(ticket_doc.get('notes', []), limit=6),   # <-- thêm dòng này
        time_utc=datetime.utcnow().strftime('%H:%M:%S UTC')
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Đã khắc phục", callback_data=f"fix:{tid}")]])
    await context.bot.send_message(
        chat_id=INCIDENT_GROUP_ID, text=text, reply_markup=kb,
        disable_web_page_preview=True, parse_mode='HTML'
    )


# ========== Callback ==========
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    action, tid = q.data.split(':', 1)
    actor = q.from_user.username or str(q.from_user.id)

    if action == 'fix':
        set_status(tid, 'FIXED'); add_event(tid, actor, 'fix')
        row = col_tickets.find_one({'id': tid}, {'chat_id': 1})
        if row:
            await context.bot.send_message(chat_id=row['chat_id'], text=FIXED_USER, parse_mode='HTML')
        await q.edit_message_text(q.message.text + GROUP_FIX_SUFFIX, parse_mode='HTML')

    elif action == 'user_confirm':
        t = col_tickets.find_one({'id': tid})
        if not t: return
        set_status(tid, 'NEW'); add_event(tid, actor, 'confirm')
        await q.message.reply_text(
            "Dạ, em đã chuyển thông tin cho team kỹ thuật, team sẽ kiểm tra ngay và phản hồi sớm ạ."
        )
        await _forward_to_group(context, tid, t.get('text',''), q.from_user, t)

    elif action == 'user_update':
        set_status(tid, 'UPDATING'); add_event(tid, actor, 'update')
        await q.message.reply_text(
            "Dạ, mời anh/chị gửi thêm ảnh/video/miêu tả chi tiết để em cập nhật vào phiếu ạ.",
            parse_mode='HTML'
        )

    elif action == 'user_cancel':
        set_status(tid, 'CANCELLED'); add_event(tid, actor, 'cancel_via_button')
        row = col_tickets.find_one({'id': tid}, {'chat_id': 1})
        if row:
            await context.bot.send_message(
                chat_id=row['chat_id'], text=CANCELLED_USER.format(ticket_id=tid), parse_mode='HTML'
            )
        await q.edit_message_text(q.message.text + "\n\n<b>⛔ Phiếu đã được hủy.</b>", parse_mode='HTML')


# ========== Message pipeline ==========
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = msg.from_user
    text = msg.text or msg.caption or ''
    upsert_user(user.id, user.username, user.full_name)

    draft = latest_open_draft(user.id)

    # 1) Đang DRAFT → không thoát flow, luôn hiển thị preview
    if draft and draft.get('status') == 'DRAFT' and text:
        meta = extract_entities(text)
        update_meta(draft['id'], meta)
        t = col_tickets.find_one({'id': draft['id']})
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("Xác nhận phiếu", callback_data=f"user_confirm:{t['id']}"),
            InlineKeyboardButton("Cập nhật phiếu",  callback_data=f"user_update:{t['id']}"),
            InlineKeyboardButton("Hủy phiếu",       callback_data=f"user_cancel:{t['id']}")
        ]])
        await msg.reply_text(
            ticket_preview_text(t), reply_markup=kb,
            disable_web_page_preview=True, parse_mode='HTML'   # <-- quan trọng để HTML render
        )
        return

    # 2) Đang UPDATING: file → upload; text → note + preview; không classifier/RAG
    if draft and draft.get('status') == 'UPDATING':
        if msg.photo or msg.document or msg.video:
            if msg.photo:
                file_id = msg.photo[-1].file_id
                filename = f"photo_{msg.photo[-1].file_unique_id}.jpg"
            elif msg.document:
                file_id = msg.document.file_id
                filename = msg.document.file_name or f"doc_{msg.document.file_unique_id}"
            else:  # video
                file_id = msg.video.file_id
                filename = msg.video.file_name or f"video_{msg.video.file_unique_id}.mp4"

            tgfile = await context.bot.get_file(file_id)
            bio = io.BytesIO()
            await tgfile.download_to_memory(out=bio)
            bio.seek(0)
            url = upload_bytes(bio.read(),
                               f"tickets/{draft['id']}/{filename}",
                               guess_content_type(filename))
            add_attachment(draft['id'], {'type': 'file', 'name': filename, 'url': url or ''})

        if text:
            add_event(draft['id'], str(user.id), 'note', note=text)
            from db import add_note
            add_note(draft['id'], author=str(user.id), content=text)

        t = col_tickets.find_one({'id': draft['id']})
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("Xác nhận phiếu", callback_data=f"user_confirm:{t['id']}"),
            InlineKeyboardButton("Cập nhật phiếu", callback_data=f"user_update:{t['id']}"),
            InlineKeyboardButton("Hủy phiếu", callback_data=f"user_cancel:{t['id']}")
        ]])
        await msg.reply_text(
            ticket_preview_text(t), reply_markup=kb,
            disable_web_page_preview=True, parse_mode='HTML'
        )
        return

    # 3) Không có draft → classifier
    if text:
        cls = classify(text)
        if cls.get('class') == 'BUG' and cls.get('confidence', 0) >= 0.6:
            tid = new_ticket_id()
            create_ticket({
                'id': tid, 'user_id': user.id, 'chat_id': msg.chat_id, 'src_message_id': msg.id, 'text': text,
                'status': 'DRAFT', 'priority': 'P3', 'khl_tag': None,
                'meta': {"platform": "unknown", "os": "unknown", "device_model": "unknown", "app_version": "unknown"},
                'attachments': [],
                'notes': [],
                'created_at': now_iso(), 'updated_at': now_iso()
            })

            await msg.reply_text(SOOTHING_ASK_ENV, parse_mode='HTML')
            return

    # 4) QnA → RAG (giữ Markdown do backend định dạng **bold**)
    answer = rag_answer(user.id, text)
    await msg.reply_text(answer, parse_mode='Markdown', disable_web_page_preview=True)
