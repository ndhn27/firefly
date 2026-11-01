"""Bản đóng gói PyInstaller (chậm, build khoảng 30–60 giây):  FFV_TEST_PACK=1 python -m pytest tests/test_pack.py
Chạy file đã đóng gói như người dùng thật: PATH để trống (buộc dùng FFmpeg kèm theo), dữ liệu phải nằm cạnh file chạy,
xuất video song song, nhật ký được ghi, tắt rồi mở lại vẫn còn dự án, mở lần hai thì nhận ra bản đang chạy.
Chạy cả với FFV_MP=spawn – cách tạo tiến trình con của Windows/macOS – vì đó là đường dễ hỏng nhất khi đóng gói.
Dùng sẵn bản đã build: đặt FFV_PACK_DIST=<đường dẫn dist/FireflyVideo> để khỏi build lại."""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("FFV_TEST_PACK"), reason="chậm: đặt FFV_TEST_PACK=1 để chạy")
HERE = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    pre = os.environ.get("FFV_PACK_DIST")
    if pre:
        d = tmp_path_factory.mktemp("copy") / "FireflyVideo"
        shutil.copytree(pre, d, symlinks=True, ignore=shutil.ignore_patterns("projects", "logs"))  # bản sạch, không dính dữ liệu cũ
        return d
    pytest.importorskip("PyInstaller")
    out = tmp_path_factory.mktemp("pack")
    r = subprocess.run([sys.executable, "-m", "PyInstaller", str(HERE / "firefly.spec"), "--noconfirm", "--clean",
                        "--distpath", str(out / "dist"), "--workpath", str(out / "work")], cwd=HERE, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    return out / "dist" / "FireflyVideo"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start(dist, port, mp=None, tmp=None):
    exe = dist / ("FireflyVideo.exe" if os.name == "nt" else "FireflyVideo")
    empty = tmp / "path-trong"
    empty.mkdir(exist_ok=True)
    env = dict(os.environ, FFV_FAKE_TTS="1", PORT=str(port), PATH=str(empty), FFV_LOG_LEVEL="DEBUG")
    if os.name == "nt":
        env["PATH"] = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    env.pop("FFV_HOME", None)
    env.pop("FFV_MP", None)
    if mp:
        env["FFV_MP"] = mp
    return subprocess.Popen([str(exe)], cwd=str(tmp), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def call(port, path, data=None, method=None, timeout=60):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(data).encode() if data is not None else None,
                                 method=method or ("POST" if data is not None else "GET"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def wait_up(port, proc, timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            raise AssertionError("tiến trình thoát sớm:\n" + (proc.stdout.read() or "")[-3000:])
        try:
            if call(port, "/api/ping", timeout=2).get("app") == "firefly-video":
                return
        except Exception:  # noqa
            time.sleep(0.5)
    raise AssertionError("không lên được sau %ss" % timeout)


def wait_job(port, jid, timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = call(port, f"/api/jobs/{jid}")
        if st["state"] != "running":
            return st
        time.sleep(0.5)
    raise AssertionError("job quá lâu")


def stop(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(15)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.mark.parametrize("mp", [None, "spawn"], ids=["mac-dinh", "spawn-nhu-windows"])
def test_frozen_app_end_to_end(dist, tmp_path, mp):
    from PIL import Image
    for sub in ("projects", "logs"):  # mỗi lần chạy bắt đầu sạch (cùng một bản build dùng cho nhiều tham số)
        shutil.rmtree(dist / sub, ignore_errors=True)
    port = free_port()
    proc = start(dist, port, mp, tmp_path)
    try:
        wait_up(port, proc)
        # --- kiểm tra máy: FFmpeg phải là bản kèm theo, không phải của máy
        items = {i["name"]: i for i in call(port, "/api/doctor")["items"]}
        ff = items["FFmpeg"]
        assert ff["ok"] and str(dist) in ff["detail"], ff
        # --- một dự án nhỏ, có ảnh, có giọng (giả), xuất song song
        r = call(port, "/api/projects", {"name": "Đóng gói", "aspect": "9:16", "quality": 360, "fps": 24})
        pid, p = r["id"], r["project"]
        img = tmp_path / "a.png"
        Image.new("RGB", (640, 360), (40, 90, 160)).save(img)
        import http.client, mimetypes  # noqa: E401
        boundary = uuid.uuid4().hex
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.png"\r\nContent-Type: image/png\r\n\r\n').encode() \
            + img.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        c.request("POST", f"/api/projects/{pid}/upload", body, {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        fname = json.loads(c.getresponse().read())["file"]
        p["scenes"] = [dict(id="a", title="Bản đóng gói", subtitle="", narration="Xin chào, đây là bản đóng gói chạy thử.", voice=True,
                            caption=True, images=[dict(file=fname, mode="card", anim="zoom")], transition="fade"),
                       dict(id="b", title="Cảnh hai", subtitle="", narration="Cảnh thứ hai ngắn thôi.", voice=True, caption=True,
                            images=[], transition="none")]
        p["export_tier"] = "draft"
        call(port, f"/api/projects/{pid}", p, "PUT")
        st = wait_job(port, call(port, f"/api/projects/{pid}/render", {"mode": "final"})["job"])
        assert st["state"] == "done", st
        out = dist / "projects" / pid / "out" / Path(st["file"]).name
        assert out.stat().st_size > 5000, "video phải nằm trong projects/ cạnh file chạy"
        assert st["info"]["frames"] > 20
        # --- nhật ký
        log = (dist / "logs" / "firefly.log").read_text("utf-8")
        assert "bản đóng gói" in log and "Xuất xong" in log and "sẵn sàng" in log, "log của tiến trình con phải về được file chính"
        # --- mở lần hai: nhận ra bản đang chạy rồi thoát
        second = start(dist, port, mp, tmp_path)
        assert second.wait(60) == 0 and "đã chạy sẵn" in second.stdout.read()
    finally:
        stop(proc)
    # --- tắt rồi mở lại: dự án vẫn còn (dữ liệu cạnh file chạy, không nằm trong thư mục tạm)
    port2 = free_port()
    proc2 = start(dist, port2, mp, tmp_path)
    try:
        wait_up(port2, proc2)
        assert [x["id"] for x in call(port2, "/api/projects")] == [pid]
    finally:
        stop(proc2)
