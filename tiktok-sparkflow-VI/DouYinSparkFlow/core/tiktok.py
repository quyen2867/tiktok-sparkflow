"""TikTok's visible Web UI only. No private API, fingerprint spoofing or retries.

Selectors are an explicit, replaceable DOM contract, not a claim that all TikTok
regions expose the same UI. Missing/ambiguous identity always stops the operation.
"""
import asyncio
import re
from urllib.parse import urlsplit, unquote

from utils.config import get_config

HOME_URL = "https://www.tiktok.com/"
CHAT_URL = "https://www.tiktok.com/messages"
DEFAULT_SELECTORS = {
    "selfProfile": '[data-e2e="profile-icon"], a[data-e2e="profile-icon"], [data-e2e="profile-icon"] a, header a[href*="/@"], [data-e2e="nav-profile"]',
    "chatList": '[data-e2e="dm-new-conversation-list"], [data-e2e="inbox-list"]',
    "chatRow": '[data-e2e="dm-new-conversation-item"]',
    "rowProfile": 'a[href*="/@"]',
    # Header DM mới: text @username trong [data-e2e="chat-uniqueid"], không phải link
    "chatHeaderProfile": '[data-e2e="chat-uniqueid"]',
    "composer": '[data-e2e="dm-new-input-editor"] [contenteditable="true"], [data-e2e="message-input-area"] [contenteditable="true"], [data-e2e="dm-new-chatbox"] [contenteditable="true"]',
    "sendButton": '[data-e2e="dm-new-send-btn"]',
    # Tin nhắn trong hội thoại mở (cả gửi + nhận); xác nhận bằng so khớp text trước/sau
    "outgoingMessage": '[data-e2e="dm-new-chat-item"]',
    "challenge": '[id*="captcha"], [class*="captcha"], iframe[src*="captcha"], [data-e2e="verify-dialog"]',
    "login": '[data-e2e="login-modal"], [data-e2e="top-login-button"]',
    "restriction": '[data-e2e="chat-restriction"], [data-e2e="message-send-error"]',
    "sendFailure": '[data-e2e="message-send-failed"]',
}


class TikTokError(RuntimeError):
    def __init__(self, category, message):
        super().__init__(message)
        self.category = category


def handle_from_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in {"", "http", "https"}:
        return None
    if parsed.netloc and parsed.hostname not in {"www.tiktok.com", "tiktok.com"}:
        return None
    match = re.fullmatch(r"/@([A-Za-z0-9._]{1,24})/?", unquote(parsed.path))
    return '@' + match.group(1).casefold() if match else None


def normalize_target(value):
    raw = str(value).strip()
    if not re.fullmatch(r"@[A-Za-z0-9._]{1,24}", raw):
        raise ValueError("Nhập chính xác @username, mỗi dòng một người; không dùng tên hiển thị")
    return raw.casefold()


class TikTokWeb:
    def __init__(self, page, config=None):
        self.page = page
        self.http_block = None
        page.on("response", self.observe_response)
        cfg = (config or get_config()).get("tiktok", {})
        self.selectors = {**DEFAULT_SELECTORS, **cfg.get("selectors", {})}
        self.timeout = int(cfg.get("timeoutMs", 15000))
        self.max_scrolls = max(1, min(100, int(cfg.get("maxScrolls", 30))))

    def observe_response(self, response):
        host = urlsplit(response.url).hostname or ""
        if (host == "tiktok.com" or host.endswith(".tiktok.com")) and response.status in (403, 429):
            self.http_block = response.status

    def loc(self, name):
        return self.page.locator(self.selectors[name])

    async def visible(self, name):
        for loc in await self.loc(name).all():
            if await loc.is_visible():
                return True
        return False

    async def guard(self):
        if self.http_block:
            raise TikTokError("account_restricted", f"TikTok trả về lỗi HTTP {self.http_block}; đã dừng gửi")
        host = urlsplit(self.page.url).hostname
        if host not in {"www.tiktok.com", "tiktok.com"}:
            raise TikTokError("navigation", "Trang đang mở không thuộc TikTok; đã dừng thao tác")
        if await self.visible("challenge"):
            raise TikTokError("verification_required", "Hãy tự hoàn thành xác minh trên TikTok rồi đăng nhập lại")
        if '/login' in urlsplit(self.page.url).path or await self.visible("login"):
            raise TikTokError("login_required", "Hãy tự đăng nhập TikTok trong cửa sổ trình duyệt")
        if await self.visible("restriction") or await self.visible("sendFailure"):
            raise TikTokError("account_restricted", "TikTok báo hạn chế hoặc lỗi nhắn tin; đã tạm dừng gửi")
        # Restrict text detection to UI alerts, not user-authored chat bubbles.
        alerts = self.page.locator('[role="alert"], [role="dialog"]')
        for item in await alerts.all():
            if not await item.is_visible():
                continue
            text = (await item.inner_text()).casefold()
            if any(word in text for word in ("too many attempts", "too fast", "temporarily suspended", "verify to continue", "quá nhiều", "tạm thời bị", "verify you are human")):
                raise TikTokError("account_restricted", "TikTok yêu cầu bạn xử lý; đã tạm dừng gửi")

    async def unique(self, name):
        items = [item for item in await self.loc(name).all() if await item.is_visible()]
        if len(items) != 1:
            raise TikTokError("selector", f"Cần đúng một phần tử {name} hiển thị, nhưng tìm thấy {len(items)}. Hãy kiểm tra bộ chọn giao diện.")
        return items[0]

    async def identity(self):
        await self.guard()
        # 1. Thử selector chuẩn (chịu được 2 icon trùng do TikTok render 2 lần)
        try:
            for link in await self.loc("selfProfile").all():
                try:
                    if not await link.is_visible():
                        continue
                    handle = handle_from_url(await link.get_attribute('href') or '')
                    if handle:
                        return handle
                except Exception:
                    continue
        except Exception:
            pass
        # 2. Fallback: quét mọi link /@xxx trên header (TikTok mới đổi data-e2e)
        try:
            candidates = set()
            for link in await self.page.locator('header a[href*="/@"], div[data-e2e="profile-icon"] a, a[data-e2e="profile-icon"], [data-e2e="nav-profile"] a, a[href*="/@"]').all():
                try:
                    if not await link.is_visible():
                        continue
                    h = handle_from_url(await link.get_attribute('href') or '')
                    if h:
                        candidates.add(h)
                except Exception:
                    continue
            # Bỏ các link follow gợi ý (/foryou... không có), nếu chỉ còn 1 ứng viên thì lấy
            if len(candidates) == 1:
                return next(iter(candidates))
        except Exception:
            pass
        # 3. Fallback cuối: nếu đang ở trang profile của chính mình thì lấy từ URL
        url_handle = handle_from_url(self.page.url)
        if url_handle:
            return url_handle
        raise TikTokError("login_required", "Không xác minh được tài khoản (không thấy icon profile hay URL /@...). Hãy mở trang Hồ sơ của bạn rồi bấm Lưu lại.")

    async def open_inbox(self, expected_account=None):
        response = await self.page.goto(CHAT_URL, wait_until="domcontentloaded", timeout=45000)
        if response and response.status in (403, 429):
            raise TikTokError("account_restricted", f"TikTok trả về lỗi HTTP {response.status}; đã dừng gửi")
        try:
            await self.loc('chatList').first.wait_for(state='attached', timeout=self.timeout)
        except Exception:
            await self.guard()
            raise TikTokError('selector', 'Không mở được hộp thư. Hãy kiểm tra đăng nhập và bộ chọn chatList.')
        await self.guard()
        if expected_account and await self.identity() != normalize_target('@' + expected_account.lstrip('@')):
            raise TikTokError('identity_mismatch', 'Tài khoản đang đăng nhập không trùng với tài khoản đã cấu hình')

    async def row_handle(self, row):
        ordered = []
        for link in await row.locator(self.selectors['rowProfile']).all():
            try:
                href = await link.get_attribute('href') or ''
            except Exception:
                continue
            if '/video/' in href:
                continue  # link video preview, không phải profile người gửi
            try:
                handle = handle_from_url(href)
            except Exception:
                continue
            if handle:
                ordered.append(handle)
        if not ordered:
            return None
        # TikTok mới: mỗi dòng có 2 link người gửi (avatar+tên) + link video.
        # Nếu 2 link đầu cùng 1 người thì đó chắc chắn là người gửi.
        if len(ordered) >= 2 and ordered[0] == ordered[1]:
            return ordered[0]
        # Dự phòng: thử lấy handle trong vùng tiêu đề (inbox-title) trước
        try:
            for sel in ('[data-e2e="inbox-title"] a[href*="/@"], [data-e2e="inbox-content"] a[href*="/@"]',):
                for link in await row.locator(sel).all():
                    href = await link.get_attribute('href') or ''
                    if '/video/' in href:
                        continue
                    handle = handle_from_url(href)
                    if handle:
                        return handle
        except Exception:
            pass
        uniq = list(dict.fromkeys(ordered))
        return uniq[0] if uniq else None

    async def _read_open_uniqueid(self):
        await self.loc('chatHeaderProfile').first.wait_for(state='attached', timeout=self.timeout)
        raw = await self.loc('chatHeaderProfile').first.inner_text()
        raw = (raw or '').strip()
        if not raw:
            return ''
        if not raw.startswith('@'):
            raw = '@' + raw
        try:
            return normalize_target(raw)
        except ValueError:
            return raw.casefold()

    async def _open_row(self, index):
        rows = await self.loc('chatRow').all()
        if index >= len(rows):
            raise TikTokError('friend_not_found', 'Hết danh sách chat để kiểm tra')
        row = rows[index]
        try:
            await row.evaluate('(el) => el.click()')
        except Exception:
            await row.click(timeout=self.timeout)
        handle = await self._read_open_uniqueid()
        return handle

    async def scan(self, target=None):
        try:
            await self.loc('chatList').first.wait_for(state='attached', timeout=self.timeout)
        except Exception:
            pass
        await self.guard()
        found = {}
        total = len(await self.loc('chatRow').all())
        for index in range(min(total, self.max_scrolls * 20)):
            await self.guard()
            try:
                handle = await self._open_row(index)
            except TikTokError:
                raise
            except Exception:
                continue
            if handle:
                found.setdefault(handle, index)
            if target and handle == target:
                return target
        # Thử cuộn thêm nếu chưa thấy target (list dài)
        if target and target not in found:
            try:
                await self.page.evaluate('''() => {
                    const el = document.querySelector('[data-e2e="dm-new-conversation-list"]');
                    if (el) el.scrollTop = el.scrollHeight;
                }''')
                await asyncio.sleep(1.5)
            except Exception:
                pass
            total2 = len(await self.loc('chatRow').all())
            for index in range(total, total2):
                await self.guard()
                try:
                    handle = await self._open_row(index)
                except Exception:
                    continue
                if handle:
                    found.setdefault(handle, index)
                if target and handle == target:
                    return target
        if target:
            raise TikTokError('friend_not_found', f'Không tìm thấy {target} trong {len(found)} hội thoại đã mở; hệ thống không tạo chat mới')
        return sorted(found)

    async def verify_recipient(self, target):
        await self.guard()
        handle = await self._read_open_uniqueid()
        if handle != target:
            raise TikTokError('identity_mismatch', 'Người nhận trong chat đang mở không trùng @username đã chọn')

    async def outgoing_count(self, message):
        count = 0
        for item in await self.loc('outgoingMessage').all():
            try:
                if (await item.inner_text()).strip() == message.strip():
                    count += 1
            except Exception:
                continue
        return count

    async def send(self, target, message, before_submit):
        if not message.strip():
            raise TikTokError('empty_message', 'Nội dung tin nhắn không được để trống')
        await self.scan(target)
        composers = [c for c in await self.loc('composer').all()]
        composer = None
        for c in composers:
            try:
                await c.wait_for(state='attached', timeout=3000)
                composer = c
                break
            except Exception:
                continue
        if composer is None:
            raise TikTokError('selector', 'Không thấy ô soạn tin. Hãy kiểm tra bộ chọn composer.')
        try:
            draft = await composer.inner_text()
        except Exception:
            draft = ''
        if draft.strip():
            raise TikTokError('existing_draft', 'Chat đang có tin nháp; đã dừng để giữ nguyên nội dung của bạn')
        before = await self.outgoing_count(message)
        try:
            await composer.click(timeout=8000)
        except Exception:
            await composer.evaluate('(el) => el.focus()')
        await self.page.keyboard.type(message, delay=15)
        await asyncio.sleep(1.2)
        # Nút Gửi chỉ hiện sau khi đã gõ chữ -> tìm sau khi gõ
        button = None
        try:
            await self.loc('sendButton').first.wait_for(state='attached', timeout=8000)
            buttons = await self.loc('sendButton').all()
            button = buttons[0] if buttons else None
        except Exception:
            button = None
        if button is None:
            raise TikTokError('selector', 'Không thấy nút gửi. Hãy kiểm tra bộ chọn sendButton.')
        await self.verify_recipient(target)
        # Write-ahead journal: crashes/timeouts after this point must never auto-resend.
        before_submit()
        try:
            await button.click(timeout=self.timeout)
        except Exception:
            await button.evaluate('(el) => el.click()')
        for _ in range(20):
            await self.verify_recipient(target)
            try:
                empty = not (await composer.inner_text()).strip()
            except Exception:
                empty = True
            if await self.outgoing_count(message) > before and empty:
                return 'browser_echo'
            await asyncio.sleep(.5)
        raise TikTokError('send_unconfirmed', 'Đã thử gửi nhưng chưa thấy tin hiện trên Web. Hãy kiểm tra thủ công trên TikTok.')
