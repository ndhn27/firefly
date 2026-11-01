"""Nhật ký: ghi ra file logs/firefly.log (xoay vòng 5 x 1 MB) và ra cửa sổ lệnh.
Xuất video chạy ở nhiều tiến trình con; chúng gửi log về tiến trình chính qua hàng đợi để cùng nằm trong một file
(nhiều tiến trình cùng ghi và xoay vòng một file trên Windows sẽ hỏng file).
Đổi mức chi tiết bằng biến môi trường FFV_LOG_LEVEL=DEBUG (có cả lệnh FFmpeg và thời gian từng bước)."""
import logging
import logging.handlers
import os
import platform
import sys
import threading
from pathlib import Path

import paths
from version import APP_NAME, __version__

ROOT_NAME = "ffv"
FMT = "%(asctime)s %(levelname)-7s [%(processName)s] %(name)s: %(message)s"
MAX_BYTES, BACKUPS = 1_000_000, 5
_state = {}


def get(name):
    return logging.getLogger(f"{ROOT_NAME}.{name}")


def log_path():
    return Path(_state.get("dir") or (paths.DATA_DIR / "logs")) / "firefly.log"


def setup(log_dir=None, level=None, console=True):
    """Gọi một lần ở tiến trình chính (gọi lại thì cấu hình lại – dùng cho test)."""
    teardown()
    d = Path(log_dir) if log_dir else paths.DATA_DIR / "logs"
    d.mkdir(parents=True, exist_ok=True)
    level = (level or os.environ.get("FFV_LOG_LEVEL") or "INFO").upper()
    fh = logging.handlers.RotatingFileHandler(d / "firefly.log", maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
    fh.setFormatter(logging.Formatter(FMT))
    handlers = [fh]
    if console and getattr(sys, "stderr", None) is not None:  # bản đóng gói không có cửa sổ lệnh thì stderr là None
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
        sh.setLevel(logging.INFO)
        handlers.append(sh)
    root = logging.getLogger(ROOT_NAME)
    root.handlers = handlers
    root.setLevel(getattr(logging, level, logging.INFO))
    root.propagate = False
    _state.update(dir=str(d), handlers=handlers, level=root.level)
    _install_hooks()
    return root


def teardown():
    _remove_hooks()
    root = logging.getLogger(ROOT_NAME)
    for h in list(root.handlers):
        try:
            h.close()
        except Exception:  # noqa
            pass
        root.removeHandler(h)
    _state.pop("handlers", None)
    _state.pop("dir", None)


def configured():
    return bool(_state.get("handlers"))


def _install_hooks():
    """Lỗi không ai bắt (kể cả trong luồng nền) cũng phải vào nhật ký, không chỉ trôi mất ở cửa sổ lệnh."""
    if _state.get("prev_hook") is not None:
        return
    prev, prev_t = sys.excepthook, threading.excepthook

    def hook(et, ev, tb):
        if not issubclass(et, KeyboardInterrupt):
            get("crash").critical("Lỗi không bắt được", exc_info=(et, ev, tb))
        prev(et, ev, tb)

    def thook(args):
        if not issubclass(args.exc_type, SystemExit):
            get("crash").critical("Lỗi không bắt được trong luồng %s", getattr(args.thread, "name", "?"),
                                  exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        prev_t(args)

    _state.update(prev_hook=prev, prev_thook=prev_t, hook=hook, thook=thook)
    sys.excepthook, threading.excepthook = hook, thook


def _remove_hooks():
    if _state.get("prev_hook") is None:
        return
    if sys.excepthook is _state["hook"]:
        sys.excepthook = _state["prev_hook"]
    if threading.excepthook is _state["thook"]:
        threading.excepthook = _state["prev_thook"]
    for k in ("prev_hook", "prev_thook", "hook", "thook"):
        _state.pop(k, None)


def banner(extra=None):
    lg = get("app")
    lg.info("=" * 60)
    lg.info("%s v%s · Python %s · %s · %s", APP_NAME, __version__, platform.python_version(), platform.platform(),
            "bản đóng gói" if getattr(sys, "frozen", False) else "chạy từ mã nguồn")
    lg.info("Dữ liệu: %s · tài nguyên: %s · CPU: %s luồng", paths.DATA_DIR, paths.RES_DIR, os.cpu_count())
    for k, v in (extra or {}).items():
        lg.info("%s: %s", k, v)


def tail(n=200, max_bytes=400_000):
    """n dòng cuối của file nhật ký hiện tại ([] nếu chưa có)."""
    p = log_path()
    try:
        size = p.stat().st_size
        with open(p, "rb") as f:
            f.seek(max(0, size - max_bytes))
            data = f.read()
    except OSError:
        return []
    lines = data.decode("utf-8", "replace").splitlines()
    if size > max_bytes and lines:
        lines = lines[1:]  # dòng đầu có thể bị cắt dở
    return lines[-max(1, int(n)):]


# ----------------------------------------------------------------------------- tiến trình con
def attach_queue(ctx):
    """Tạo hàng đợi log cho một nhóm tiến trình con (phải cùng `ctx` multiprocessing với nhóm đó).
    -> (hàng đợi hoặc None nếu chưa bật nhật ký, hàm dừng). Phía chính đọc hàng đợi và ghi vào đúng các handler ở trên."""
    if not configured():
        return None, lambda: None
    q = ctx.Queue(-1)
    listener = logging.handlers.QueueListener(q, *_state["handlers"], respect_handler_level=True)
    listener.start()

    def stop():
        try:
            listener.stop()
        except Exception:  # noqa
            pass

    return q, stop


def worker_init(q, level=logging.INFO):
    """Chạy đầu tiên trong mỗi tiến trình con: bỏ handler thừa kế từ tiến trình chính (fork) và gửi log về hàng đợi."""
    root = logging.getLogger(ROOT_NAME)
    root.handlers = []
    root.propagate = False
    if q is not None:
        root.addHandler(logging.handlers.QueueHandler(q))
        root.setLevel(level)
    else:
        root.addHandler(logging.NullHandler())


def selftest_worker(msg):
    """Chỉ để test: ghi 1 dòng log từ tiến trình con."""
    get("worker").warning("%s", msg)
    return os.getpid()
