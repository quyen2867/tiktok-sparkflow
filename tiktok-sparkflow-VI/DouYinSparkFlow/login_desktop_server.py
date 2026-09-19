"""Local, visible login window. All login and verification is done by the user."""
import asyncio
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from core.browser import get_browser
from core.login import collect_login_result
from core.tiktok import HOME_URL


class LoginDesktop:
    def __init__(self):
        self.playwright = self.browser = self.context = self.page = None
        self.lock = asyncio.Lock()

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.playwright = self.browser = self.context = self.page = None

    async def open(self):
        await self.close()
        self.playwright, self.browser = await get_browser(GUI=True)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        await self.page.goto(HOME_URL, wait_until='domcontentloaded')


manager = LoginDesktop()


@asynccontextmanager
async def lifespan(app):
    yield
    await manager.close()


app = FastAPI(lifespan=lifespan)


@app.middleware('http')
async def local_only(request: Request, call_next):
    # Browser pages must not be able to export a local session through this helper.
    if request.headers.get('origin') or request.headers.get('sec-fetch-site'):
        return JSONResponse({'error': 'Hãy thao tác qua bảng điều khiển đã đăng nhập'}, status_code=403)
    if request.client and request.client.host not in {'127.0.0.1', '::1', 'testclient'}:
        return JSONResponse({'error': 'Chỉ cho phép truy cập từ máy này'}, status_code=403)
    if request.url.hostname not in {'127.0.0.1', 'localhost', '::1', 'testserver'}:
        return JSONResponse({'error': 'Địa chỉ máy chủ không hợp lệ'}, status_code=403)
    try:
        async with manager.lock:
            return await call_next(request)
    except Exception as exc:
        return JSONResponse({'ok': False, 'error': str(exc)}, status_code=400)


@app.get('/health')
@app.get('/preflight')
async def health():
    return {'ok': True, 'route': 'direct'}


@app.post('/open-login')
async def open_login():
    await manager.open()
    return {'ok': True}


@app.post('/close')
@app.post('/reset')
async def close():
    await manager.close()
    return {'ok': True}


@app.post('/focus')
async def focus():
    if manager.page:
        await manager.page.bring_to_front()
    return {'ok': True}


@app.get('/status')
async def status():
    running = bool(manager.page and not manager.page.is_closed())
    result = {}
    if running:
        try:
            result = await collect_login_result(manager.page, manager.context, timeout_ms=3000)
        except Exception:
            pass
    return {'running': running, 'logged_in': bool(result), 'unique_id': result.get('unique_id', ''),
            'username': result.get('username', ''), 'current_url': manager.page.url if running else '',
            'network': {'mode': 'direct', 'route': 'direct'}}


@app.post('/export')
async def export():
    if not manager.page:
        raise RuntimeError('Hãy mở cửa sổ đăng nhập trước')
    return {'ok': True, 'result': await collect_login_result(manager.page, manager.context, timeout_ms=8000)}


@app.get('/qr')
@app.post('/refresh-qr')
async def qr():
    return JSONResponse({'ok': False, 'error': 'Hãy đăng nhập, quét QR và xác minh TikTok trong cửa sổ Chromium trên máy Mac'}, status_code=409)


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=18090)
