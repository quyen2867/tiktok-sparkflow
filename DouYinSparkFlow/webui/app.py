import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import urllib.error
import urllib.request
from urllib.parse import quote
from contextlib import asynccontextmanager

import uvicorn
import websockets
from websockets.exceptions import ConnectionClosed
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from core.friends import fetch_account_friends
from core.send_state import history_entry_is_strong_confirmed_today, parse_sent_at
from core.tasks import run_browser_tasks, task_run_lock, scheduler_loop, TaskRunAlreadyInProgress
from core.tiktok import normalize_target
from zoneinfo import ZoneInfo
from utils.config import (
    get_app_settings,
    get_config,
    get_userData,
    normalize_unique_id,
    save_app_settings,
    save_config,
    save_userData,
    upsert_user_account,
)
from webui.auth import (
    bootstrap_admin_password,
    clear_session,
    csrf_token,
    current_user,
    current_principal,
    is_bootstrapped,
    is_https_request,
    issue_session,
    update_admin_password,
    validate_csrf,
    verify_password,
)
from webui.users import (
    UserStoreError,
    account_by_ref,
    account_by_unique_id,
    all_assigned_refs,
    can_access_account,
    create_web_user,
    delete_web_user,
    ensure_account_refs,
    get_visible_accounts,
    get_web_users,
    remove_account_refs_from_users,
    update_web_user,
)
from webui.login_lock import (
    begin_expiration as begin_login_expiration,
    begin_force_reset as begin_login_force_reset,
    begin_release as begin_login_release,
    cancel_request as cancel_login_request,
    finish_transition as finish_login_transition,
    get_lock as get_login_lock,
    get_workspace_state,
    heartbeat as heartbeat_login,
    owns as owns_login_lock,
    request_workspace,
    workspace_status,
)
from webui.ops import (
    TASK_ALREADY_RUNNING,
    get_overview_snapshot,
    get_ops_snapshot,
    read_log_tail,
    refresh_proxy,
    restart_proxy,
    run_failed_retry_now,
    run_task_now,
    run_unsent_retry_now,
    task_run_lock_status,
    sync_daily_schedule_from_config,
    update_daily_schedule,
)

logger = logging.getLogger(__name__)


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
DEBUG_ARTIFACTS_DIR = BASE_DIR.parent / "logs" / "debug_artifacts"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _dedupe_targets(values):
    seen = set()
    result = []
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _split_target_entries(values):
    expanded = []
    for value in values:
        raw = str(value).replace(",", "\n")
        expanded.extend(raw.splitlines())
    return _dedupe_targets(expanded)


def extract_targets_from_form(form):
    if hasattr(form, "getlist"):
        checkbox_targets = _split_target_entries(form.getlist("targets"))
        if checkbox_targets:
            return checkbox_targets
    raw_targets = str(form.get("targets", ""))
    return _split_target_entries([raw_targets])


def find_account(accounts, unique_id):
    normalized = normalize_unique_id(unique_id)
    for account in accounts:
        if normalize_unique_id(account.get("unique_id")) == normalized:
            return account
    return None


def is_account_enabled(account):
    return bool(account.get("enabled", True))


def coerce_int(value, default, minimum=0):
    try:
        return max(minimum, int(str(value).strip()))
    except (TypeError, ValueError):
        return max(minimum, int(default))


def _schedule_timezone():
    return ZoneInfo(os.getenv("SPARKFLOW_TIMEZONE") or get_config().get("timezone", "Asia/Seoul"))


def _parse_sent_at(raw_value):
    return parse_sent_at(raw_value, _schedule_timezone())


def _history_entry_strong_confirmed_today(entry):
    return history_entry_is_strong_confirmed_today(
        entry,
        datetime.now(_schedule_timezone()),
    )


def _target_sent_today(account, target_name):
    entry = dict(account.get("message_history") or {}).get(target_name) or {}
    return _history_entry_strong_confirmed_today(entry)


def _target_unconfirmed_today(account, target_name):
    entry = dict(account.get("message_history") or {}).get(target_name) or {}
    sent_at = _parse_sent_at(entry.get("sentAt"))
    if sent_at and sent_at.date() == datetime.now(_schedule_timezone()).date() and not _history_entry_strong_confirmed_today(entry):
        return True
    failure_entry = dict(account.get("failure_queue") or {}).get(target_name) or {}
    last_attempt_at = _parse_sent_at(failure_entry.get("lastAttemptAt"))
    return bool(
        last_attempt_at
        and last_attempt_at.date() == datetime.now(_schedule_timezone()).date()
        and str(failure_entry.get("category") or "") == "send_unconfirmed"
    )


def mark_target_unconfirmed(account, target_name, *, reason="manual_reset_possible_false_positive", force=False):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    history = dict(account.get("message_history") or {})
    existing = dict(history.get(target_name) or {})
    sent_at = _parse_sent_at(existing.get("sentAt"))
    today = datetime.now(_schedule_timezone()).date()
    if existing and sent_at and sent_at.date() != today and not force:
        return False
    if existing and _history_entry_strong_confirmed_today(existing) and not force:
        return False

    previous_status = existing.get("status") or ("legacy_sentAt_only" if existing else "missing_history")
    message = str(existing.get("message") or "")
    history[target_name] = {
        **existing,
        "message": message,
        "sentAt": existing.get("sentAt") or now,
        "status": "unconfirmed",
        "confirmationLevel": existing.get("confirmationLevel") or "legacy",
        "confirmationSource": existing.get("confirmationSource") or "manual_reset",
        "confirmationDetail": existing.get("confirmationDetail") or "Bạn đã đánh dấu cần kiểm tra trước khi gửi lại.",
        "needsVerification": True,
        "resetAt": now,
        "resetReason": reason,
        "previousStatus": previous_status,
    }
    account["message_history"] = history

    queue = dict(account.get("failure_queue") or {})
    existing_failure = dict(queue.get(target_name) or {})
    queue[target_name] = {
        "category": "send_unconfirmed",
        "reason": reason,
        "message": message,
        "firstAttemptAt": existing_failure.get("firstAttemptAt") or now,
        "lastAttemptAt": now,
        "attemptCount": int(existing_failure.get("attemptCount") or 0) + 1,
        "lastRunMode": "manual_reset",
        "confirmationLevel": history[target_name].get("confirmationLevel"),
        "confirmationSource": history[target_name].get("confirmationSource"),
    }
    account["failure_queue"] = queue
    return True


def login_desktop_api_url():
    settings = get_app_settings(force_reload=True)
    configured = os.getenv("SPARKFLOW_LOGIN_DESKTOP_API_URL") or settings.get("login_desktop_api_url")
    return str(configured or "http://127.0.0.1:18090").rstrip("/")


def login_desktop_display_mode() -> str:
    settings = get_app_settings(force_reload=True)
    configured = os.getenv("SPARKFLOW_LOGIN_DESKTOP_MODE") or settings.get("login_desktop_mode")
    mode = str(configured or ("native" if os.name == "nt" else "novnc")).strip().lower()
    return mode if mode in {"native", "novnc"} else "novnc"


def login_desktop_public_url(request: Request) -> str:
    settings = get_app_settings(force_reload=True)
    configured_url = str(
        os.getenv("SPARKFLOW_LOGIN_DESKTOP_PUBLIC_URL")
        or settings.get("login_desktop_public_url")
        or ""
    ).strip()
    if configured_url:
        return configured_url
    if login_desktop_display_mode() == "native":
        return ""

    return (
        "/login-desktop/proxy/vnc.html"
        "?autoconnect=1&resize=scale&view_only=0"
        "&path=login-desktop/proxy/websockify"
    )


def login_desktop_novnc_http_url() -> str:
    return str(os.getenv("SPARKFLOW_LOGIN_DESKTOP_NOVNC_URL") or "http://login-desktop:6080").rstrip("/")


def login_desktop_novnc_ws_url() -> str:
    return str(os.getenv("SPARKFLOW_LOGIN_DESKTOP_NOVNC_WS_URL") or "ws://login-desktop:6080/websockify")


def fetch_login_desktop_asset(asset_path: str, query: str = ""):
    safe_path = quote(str(asset_path or "vnc.html").lstrip("/"), safe="/._-")
    url = f"{login_desktop_novnc_http_url()}/{safe_path}"
    if query:
        url = f"{url}?{query}"
    upstream_request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(upstream_request, timeout=20) as upstream:
            headers = {
                key: value
                for key, value in upstream.headers.items()
                if key.lower() in {"content-type", "content-encoding", "cache-control", "etag", "last-modified"}
            }
            return upstream.status, headers, upstream.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Không kết nối được cửa sổ đăng nhập: {exc}") from exc


def call_login_desktop(path: str, *, method: str = "GET", payload: dict | None = None, timeout: int = 20) -> dict:
    url = f"{login_desktop_api_url()}{path}"
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        message = body
        try:
            payload = json.loads(body)
            detail = payload.get("detail") if isinstance(payload, dict) else None
            if isinstance(detail, dict):
                message = str(detail.get("message") or detail.get("code") or body)
            elif detail:
                message = str(detail)
        except (TypeError, ValueError):
            pass
        raise RuntimeError(f"Dịch vụ đăng nhập báo lỗi {exc.code}: {message}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(f"Dịch vụ đăng nhập không khả dụng: {reason}") from exc


async def _run_websocket_relays(*coroutines):
    tasks = {asyncio.create_task(coroutine) for coroutine in coroutines}
    try:
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, (ConnectionClosed, WebSocketDisconnect, asyncio.CancelledError)):
                continue
            if isinstance(result, BaseException):
                raise result
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def _dedupe_account_records(accounts: list[dict], *, unique_id: str, keep_ref: str) -> set[str]:
    normalized = normalize_unique_id(unique_id)
    removed_refs = set()
    remaining = []
    for account in accounts:
        if normalize_unique_id(account.get("unique_id")) == normalized and str(account.get("account_ref", "")) != str(keep_ref):
            ref = str(account.get("account_ref", "")).strip()
            if ref:
                removed_refs.add(ref)
            continue
        remaining.append(account)
    if len(remaining) != len(accounts):
        accounts[:] = remaining
    if removed_refs:
        remove_account_refs_from_users(removed_refs)
    return removed_refs


def save_exported_login_result(login_result: dict, *, relogin_unique_id: str = "", relogin_account_ref: str = "", display_name: str = "") -> tuple[dict, str]:
    unique_id = normalize_unique_id(login_result.get("unique_id"))
    username = str(display_name or login_result.get("username") or "").strip()
    cookies = list(login_result.get("cookies") or [])
    if not unique_id or not username or not cookies:
        raise RuntimeError("Dữ liệu phiên đăng nhập chưa đầy đủ")

    accounts, _ = ensure_account_refs(get_userData(force_reload=True))

    if relogin_account_ref or relogin_unique_id:
        target = account_by_ref(accounts, relogin_account_ref) if relogin_account_ref else find_account(accounts, relogin_unique_id)
        if not target:
            raise RuntimeError("Không tìm thấy tài khoản cần đăng nhập lại")
        if normalize_unique_id(target.get("unique_id")) != unique_id:
            raise RuntimeError("Tài khoản TikTok đang đăng nhập khác với tài khoản bạn đã chọn")
        target["unique_id"] = unique_id
        target["username"] = username
        target["cookies"] = cookies
        target.update(platform="tiktok", storage_state=login_result.get("storage_state"), account_failure={})
        target.setdefault("enabled", True)
        _dedupe_account_records(accounts, unique_id=unique_id, keep_ref=target.get("account_ref", ""))
        save_userData(accounts)
        return target, "updated"

    existing = find_account(accounts, unique_id)
    if existing:
        existing["username"] = username
        existing["cookies"] = cookies
        existing.update(platform="tiktok", storage_state=login_result.get("storage_state"), account_failure={})
        existing.setdefault("enabled", True)
        _dedupe_account_records(accounts, unique_id=unique_id, keep_ref=existing.get("account_ref", ""))
        save_userData(accounts)
        return existing, "updated"

    account = upsert_user_account(unique_id, username, cookies, [], extra={"platform": "tiktok", "storage_state": login_result.get("storage_state")})
    accounts, _ = ensure_account_refs(get_userData(force_reload=True))
    _dedupe_account_records(accounts, unique_id=unique_id, keep_ref=account.get("account_ref", ""))
    save_userData(accounts)
    return account, "created"


def public_app_settings():
    settings = get_app_settings(force_reload=True)
    allowed_keys = (
        "compose_root",
        "ui_host",
        "ui_port",
        "ops_log_file",
        "proxy_refresh_script",
        "login_desktop_api_url",
        "login_desktop_public_url",
        "login_desktop_public_scheme",
        "login_desktop_public_port",
    )
    return {key: settings.get(key) for key in allowed_keys}


def create_app():
    settings = get_app_settings()

    @asynccontextmanager
    async def lifespan(_app):
        # Add stable ownership identifiers without changing existing account data.
        ensure_account_refs()
        result = sync_daily_schedule_from_config()
        if result.returncode != 0:
            logger.warning("Failed to synchronize the configured daily schedule: %s", result.stderr)
        watchdog = asyncio.create_task(login_workspace_watchdog())
        scheduler = asyncio.create_task(scheduler_loop())
        try:
            yield
        finally:
            watchdog.cancel()
            scheduler.cancel()
            await asyncio.gather(watchdog, scheduler, return_exceptions=True)
    secure_cookie = str(os.getenv("SPARKFLOW_SESSION_COOKIE_SECURE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    app = FastAPI(title="TikTok SparkFlow Admin", lifespan=lifespan)
    @app.middleware("http")
    async def guard_account_mutations(request, call_next):
        path = request.url.path
        mutates_accounts = (path.startswith("/accounts/") or path in {"/login-desktop/save", "/ops/reset-today-unconfirmed"})
        if request.method == "POST" and mutates_accounts and not path.endswith("/retry-target"):
            try:
                with task_run_lock():
                    return await call_next(request)
            except TaskRunAlreadyInProgress:
                return JSONResponse({"error": "Đang gửi tin. Hãy chờ tác vụ hoàn tất trước khi sửa tài khoản."}, status_code=409)
        return await call_next(request)

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings["session_secret"],
        max_age=settings["session_max_age_seconds"],
        same_site="lax",
        https_only=secure_cookie,
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    DEBUG_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return PlainTextResponse(
            "Có lỗi hệ thống. Hãy xem nhật ký để biết chi tiết.",
            status_code=500,
            headers={"Cache-Control": "no-store"},
        )

    def render_template(request, template_name, context=None, status_code=200):
        base_context = dict(context or {})
        base_context.update(
            {
                "request": request,
                "current_user": current_user(request),
                "csrf_token": csrf_token(request) if current_user(request) else "",
                "is_https": is_https_request(request),
                "principal": current_principal(request),
                "is_admin": bool(current_principal(request) and current_principal(request).get("role") == "admin"),
                "app_settings": public_app_settings(),
                "login_desktop_public_url": login_desktop_public_url(request),
                "login_desktop_display_mode": login_desktop_display_mode(),
            }
        )
        return templates.TemplateResponse(
            request,
            template_name,
            base_context,
            status_code=status_code,
            headers={"Cache-Control": "no-store"},
        )

    def redirect(path="/", status_code=303):
        return RedirectResponse(url=path, status_code=status_code)

    def principal(request):
        resolved = current_principal(request)
        if resolved:
            return resolved
        # Keep compatibility with older tests/signed sessions that only expose
        # the legacy ``user`` value.
        legacy_user = current_user(request)
        admin_username = str(get_app_settings().get("admin_username", "admin")).strip() or "admin"
        if legacy_user and str(legacy_user).casefold() == admin_username.casefold():
            return {"username": admin_username, "role": "admin", "account_refs": [], "session_id": "", "enabled": True}
        return None

    def require_user(request):
        if not principal(request):
            return redirect("/login")
        return None

    def require_admin(request):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return maybe_redirect
        if principal(request).get("role") != "admin":
            return PlainTextResponse("Bạn không có quyền thực hiện thao tác này", status_code=403)
        return None

    def account_for_request(request, unique_id):
        accounts, _ = ensure_account_refs(get_userData(force_reload=True))
        account = account_by_unique_id(accounts, unique_id)
        if not account:
            return accounts, None, PlainTextResponse("Không tìm thấy tài khoản", status_code=404)
        if not can_access_account(principal(request), account):
            return accounts, None, PlainTextResponse("Bạn không có quyền thực hiện thao tác này", status_code=403)
        return accounts, account, None

    def principal_account_refs(request):
        current = principal(request)
        if not current or current.get("role") == "admin":
            return None
        return list(current.get("account_refs", []))

    def scoped_ops_snapshot(request):
        refs = principal_account_refs(request)
        snapshot = get_ops_snapshot(account_refs=refs)
        if refs is not None:
            # Do not place host/container state or global log tails into a
            # normal user's rendered context.
            snapshot["containers"] = []
            snapshot["task_containers"] = []
            snapshot["crontab"] = ""
            snapshot["log_tail"] = []
            snapshot["compose_root"] = ""
            snapshot["compose_file"] = ""
            snapshot["image_present"] = False
        return snapshot

    def scoped_overview_snapshot(request):
        return get_overview_snapshot(account_refs=principal_account_refs(request))

    def flash(request, message, level="info"):
        request.session["flash"] = {"message": message, "level": level}

    def pop_flash(request):
        return request.session.pop("flash", None)

    @app.get("/debug-artifacts/{artifact_path:path}")
    async def debug_artifact(request: Request, artifact_path: str):
        maybe_redirect = require_admin(request)
        if maybe_redirect:
            return maybe_redirect
        root = DEBUG_ARTIFACTS_DIR.resolve()
        candidate = (root / artifact_path).resolve()
        if root not in candidate.parents or not candidate.is_file():
            return PlainTextResponse("Not found", status_code=404)
        return FileResponse(candidate, headers={"Cache-Control": "no-store"})

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        if current_user(request):
            return redirect("/")
        return render_template(
            request,
            "login.html",
            {
                "flash": pop_flash(request),
                "bootstrapped": is_bootstrapped(),
            },
        )

    @app.post("/bootstrap")
    async def bootstrap(request: Request):
        if is_bootstrapped():
            flash(request, "Tài khoản quản trị đã được thiết lập.", "warning")
            return redirect("/login")

        form = await request.form()
        username = str(form.get("username", "admin")).strip() or "admin"
        password = str(form.get("password", ""))
        confirm = str(form.get("confirm_password", ""))
        if not password or password != confirm:
            flash(request, "Không thiết lập được mật khẩu. Hãy nhập hai mật khẩu giống nhau.", "error")
            return redirect("/login")

        bootstrap_admin_password(password, username=username)
        flash(request, "Đã tạo tài khoản quản trị. Hãy đăng nhập.", "success")
        return redirect("/login")

    @app.post("/login")
    async def login_action(request: Request):
        if not is_bootstrapped():
            flash(request, "Hãy tạo mật khẩu quản trị trước.", "warning")
            return redirect("/login")

        form = await request.form()
        username = str(form.get("username", "")).strip()
        password = str(form.get("password", ""))
        from webui.users import authenticate

        identity = authenticate(username, password)
        if not identity:
            flash(request, "Tên đăng nhập hoặc mật khẩu không đúng.", "error")
            return redirect("/login")

        issue_session(
            request,
            identity["username"],
            role=identity["role"],
            account_refs=identity.get("account_refs", []),
        )
        flash(request, "Đã đăng nhập thành công.", "success")
        return redirect("/")

    @app.post("/logout")
    async def logout_action(request: Request):
        clear_session(request)
        return redirect("/login")

    @app.get("/api/ops/overview")
    async def ops_overview(request: Request):
        if not current_user(request):
            return JSONResponse(
                {"error": "Bạn chưa đăng nhập"},
                status_code=401,
                headers={"Cache-Control": "no-store"},
            )
        return JSONResponse(
            scoped_overview_snapshot(request),
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/account/password")
    async def change_own_password(request: Request):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return maybe_redirect
        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return Response("Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại.", status_code=403)
        current = principal(request)
        if current.get("role") == "admin":
            flash(request, "Hãy đổi mật khẩu quản trị trong phần Cài đặt.", "info")
            return redirect("/")
        password = str(form.get("new_password", ""))
        confirm = str(form.get("confirm_password", ""))
        if not password or password != confirm:
            flash(request, "Hai mật khẩu không trùng nhau.", "error")
            return redirect("/")
        try:
            update_web_user(current["username"], password=password)
            flash(request, "Đã đổi mật khẩu. Hãy đăng nhập lại.", "success")
            clear_session(request)
            return redirect("/login")
        except UserStoreError as exc:
            flash(request, str(exc), "error")
            return redirect("/")

    @app.post("/admin/users/create")
    async def create_admin_user(request: Request):
        maybe_redirect = require_admin(request)
        if maybe_redirect:
            return maybe_redirect
        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return Response("Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại.", status_code=403)
        refs = [value for value in form.getlist("account_refs")] if hasattr(form, "getlist") else []
        try:
            create_web_user(
                str(form.get("username", "")),
                str(form.get("password", "")),
                enabled=str(form.get("enabled", "")) == "on",
                account_refs=refs,
            )
            flash(request, "Đã tạo người dùng.", "success")
        except UserStoreError as exc:
            flash(request, str(exc), "error")
        return redirect("/#user-management")

    @app.post("/admin/users/{username}/update")
    async def update_admin_user(request: Request, username: str):
        maybe_redirect = require_admin(request)
        if maybe_redirect:
            return maybe_redirect
        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return Response("Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại.", status_code=403)
        refs = [value for value in form.getlist("account_refs")] if hasattr(form, "getlist") else []
        try:
            update_web_user(
                username,
                new_username=str(form.get("new_username", "")).strip() or None,
                password=str(form.get("password", "")) or None,
                enabled=str(form.get("enabled", "")) == "on",
                account_refs=refs,
            )
            flash(request, "Đã cập nhật người dùng.", "success")
        except UserStoreError as exc:
            flash(request, str(exc), "error")
        return redirect("/#user-management")

    @app.post("/admin/users/{username}/delete")
    async def delete_admin_user(request: Request, username: str):
        maybe_redirect = require_admin(request)
        if maybe_redirect:
            return maybe_redirect
        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return Response("Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại.", status_code=403)
        try:
            if delete_web_user(username):
                flash(request, "Đã xóa người dùng; dữ liệu tài khoản TikTok vẫn được giữ.", "success")
            else:
                flash(request, "Không tìm thấy người dùng.", "error")
        except UserStoreError as exc:
            flash(request, str(exc), "error")
        return redirect("/#user-management")

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return maybe_redirect

        current = principal(request)
        accounts = get_visible_accounts(current, get_userData(force_reload=True))
        return render_template(
            request,
            "dashboard.html",
            {
                "flash": pop_flash(request),
                "accounts": accounts,
                "runtime_config": get_config(force_reload=True) if current.get("role") == "admin" else {},
                "ops": scoped_ops_snapshot(request),
                "principal": current,
                "is_admin": current.get("role") == "admin",
                "web_users": get_web_users() if current.get("role") == "admin" else [],
                "all_accounts": get_userData(force_reload=True) if current.get("role") == "admin" else [],
            },
        )

    @app.get("/ops/send-console", response_class=HTMLResponse)
    async def send_console_page(request: Request):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return maybe_redirect

        return render_template(
            request,
            "send_console.html",
            {
                "flash": pop_flash(request),
                "ops": scoped_ops_snapshot(request),
            },
        )

    @app.post("/accounts/{unique_id}/update")
    async def update_account(request: Request, unique_id: str):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return maybe_redirect

        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return Response("Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại.", status_code=403)

        username = str(form.get("username", "")).strip()
        try:
            targets = list(dict.fromkeys(normalize_target(t) for t in extract_targets_from_form(form)))
        except ValueError as exc:
            return Response(str(exc), status_code=400)

        accounts, account, access_error = account_for_request(request, unique_id)
        if access_error:
            return access_error
        if account:
            account["username"] = username or account.get("username", "")
            account["targets"] = targets
            account["enabled"] = str(form.get("enabled", "")) == "on"
            save_userData(accounts)
            flash(request, f"Đã cập nhật tài khoản {account['username']}.", "success")
        else:
            flash(request, "Không tìm thấy tài khoản.", "error")

        return redirect("/")

    @app.post("/accounts/{unique_id}/toggle-enabled")
    async def toggle_account_enabled(request: Request, unique_id: str):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return maybe_redirect

        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return Response("Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại.", status_code=403)

        accounts, account, access_error = account_for_request(request, unique_id)
        if access_error:
            return access_error

        account["enabled"] = not is_account_enabled(account)
        save_userData(accounts)
        flash(
            request,
            f"{account.get('username', 'Tài khoản')}: đã {'bật' if account['enabled'] else 'tắt'} gửi tin tự động.",
            "success",
        )
        return redirect("/")

    @app.post("/accounts/{unique_id}/friends/refresh")
    async def refresh_account_friend_list(request: Request, unique_id: str):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return JSONResponse({"error": "Bạn chưa đăng nhập"}, status_code=401)

        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return JSONResponse({"error": "Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại."}, status_code=403)

        accounts, account, access_error = account_for_request(request, unique_id)
        if access_error:
            return JSONResponse({"error": "Bạn không có quyền thực hiện thao tác này" if access_error.status_code == 403 else "Không tìm thấy tài khoản."}, status_code=access_error.status_code)

        try:
            friends = await fetch_account_friends(account)
            account["friends_cache"] = friends
            account["friends_cache_updated_at"] = datetime.now().isoformat(timespec="seconds")
            save_userData(accounts)
            return JSONResponse(
                {
                    "friends": friends,
                    "updated_at": account["friends_cache_updated_at"],
                    "message": f"Đã đọc {len(friends)} cuộc trò chuyện",
                }
            )
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.post("/accounts/{unique_id}/resolve-tiktok")
    async def resolve_tiktok(request: Request, unique_id: str):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return maybe_redirect
        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return Response("Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại.", status_code=403)
        accounts, account, access_error = account_for_request(request, unique_id)
        if access_error:
            return access_error
        target = str(form.get("target", "")).strip()
        action = str(form.get("action", ""))
        if action == "resume":
            account["account_failure"] = {}
        elif target in account.get("targets", []) and action in {"delivered", "not_sent"}:
            history = account.setdefault("message_history", {})
            if action == "delivered":
                history[target] = {**history.get(target, {}), "sentAt": datetime.now(_schedule_timezone()).isoformat(),
                                   "status": "confirmed", "confirmationLevel": "strong",
                                   "confirmationSource": "manual_verification", "needsVerification": False}
            else:
                history.pop(target, None)
            account.setdefault("failure_queue", {}).pop(target, None)
        else:
            return Response("Người nhận hoặc thao tác không hợp lệ", status_code=400)
        save_userData(accounts)
        return redirect("/")

    @app.post("/accounts/{unique_id}/delete")
    async def delete_account(request: Request, unique_id: str):
        maybe_redirect = require_admin(request)
        if maybe_redirect:
            return maybe_redirect

        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return Response("Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại.", status_code=403)

        accounts, account, access_error = account_for_request(request, unique_id)
        if access_error:
            return access_error
        updated_accounts = [item for item in accounts if normalize_unique_id(item.get("unique_id")) != normalize_unique_id(unique_id)]
        if len(updated_accounts) != len(accounts):
            save_userData(updated_accounts)
            flash(request, "Đã xóa tài khoản.", "success")
        else:
            flash(request, "Không tìm thấy tài khoản.", "error")
        return redirect("/")

    @app.post("/accounts/{unique_id}/retry-target")
    async def retry_account_target(request: Request, unique_id: str):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return maybe_redirect

        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return Response("Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại.", status_code=403)

        target_name = str(form.get("target", "")).strip()
        if not target_name:
            flash(request, "Hãy chọn người nhận cần thử lại.", "error")
            return redirect("/ops/send-console")

        accounts, account, access_error = account_for_request(request, unique_id)
        if access_error:
            return access_error

        lock_status = task_run_lock_status()
        if lock_status.get("running"):
            flash(request, "Đang có lượt gửi chạy. Hãy chờ hoàn tất trước khi thử lại chat này.", "warning")
            return redirect("/ops/send-console")

        if target_name not in account.get("targets", []):
            return Response("Người nhận này chưa được chọn cho tài khoản", status_code=400)
        account_copy = dict(account)
        account_copy["targets"] = [target_name]
        config = get_config(force_reload=True)
        config["taskCount"] = 1

        try:
            with task_run_lock():
                await run_browser_tasks(config, [account_copy])
        except Exception as exc:
            flash(request, f"Không xử lý được {account.get('username', 'Tài khoản')} / {target_name}: {exc}", "error")
            return redirect("/ops/send-console")

        updated_account = find_account(get_userData(force_reload=True), unique_id) or {}
        if _target_sent_today(updated_account, target_name):
            flash(request, f"Đã xử lý {account.get('username', 'Tài khoản')} / {target_name}; kết quả đã được xác nhận.", "success")
        elif _target_unconfirmed_today(updated_account, target_name):
            failure_entry = dict(updated_account.get("failure_queue") or {}).get(target_name) or {}
            reason = str(failure_entry.get("reason") or "Đã chạy nhưng chưa xác nhận được kết quả. Hãy kiểm tra trên TikTok.")
            flash(request, f"Đã xử lý {account.get('username', 'Tài khoản')} / {target_name}, nhưng cần kiểm tra kết quả: {reason}", "warning")
        else:
            account_failure = dict(updated_account.get("account_failure") or {})
            affected_targets = list(account_failure.get("affectedTargets") or [])
            failure_entry = dict(updated_account.get("failure_queue") or {}).get(target_name) or {}
            if target_name in affected_targets:
                reason = str(account_failure.get("reason") or "Có lỗi trình duyệt ảnh hưởng đến tài khoản.")
            else:
                reason = str(failure_entry.get("reason") or "Chưa xác nhận được tin đã gửi. Hãy kiểm tra trên TikTok.")
            flash(request, f"Chưa gửi được cho {account.get('username', 'Tài khoản')} / {target_name}: {reason}", "error")
        return redirect("/ops/send-console")

    @app.post("/accounts/{unique_id}/mark-target-unconfirmed")
    async def mark_account_target_unconfirmed(request: Request, unique_id: str):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return maybe_redirect

        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return Response("Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại.", status_code=403)

        target_name = str(form.get("target", "")).strip()
        if not target_name:
            flash(request, "Hãy chọn người nhận.", "error")
            return redirect("/ops/send-console")

        accounts, account, access_error = account_for_request(request, unique_id)
        if access_error:
            return access_error

        changed = mark_target_unconfirmed(account, target_name)
        if changed:
            save_userData(accounts)
            flash(request, f"Đã đánh dấu {account.get('username', 'Tài khoản')} / {target_name} là cần kiểm tra trước khi gửi lại.", "warning")
        else:
            flash(request, f"Bản ghi {target_name} đã được xác nhận hoặc không thuộc hôm nay; hệ thống giữ nguyên.", "info")
        return redirect("/ops/send-console")

    @app.post("/ops/reset-today-unconfirmed")
    async def reset_today_unconfirmed(request: Request):
        maybe_redirect = require_admin(request)
        if maybe_redirect:
            return maybe_redirect

        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return Response("Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại.", status_code=403)

        accounts = get_userData(force_reload=True)
        changed_count = 0
        for account in accounts:
            for target_name in list(account.get("targets") or []):
                entry = dict(account.get("message_history") or {}).get(target_name) or {}
                sent_at = _parse_sent_at(entry.get("sentAt"))
                if not sent_at or sent_at.date() != datetime.now(_schedule_timezone()).date():
                    continue
                if _history_entry_strong_confirmed_today(entry):
                    continue
                if mark_target_unconfirmed(account, target_name, reason="batch_reset_today_suspicious_success"):
                    changed_count += 1
        if changed_count:
            save_userData(accounts)
            flash(request, f"Đã đánh dấu {changed_count} bản ghi hôm nay là cần kiểm tra trước khi gửi lại.", "warning")
        else:
            flash(request, "Không có bản ghi hôm nay cần đánh dấu lại.", "info")
        return redirect("/ops/send-console")

    @app.post("/config")
    async def save_runtime_config(request: Request):
        maybe_redirect = require_admin(request)
        if maybe_redirect:
            return maybe_redirect

        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return Response("Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại.", status_code=403)

        config = get_config(force_reload=True)
        if "scheduleSettings" in form:
            config["scheduleEnabled"] = form.get("scheduleEnabled") == "on"
            try:
                ZoneInfo(str(form.get("timezone", "Asia/Seoul")))
            except Exception:
                return Response("Múi giờ không hợp lệ", status_code=400)
            config["timezone"] = str(form.get("timezone"))
        if "messageTemplate" in form:
            config["messageTemplate"] = str(form.get("messageTemplate", config.get("messageTemplate", "")))
        if "multiTask" in form:
            config["multiTask"] = str(form.get("multiTask", "")) == "on"
        if "taskCount" in form:
            config["taskCount"] = coerce_int(form.get("taskCount", config.get("taskCount", 1)), config.get("taskCount", 1), 1)
        if "hitokotoTypes" in form:
            raw_types = str(form.get("hitokotoTypes", ""))
            config["hitokotoTypes"] = [item.strip() for item in raw_types.replace(",", "\n").splitlines() if item.strip()]

        send_strategy = config.get("sendStrategy", {}) or {}
        if "shuffleTargets" in form:
            send_strategy["shuffleTargets"] = str(form.get("shuffleTargets", "")) == "on"
        if "accountStartDelaySecondsMin" in form:
            send_strategy["accountStartDelaySecondsMin"] = coerce_int(
                form.get("accountStartDelaySecondsMin", send_strategy.get("accountStartDelaySecondsMin", 0)),
                send_strategy.get("accountStartDelaySecondsMin", 0),
                0,
            )
        if "accountStartDelaySecondsMax" in form:
            send_strategy["accountStartDelaySecondsMax"] = coerce_int(
                form.get("accountStartDelaySecondsMax", send_strategy.get("accountStartDelaySecondsMax", 0)),
                send_strategy.get("accountStartDelaySecondsMax", 0),
                send_strategy.get("accountStartDelaySecondsMin", 0),
            )
        if "messageIntervalSecondsMin" in form:
            send_strategy["messageIntervalSecondsMin"] = coerce_int(
                form.get("messageIntervalSecondsMin", send_strategy.get("messageIntervalSecondsMin", 0)),
                send_strategy.get("messageIntervalSecondsMin", 0),
                0,
            )
        if "messageIntervalSecondsMax" in form:
            send_strategy["messageIntervalSecondsMax"] = coerce_int(
                form.get("messageIntervalSecondsMax", send_strategy.get("messageIntervalSecondsMax", 0)),
                send_strategy.get("messageIntervalSecondsMax", 0),
                send_strategy.get("messageIntervalSecondsMin", 0),
            )
        if "messageVariants" in form:
            raw_variants = str(form.get("messageVariants", ""))
            send_strategy["messageVariants"] = [
                item.strip() for item in raw_variants.replace("\r", "\n").split("\n") if item.strip()
            ]
        config["sendStrategy"] = send_strategy

        happy_new_year = config.get("happyNewYear", {})
        if "happyNewYearEnabled" in form:
            happy_new_year["enabled"] = str(form.get("happyNewYearEnabled", "")) == "on"
        if "happyNewYearTemplate" in form:
            happy_new_year["messageTemplate"] = str(form.get("happyNewYearTemplate", happy_new_year.get("messageTemplate", "")))
        config["happyNewYear"] = happy_new_year
        save_config(config)

        flash(request, "Đã lưu cấu hình gửi tin.", "success")
        return redirect("/")

    @app.post("/settings")
    async def save_panel_settings(request: Request):
        maybe_redirect = require_admin(request)
        if maybe_redirect:
            return maybe_redirect

        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return Response("Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại.", status_code=403)

        settings = get_app_settings(force_reload=True)
        settings["compose_root"] = str(form.get("compose_root", settings.get("compose_root", ""))).strip()
        settings["ops_log_file"] = str(form.get("ops_log_file", settings.get("ops_log_file", ""))).strip()
        settings["proxy_refresh_script"] = str(form.get("proxy_refresh_script", settings.get("proxy_refresh_script", ""))).strip()
        settings["login_desktop_api_url"] = str(
            form.get("login_desktop_api_url", settings.get("login_desktop_api_url", "http://127.0.0.1:18090"))
        ).strip()
        network_mode = str(form.get("douyin_network_mode", settings.get("douyin_network_mode", "direct"))).strip().lower()
        settings["douyin_network_mode"] = network_mode if network_mode in {"direct", "mihomo"} else "direct"
        settings["douyin_proxy_url"] = str(form.get("douyin_proxy_url", settings.get("douyin_proxy_url", "http://proxy:7890"))).strip()
        settings["ui_port"] = int(form.get("ui_port", settings.get("ui_port", 8787)))
        save_app_settings(settings)

        new_password = str(form.get("new_password", ""))
        confirm_password = str(form.get("confirm_password", ""))
        if new_password:
            if new_password != confirm_password:
                flash(request, "Chưa đổi mật khẩu quản trị vì hai mật khẩu không trùng nhau.", "error")
                return redirect("/")
            update_admin_password(new_password)

        flash(request, "Đã lưu cài đặt bảng điều khiển.", "success")
        return redirect("/")

    @app.post("/ops/run-now")
    async def run_now(request: Request):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return maybe_redirect

        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return Response("Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại.", status_code=403)

        refs = principal_account_refs(request)
        pid = run_task_now(force_all=refs is None, account_refs=refs)
        if pid == TASK_ALREADY_RUNNING:
            flash(request, "Đang có lượt gửi chạy. Hãy chờ hoàn tất trước khi bắt đầu lượt mới.", "warning")
        elif pid == -1:
            flash(request, "Không bắt đầu được lượt gửi. Hãy xem nhật ký để biết chi tiết.", "error")
        else:
            flash(request, f"Đã bắt đầu lượt gửi (mã tiến trình {pid}). Cập nhật trang Theo dõi gửi tin để xem kết quả thực tế.", "info")
        return redirect("/ops/send-console")

    @app.post("/ops/run-failed")
    async def run_failed_retry(request: Request):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return maybe_redirect

        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return Response("Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại.", status_code=403)

        refs = principal_account_refs(request)
        pid = run_failed_retry_now(account_refs=refs)
        if pid == TASK_ALREADY_RUNNING:
            flash(request, "Đang có lượt gửi chạy. Hãy chờ hoàn tất trước khi gửi các chat còn lại.", "warning")
        elif pid == -1:
            flash(request, "Không bắt đầu được lượt xử lý chat bị lỗi. Hãy xem nhật ký.", "error")
        else:
            flash(request, f"Đã bắt đầu lượt xử lý các chat còn lại (mã tiến trình {pid}). Cập nhật trang Theo dõi gửi tin để xem kết quả.", "info")
        return redirect("/ops/send-console")

    @app.post("/ops/run-unsent")
    async def run_unsent_retry(request: Request):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return maybe_redirect

        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return Response("Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại.", status_code=403)

        refs = principal_account_refs(request)
        pid = run_unsent_retry_now(account_refs=refs)
        if pid == TASK_ALREADY_RUNNING:
            flash(request, "Đang có lượt gửi chạy; chưa bắt đầu lượt gửi các chat còn lại.", "warning")
        elif pid == -1:
            flash(request, "Không bắt đầu được lượt gửi các chat còn lại. Hãy xem nhật ký.", "error")
        else:
            flash(request, f"Đã bắt đầu lượt xử lý các chat còn lại (mã tiến trình {pid}). Cập nhật trang Theo dõi gửi tin để xem kết quả.", "info")
        return redirect("/ops/send-console")

    @app.post("/ops/proxy/refresh")
    async def proxy_refresh(request: Request):
        maybe_redirect = require_admin(request)
        if maybe_redirect:
            return maybe_redirect

        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return Response("Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại.", status_code=403)

        refresh_proxy()
        flash(request, "Đã cập nhật cấu hình proxy.", "success")
        return redirect("/")

    @app.post("/ops/proxy/restart")
    async def proxy_restart(request: Request):
        maybe_redirect = require_admin(request)
        if maybe_redirect:
            return maybe_redirect

        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return Response("Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại.", status_code=403)

        restart_proxy()
        flash(request, "Đã khởi động lại dịch vụ proxy.", "success")
        return redirect("/")

    @app.post("/ops/schedule")
    async def save_schedule(request: Request):
        maybe_redirect = require_admin(request)
        if maybe_redirect:
            return maybe_redirect

        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return Response("Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại.", status_code=403)

        time_string = str(form.get("daily_schedule", "")).strip()
        result = update_daily_schedule(time_string)
        if getattr(result, "returncode", 1) == 0:
            flash(request, f"Đã lưu lịch gửi hằng ngày: {time_string}.", "success")
        else:
            flash(request, f"Không lưu được lịch {time_string}: {getattr(result, 'stderr', '')}", "error")
        return redirect("/")

    @app.get("/ops/logs", response_class=HTMLResponse)
    async def logs_page(request: Request):
        maybe_redirect = require_admin(request)
        if maybe_redirect:
            return maybe_redirect
        return render_template(
            request,
            "logs.html",
            {
                "flash": pop_flash(request),
                "log_tail": read_log_tail(400),
            },
        )

    login_transition_lock = asyncio.Lock()

    def _workspace_payload(request):
        current = principal(request)
        state = get_workspace_state()
        mine = workspace_status(
            username=current.get("username", "") if current else "",
            session_id=current.get("session_id", "") if current else "",
        )
        active = state.get("active") or {}
        is_owner = bool(current and owns_login_lock(
            active,
            username=current.get("username", ""),
            session_id=current.get("session_id", ""),
        ))
        return {
            "state": mine.get("state", "closed"),
            "position": mine.get("position", 0),
            "ticket": mine.get("ticket", ""),
            "remaining_seconds": mine.get("remaining_seconds", 0),
            "queue_length": len(state.get("queue") or []),
            "active": is_owner,
            "active_username": active.get("username", "") if current and current.get("role") == "admin" else (current.get("username", "") if is_owner and current else ""),
        }

    async def _reset_and_promote(*, force=False, clear_queue=False):
        """Reset the shared browser profile, then activate the next queue item."""
        async with login_transition_lock:
            state = get_workspace_state()
            if force:
                transition = begin_login_force_reset(clear_queue=clear_queue)
            else:
                transition = begin_login_expiration()
            state_after = get_workspace_state()
            needs_reset = bool(transition or state_after.get("phase") == "resetting")
            if not needs_reset:
                return True, None
            try:
                try:
                    call_login_desktop("/close", method="POST", payload={}, timeout=60)
                except RuntimeError:
                    # Older login-desktop images do not have /close; reset is
                    # still safe because it clears the temporary login profile.
                    call_login_desktop("/reset", method="POST", payload={}, timeout=120)
            except RuntimeError as exc:
                logger.error("Failed to reset login workspace: %s", exc)
                return False, None
            promoted = finish_login_transition()
            if promoted:
                try:
                    call_login_desktop("/open-login", method="POST", payload={}, timeout=90)
                except RuntimeError as exc:
                    logger.error("Failed to open login workspace for queued user: %s", exc)
                    return False, promoted
            return True, promoted

    async def _expire_login_workspace():
        return await _reset_and_promote()

    async def login_workspace_watchdog():
        """Reap abandoned leases even when no browser request arrives."""
        while True:
            await asyncio.sleep(10)
            try:
                await _expire_login_workspace()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("login workspace watchdog failed")

    def login_lock_owner(request):
        current = principal(request)
        active = get_login_lock()
        if not current or not active:
            return current, active, False
        return current, active, owns_login_lock(
            active,
            username=current["username"],
            session_id=current.get("session_id", ""),
        )

    def login_lock_required(request, *, api=False):
        current, active, allowed = login_lock_owner(request)
        if allowed:
            return None
        if api:
            return JSONResponse({"ok": False, "error": "Phiên hiện tại chưa được cấp cửa sổ đăng nhập", "workspace": _workspace_payload(request)}, status_code=423)
        return HTMLResponse(
            """<!doctype html><html lang='vi'><meta charset='utf-8'><title>Chờ cửa sổ đăng nhập</title>
            <body style='font-family:sans-serif;padding:32px'><h2>Chưa đến lượt đăng nhập</h2>
            <p>Quay lại phần Tài khoản và chat, bấm “Đăng nhập lại” ở tài khoản cần xử lý. Nếu có người dùng trước, bạn sẽ được đưa vào hàng chờ.</p></body></html>""",
            status_code=423,
        )

    @app.get("/login-desktop/proxy")
    async def login_desktop_proxy_root(request: Request):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return maybe_redirect
        lock_error = login_lock_required(request)
        if lock_error:
            return lock_error
        return RedirectResponse(login_desktop_public_url(request), status_code=307)

    @app.get("/login-desktop/proxy/{asset_path:path}")
    async def login_desktop_proxy_asset(request: Request, asset_path: str):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return maybe_redirect
        lock_error = login_lock_required(request)
        if lock_error:
            return lock_error
        try:
            status, headers, content = await asyncio.to_thread(
                fetch_login_desktop_asset,
                asset_path,
                request.url.query,
            )
            return Response(content=content, status_code=status, headers=headers)
        except RuntimeError as exc:
            return PlainTextResponse(str(exc), status_code=502)

    @app.websocket("/login-desktop/proxy/websockify")
    async def login_desktop_proxy_websocket(websocket: WebSocket):
        current = current_principal(websocket)
        active = get_login_lock()
        if not current:
            await websocket.close(code=4401)
            return
        if not owns_login_lock(
            active,
            username=current.get("username", ""),
            session_id=current.get("session_id", ""),
        ):
            await websocket.close(code=4423)
            return

        requested_protocols = [
            item.strip()
            for item in websocket.headers.get("sec-websocket-protocol", "").split(",")
            if item.strip()
        ]
        accepted = False
        try:
            async with websockets.connect(
                login_desktop_novnc_ws_url(),
                subprotocols=requested_protocols or None,
                open_timeout=10,
                close_timeout=5,
            ) as upstream:
                await websocket.accept(subprotocol=upstream.subprotocol)
                accepted = True

                async def client_to_upstream():
                    while True:
                        message = await websocket.receive()
                        if message["type"] == "websocket.disconnect":
                            return
                        if message.get("bytes") is not None:
                            await upstream.send(message["bytes"])
                        elif message.get("text") is not None:
                            await upstream.send(message["text"])

                async def upstream_to_client():
                    async for message in upstream:
                        if isinstance(message, bytes):
                            await websocket.send_bytes(message)
                        else:
                            await websocket.send_text(message)

                await _run_websocket_relays(client_to_upstream(), upstream_to_client())
        except (ConnectionClosed, WebSocketDisconnect):
            pass
        except Exception as exc:
            logger.warning("login desktop WebSocket proxy failed: %s", exc)
            if not accepted:
                await websocket.close(code=1011)

    @app.get("/login-desktop/qr")
    async def login_desktop_qr(request: Request):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return maybe_redirect
        lock_error = login_lock_required(request)
        if lock_error:
            return lock_error
        url = f"{login_desktop_api_url()}/qr"
        try:
            upstream_request = urllib.request.Request(url, method="GET")
            def read_qr_response():
                upstream = urllib.request.urlopen(upstream_request, timeout=20)
                try:
                    raw_headers = getattr(upstream, "headers", {})
                    try:
                        headers = dict(raw_headers)
                    except (TypeError, ValueError):
                        headers = {}
                    return getattr(upstream, "status", 200), headers, upstream.read()
                finally:
                    close = getattr(upstream, "close", None)
                    if close:
                        close()
            upstream_status, upstream_headers, content = await asyncio.to_thread(read_qr_response)
            if upstream_status == 202:
                retry_after = upstream_headers.get("Retry-After", "2")
                return JSONResponse(
                    {"ok": False, "state": "starting", "retry_after": int(retry_after or 2)},
                    status_code=202,
                    headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
                )
            return Response(content=content, media_type="image/png", headers={"Cache-Control": "no-store, max-age=0"})
        except urllib.error.HTTPError as exc:
            if exc.code in {404, 409, 202}:
                return JSONResponse(
                    {"ok": False, "state": "starting", "retry_after": 2},
                    status_code=202,
                    headers={"Retry-After": "2", "Cache-Control": "no-store"},
                )
            return PlainTextResponse("login QR service is unavailable", status_code=502)
        except (urllib.error.URLError, TimeoutError):
            return PlainTextResponse("login QR service is unavailable", status_code=502)

    @app.post("/login-desktop/qr/refresh")
    async def login_desktop_qr_refresh(request: Request):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return JSONResponse({"redirect": "/login"}, status_code=401)
        lock_error = login_lock_required(request, api=True)
        if lock_error:
            return lock_error
        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return JSONResponse({"ok": False, "error": "Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại."}, status_code=403)
        heartbeat_login(
            username=principal(request)["username"],
            session_id=principal(request).get("session_id", ""),
            ticket=str(form.get("ticket", "")),
        )
        try:
            payload = call_login_desktop("/refresh-qr", method="POST", payload={}, timeout=90)
            return JSONResponse({"ok": True, "result": payload, "workspace": _workspace_payload(request)})
        except RuntimeError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=503)

    @app.post("/login-desktop/focus")
    async def login_desktop_focus(request: Request):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return JSONResponse({"redirect": "/login"}, status_code=401)
        lock_error = login_lock_required(request, api=True)
        if lock_error:
            return lock_error
        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return JSONResponse({"ok": False, "error": "Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại."}, status_code=403)
        heartbeat_login(
            username=principal(request)["username"],
            session_id=principal(request).get("session_id", ""),
            ticket=str(form.get("ticket", "")),
        )
        try:
            payload = call_login_desktop("/focus", method="POST", payload={}, timeout=20)
            return JSONResponse({"ok": True, "result": payload, "workspace": _workspace_payload(request)})
        except RuntimeError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=503)

    @app.get("/login-desktop/status")
    async def login_desktop_status(request: Request):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return JSONResponse({"redirect": "/login"}, status_code=401)
        await _expire_login_workspace()
        try:
            payload = call_login_desktop("/status")
            payload["public_url"] = login_desktop_public_url(request)
            payload["workspace"] = _workspace_payload(request)
            return JSONResponse(payload)
        except RuntimeError as exc:
            return JSONResponse({"ok": False, "error": str(exc), "public_url": login_desktop_public_url(request), "workspace": _workspace_payload(request)}, status_code=503)

    @app.get("/login-desktop/workspace-status")
    async def login_desktop_workspace_status(request: Request):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return JSONResponse({"redirect": "/login"}, status_code=401)
        await _expire_login_workspace()
        return JSONResponse({"ok": True, "workspace": _workspace_payload(request)}, headers={"Cache-Control": "no-store"})

    @app.post("/login-desktop/heartbeat")
    async def login_desktop_heartbeat(request: Request):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return JSONResponse({"redirect": "/login"}, status_code=401)
        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return JSONResponse({"ok": False, "error": "Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại."}, status_code=403)
        await _expire_login_workspace()
        current = principal(request)
        ok = heartbeat_login(
            username=current["username"],
            session_id=current.get("session_id", ""),
            ticket=str(form.get("ticket", "")),
        )
        if not ok:
            return JSONResponse({"ok": False, "error": "Lượt đăng nhập đã kết thúc. Hãy mở lại cửa sổ đăng nhập."}, status_code=423)
        return JSONResponse({"ok": True, "workspace": _workspace_payload(request)})

    @app.post("/login-desktop/open")
    async def login_desktop_open(request: Request):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return JSONResponse({"redirect": "/login"}, status_code=401)
        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return JSONResponse({"ok": False, "error": "Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại."}, status_code=403)
        await _expire_login_workspace()
        current = principal(request)
        relogin_unique_id = str(form.get("relogin_unique_id", "")).strip()
        requested_mode = str(form.get("mode", "")).strip().lower()
        mode = requested_mode if requested_mode in {"add", "relogin"} else ("relogin" if relogin_unique_id else "add")
        account_ref = ""
        if relogin_unique_id:
            _, account, access_error = account_for_request(request, relogin_unique_id)
            if access_error:
                return JSONResponse({"ok": False, "error": "Bạn không có quyền thao tác với tài khoản này"}, status_code=access_error.status_code)
            account_ref = account.get("account_ref", "")
            mode = "relogin"
        elif mode != "add":
            return JSONResponse({"ok": False, "error": "Hãy chọn tài khoản cần đăng nhập lại"}, status_code=400)

        result = request_workspace(
            username=current["username"],
            session_id=current.get("session_id", ""),
            account_ref=account_ref,
            mode=mode,
        )
        if result["state"] == "full":
            return JSONResponse({"ok": False, "error": "Hàng chờ đăng nhập đã đầy. Hãy thử lại sau."}, status_code=429)
        if result["state"] == "queued":
            return JSONResponse({"ok": True, "state": "queued", "workspace": _workspace_payload(request)}, status_code=202)
        try:
            call_login_desktop("/open-login", method="POST", payload={}, timeout=90)
            return JSONResponse({"ok": True, "state": "active", "public_url": login_desktop_public_url(request), "workspace": _workspace_payload(request)})
        except RuntimeError as exc:
            begin_login_release(username=current["username"], session_id=current.get("session_id", ""), ticket=result["request"].get("ticket", ""), account_ref=account_ref)
            await _reset_and_promote()
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=503)

    @app.post("/login-desktop/close")
    async def login_desktop_close(request: Request):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return JSONResponse({"redirect": "/login"}, status_code=401)
        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return JSONResponse({"ok": False, "error": "Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại."}, status_code=403)
        current = principal(request)
        if current.get("role") == "admin":
            await _reset_and_promote(force=True)
            return JSONResponse({"ok": True, "workspace": _workspace_payload(request)})
        active = get_login_lock()
        if owns_login_lock(active, username=current["username"], session_id=current.get("session_id", "")):
            begin_login_release(
                username=current["username"],
                session_id=current.get("session_id", ""),
                ticket=active.get("ticket", ""),
                account_ref=active.get("account_ref", ""),
            )
            await _reset_and_promote()
        else:
            cancel_login_request(username=current["username"], session_id=current.get("session_id", ""))
        return JSONResponse({"ok": True, "workspace": _workspace_payload(request)})

    @app.post("/login-desktop/reset")
    async def login_desktop_reset(request: Request):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return JSONResponse({"redirect": "/login"}, status_code=401)
        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return JSONResponse({"ok": False, "error": "Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại."}, status_code=403)
        current = principal(request)
        if current.get("role") == "admin":
            await _reset_and_promote(force=True, clear_queue=str(form.get("clear_queue", "")) == "1")
            return JSONResponse({"ok": True, "workspace": _workspace_payload(request)})
        active = get_login_lock()
        if not owns_login_lock(active, username=current["username"], session_id=current.get("session_id", "")):
            kind, _ = cancel_login_request(username=current["username"], session_id=current.get("session_id", ""))
            return JSONResponse({"ok": kind == "queued", "workspace": _workspace_payload(request)})
        begin_login_release(username=current["username"], session_id=current.get("session_id", ""), ticket=active.get("ticket", ""), account_ref=active.get("account_ref", ""))
        await _reset_and_promote()
        return JSONResponse({"ok": True, "workspace": _workspace_payload(request)})

    @app.post("/login-desktop/save")
    async def login_desktop_save(request: Request):
        maybe_redirect = require_user(request)
        if maybe_redirect:
            return JSONResponse({"redirect": "/login"}, status_code=401)
        form = await request.form()
        if not validate_csrf(request, str(form.get("csrf_token", ""))):
            return JSONResponse({"ok": False, "error": "Phiên thao tác đã hết hạn. Hãy tải lại trang rồi thử lại."}, status_code=403)

        current = principal(request)
        active = get_login_lock()
        if not owns_login_lock(active, username=current["username"], session_id=current.get("session_id", "")):
            return JSONResponse({"ok": False, "error": "Lượt đăng nhập đã kết thúc. Hãy mở lại cửa sổ đăng nhập."}, status_code=423)
        relogin_unique_id = str(form.get("relogin_unique_id", "")).strip()
        display_name = str(form.get("display_name", "")).strip()
        operation = str(active.get("mode", "relogin"))
        relogin_account_ref = str(active.get("account_ref", ""))
        if relogin_account_ref:
            account = account_by_ref(get_userData(force_reload=True), relogin_account_ref)
            if not account or not can_access_account(current, account):
                return JSONResponse({"ok": False, "error": "Bạn không có quyền thao tác với tài khoản này"}, status_code=403)
            relogin_unique_id = account.get("unique_id", "")
            operation = "relogin"
        elif operation != "add" and current.get("role") != "admin":
            return JSONResponse({"ok": False, "error": "Bạn chỉ được chọn tài khoản TikTok được cấp quyền"}, status_code=400)
        try:
            payload = call_login_desktop("/export", method="POST", payload={}, timeout=30)
            if not payload.get("ok"):
                raise RuntimeError("Dịch vụ đăng nhập chưa xuất được phiên hợp lệ")
            exported = payload.get("result", {}) or {}
            existing = account_by_unique_id(get_userData(force_reload=True), exported.get("unique_id"))
            if existing and str(existing.get("account_ref", "")) != relogin_account_ref and not can_access_account(current, existing):
                raise RuntimeError("Tài khoản TikTok này đã được cấp cho người dùng khác; không thể ghi đè")
            if operation == "add" and current.get("role") == "user" and existing:
                relogin_account_ref = existing.get("account_ref", "")
                relogin_unique_id = existing.get("unique_id", "")
                operation = "relogin"
            account, action = save_exported_login_result(
                exported,
                relogin_unique_id=relogin_unique_id,
                relogin_account_ref=relogin_account_ref,
                display_name=display_name,
            )
            if operation == "add" and current.get("role") == "user":
                refs = list(dict.fromkeys(list(current.get("account_refs", [])) + [account.get("account_ref", "")]))
                update_web_user(current["username"], account_refs=refs)
            begin_login_release(username=current["username"], session_id=current.get("session_id", ""), ticket=active.get("ticket", ""), account_ref=active.get("account_ref", ""))
            await _reset_and_promote()
            return JSONResponse({
                "ok": True,
                "action": action,
                "account": {
                    "account_ref": account.get("account_ref"),
                    "unique_id": account.get("unique_id"),
                    "username": account.get("username"),
                    "enabled": account.get("enabled", True),
                },
                "workspace": _workspace_payload(request),
            })
        except RuntimeError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    return app


app = create_app()


def run_web_app(host=None, port=None):
    settings = get_app_settings(force_reload=True)
    uvicorn.run(
        "webui.app:app",
        host=host or settings["ui_host"],
        port=port or settings["ui_port"],
        reload=False,
    )
