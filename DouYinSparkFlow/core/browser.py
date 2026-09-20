import os
import re
import subprocess
import sys
import traceback
from pathlib import Path

from playwright.async_api import async_playwright
from rich.console import Console

from utils.config import DEBUG, Environment, get_app_settings, get_environment


console = Console()
PLAYWRIGHT_BROWSERS_PATH = "../chrome"
DEFAULT_PROFILE_ROOT = str(Path(__file__).resolve().parents[1] / "state" / "browser-profiles")
BRAVE_EXECUTABLE = Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")


def _local_browser_bundle_path():
    return Path(__file__).resolve().parent / PLAYWRIGHT_BROWSERS_PATH


def configure_playwright_environment():
    if os.getenv("PLAYWRIGHT_BROWSERS_PATH"):
        return

    env = get_environment()
    if env == Environment.PACKED:
        bundle_path = Path(sys.executable).resolve().parent / PLAYWRIGHT_BROWSERS_PATH
    else:
        bundle_path = _local_browser_bundle_path()

    if bundle_path.exists():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(bundle_path.resolve())


def _headless_for(GUI=False):
    headful_env = str(os.getenv("SPARKFLOW_BROWSER_HEADFUL") or "").strip().lower()
    if headful_env in {"1", "true", "yes", "on"}:
        return False

    headless = not GUI
    if get_environment() == Environment.LOCAL and DEBUG:
        headless = False
    return headless


def _browser_launch_options(GUI=False, network_mode=None):
    opts = {"headless": _headless_for(GUI)}
    # Keep explicit overrides; otherwise also prefer installed Brave for CLI entry points.
    channel = str(os.getenv("SPARKFLOW_BROWSER_CHANNEL") or "").strip()
    exe = str(os.getenv("SPARKFLOW_BROWSER_EXECUTABLE") or "").strip()
    if exe:
        opts["executable_path"] = exe
    elif channel:
        opts["channel"] = channel
    elif sys.platform == "darwin" and BRAVE_EXECUTABLE.is_file() and os.access(BRAVE_EXECUTABLE, os.X_OK):
        opts["executable_path"] = str(BRAVE_EXECUTABLE)
    return opts


def sanitize_profile_name(value):
    raw = str(value or "").strip()
    if not raw:
        raw = "unknown"
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", raw)
    safe = safe.strip("._-") or "unknown"
    return safe[:80]


def browser_profile_root(root=None):
    configured = (
        root
        or os.getenv("SPARKFLOW_BROWSER_PROFILE_ROOT")
        or DEFAULT_PROFILE_ROOT
    )
    return Path(configured)


async def install_browser():
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        console.print("[bold green]Đã cài trình duyệt. Hãy chạy lại lệnh.[/bold green]")
    except subprocess.CalledProcessError as exc:
        console.print(f"[bold red]Không cài được trình duyệt: {exc}[/bold red]")


async def get_browser(GUI=False, network_mode=None):
    configure_playwright_environment()

    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(**_browser_launch_options(GUI, network_mode=network_mode))
        return playwright, browser
    except Exception as exc:
        if "Executable doesn't exist" in str(exc) and get_environment() != Environment.GITHUBACTION:
            console.print("[bold red]Chưa cài trình duyệt Playwright.[/bold red]")
            await install_browser()
            sys.exit(1)
        if "playwright" in locals():
            await playwright.stop()
        raise


async def get_persistent_browser_context(profile_name, GUI=False, root=None, network_mode=None):
    configure_playwright_environment()

    profile_dir = browser_profile_root(root) / sanitize_profile_name(profile_name)
    profile_dir.mkdir(parents=True, exist_ok=True)

    try:
        playwright = await async_playwright().start()
        launch_options = _browser_launch_options(GUI, network_mode=network_mode)
        launch_options["viewport"] = {"width": 1600, "height": 1000}
        context = await playwright.chromium.launch_persistent_context(
            str(profile_dir),
            **launch_options,
        )
        return playwright, context, profile_dir
    except Exception as exc:
        if "Executable doesn't exist" in str(exc) and get_environment() != Environment.GITHUBACTION:
            console.print("[bold red]Chưa cài trình duyệt Playwright.[/bold red]")
            await install_browser()
            sys.exit(1)
        if "playwright" in locals():
            await playwright.stop()
        raise
