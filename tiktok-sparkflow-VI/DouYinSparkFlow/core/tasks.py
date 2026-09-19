"""Daily schedule and durable, at-most-once TikTok UI submission attempts."""
import asyncio
import hashlib
import errno
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from core.browser import get_browser
from core.friends import account_context
from core.msg_builder import build_message
from core.tiktok import TikTokWeb, TikTokError, normalize_target
from core.send_state import parse_sent_at
from utils.config import get_config, get_userData, save_userData, repo_root

logger = logging.getLogger(__name__)


def _schedule_timezone():
    name = os.getenv('SPARKFLOW_TIMEZONE') or get_config().get('timezone', 'Asia/Seoul')
    return ZoneInfo(name)


def _account_identity(user):
    return str(user.get('unique_id') or user.get('username') or 'unknown').strip()


def already_attempted(user, target, now):
    history = (user.get('message_history') or {}).get(target, {})
    # Ambiguous sends remain blocked across days until a person resolves them.
    if history.get('needsVerification'):
        return True
    for entry, key in [(history, 'sentAt'), ((user.get('failure_queue') or {}).get(target, {}), 'lastAttemptAt')]:
        at = parse_sent_at(entry.get(key), now.tzinfo)
        if at and at.date() == now.date():
            return True
    return False


def select_due_targets(user, config, now, manual=False):
    if not user.get('enabled', True) or (user.get('account_failure') or {}).get('requiresManualAction'):
        return []
    if user.get('platform') != 'tiktok':
        return []  # Do not reuse Douyin sessions or targets.
    window = config.get('dailySendWindow', {})
    selected = []
    for raw in user.get('targets', []):
        target = normalize_target(raw)
        if target in selected or already_attempted(user, target, now):
            continue
        if not manual:
            if not config.get('scheduleEnabled', False):
                continue
            if window.get('enabled'):
                start, end = int(window['startHour']), int(window['endHour'])
                if not 0 <= start < end <= 24:
                    raise ValueError('Khung giờ không hợp lệ: cần 0 <= startHour < endHour <= 24')
                # endHour=24 is midnight next day, not datetime.replace(hour=24).
                end_at = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=end)
                grace_end = end_at + timedelta(minutes=int(window.get('scheduleIntervalMinutes', 20)))
                if now > grace_end or now < _scheduled_send_time(user, target, window, now):
                    continue
            else:
                hour, minute = map(int, str(config.get('scheduleTime') or '10:00').split(':'))
                if now < now.replace(hour=hour, minute=minute, second=0, microsecond=0):
                    continue
        selected.append(target)
    return selected


def update_account(user, mutate):
    accounts = get_userData(force_reload=True)
    account = next((a for a in accounts if a.get('account_ref') == user.get('account_ref')
                    and a.get('unique_id') == user.get('unique_id')), None)
    if account is None:
        raise RuntimeError('Tài khoản đã bị xóa hoặc thay đổi trong lúc chạy')
    mutate(account)
    save_userData(accounts)
    user.update(account)


def record_attempt(user, target, message, now):
    def mutate(account):
        account.setdefault('message_history', {})[target] = {
            'message': message, 'sentAt': now.isoformat(), 'status': 'unconfirmed',
            'confirmationLevel': 'weak', 'confirmationSource': 'submission_started',
            'needsVerification': True,
        }
    update_account(user, mutate)


def record_result(user, target, message, now, error=None):
    def mutate(account):
        if error:
            category = getattr(error, 'category', 'browser_error')
            account.setdefault('failure_queue', {})[target] = {
                'message': message, 'category': category, 'reason': str(error),
                'lastAttemptAt': now.isoformat(), 'firstAttemptAt': now.isoformat(), 'attemptCount': 1,
            }
            account['account_failure'] = {
                'category': category, 'reason': str(error), 'requiresManualAction': True,
                'lastAttemptAt': now.isoformat(), 'attemptCount': 1,
                'affectedTargets': list(account.get('targets', [])),
            }
        else:
            # An outgoing DOM echo is evidence of a submission, not server delivery or streak.
            entry = account.setdefault('message_history', {}).setdefault(target, {})
            entry.update(status='unconfirmed', confirmationSource='tiktok_browser_echo',
                         confirmationLevel='weak', needsVerification=False)
            account.setdefault('failure_queue', {}).pop(target, None)
    update_account(user, mutate)


async def run_browser_tasks(active_config, browser_user_data):
    if active_config.get('useProtocolSender'):
        raise ValueError('Không hỗ trợ gửi bằng giao thức riêng; đặt useProtocolSender=false')
    for supplied in browser_user_data:
        # Re-read authorization and selections; stale dashboard requests cannot add targets.
        fresh = next((a for a in get_userData(force_reload=True)
                      if a.get('account_ref') == supplied.get('account_ref')), None)
        if not fresh:
            continue
        permitted = set(fresh.get('targets', []))
        user = dict(fresh)
        user['targets'] = [t for t in supplied.get('targets', []) if t in permitted]
        targets = select_due_targets(user, active_config, datetime.now(_schedule_timezone()), manual=True)
        if not targets:
            continue
        playwright = browser = None
        current_target = targets[0]
        message = ''
        try:
            playwright, browser = await get_browser()
            context = await account_context(browser, user)
            ui = TikTokWeb(await context.new_page(), active_config)
            await ui.open_inbox(user['unique_id'])
            for target in targets:
                current_target = target
                message = build_message(config=active_config)
                now = datetime.now(_schedule_timezone())
                await ui.send(target, message, lambda: record_attempt(user, target, message, now))
                record_result(user, target, message, now)
                logger.info('TikTok %s -> %s: tin đã hiện trên Web; chưa xác nhận giao tin hoặc streak', user['unique_id'], target)
                if target != targets[-1]:
                    await asyncio.sleep(max(1, float(active_config.get('sendStrategy', {}).get('messageIntervalSecondsMin', 30))))
        except Exception as exc:
            record_result(user, current_target, message, datetime.now(_schedule_timezone()), error=exc)
            logger.warning('Đã tạm dừng tài khoản TikTok %s: %s', user['unique_id'], exc)
        finally:
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()


async def runTasks():
    try:
        with task_run_lock():
            config = get_config(force_reload=True)
            manual = os.getenv('SPARKFLOW_MANUAL_RUN') == '1'
            refs = os.getenv('SPARKFLOW_ACCOUNT_REFS')
            allowed = set(refs.split(',')) if refs is not None else None
            users = []
            for user in get_userData(force_reload=True):
                if allowed is not None and user.get('account_ref') not in allowed:
                    continue
                targets = select_due_targets(user, config, datetime.now(_schedule_timezone()), manual)
                if targets:
                    users.append({**user, 'targets': targets})
            await run_browser_tasks(config, users)
    except TaskRunAlreadyInProgress:
        logger.info('Đang có lượt gửi khác chạy; bỏ qua lượt này')


async def scheduler_loop():
    """Local scheduler while dashboard is open; no host crontab modifications."""
    last_slot = None
    while True:
        try:
            config = get_config(force_reload=True)
            now = datetime.now(_schedule_timezone())
            slot = int(now.timestamp()) // 60
            if config.get('scheduleEnabled') and slot != last_slot:
                last_slot = slot
                await runTasks()
        except Exception:
            logger.exception('Lượt gửi theo lịch bị lỗi; hãy kiểm tra cấu hình')
        await asyncio.sleep(10)


def _scheduled_send_time(user, target_name, send_window, now):
    window_minutes = (send_window["endHour"] - send_window["startHour"]) * 60
    start_of_window = now.replace(
        hour=send_window["startHour"],
        minute=0,
        second=0,
        microsecond=0,
    )
    seed = f"{now.date().isoformat()}|{_account_identity(user)}|{target_name}"
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    offset_minutes = int.from_bytes(digest[:8], "big") % window_minutes
    interval = max(1, int(send_window.get("scheduleIntervalMinutes", 20)))
    offset_minutes = (offset_minutes // interval) * interval
    return start_of_window + timedelta(minutes=offset_minutes)

def _pid_is_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        if getattr(exc, "winerror", None) == 87 or exc.errno == errno.ESRCH:
            return False
        if exc.errno in (errno.EPERM, errno.EACCES):
            return True
        raise
    return True

class TaskRunAlreadyInProgress(RuntimeError):
    """Raised when a live task process already owns the global run lock."""

@contextmanager
def task_run_lock():
    import fcntl
    lock_path = repo_root() / "logs" / "task.run.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise TaskRunAlreadyInProgress("Đang có một lượt gửi khác chạy") from exc
        try:
            handle.seek(0)
            handle.truncate()
            handle.write(f"{os.getpid()}\n")
            handle.flush()
            yield
        finally:
            handle.seek(0)
            handle.truncate()
            handle.flush()
            fcntl.flock(handle, fcntl.LOCK_UN)
