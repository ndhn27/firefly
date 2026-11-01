"""Đường dẫn của tool.
  RES_DIR  – nơi đọc file kèm theo (static/, fonts/).
  DATA_DIR – nơi ghi (projects/, logs/, ai_settings.json, font tải thêm).
Chạy từ mã nguồn: cả hai là thư mục dự án. Chạy bản đóng gói PyInstaller: RES_DIR là thư mục bundle (chỉ đọc, có thể là
thư mục tạm), DATA_DIR là thư mục chứa file .exe để dự án và nhật ký không mất khi bản tạm bị xoá.
Đặt biến môi trường FFV_HOME để đưa dữ liệu sang chỗ khác."""
import os
import sys
from pathlib import Path


def resolve(frozen=None, meipass=None, executable=None, env=None, source_dir=None):
    """-> (RES_DIR, DATA_DIR). Các tham số để test mô phỏng bản đóng gói; bình thường để trống."""
    env = os.environ if env is None else env
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    src = Path(source_dir) if source_dir else Path(__file__).resolve().parent
    if frozen:
        res = Path(meipass or getattr(sys, "_MEIPASS", None) or src)
        data = Path(executable or sys.executable).resolve().parent
    else:
        res, data = src, src
    if env.get("FFV_HOME"):
        data = Path(env["FFV_HOME"]).expanduser()
    return res, data


RES_DIR, DATA_DIR = resolve()
