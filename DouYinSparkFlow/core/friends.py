"""Discover existing TikTok one-to-one conversations by exact public username."""
from core.browser import get_browser
from core.tiktok import TikTokWeb


async def account_context(browser, account):
    state = account.get('storage_state')
    context = await browser.new_context(storage_state=state) if state else await browser.new_context()
    if not state:
        await context.add_cookies(account.get('cookies') or [])
    return context


async def fetch_account_friends(account):
    playwright, browser = await get_browser()
    try:
        context = await account_context(browser, account)
        ui = TikTokWeb(await context.new_page())
        await ui.open_inbox(account['unique_id'])
        return await ui.scan()
    finally:
        await browser.close()
        await playwright.stop()
