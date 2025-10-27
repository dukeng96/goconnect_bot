# FLOW.md — Luồng hoạt động chính của GoConnect Telegram Incident Assistant

Tài liệu này mô tả **các flow chính** đang chạy trong bản hiện tại, kèm **code snippet** minh họa để tiện tra cứu/đối chiếu nhanh trong repo.

---

## 1) Flow Q&A (RAG)

### Mô tả
- Người dùng nhắn một câu hỏi chung.
- Trợ lý dùng **LLM classifier** để nhận diện loại yêu cầu. Nếu **không phải** bug (hoặc classifier không đủ tự tin), bot sẽ rẽ sang **RAG** (chính là Smartbot tri thức).
- Backend RAG có thể trả **nhiều câu** (nhiều `card_data`), bot sẽ gửi tuần tự từng câu.

### Snippet (trích `handler.py` – phần cuối pipeline)
```python
# 4) QnA → RAG (backend có thể trả nhiều card text)
answers = rag_answer(user.id, text)   # list[str]
for a in answers:
    await msg.reply_text(a, disable_web_page_preview=True)
```

### Snippet (trích `llm.py` – gọi RAG & trả list câu)
```python
def rag_answer(telegram_id: int, text: str) -> List[str]:
    payload = {
        "bot_id": RAG_BOT_ID,
        "sender_id": str(telegram_id),
        "logSTT_id": "DTMF",
        "input_channel": "telegram",
        "text": text,
    }
    try:
        r = requests.post(RAG_URL, json=payload, timeout=20)
        r.raise_for_status()
        j = r.json() or {}
        cards = j.get("card_data") or []

        # (Nếu bật log RAG tối giản) save_rag_log(telegram_id, text, j.get("slots", {}).get("is_outdomain","0"))

        out = [ (c or {}).get("text","").strip() for c in cards if isinstance(c, dict) ]
        out = [t for t in out if t]
        return out or [QNA_NOT_FOUND]
    except Exception:
        logger.exception("RAG call failed")
        return [QNA_BUSY]
```


---

## 2) Flow Báo lỗi → Tạo ticket (DRAFT → CONFIRM/UPDATE/CANCEL)

### Mô tả
1. Người dùng mô tả **sự cố**.  
2. **Classifier** nhận diện “BUG” → tạo **ticket DRAFT**.  
3. Bot **hỏi môi trường** (web/app, OS, thiết bị) và **extract entity** bằng LLM để điền vào `meta`.  
4. Bot hiển thị **bản xem trước** (preview) + 3 nút:  
   - **Xác nhận phiếu** → chuyển `status: NEW` rồi **forward** sang nhóm kỹ thuật.  
   - **Cập nhật phiếu** → chuyển `status: UPDATING`, người dùng gửi thêm **ảnh/video/text** (được **upload lên MinIO** và/hoặc **append vào notes**).  
   - **Hủy phiếu** → `status: CANCELLED` và kết thúc flow.  
5. Khi ở **DRAFT/UPDATING**, người dùng **không thoát** flow cho đến khi **Xác nhận** hoặc **Hủy**.  

### Snippet: tạo DRAFT + hỏi môi trường (trích `handler.py`)
```python
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
```

### Snippet: cập nhật meta + hiển thị preview (trích `handler.py`)
```python
if draft and draft.get('status') == 'DRAFT' and text:
    meta = extract_entities(text)            # LLM entity extraction
    update_meta(draft['id'], meta)
    t = col_tickets.find_one({'id': draft['id']})
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Xác nhận phiếu", callback_data=f"user_confirm:{t['id']}"),
        InlineKeyboardButton("Cập nhật phiếu",  callback_data=f"user_update:{t['id']}"),
        InlineKeyboardButton("Hủy phiếu",       callback_data=f"user_cancel:{t['id']}")
    ]])
    await msg.reply_text(
        ticket_preview_text(t), reply_markup=kb,
        disable_web_page_preview=True, parse_mode='HTML'
    )
    return
```

### Snippet: người dùng **Cập nhật phiếu** (trích `handler.py`)
```python
elif action == 'user_update':
    set_status(tid, 'UPDATING'); add_event(tid, actor, 'update')
    await q.message.reply_text(
        "Dạ, mời anh/chị gửi thêm ảnh/video/miêu tả chi tiết để em cập nhật vào phiếu ạ.",
        parse_mode='HTML'
    )
```

### Snippet: nhận **attachment** + **note** trong UPDATING (trích `handler.py`)
```python
if draft and draft.get('status') == 'UPDATING':
    if msg.photo or msg.document or msg.video:
        # tải file từ Telegram rồi upload MinIO
        # add_attachment(draft['id'], {'type': 'file', 'name': filename, 'url': url})
    if text:
        add_event(draft['id'], str(user.id), 'note', note=text)
        add_note(draft['id'], author=str(user.id), content=text)  # append note
    # trả lại preview + 3 nút như trên
```

### Snippet: **Hủy phiếu** (trích `handler.py`)
```python
elif action == 'user_cancel':
    set_status(tid, 'CANCELLED'); add_event(tid, actor, 'cancel_via_button')
    row = col_tickets.find_one({'id': tid}, {'chat_id': 1})
    if row:
        await context.bot.send_message(
            chat_id=row['chat_id'], text=CANCELLED_USER.format(ticket_id=tid), parse_mode='HTML'
        )
    await q.edit_message_text(q.message.text + "\n\n<b>⛔ Phiếu đã được hủy.</b>", parse_mode='HTML')
```


---

## 3) Forward ticket sang nhóm Kỹ thuật + “Đã khắc phục”

### Mô tả
- Khi người dùng **Xác nhận phiếu**, ticket chuyển `NEW`, bot **forward** sang **nhóm kỹ thuật** (Incident).
- Tin nhắn trong nhóm có nút **“Đã khắc phục”**.  
- Khi kỹ thuật bấm “Đã khắc phục”:
  - Ticket chuyển `FIXED`, add event `fix`.
  - **Xóa** message khỏi nhóm kỹ thuật (để group luôn sạch/tồn đọng).  
  - Nhắn riêng báo lại cho người dùng đã fix thành công.

### Snippet: forward & lưu `group_message_id` (trích `handler.py`)
```python
msg = await context.bot.send_message(
    chat_id=INCIDENT_GROUP_ID, text=text, reply_markup=kb,
    disable_web_page_preview=True, parse_mode='HTML'
)
col_tickets.find_one_and_update(
    {'id': tid},
    {'$set': {'group_message_id': msg.message_id, 'updated_at': now_iso()}}
)
```

### Snippet: xử lý nút “Đã khắc phục” (trích `handler.py`)
```python
if action == 'fix':
    set_status(tid, 'FIXED'); add_event(tid, actor, 'fix')
    row = col_tickets.find_one({'id': tid}, {'chat_id': 1, 'group_message_id': 1})
    if row and row.get('group_message_id'):
        try:
            await context.bot.delete_message(chat_id=INCIDENT_GROUP_ID, message_id=row['group_message_id'])
        except Exception:
            await update.effective_message.edit_text(update.effective_message.text + GROUP_FIX_SUFFIX, parse_mode='HTML')
    if row:
        await context.bot.send_message(chat_id=row['chat_id'], text=FIXED_USER, parse_mode='HTML')
```


---

## 4) Upload file MinIO (attachment)

### Mô tả
- Khi người dùng gửi ảnh/video/tài liệu trong **UPDATING**, bot sẽ lấy file từ Telegram, upload lên **MinIO/S3** và lưu URL vào `attachments` của ticket.
- URL ưu tiên **presigned** (hết hạn theo ENV), fallback **public path** nếu được cấu hình public.  

### Snippet (trích `storage.py`)
```python
def upload_bytes(data: bytes, key: str, content_type: str | None = None) -> str | None:
    if not s3: return None
    s3.put_object(Bucket=MINIO_FOLDER_NAME, Key=key, Body=data, ContentType=content_type or 'application/octet-stream')
    return s3.generate_presigned_url('get_object',
                                     Params={'Bucket': MINIO_FOLDER_NAME, 'Key': key},
                                     ExpiresIn=MINIO_EXPIRE_TIME)
```

### Snippet (trích `handler.py` – khi nhận file)
```python
tgfile = await context.bot.get_file(file_id)
bio = io.BytesIO()
await tgfile.download_to_memory(out=bio)
bio.seek(0)
url = upload_bytes(bio.read(), f"tickets/{draft['id']}/{filename}", guess_content_type(filename))
add_attachment(draft['id'], {'type': 'file', 'name': filename, 'url': url or ''})
```


---

## 5) Render phiếu/preview bằng HTML

### Mô tả
- Tất cả **tin nhắn có định dạng** dùng `parse_mode='HTML'` (template ở `message_config.py`) để có **bold/italic**, **hyperlink**, **icon**.  
- Chú ý **escape** nội dung user (`html_escape`) trước khi chèn vào template để tránh phá HTML.

### Snippet (trích `message_config.py`)
```python
TICKET_PREVIEW_HEADER = \"\"\"
<b>📝 Em xin phép khởi tạo phiếu báo hỏng cho anh/chị</b>:

<b>Mã phiếu:</b> <code>{ticket_id}</code>
<b>Tóm tắt:</b> {text}
<b>Thiết bị/phiên bản:</b> {platform} | {os} | {app_version}
<b>Đính kèm:</b>
{attachments}
\"\"\"
TICKET_PREVIEW_FOOTER = \"\"\"
Nếu anh/chị muốn đính kèm thêm thông tin (ảnh/video/bước tái hiện), hãy bấm <b>Cập nhật phiếu</b>.
Nếu muốn gửi phiếu ngay đến team kỹ thuật, hãy bấm <b>Xác nhận phiếu</b>.
\"\"\"
```

### Snippet (trích `formatting.py`)
```python
def fmt_attachments(att: List[Dict[str, str]]) -> str:
    if not att:
        return "<i>Không</i>"
    parts = []
    for i, a in enumerate(att, 1):
        url = a.get("url"); name = a.get("name", f"tệp {i}")
        parts.append(f"• <a href=\"{url}\">{name}</a>" if url else f"• {name}")
    return "\n".join(parts)
```


---

## 6) Reset flow & lệnh cơ bản

### Mô tả
- `/start`: reset mọi DRAFT/UPDATING → `CANCELLED` và giới thiệu.
- `/help`: trợ giúp ngắn.
- `/cancel`: reset phiên làm việc (hủy các draft đang mở).

### Snippet (trích `handler.py`)
```python
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else None
    if uid:
        reset_user_flow(uid)
    await update.message.reply_text(START, parse_mode='HTML')

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else None
    if uid:
        reset_user_flow(uid)
    await update.message.reply_text("Em đã đặt lại phiên làm việc. Anh/chị có thể bắt đầu câu hỏi mới ạ.", parse_mode='HTML')
```


---

## 7) Forward Live Support (Fallback người)

### Mô tả
- Khi cần escalate/hỗ trợ trực tiếp, bot có thể **mention/link** nhóm **Live Support** (ví dụ: `https://t.me/<group_username>`).  
- **(Nếu đã cấu hình)** bot có thể đứng trong nhóm này để **log toàn bộ tin nhắn** (phục vụ thống kê sau này).

### Snippet: logger Live Support (trích `handler.py`)
```python
async def on_live_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.id != LIVE_SUPPORT_CHAT_ID:
        return
    msg = update.effective_message
    text = (msg.text or msg.caption or '').strip()
    if not text: return
    user = msg.from_user
    save_live_support_message(
        chat_id=update.effective_chat.id,
        msg_id=msg.id,
        from_user_id=user.id if user else 0,
        from_username=(user.username if user else None),
        text=text
    )
```


---

## 8) Data schema

- **tickets**
```json
{
  "id": "GC-20251015-8D51",
  "user_id": 578157859,
  "chat_id": -100, 
  "src_message_id": 1234,
  "text": "anh đang chat mà ko gửi được file",
  "status": "DRAFT|NEW|UPDATING|FIXED|CANCELLED",
  "priority": "P3",
  "khl_tag": null,
  "meta": { "platform": "app", "os": "Windows", "device_model": "unknown", "app_version": "unknown" },
  "attachments": [ { "type": "file", "name": "photo_xxx.jpg", "url": "https://..." } ],
  "notes": [ { "author": "578157859", "content": "mô tả bổ sung ...", "at": "..." } ],
  "group_message_id": 5678,
  "created_at": "...",
  "updated_at": "..."
}
```

- **events**
```json
{
  "ticket_id": "GC-20251015-8D51",
  "actor": "dukeng96",
  "action": "confirm|update|note|fix|cancel_via_button",
  "note": "nội dung thêm (nếu có)",
  "at": "..."
}
```

- **users**
```json
{
  "telegram_id": 578157859,
  "username": "dukeng96",
  "full_name": "Duke",
  "last_seen": "..."
}
```