import copy
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from core import tasks
from core.tiktok import TikTokWeb, TikTokError, handle_from_url, normalize_target
from utils.config import DEFAULT_CONFIG, normalize_unique_id
from webui import ops


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 18, 17, 59, tzinfo=ZoneInfo('Asia/Seoul'))
        self.config = copy.deepcopy(DEFAULT_CONFIG)
        self.config['scheduleEnabled'] = True
        self.user = {'unique_id': 'owner123', 'account_ref': 'acc-1', 'platform': 'tiktok',
                     'targets': ['@friend123'], 'enabled': True}

    def test_usernames_preserve_letters_digits_and_exact_match(self):
        self.assertEqual('alice123', normalize_unique_id('@Alice123'))
        self.assertNotEqual(normalize_unique_id('alice123'), normalize_unique_id('bob123'))
        self.assertEqual('@friend123', handle_from_url('https://www.tiktok.com/@Friend123'))
        self.assertIsNone(handle_from_url('https://evil.example/@friend123'))
        with self.assertRaises(ValueError):
            normalize_target('Friend display name')

    def test_schedule_requires_opt_in_and_tiktok_account(self):
        self.assertEqual(['@friend123'], tasks.select_due_targets(self.user, self.config, self.now))
        self.config['scheduleEnabled'] = False
        self.assertEqual([], tasks.select_due_targets(self.user, self.config, self.now))
        self.assertEqual(['@friend123'], tasks.select_due_targets(self.user, self.config, self.now, manual=True))
        self.user.pop('platform')
        self.assertEqual([], tasks.select_due_targets(self.user, self.config, self.now, manual=True))

    def test_unconfirmed_submission_never_auto_retries_even_next_day(self):
        self.user['message_history'] = {'@friend123': {'sentAt': self.now.isoformat(), 'needsVerification': True}}
        for now in (self.now, self.now + timedelta(days=1)):
            self.assertEqual([], tasks.select_due_targets(self.user, self.config, now, manual=True))

    def test_browser_echo_only_once_per_day_and_next_day_eligible(self):
        self.user['message_history'] = {'@friend123': {'sentAt': self.now.isoformat(),
            'confirmationSource': 'tiktok_browser_echo', 'needsVerification': False}}
        self.assertEqual([], tasks.select_due_targets(self.user, self.config, self.now, manual=True))
        self.assertEqual(['@friend123'], tasks.select_due_targets(self.user, self.config, self.now + timedelta(days=1)))

    def test_account_pause_persists_across_days_and_manual_trigger(self):
        self.user['account_failure'] = {'requiresManualAction': True, 'lastAttemptAt': self.now.isoformat()}
        self.assertEqual([], tasks.select_due_targets(self.user, self.config, self.now + timedelta(days=2), manual=True))

    def test_midnight_end_and_schedule_consistency(self):
        window = {**self.config['dailySendWindow'], 'endHour': 24}
        self.config['dailySendWindow'] = window
        now = self.now.replace(hour=23, minute=59)
        self.assertEqual(['@friend123'], tasks.select_due_targets(self.user, self.config, now))
        self.assertEqual(tasks._scheduled_send_time(self.user, '@friend123', window, now),
                         ops._scheduled_send_time(self.user, '@friend123', window, now))

    def test_fixed_time_and_disabled_account(self):
        self.config['dailySendWindow']['enabled'] = False
        self.config['scheduleTime'] = '18:00'
        self.assertEqual([], tasks.select_due_targets(self.user, self.config, self.now))
        self.assertEqual(['@friend123'], tasks.select_due_targets(self.user, self.config, self.now.replace(hour=18)))
        self.user['enabled'] = False
        self.assertEqual([], tasks.select_due_targets(self.user, self.config, self.now, manual=True))

    def test_lock_prevents_concurrent_runs_and_releases(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(tasks, 'repo_root', return_value=Path(temp)), patch.object(ops, 'repo_root', return_value=Path(temp)):
            with tasks.task_run_lock():
                self.assertTrue(ops.task_run_lock_status()['running'])
                with self.assertRaises(tasks.TaskRunAlreadyInProgress):
                    with tasks.task_run_lock():
                        pass
            self.assertFalse(ops.task_run_lock_status()['running'])
            with tasks.task_run_lock():
                pass

    def test_write_ahead_journal_survives_result_failure(self):
        accounts = [copy.deepcopy(self.user)]
        def save(items):
            accounts[:] = copy.deepcopy(items)
        with patch.object(tasks, 'get_userData', side_effect=lambda **kw: copy.deepcopy(accounts)), patch.object(tasks, 'save_userData', side_effect=save):
            tasks.record_attempt(self.user, '@friend123', 'Hello', self.now)
        self.assertTrue(accounts[0]['message_history']['@friend123']['needsVerification'])
        self.assertTrue(tasks.already_attempted(accounts[0], '@friend123', self.now + timedelta(days=1)))

    def test_private_sender_rejected(self):
        import asyncio
        with self.assertRaises(ValueError):
            asyncio.run(tasks.run_browser_tasks({'useProtocolSender': True}, []))


class BrowserContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.p = await async_playwright().start()
        self.browser = await self.p.chromium.launch()
        self.page = await self.browser.new_page()
        html = (Path(__file__).parent / 'fixtures/tiktok-inbox.html').read_text()
        await self.page.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html', body=html))
        await self.page.goto('https://www.tiktok.com/messages')
        self.ui = TikTokWeb(self.page, {'tiktok': {'timeoutMs': 300}})

    async def asyncTearDown(self):
        await self.browser.close()
        await self.p.stop()

    async def test_discovery_uses_handles_not_duplicate_display_names(self):
        self.assertEqual(['@friend123', '@other123'], await self.ui.scan())
        self.assertEqual('@owner123', await self.ui.identity())

    async def test_send_journals_before_one_click_and_observes_echo(self):
        calls = []
        result = await self.ui.send('@friend123', 'Hello 🔥', lambda: calls.append('journal'))
        self.assertEqual(['journal'], calls)
        self.assertEqual('browser_echo', result)
        self.assertEqual(1, await self.page.evaluate('window.sent'))

    async def test_journal_write_failure_prevents_click(self):
        def failed_write():
            raise OSError('disk full')
        with self.assertRaises(OSError):
            await self.ui.send('@friend123', 'Hello', failed_write)
        self.assertEqual(0, await self.page.evaluate('window.sent'))

    async def test_wrong_recipient_stops_before_typing(self):
        await self.page.evaluate("window.wrongRecipient = true; document.querySelector('[data-e2e=chat-header] a').href='/@wrong'")
        with self.assertRaises(TikTokError) as caught:
            await self.ui.send('@friend123', 'Hello', lambda: None)
        self.assertEqual('identity_mismatch', caught.exception.category)
        self.assertEqual(0, await self.page.evaluate('window.sent'))

    async def test_challenge_and_429_stop_without_click(self):
        await self.page.evaluate("document.body.insertAdjacentHTML('beforeend','<div id=captcha>Verify</div>')")
        with self.assertRaises(TikTokError) as caught:
            await self.ui.send('@friend123', 'Hello', lambda: None)
        self.assertEqual('verification_required', caught.exception.category)
        await self.page.evaluate("document.querySelector('#captcha').remove()")
        self.ui.observe_response(type('R', (), {'url':'https://www.tiktok.com/test','status':429})())
        with self.assertRaises(TikTokError) as caught:
            await self.ui.guard()
        self.assertEqual('account_restricted', caught.exception.category)
        self.assertEqual(0, await self.page.evaluate('window.sent'))

    async def test_existing_draft_is_preserved(self):
        await self.page.locator('[contenteditable]').fill('My unfinished message')
        with self.assertRaises(TikTokError) as caught:
            await self.ui.send('@friend123', 'Hello', lambda: None)
        self.assertEqual('existing_draft', caught.exception.category)
        self.assertEqual('My unfinished message', await self.page.locator('[contenteditable]').inner_text())

    async def test_missing_echo_never_clicks_twice(self):
        await self.page.evaluate('window.suppressEcho = true')
        with patch('core.tiktok.asyncio.sleep', new=AsyncMock()):
            with self.assertRaises(TikTokError) as caught:
                await self.ui.send('@friend123', 'Hello', lambda: None)
        self.assertEqual('send_unconfirmed', caught.exception.category)
        self.assertEqual(1, await self.page.evaluate('window.sent'))

    async def test_missing_or_duplicate_row_is_not_guessed(self):
        with self.assertRaises(TikTokError):
            await self.ui.scan('@missing')
        await self.page.evaluate("const row=document.querySelector('[data-e2e=chat-list-item]');row.parentNode.appendChild(row.cloneNode(true))")
        with self.assertRaises(TikTokError) as caught:
            await self.ui.scan('@friend123')
        self.assertEqual('identity_mismatch', caught.exception.category)
        self.assertEqual(0, await self.page.evaluate('window.sent'))


class WebIntegrationTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from webui import app as app_module
        self.mod = app_module
        self.client = TestClient(app_module.app)
        self.account = {'account_ref': 'acc-test', 'unique_id': 'owner123', 'username': '@owner123',
                        'platform': 'tiktok', 'targets': ['@friend123'], 'cookies': [{'secret': 'do-not-render'}],
                        'storage_state': {'secret': 'do-not-render'}, 'account_failure': {}, 'enabled': True}

    def test_dashboard_with_real_account_and_runtime_config_renders(self):
        with patch.object(self.mod, 'current_principal', return_value={'username':'admin','role':'admin'}), patch.object(self.mod, 'current_user', return_value='admin'), patch.object(self.mod, 'get_userData', return_value=[self.account]), patch.object(ops, 'get_userData', return_value=[self.account]):
            response = self.client.get('/')
        self.assertEqual(200, response.status_code)
        self.assertIn('scheduleEnabled', response.text)
        self.assertIn('resolve-tiktok', response.text)
        self.assertNotIn('do-not-render', response.text)

    def test_resolution_requires_csrf_and_selected_target(self):
        with patch.object(self.mod, 'current_user', return_value='admin'), patch.object(self.mod, 'get_userData', return_value=[self.account]):
            result = self.client.post('/accounts/owner123/resolve-tiktok', data={'action':'resume'}, follow_redirects=False)
            self.assertEqual(403, result.status_code)
            with patch.object(self.mod, 'validate_csrf', return_value=True), patch.object(self.mod, 'save_userData') as save:
                result = self.client.post('/accounts/owner123/resolve-tiktok', data={'action':'not_sent','target':'@unselected'}, follow_redirects=False)
                self.assertEqual(400, result.status_code)
                save.assert_not_called()

    def test_resolution_clears_ambiguous_target_only_on_explicit_action(self):
        self.account['message_history'] = {'@friend123': {'needsVerification': True}}
        with patch.object(self.mod, 'current_user', return_value='admin'), patch.object(self.mod, 'get_userData', return_value=[self.account]), patch.object(self.mod, 'validate_csrf', return_value=True), patch.object(self.mod, 'save_userData') as save:
            result = self.client.post('/accounts/owner123/resolve-tiktok', data={'action':'not_sent','target':'@friend123'}, follow_redirects=False)
            self.assertEqual(303, result.status_code)
            self.assertNotIn('@friend123', save.call_args.args[0][0]['message_history'])

    def test_helper_rejects_browser_origin_and_wrong_host(self):
        from fastapi.testclient import TestClient
        import login_desktop_server
        helper = TestClient(login_desktop_server.app)
        self.assertEqual(403, helper.post('/export', headers={'origin':'https://www.tiktok.com'}).status_code)
        self.assertEqual(403, helper.post('/export', headers={'host':'evil.example'}).status_code)
        self.assertEqual(200, helper.get('/health').status_code)

    def test_relogin_refuses_different_account(self):
        with patch.object(self.mod, 'get_userData', return_value=[self.account]):
            with self.assertRaisesRegex(RuntimeError, 'khác với tài khoản'):
                self.mod.save_exported_login_result({'unique_id':'other123','username':'@other123','cookies':[{}]}, relogin_account_ref='acc-test')
