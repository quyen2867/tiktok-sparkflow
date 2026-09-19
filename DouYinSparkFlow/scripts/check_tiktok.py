"""Check the configured DOM contract with an existing session. Never sends."""
import argparse
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.browser import get_browser
from core.friends import account_context
from core.tiktok import TikTokWeb, CHAT_URL, normalize_target
from utils.config import get_userData


async def check(account_name, target):
    account = next((a for a in get_userData() if a['unique_id'] == account_name.lstrip('@').casefold()), None)
    if not account:
        raise SystemExit('Không tìm thấy tài khoản. Hãy chạy python main.py --login trước.')
    p, browser = await get_browser(GUI=True)
    try:
        context = await account_context(browser, account)
        page = await context.new_page()
        await page.goto(CHAT_URL, wait_until='domcontentloaded')
        print('Kiểm tra cửa sổ đang mở và tự đăng nhập/xác minh. Lệnh này không gửi tin.')
        await asyncio.to_thread(input, 'Khi hộp thư đã sẵn sàng, nhấn Enter: ')
        ui = TikTokWeb(page)
        for key in ui.selectors:
            print(f'{key}: {await ui.loc(key).count()} phần tử')
        print('Tài khoản:', await ui.identity())
        print('Các chat đã tìm thấy:', await ui.scan())
        if target:
            await ui.scan(normalize_target(target))
            for key in ['chatHeaderProfile', 'composer', 'sendButton']:
                await ui.unique(key)
            print('Đã kiểm tra người nhận, ô soạn và nút gửi. Chưa gửi tin nào.')
        await asyncio.to_thread(input, 'Nhấn Enter để đóng: ')
    finally:
        await browser.close()
        await p.stop()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account', required=True)
    parser.add_argument('--target')
    args = parser.parse_args()
    asyncio.run(check(args.account, args.target))
