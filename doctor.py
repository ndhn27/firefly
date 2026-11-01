"""Kiểm tra môi trường trước khi dùng:  python doctor.py   (hoặc mở http://localhost:8765/api/doctor khi tool đang chạy).
Mỗi mục có level: ok / warn (dùng được nhưng nên biết) / error (sẽ không chạy được)."""
import importlib
import importlib.metadata
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import paths
from version import APP_NAME, __version__

HERE = paths.DATA_DIR  # ai_settings.json nằm ở thư mục dữ liệu (cạnh file .exe khi chạy bản đóng gói)
PACKAGES = [("flask", "flask"), ("numpy", "numpy"), ("cv2", "opencv-python-headless"), ("PIL", "pillow"),
            ("edge_tts", "edge-tts"), ("imageio_ffmpeg", "imageio-ffmpeg"), ("pydantic", "pydantic")]
FONT_FILES = ["BeVietnamPro-Bold.ttf", "BeVietnamPro-SemiBold.ttf", "BeVietnamPro-Regular.ttf"]


def _item(name, level, detail):
    return dict(name=name, level=level, ok=level != "error", detail=detail)


def check_python():
    v = sys.version_info
    ok = v >= (3, 10)
    return _item("Python", "ok" if ok else "error", f"{v.major}.{v.minor}.{v.micro}" + ("" if ok else " – cần 3.10 trở lên"))


def check_packages():
    out = []
    for mod, pipname in PACKAGES:
        try:
            importlib.import_module(mod)
            try:
                ver = importlib.metadata.version(pipname)
            except Exception:  # noqa
                ver = "đã cài"
            out.append(_item(f"Thư viện {pipname}", "ok", ver))
        except Exception:  # noqa
            out.append(_item(f"Thư viện {pipname}", "error", f"chưa cài – chạy: pip install {pipname}"))
    return out


def check_ffmpeg():
    try:
        import media as M
        exe = M.ffmpeg_exe()
        ver = subprocess.run([exe, "-version"], capture_output=True, timeout=15, **M.NOWIN).stdout.decode("utf-8", "ignore")
        first = ver.splitlines()[0] if ver else exe
        enc = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, timeout=15, **M.NOWIN).stdout.decode("utf-8", "ignore")
    except Exception as e:  # noqa
        return [_item("FFmpeg", "error", f"không chạy được ({e}). Cài: winget install Gyan.FFmpeg, hoặc pip install imageio-ffmpeg")]
    out = [_item("FFmpeg", "ok", f"{first} ({exe})")]
    try:  # chuẩn hoá âm lượng cần 2 bộ lọc này
        flt = subprocess.run([exe, "-hide_banner", "-filters"], capture_output=True, timeout=15, **M.NOWIN).stdout.decode("utf-8", "ignore")
    except Exception:  # noqa
        flt = ""
    miss = [n for n in ("loudnorm", "alimiter") if n not in flt]
    out.append(_item("Bộ lọc âm lượng (loudnorm, alimiter)", "ok" if not miss else "error",
                     "có" if not miss else f"bản FFmpeg này thiếu {', '.join(miss)} – không chuẩn hoá được âm lượng, cần bản FFmpeg khác"))
    out.append(_item("Encoder libx264 (CPU)", "ok" if "libx264" in enc else "error",
                     "có" if "libx264" in enc else "bản FFmpeg này không có libx264 – cần bản khác"))
    for label, name in (("NVIDIA NVENC", "h264_nvenc"), ("Intel QSV", "h264_qsv"), ("AMD AMF", "h264_amf")):
        if name not in enc:
            out.append(_item(f"Encoder {label}", "warn", "bản FFmpeg này không kèm encoder đó"))
            continue
        ok, detail = M.probe_encoder(name)
        out.append(_item(f"Encoder {label}", "ok" if ok else "warn", "dùng được" if ok else f"có trong FFmpeg nhưng máy không chạy được ({detail})"))
    return out


def check_fonts():
    dirs = [paths.DATA_DIR / "fonts", paths.RES_DIR / "fonts"]
    miss = [f for f in FONT_FILES if not any((x / f).exists() for x in dirs)]
    if not miss:
        return _item("Font Be Vietnam Pro", "ok", "đủ 3 file trong fonts/")
    return _item("Font Be Vietnam Pro", "warn", "thiếu " + ", ".join(miss) + " – tool sẽ thử tải lại, không được thì dùng font hệ thống (có thể lệch dấu)")


def check_network():
    try:
        socket.create_connection(("speech.platform.bing.com", 443), timeout=4).close()
        return _item("Kết nối dịch vụ giọng đọc", "ok", "tới được speech.platform.bing.com")
    except Exception as e:  # noqa
        return _item("Kết nối dịch vụ giọng đọc", "warn", f"không tới được ({e.__class__.__name__}) – cần internet mới tạo được giọng Edge TTS (giọng dự phòng chạy trên máy thì không cần)")


def check_tts_fallback():
    """Giọng dự phòng khi Edge TTS (endpoint không chính thức) bị đổi/chặn. Chỉ là cảnh báo, không bao giờ là lỗi: tool vẫn chạy bằng giọng chính."""
    import tts as T
    out, have_backup = [], False
    for e in T.status():
        if e["primary"]:
            out.append(_item(f"Giọng đọc chính – {e['label']}", "ok" if e["ok"] else "warn", e["detail"]))
        else:
            have_backup |= e["ok"]
            out.append(_item(f"Giọng dự phòng – {e['label']}", "ok" if e["ok"] else "warn",
                             e["detail"] if e["ok"] else e["detail"] + " (tuỳ chọn; xem README, mục Giọng dự phòng)"))
    if not have_backup:
        out.append(_item("Giọng dự phòng", "warn", "chưa có giọng dự phòng nào dùng được – nếu Microsoft đổi hoặc chặn Edge TTS thì không tạo được giọng. "
                                                   "Nên cài Piper (chạy trên máy) hoặc gTTS: xem README, mục Giọng dự phòng"))
    return out


def check_ollama():
    """Tuỳ chọn: chỉ cần khi dùng \"Tạo kịch bản bằng AI\", nên không chạy được cũng chỉ là cảnh báo."""
    try:
        import scriptgen as G
        cfg = G.load_config(HERE / "ai_settings.json")
        models = G.list_models(cfg["url"], timeout=2.0)
    except Exception as e:  # noqa
        return _item("Ollama (kịch bản AI, tuỳ chọn)", "warn", f"{e} Không dùng AI thì bỏ qua mục này.")
    if not models:
        return _item("Ollama (kịch bản AI, tuỳ chọn)", "warn", f"chạy ở {cfg['url']} nhưng chưa có mô hình nào – chạy: ollama pull <tên mô hình>")
    return _item("Ollama (kịch bản AI, tuỳ chọn)", "ok", f"{cfg['url']} – {len(models)} mô hình: " + ", ".join(m["name"] for m in models[:5]))


def check_resources():
    import os
    try:
        free = shutil.disk_usage(paths.DATA_DIR).free / 1e9
    except OSError as e:
        return [_item("Ổ đĩa trống", "warn", f"không đọc được ({e})")]
    level = "error" if free < 0.5 else "ok" if free >= 5 else "warn"
    return [_item("CPU", "ok", f"{os.cpu_count()} luồng"),
            _item("Ổ đĩa trống", level, f"{free:.1f} GB" + ("" if free >= 5 else " – xuất 2K nên còn trống từ 5 GB" if free >= 0.5 else " – gần đầy, không xuất được"))]


def check_data_dir():
    """Thư mục dự án + nhật ký phải ghi được (hay hỏng khi để tool trong Program Files hoặc thư mục chỉ đọc)."""
    import logsetup as L
    out = []
    for label, p in (("Thư mục dự án", paths.DATA_DIR / "projects"), ("Thư mục nhật ký", L.log_path().parent)):
        try:
            p.mkdir(parents=True, exist_ok=True)
            probe = p / ".write-test"
            probe.write_text("ok", "utf-8")
            probe.unlink()
            out.append(_item(label, "ok", f"ghi được ({p})"))
        except OSError as e:
            out.append(_item(label, "error", f"không ghi được {p} ({e.__class__.__name__}). Chuyển tool sang thư mục khác (không phải Program Files) hoặc đặt biến FFV_HOME"))
    return out


def run_checks():
    import logsetup as L
    items = [_item(APP_NAME, "ok", f"v{__version__} · nhật ký: {L.log_path()}"), check_python()] + check_packages() + check_ffmpeg() \
        + [check_fonts()] + check_data_dir() + [check_network()] + check_tts_fallback() + [check_ollama()] + check_resources()
    return dict(ok=all(i["ok"] for i in items), items=items)


def main():
    sys.path.insert(0, str(HERE))
    res = run_checks()
    mark = {"ok": "[ OK ]", "warn": "[ !  ]", "error": "[LỖI ]"}
    for i in res["items"]:
        print(f"{mark[i['level']]} {i['name']}: {i['detail']}")
    print("\nĐủ điều kiện chạy." if res["ok"] else "\nCòn lỗi cần sửa (các mục [LỖI ]).")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
