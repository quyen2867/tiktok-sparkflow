import asyncio
from core.browser import get_browser
from core.tiktok import TikTokWeb, HOME_URL
from utils.config import upsert_user_account, get_userData


async def wait_for_logged_in_identity(page, timeout_ms=300000):
    deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
    last_error = None
    while asyncio.get_running_loop().time() < deadline:
        try:
            handle = await TikTokWeb(page).identity()
            return handle[1:], handle
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(.5)
    raise RuntimeError(f'Hãy hoàn thành đăng nhập/xác minh trong cửa sổ TikTok: {last_error}')


async def collect_login_result(page, context, timeout_ms=300000):
    unique_id, username = await wait_for_logged_in_identity(page, timeout_ms)
    return {'unique_id': unique_id, 'username': username,
            'cookies': await context.cookies(), 'storage_state': await context.storage_state(),
            'platform': 'tiktok'}


async def userLogin(targets=None):
    playwright, browser = await get_browser(GUI=True)
    try:
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(HOME_URL, wait_until='domcontentloaded')
        print('Hãy tự đăng nhập và hoàn thành xác minh trong Chromium. Mở trang hồ sơ của bạn nếu cần.')
        await asyncio.to_thread(input, 'Đăng nhập xong, nhấn Enter tại đây để kiểm tra và lưu: ')
        result = await collect_login_result(page, context, timeout_ms=5000)
        from core.tasks import task_run_lock
        with task_run_lock():
            existing = next((a for a in get_userData(force_reload=True) if a['unique_id'] == result['unique_id']), {})
            selected = existing.get('targets', []) if targets is None else targets
            return upsert_user_account(result['unique_id'], result['username'], result['cookies'], selected,
                                       extra={'platform': 'tiktok', 'storage_state': result['storage_state'],
                                              'account_failure': {}})

    finally:
        await browser.close()
        await playwright.stop()
