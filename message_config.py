"""Centralized message templates (HTML) for GoConnect bot.
All dynamic fields are formatted with .format(...). Use HTML parse mode for templates.
"""

# ── User prompts / replies (HTML) ─────────────────────────────────────────────
START = (
    """
<b>Dạ em là Trợ lý GoConnect</b>.
Em có thể hướng dẫn anh/chị cách sử dụng hoặc hỗ trợ các sự cố. Anh/chị cần em giúp gì ạ?
"""
)

HELP = (
    """
<b>/start</b> – reset & giới thiệu
<b>/help</b> – trợ giúp
<b>/cancel</b> – hủy các phiếu nháp đang mở

Cứ nhắn câu hỏi hoặc mô tả sự cố, em sẽ hỗ trợ ạ.
"""
)

SOOTHING_ASK_ENV = (
    """
Dạ, em rất tiếc vì sự cố anh/chị gặp phải. Anh/chị đang sử dụng bản <b>web</b> hay <b>app</b>, và trên <b>thiết bị nào</b> ạ?
"""
)

NEED_INFO_USER = (
    """
Để xử lý nhanh hơn, anh/chị cho em xin thêm: thiết bị, hệ điều hành, phiên bản app, bước tái hiện và ảnh/chụp màn hình ạ.
"""
)

FIXED_USER = (
    """
Anh/chị ơi, sự cố vừa rồi đã được đội xử lý xong. Anh/chị thử lại giúp em xem đã ổn chưa ạ. Em cảm ơn anh/chị!
"""
)

QNA_BUSY = "Em xin lỗi, hệ thống hỏi đáp đang bận. Anh/chị vui lòng thử lại giúp em ạ."
QNA_NOT_FOUND = "Em xin lỗi, hiện em chưa tìm được thông tin phù hợp trong kho kiến thức ạ."

# ── Group templates (HTML) ───────────────────────────────────────────────────
GROUP_BUG_TEMPLATE = (
    """
<b>🧰 [BUG]</b> <code>{ticket_id}</code>

<b>Từ:</b> @{username} (<code>{user_id}</code>)

<b>Nội dung:</b> {text}

<b>Thiết bị/phiên bản:</b> {platform} | {os} | {app_version}

<b>Đính kèm:</b>
{attachments}

<b>Thời điểm:</b> {time_utc}
"""
)

GROUP_FIX_SUFFIX = (
    """


<b>🟢 Đã khắc phục</b> và đã nhắn lại người dùng.
"""
)

# ── Ticket preview to user (HTML) ─────────────────────────────────────────────
TICKET_PREVIEW_HEADER = (
    """
<b>📝 Em xin phép khởi tạo phiếu báo hỏng cho anh/chị</b>:


<b>Mã phiếu:</b> <code>{ticket_id}</code>

<b>Tóm tắt:</b> {text}

<b>Thiết bị/phiên bản:</b> {platform} | {os} | {app_version}

<b>Đính kèm:</b>
{attachments}
"""
)

TICKET_PREVIEW_FOOTER = (
    """

Nếu anh/chị muốn đính kèm thêm thông tin (ảnh/video/bước tái hiện), hãy bấm <b>Cập nhật phiếu</b>.
Nếu muốn gửi phiếu ngay đến team kỹ thuật, hãy bấm <b>Xác nhận phiếu</b>.
"""
)

# ── LLM prompts (escape JSON braces with double {{ }}) ───────────────────────
CLASSIFIER_PROMPT = (
    """
Bạn là bộ phân loại tin nhắn cho trợ lý hỗ trợ GoConnect. Phân loại:
- BUG: người dùng mô tả sự cố/lỗi/không làm được.
- QNA: hỏi cách dùng/thông tin.
Chỉ trả JSON một dòng: {{"class": "BUG|QNA", "confidence": 0..1}}.
Văn bản: "{text}"
"""
)

ENTITY_PROMPT = (
    """
Nhiệm vụ: trích xuất thông tin thiết bị từ câu của người dùng về môi trường sử dụng GoConnect.
Trả JSON một dòng với các khóa: {{ "platform": "web|app|unknown", "os": "Windows|macOS|iOS|Android|Linux|unknown", "device_model": "...|unknown", "app_version": "...|unknown" }}.
Văn bản: "{text}"
"""
)