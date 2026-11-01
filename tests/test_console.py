"""In tiếng Việt ra cửa sổ lệnh / ống (pipe) không bao giờ làm app sập vì bảng mã.
Lỗi thật trên Windows: bản .exe của PyInstaller bỏ qua PYTHONUTF8, nên khi stdout là ống nó dùng cp1252; "đ" không mã hoá được
-> UnicodeEncodeError ở dòng in địa chỉ, rồi thêm một lỗi nữa trong khối báo lỗi -> "Failed to execute script 'app'"."""
import io
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

import app as A

ROOT = Path(__file__).resolve().parent.parent
TEXT = "Firefly Video v0.9 đang chạy · LỖI: cổng bận"


def legacy(tty=False, encoding="cp1252"):
    """Luồng ra giống stdout dạng ống trên Windows tiếng Anh (bảng mã ANSI cp1252).
    newline="\n": test này chỉ kiểm BẢNG MÃ. Mặc định (newline=None) Windows dịch "\n" thành "\r\n" nên cùng một test
    sẽ cho kết quả khác nhau giữa Windows và Linux/macOS."""
    raw = io.BytesIO()
    cls = type("Tty", (io.TextIOWrapper,), {"isatty": lambda self: True}) if tty else io.TextIOWrapper
    return raw, cls(raw, encoding=encoding, newline="\n", write_through=True)


def test_premise_a_cp1252_pipe_really_cannot_print_vietnamese():
    _, out = legacy()
    with pytest.raises(UnicodeEncodeError):
        print(TEXT, file=out)


def test_pipes_become_utf8_and_never_raise(monkeypatch):
    raw_o, out = legacy()
    raw_e, err = legacy()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    A.utf8_stdio()
    print(TEXT)
    print(TEXT, file=sys.stderr)
    assert raw_o.getvalue().decode("utf-8") == TEXT + "\n" and raw_e.getvalue().decode("utf-8") == TEXT + "\n"


def test_a_real_console_keeps_its_own_encoding_but_still_never_raises(monkeypatch):
    raw, out = legacy(tty=True, encoding="cp437")
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", None)  # bản không có cửa sổ lệnh: stderr là None
    A.utf8_stdio()
    print(TEXT)  # "đ" không có trong cp437 -> thay bằng "?", không ném lỗi
    assert out.encoding.lower().replace("_", "") in ("cp437", "ibm437") and b"?" in raw.getvalue()


def test_app_starts_and_prints_utf8_even_when_stdout_is_a_cp1252_pipe(tmp_path):
    """Chạy app.py như bản .exe trên Windows chạy dưới CI: stdout/stderr là ống, bảng mã mặc định là cp1252."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = dict(os.environ, PYTHONUTF8="0", PYTHONIOENCODING="cp1252", FFV_HOME=str(tmp_path), FFV_NO_BROWSER="1", PORT=str(port))
    proc = subprocess.Popen([sys.executable, str(ROOT / "app.py")], env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    up = False
    try:
        t0 = time.time()
        while time.time() - t0 < 60 and proc.poll() is None and not up:
            try:
                up = b"firefly-video" in urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=2).read()
            except OSError:
                time.sleep(0.3)
    finally:
        proc.terminate()
        try:
            out = proc.communicate(timeout=15)[0]
        except subprocess.TimeoutExpired:
            proc.kill()
            out = proc.communicate()[0]
    text = out.decode("utf-8")  # nghiêm ngặt: sai bảng mã là hỏng ngay
    assert up, text[-2000:]
    assert "đang chạy tại" in text and "Traceback" not in text and "Logging error" not in text, text[-2000:]
