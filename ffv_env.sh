# Dùng chung cho run.sh và build_exe.sh trên Linux/macOS/WSL (dùng bằng `source`, đừng chạy trực tiếp). Chỉ dùng tính năng của bash 3.2 (bản kèm macOS).
#
# Vì sao có môi trường riêng (.venv)? Python mới trên Debian/Ubuntu/Homebrew từ chối `pip install` vào Python hệ thống
# ("externally-managed-environment"), nên `python3 -m pip install -r requirements.txt` thẳng vào hệ thống hỏng ngay lần chạy đầu.

# In đường dẫn một Python từ 3.10 trở lên (ưu tiên bản mới nhất), hoặc trả mã lỗi.
ffv_find_python() {
  local c
  for c in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
      command -v "$c"
      return 0
    fi
  done
  return 1
}

# ffv_venv <thư mục>: tạo môi trường nếu chưa có, in ra đường dẫn python trong đó. Thông báo lỗi ra stderr.
ffv_venv() {
  local dir="$1" py
  if [ ! -x "$dir/bin/python" ]; then
    if ! py="$(ffv_find_python)"; then
      {
        echo "Cần Python 3.10 trở lên nhưng máy chưa có."
        echo "  macOS:          brew install python   (hoặc tải bản cài ở https://www.python.org/downloads/)"
        echo "  Ubuntu/Debian:  sudo apt install python3 python3-venv"
        echo "  Fedora:         sudo dnf install python3"
      } >&2
      return 1
    fi
    if ! "$py" -m venv "$dir" >/dev/null 2>&1; then
      rm -rf "$dir"
      {
        echo "Không tạo được môi trường Python riêng bằng $py."
        echo "  Ubuntu/Debian: sudo apt install python3-venv     rồi chạy lại."
      } >&2
      return 1
    fi
  fi
  echo "$dir/bin/python"
}

# ffv_install <python của venv> <file requirements>...: chỉ cài khi nội dung các file đó đổi từ lần cài trước (khởi động lại thì gần như tức thì).
ffv_install() {
  local py="$1" f stamp mark
  shift
  local args=()
  for f in "$@"; do args+=(-r "$f"); done
  stamp="$(cat "$@" | cksum | tr -d ' ')"
  mark="$(dirname "$py")/../.requirements-stamp"
  if [ "$(cat "$mark" 2>/dev/null)" = "$stamp" ]; then
    return 0
  fi
  echo "Đang cài thư viện (lần đầu hoặc khi requirements đổi; cần internet, có thể mất vài phút)…" >&2
  if ! "$py" -m pip install -q --disable-pip-version-check "${args[@]}"; then
    echo "Không cài được thư viện. Kiểm tra kết nối internet rồi chạy lại." >&2
    return 1
  fi
  echo "$stamp" > "$mark"
}
