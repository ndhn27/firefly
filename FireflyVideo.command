#!/usr/bin/env bash
# macOS: bấm đúp file này để chạy Firefly Video (mở trong Terminal; đóng cửa sổ Terminal là tắt tool).
# Lần đầu macOS có thể chặn vì file tải từ internet: bấm chuột phải vào file → Mở → Mở.
cd "$(dirname "$0")" || exit 1
./run.sh
code=$?
echo
echo "Firefly Video đã dừng (mã $code). Bấm Enter để đóng cửa sổ."
read -r _
exit "$code"
