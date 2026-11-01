#!/usr/bin/env bash
# Linux: thêm Firefly Video vào menu ứng dụng (và tuỳ chọn ra Desktop) để mở bằng một cú bấm.
#   ./install_linux_shortcut.sh             thêm vào menu ứng dụng
#   ./install_linux_shortcut.sh --desktop   thêm cả biểu tượng ra màn hình nền
#   ./install_linux_shortcut.sh --remove    gỡ cả hai
# Đường dẫn trong lối tắt là đường dẫn tuyệt đối tới thư mục này: chuyển thư mục đi chỗ khác thì chạy lại file này.
set -e
here="$(cd "$(dirname "$0")" && pwd)"
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
name="firefly-video.desktop"
desk=""
if command -v xdg-user-dir >/dev/null 2>&1; then desk="$(xdg-user-dir DESKTOP 2>/dev/null || true)"; fi
[ -n "$desk" ] || desk="$HOME/Desktop"

if [ "$1" = "--remove" ]; then
  rm -f "$apps/$name" "$desk/$name"
  echo "Đã gỡ lối tắt."
  exit 0
fi

mkdir -p "$apps"
# Terminal=true: tool chạy trong cửa sổ dòng lệnh, đóng cửa sổ là tắt tool (giống cửa sổ lệnh trên Windows).
cat > "$apps/$name" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Firefly Video
Comment=Dựng video giải thích: nền đom đóm, giọng đọc, phụ đề
Exec="$here/run.sh"
Path=$here
Terminal=true
Categories=AudioVideo;Video;
DESKTOP
chmod +x "$apps/$name"
echo "Đã thêm vào menu ứng dụng: $apps/$name"

if [ "$1" = "--desktop" ]; then
  mkdir -p "$desk"
  cp "$apps/$name" "$desk/$name"
  chmod +x "$desk/$name"
  # GNOME chỉ cho mở lối tắt trên Desktop khi đánh dấu "tin cậy"; các môi trường khác bỏ qua lệnh này
  gio set "$desk/$name" metadata::trusted true >/dev/null 2>&1 || true
  echo "Đã thêm ra Desktop: $desk/$name (nếu bấm không chạy: chuột phải → Allow Launching)"
fi
