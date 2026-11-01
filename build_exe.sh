#!/usr/bin/env bash
# Đóng gói thành dist/FireflyVideo/FireflyVideo (cùng một spec với Windows). Dùng môi trường riêng .venv-build nên chạy được cả trên
# Python mới của Debian/Ubuntu/Homebrew (không đụng Python hệ thống). Kết quả build theo hệ điều hành đang chạy: muốn bản Windows thì build trên Windows.
cd "$(dirname "$0")" || exit 1
# shellcheck source=ffv_env.sh
. ./ffv_env.sh
PY="$(ffv_venv .venv-build)" || exit 1
ffv_install "$PY" requirements.txt requirements-pack.txt || exit 1
"$PY" -m PyInstaller firefly.spec --noconfirm --clean || exit 1
echo "Xong. Chạy: dist/FireflyVideo/FireflyVideo"
