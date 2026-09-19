#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${SPARKFLOW_PYTHON:-../.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  echo 'Hãy tạo môi trường .venv và cài thư viện trước; xem README.md.' >&2
  exit 1
fi
umask 077
mkdir -p logs
"$PYTHON" login_desktop_server.py > logs/login-desktop.log 2>&1 &
LOGIN_PID=$!
cleanup() { kill "$LOGIN_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
export SPARKFLOW_BROWSER_HEADFUL=1
"$PYTHON" main.py --web --host 127.0.0.1 --port 8787
