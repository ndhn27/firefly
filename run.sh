#!/usr/bin/env bash
# Chạy Firefly Video từ mã nguồn (Linux, macOS, WSL). Lần đầu tự tạo môi trường riêng .venv và cài thư viện; các lần sau chạy ngay.
# Không cần quyền quản trị và không đụng Python của hệ thống. macOS: bấm đúp FireflyVideo.command. Linux: ./install_linux_shortcut.sh để có biểu tượng trong menu.
cd "$(dirname "$0")" || exit 1
# shellcheck source=ffv_env.sh
. ./ffv_env.sh
PY="$(ffv_venv .venv)" || exit 1
ffv_install "$PY" requirements.txt || exit 1
"$PY" app.py "$@"
