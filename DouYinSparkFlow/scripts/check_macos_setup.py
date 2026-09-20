"""Check dependencies and prepare the browser before starting either service."""
import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys


APP_DIR = Path(__file__).resolve().parents[1]


def main():
    missing = []
    for line in (APP_DIR / "requirements.txt").read_text(encoding="utf-8-sig").splitlines():
        name = line.strip().split("==", 1)[0]
        if not name or name.startswith("#"):
            continue
        try:
            importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            missing.append(name)
    if missing:
        raise RuntimeError(
            "Thiếu thư viện: " + ", ".join(missing)
            + ". Tại thư mục repo, activate .venv rồi chạy: "
            "python -m pip install -r DouYinSparkFlow/requirements.txt"
        )

    sys.path.insert(0, str(APP_DIR))
    from core.browser import _browser_launch_options, configure_playwright_environment
    from playwright.sync_api import sync_playwright

    options = _browser_launch_options(GUI=True)
    executable = options.get("executable_path")
    if executable:
        if not Path(executable).is_file() or not os.access(executable, os.X_OK):
            raise RuntimeError(
                f"Không tìm thấy browser executable có thể chạy: {executable}. "
                "Kiểm tra SPARKFLOW_BROWSER_EXECUTABLE; xem troubleshooting trong README."
            )
        print(f"Trình duyệt: {executable}")
        return
    if options.get("channel"):
        print(f"Trình duyệt theo SPARKFLOW_BROWSER_CHANNEL: {options['channel']}")
        return

    # Use the same browser location as the application, including custom/bundled paths.
    configure_playwright_environment()
    with sync_playwright() as playwright:
        chromium = Path(playwright.chromium.executable_path)
    if not chromium.is_file() or not os.access(chromium, os.X_OK):
        print("Chưa có Chromium của Playwright; đang tải (cần kết nối mạng)...", flush=True)
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        if not chromium.is_file() or not os.access(chromium, os.X_OK):
            raise RuntimeError(f"Cài xong nhưng chưa tìm thấy browser executable: {chromium}")
    print(f"Trình duyệt: Chromium ({chromium})")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Không thể khởi động: {exc}\nXem phần troubleshooting trong README.md.", file=sys.stderr)
        sys.exit(1)
