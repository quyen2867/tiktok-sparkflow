#!/bin/bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${SPARKFLOW_PYTHON:-$APP_DIR/../.venv/bin/python}"
if ! PYTHON="$(command -v "$PYTHON")" || [ ! -x "$PYTHON" ]; then
  echo 'Không tìm thấy Python. Tại thư mục repo, chạy từng lệnh:' >&2
  echo 'python3.11 -m venv .venv' >&2
  echo 'source .venv/bin/activate' >&2
  echo 'python -m pip install --upgrade pip' >&2
  echo 'python -m pip install -r DouYinSparkFlow/requirements.txt' >&2
  exit 1
fi
# Resolve a relative SPARKFLOW_PYTHON before changing the working directory.
PYTHON="$(cd "$(dirname "$PYTHON")" && pwd)/$(basename "$PYTHON")"
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Cần Python >=3.11; đang dùng " + sys.version.split()[0] + ". Hãy tạo lại .venv bằng Python 3.11 trở lên (xem README).")'
cd "$APP_DIR"

# Explicit browser settings take precedence over automatic Brave detection.
BRAVE='/Applications/Brave Browser.app/Contents/MacOS/Brave Browser'
if [ -z "${SPARKFLOW_BROWSER_EXECUTABLE:-}" ] && [ -z "${SPARKFLOW_BROWSER_CHANNEL:-}" ] && [ -x "$BRAVE" ]; then
  export SPARKFLOW_BROWSER_EXECUTABLE="$BRAVE"
fi
export SPARKFLOW_BROWSER_HEADFUL=1
umask 077
"$PYTHON" scripts/check_macos_setup.py
mkdir -p logs
"$PYTHON" login_desktop_server.py > logs/login-desktop.log 2>&1 &
LOGIN_PID=$!
cleanup() { kill "$LOGIN_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
"$PYTHON" main.py --web --host 127.0.0.1 --port 8787
