"""Nhật ký ra file, thông báo lỗi tiếng Việt, kiểm tra dự án trước khi xuất, khôi phục file hỏng, cổng bận,
đường dẫn bản đóng gói."""
import concurrent.futures as cf
import errno
import json
import logging
import logging.handlers
import multiprocessing
import os
import pickle
import socket
import threading
import time
from collections import namedtuple
from concurrent.futures.process import BrokenProcessPool

import pytest
from PIL import Image, UnidentifiedImageError
from werkzeug.serving import make_server

import app as A
import checks as C
import doctor as D
import errors as E
import logsetup as L
import media as M
import paths
import render as R
import scriptgen as G
from conftest import add_fake_audio, make_images, make_project


@pytest.fixture()
def logs(tmp_path):
    L.setup(log_dir=tmp_path / "logs", level="DEBUG", console=False)
    yield tmp_path / "logs" / "firefly.log"
    L.teardown()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "PROJ", tmp_path / "projects")
    A.PROJ.mkdir()
    return A.app.test_client()


def new_project(client, scenes=(), **extra):
    r = client.post("/api/projects", json={"name": "E7"}).get_json()
    pid, p = r["id"], r["project"]
    p["scenes"] = list(scenes)
    p.update(extra)
    resp = client.put(f"/api/projects/{pid}", json=p)
    assert resp.status_code == 200
    return pid, p


def scene(sid, narr="", images=(), **kw):
    return dict(id=sid, title="Tiêu đề", subtitle="", narration=narr, voice=bool(narr), caption=True,
                images=[dict(file=f, mode="card", anim="zoom") for f in images], transition="fade", **kw)


def wait_job(jid, timeout=60):
    t0 = time.time()
    while A.JOBS[jid]["state"] == "running" and time.time() - t0 < timeout:
        time.sleep(0.05)
    return A.JOBS[jid]


# ============================================================================ đường dẫn (bản đóng gói)
def test_paths_source_frozen_and_override(tmp_path):
    src = tmp_path / "src"
    assert paths.resolve(frozen=False, source_dir=src, env={}) == (src, src)
    exe = tmp_path / "app" / "FireflyVideo.exe"
    res, data = paths.resolve(frozen=True, meipass=str(tmp_path / "_MEI1"), executable=str(exe), env={}, source_dir=src)
    assert res == tmp_path / "_MEI1" and data == (tmp_path / "app").resolve(), "dữ liệu phải nằm cạnh file .exe, không phải thư mục tạm"
    _, data = paths.resolve(frozen=True, meipass="/x", executable=str(exe), env={"FFV_HOME": str(tmp_path / "home")}, source_dir=src)
    assert data == tmp_path / "home"


def test_app_reads_resources_from_res_dir_and_writes_to_data_dir():
    assert A.app.static_folder == str(paths.RES_DIR / "static")
    assert A.PROJ == paths.DATA_DIR / "projects"
    assert R.FONT_DIRS[0] == paths.DATA_DIR / "fonts" and R.FONT_DIRS[1] == paths.RES_DIR / "fonts"


def test_export_key_survives_missing_source_file(monkeypatch):
    """Bản đóng gói không có file render.py thật để băm: phải rơi về số phiên bản, và ổn định giữa các lần gọi."""
    p = make_project("9:16")
    k_src = M.export_key(p, 540, 960, 30, "libx264", [])
    monkeypatch.setattr(R, "__file__", "/khong/co/render.pyc")
    k1, k2 = (M.export_key(p, 540, 960, 30, "libx264", []) for _ in range(2))
    assert k1 == k2 and k1 != k_src


# ============================================================================ nhật ký
def test_log_file_format_rotation_and_tail(logs):
    L.get("thu").warning("xin chào %s", "đom đóm")
    text = logs.read_text("utf-8")
    assert "WARNING" in text and "ffv.thu" in text and "xin chào đom đóm" in text
    h = next(h for h in logging.getLogger("ffv").handlers if isinstance(h, logging.handlers.RotatingFileHandler))
    assert (h.maxBytes, h.backupCount) == (L.MAX_BYTES, L.BACKUPS)
    assert L.tail(1)[-1].endswith("xin chào đom đóm")
    assert L.log_path() == logs


def test_log_rotates_instead_of_growing_forever(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "MAX_BYTES", 2000)
    L.setup(log_dir=tmp_path / "l", level="INFO", console=False)
    try:
        for i in range(200):
            L.get("x").info("dòng số %d %s", i, "x" * 50)
    finally:
        L.teardown()
    files = sorted(p.name for p in (tmp_path / "l").iterdir())
    assert "firefly.log" in files and "firefly.log.1" in files and len(files) <= L.BACKUPS + 1


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_uncaught_thread_exception_is_logged_and_hook_restored(logs):
    def boom():
        raise ValueError("lỗi-luồng-nền")
    t = threading.Thread(target=boom)
    t.start()
    t.join()
    text = logs.read_text("utf-8")
    assert "CRITICAL" in text and "lỗi-luồng-nền" in text
    hook = threading.excepthook
    L.teardown()
    assert threading.excepthook is not hook, "teardown phải trả hook về như cũ"


@pytest.mark.parametrize("method", ["fork", "spawn"])
def test_worker_logs_reach_the_main_log_file(logs, method):
    """Tiến trình con gửi log về hàng đợi -> tiến trình chính ghi vào cùng một file (spawn = đường chạy của Windows)."""
    if method not in multiprocessing.get_all_start_methods():
        pytest.skip(f"hệ điều hành này không có {method}")
    ctx = multiprocessing.get_context(method)
    q, stop = L.attach_queue(ctx)
    with cf.ProcessPoolExecutor(1, mp_context=ctx, initializer=L.worker_init, initargs=(q, logging.DEBUG)) as ex:
        ex.submit(L.selftest_worker, "tin-từ-tiến-trình-con").result(timeout=90)
    stop()
    line = next(l for l in logs.read_text("utf-8").splitlines() if "tin-từ-tiến-trình-con" in l)
    assert "ffv.worker" in line and "Process-" in line


def test_attach_queue_without_logging_is_a_noop():
    L.teardown()
    q, stop = L.attach_queue(multiprocessing.get_context())
    assert q is None
    stop()


@pytest.fixture()
def small(tmp_path):
    root = tmp_path / "p"
    for s in ("media", "audio", "out"):
        (root / s).mkdir(parents=True)
    make_images(root / "media")
    proj = make_project("9:16", quality=360, fps=24)
    proj["scenes"] = proj["scenes"][1:]
    return root, add_fake_audio(root, proj)


def test_export_with_spawn_workers_logs_from_every_process(small, logs, monkeypatch):
    monkeypatch.setenv("FFV_MP", "spawn")
    root, proj = small
    out = root / "out" / "x.mp4"
    info = M.run_export({}, proj, root, out, 360, 24, "draft", "cpu")
    assert out.stat().st_size > 1000 and info["frames"] > 0
    text = logs.read_text("utf-8")
    assert "Xuất video:" in text and "Xuất xong" in text
    assert "sẵn sàng" in text, "dòng log do tiến trình con (spawn) ghi phải về được file chính"


# ============================================================================ thông báo lỗi tiếng Việt
CASES = [
    (OSError(errno.ENOSPC, "No space left on device"), "disk_full"),
    (PermissionError(errno.EACCES, "Permission denied", "C:/x/out.mp4"), "permission"),
    (FileNotFoundError(2, "No such file or directory", "ffmpeg"), "ffmpeg_missing"),
    (FileNotFoundError(2, "No such file or directory", "/a/b/anh.png"), "file_missing"),
    (OSError(errno.ENAMETOOLONG, "File name too long"), "path_too_long"),
    (MemoryError(), "out_of_memory"),
    (BrokenProcessPool("A process in the process pool was terminated abruptly"), "worker_died"),
    (E.FFmpegError("dựng đoạn 3", "[h264_nvenc @ 0x55] Cannot load libcuda.so.1\nError initializing output stream"), "gpu_encoder"),
    (E.FFmpegError("dựng đoạn 0", "[h264_nvenc @ 0x55] OpenEncodeSessionEx failed: out of memory (10)"), "gpu_encoder"),
    (E.FFmpegError("dựng đoạn 0", "[h264_qsv @ 0x1] Error creating a MFX session: -9."), "gpu_encoder"),
    (E.FFmpegError("dựng đoạn 0", "[h264_amf @ 0x1] AMF failed to initialise on given D3D11 device"), "gpu_encoder"),
    (E.FFmpegError("ghép", "Unknown encoder 'libx264'"), "encoder_missing"),
    (E.FFmpegError("xử lý âm thanh", "bgm.mp3: Invalid data found when processing input"), "bad_media"),
    (E.FFmpegError("ghép", "all.h264: No such file or directory"), "file_missing"),
    (E.FFmpegError("ghép", "mix.wav: No space left on device"), "disk_full"),
    (E.FFmpegError("ghép", "out.mp4: Permission denied"), "permission"),
    (RuntimeError("Cannot connect to host speech.platform.bing.com:443 ssl:default [Name or service not known]"), "network"),
    (TimeoutError("timed out"), "network"),
    (RuntimeError("Invalid response status, 403, WSServerHandshakeError"), "tts_denied"),
    (UnidentifiedImageError("cannot identify image file 'x.png'"), "image_corrupt"),
    (Image.DecompressionBombError("Image size (200000000 pixels) exceeds limit"), "image_huge"),
    (ValueError("lỗi lạ chưa ai gặp"), "unexpected"),
]


@pytest.mark.parametrize("exc,code", CASES, ids=[c[1] + "-" + type(c[0]).__name__ for c in CASES])
def test_explain_known_errors(exc, code):
    d = E.explain(exc, log_it=False)
    assert d["code"] == code, d
    assert d["error"] and d["hint"] and d["ref"]
    for txt in (d["error"], d["hint"]):
        assert "{" not in txt and "Traceback" not in txt and "Errno" not in txt, f"lộ chi tiết kỹ thuật/placeholder: {txt}"
    if code == "unexpected":
        assert d["ref"] in d["hint"] and "firefly.log" in d["hint"]


def test_explain_mentions_the_file_name_but_not_its_path():
    d = E.explain(PermissionError(errno.EACCES, "Permission denied", "C:\\Users\\a\\Videos\\out.mp4"), log_it=False)
    assert "out.mp4" in d["error"] and "Users" not in d["error"]


def test_no_audio_from_edge_tts_is_recognised():
    from edge_tts.exceptions import NoAudioReceived
    assert E.explain(NoAudioReceived("No audio was received. Please verify that your parameters are correct."), log_it=False)["code"] == "tts_no_audio"


def test_user_and_script_errors_pass_through_unchanged():
    d = E.explain(G.ScriptError("Địa chỉ Ollama không hợp lệ."), log_it=False)
    assert d["code"] == "ai" and d["error"] == "Địa chỉ Ollama không hợp lệ."
    d = E.explain(E.UserError("a", "b", "c"), log_it=False)
    assert (d["error"], d["hint"], d["code"]) == ("a", "b", "c")


def test_errors_survive_pickling_between_processes():
    u = pickle.loads(pickle.dumps(E.UserError("a", "b", "c")))
    assert (u.message, u.hint, u.code) == ("a", "b", "c")
    f = pickle.loads(pickle.dumps(E.FFmpegError("dựng đoạn 2", "Cannot load libcuda")))
    assert f.where == "dựng đoạn 2" and "libcuda" in f.stderr
    assert E.explain(f, log_it=False)["code"] == "gpu_encoder"


def test_unexpected_error_is_logged_with_ref_and_traceback(logs):
    try:
        raise ValueError("bí-ẩn-123")
    except ValueError as e:
        d = E.explain(e, where="thử")
    text = logs.read_text("utf-8")
    assert d["ref"] in text and "bí-ẩn-123" in text and "Traceback" in text and "(thử)" in text


def test_ffmpeg_stderr_goes_to_log_not_to_screen(logs):
    d = E.explain(E.FFmpegError("dựng đoạn 4", "x" * 100 + "Cannot load libcuda.so.1"), where="job")
    assert "libcuda" not in d["error"] + d["hint"]
    assert "libcuda" in logs.read_text("utf-8")


# ============================================================================ Flask: mọi lỗi trả JSON tiếng Việt
def test_unknown_project_is_json_404(client, logs):
    r = client.get("/api/projects/khong-co-1234")
    j = r.get_json()
    assert r.status_code == 404 and j["code"] == "not_found" and j["hint"] and "không tìm thấy" in j["error"].lower()
    assert "HTTP 404" in logs.read_text("utf-8")


def test_upload_too_large_is_json_413(client, monkeypatch):
    pid, _ = new_project(client)
    monkeypatch.setitem(A.app.config, "MAX_CONTENT_LENGTH", 1000)
    import io
    r = client.post(f"/api/projects/{pid}/upload", data={"file": (io.BytesIO(b"x" * 5000), "a.png")}, content_type="multipart/form-data")
    j = r.get_json()
    assert r.status_code == 413 and j["code"] == "upload_too_large" and "400 MB" in j["error"]


def test_unexpected_exception_in_route_becomes_json_with_ref(client, logs, monkeypatch):
    pid, _ = new_project(client)
    monkeypatch.setattr(A, "tl_json", lambda p: 1 / 0)
    r = client.get(f"/api/projects/{pid}")
    j = r.get_json()
    assert r.status_code == 500 and j["code"] == "unexpected" and j["ref"] in j["hint"]
    text = logs.read_text("utf-8")
    assert j["ref"] in text and "ZeroDivisionError" in text


def test_tts_failure_returns_vietnamese_hint(client, monkeypatch):
    pid, _ = new_project(client, [scene("a", "Có lời đọc")])
    def fail(*a, **k):
        raise RuntimeError("Cannot connect to host speech.platform.bing.com:443 ssl:default")
    monkeypatch.setattr(M, "tts_scene", fail)
    r = client.post(f"/api/projects/{pid}/tts", json={"scene": "a"})
    j = r.get_json()
    assert r.status_code == 502 and j["code"] == "network" and "internet" in j["error"] and j["hint"]


def test_job_error_carries_hint_ref_and_is_logged(logs):
    def boom(job):
        raise OSError(errno.ENOSPC, "No space left on device")
    j = wait_job(A.start_job(boom))
    assert j["state"] == "error" and j["code"] == "disk_full" and j["hint"] and j["ref"]
    text = logs.read_text("utf-8")
    assert j["ref"] in text and "bắt đầu" in text


def test_cancelled_job_is_not_an_error(logs):
    def stop(job):
        raise M.Cancelled()
    j = wait_job(A.start_job(stop))
    assert j["state"] == "cancelled" and not j.get("error")


def test_client_errors_are_logged_sanitized_and_rate_limited(client, logs, monkeypatch):
    monkeypatch.setitem(A.CLIENT_LOG, "n", 0)
    r = client.post("/api/client-log", json={"msg": "TypeError: x\nxuống dòng", "src": "app.js:1", "stack": "a" * 5000})
    assert r.status_code == 200
    text = logs.read_text("utf-8")
    assert "Lỗi giao diện" in text and "TypeError: x xuống dòng" in text and "a" * 1500 in text and "a" * 1600 not in text
    monkeypatch.setitem(A.CLIENT_LOG, "n", A.CLIENT_LOG_MAX)
    assert client.post("/api/client-log", json={"msg": "nữa"}).status_code == 429


def test_logs_endpoints(client, logs):
    L.get("x").info("dòng-thử-nghiệm")
    j = client.get("/api/logs?lines=5").get_json()
    assert j["path"] == str(logs) and any("dòng-thử-nghiệm" in l for l in j["lines"])
    r = client.get("/api/logs/download")
    assert r.status_code == 200 and "dòng-thử-nghiệm" in r.get_data(as_text=True)
    assert client.get("/api/ping").get_json()["app"] == "firefly-video"


# ============================================================================ file dự án hỏng
def test_save_keeps_previous_version_and_never_overwrites_backup_with_garbage(client):
    pid, p = new_project(client, [scene("a")])
    main, bak = A.PROJ / pid / "project.json", A.PROJ / pid / "project.json.bak"
    p["name"] = "Bản hai"
    client.put(f"/api/projects/{pid}", json=p)
    assert json.loads(bak.read_text("utf-8"))["name"] == "E7"
    main.write_text("{hỏng", "utf-8")
    A.save(pid, dict(p, name="Bản ba"))
    assert json.loads(bak.read_text("utf-8"))["name"] == "E7", "bản hỏng không được ghi đè bản sao lưu tốt"


def test_corrupt_project_recovers_from_backup(client, logs):
    pid, p = new_project(client, [scene("a")])
    client.put(f"/api/projects/{pid}", json=p)  # lần lưu thứ hai: bản sao lưu giờ đã có cảnh "a"
    main = A.PROJ / pid / "project.json"
    main.write_text("{không phải json", "utf-8")
    r = client.get(f"/api/projects/{pid}")
    assert r.status_code == 200 and r.get_json()["project"]["scenes"][0]["id"] == "a"
    assert json.loads(main.read_text("utf-8"))["name"] == "E7"
    assert list((A.PROJ / pid).glob("project.json.hong-*")), "bản hỏng phải được giữ lại để xem"
    assert "khôi phục" in logs.read_text("utf-8")


def test_corrupt_project_without_backup_gives_clear_error(client):
    pid, _ = new_project(client)
    (A.PROJ / pid / "project.json.bak").unlink(missing_ok=True)
    (A.PROJ / pid / "project.json").write_text("", "utf-8")
    r = client.get(f"/api/projects/{pid}")
    j = r.get_json()
    assert r.status_code == 500 and j["code"] == "project_corrupt" and "project.json" in j["hint"]


# ============================================================================ kiểm tra trước khi xuất
@pytest.fixture()
def proj_dir(tmp_path):
    d = tmp_path / "pd"
    (d / "media").mkdir(parents=True)
    return d


def test_preflight_missing_image_names_scene_and_file(proj_dir):
    p = dict(scenes=[scene("a", "x"), scene("b", "y", images=["mat-tieu.png"])])
    bad = C.blocking(C.preflight(p, proj_dir))
    assert len(bad) == 1 and bad[0]["code"] == "image_missing" and bad[0]["scene"] == 2
    assert "Cảnh 2" in bad[0]["msg"] and "mat-tieu.png" in bad[0]["msg"] and bad[0]["hint"]


def test_preflight_deep_catches_unreadable_image(proj_dir):
    (proj_dir / "media" / "hong.png").write_bytes(b"day khong phai anh" * 20)
    p = dict(scenes=[scene("a", "x", images=["hong.png"])])
    assert not C.blocking(C.preflight(p, proj_dir)), "kiểm tra nhanh chỉ xét file có tồn tại"
    bad = C.blocking(C.preflight(p, proj_dir, deep=True))
    assert [b["code"] for b in bad] == ["image_corrupt"] and "Cảnh 1" in bad[0]["msg"]


def test_preflight_accepts_good_image(proj_dir):
    Image.new("RGB", (64, 64), "red").save(proj_dir / "media" / "ok.png")
    p = dict(scenes=[scene("a", "x", images=["ok.png"])])
    assert C.preflight(p, proj_dir, deep=True) == [] or all(i["level"] == "warn" for i in C.preflight(p, proj_dir, deep=True))


def test_preflight_warnings_for_empty_scene_missing_bgm_and_logo(proj_dir):
    p = dict(scenes=[dict(id="a", title="", subtitle="", narration="", images=[]), scene("b", "ok")],
             bgm=dict(file="nhac.mp3"), logo=dict(file="logo.png"))
    codes = {i["code"]: i for i in C.preflight(p, proj_dir)}
    assert codes["empty_scene"]["scene"] == 1 and codes["empty_scene"]["level"] == "warn"
    assert codes["bgm_missing"]["level"] == "warn" and codes["logo_missing"]["level"] == "warn"
    assert not C.blocking(list(codes.values()))


def test_preflight_no_scenes_is_an_error(proj_dir):
    assert [i["code"] for i in C.blocking(C.preflight(dict(scenes=[]), proj_dir))] == ["no_scenes"]


def test_preflight_disk_space(proj_dir, monkeypatch):
    Usage = namedtuple("Usage", "total used free")
    p = dict(scenes=[scene("a", "x")])
    for free, expect in ((100e6, "error"), (2e9, "warn"), (10e9, None)):
        monkeypatch.setattr(C.shutil, "disk_usage", lambda d, free=free: Usage(1, 1, int(free)))
        got = [i for i in C.preflight(p, proj_dir, deep=True) if i["code"] == "disk_low"]
        assert (got[0]["level"] if got else None) == expect


def test_issues_ride_along_with_put_and_get(client):
    pid, _ = new_project(client, [scene("a", "x", images=["mat.png"])])
    p = client.get(f"/api/projects/{pid}").get_json()
    assert [(i["code"], i["scene"]) for i in p["issues"]] == [("image_missing", 1)]
    empty, _ = new_project(client)
    assert client.get(f"/api/projects/{empty}").get_json()["issues"] == [], "dự án mới chưa có cảnh không bị báo lỗi"


def test_export_is_blocked_with_a_specific_message(client, logs):
    pid, _ = new_project(client, [scene("a", "x", images=["mat.png"])])
    jid = client.post(f"/api/projects/{pid}/render", json={"mode": "final"}).get_json()["job"]
    j = wait_job(jid)
    assert j["state"] == "error" and j["code"] == "preflight"
    assert "Cảnh 1" in j["error"] and "mat.png" in j["error"] and j["hint"]
    assert not list((A.PROJ / pid / "out").glob("*.mp4"))


def test_estimate_reports_issues_and_disk(client):
    pid, p = new_project(client, [scene("a", "Một cảnh có lời đọc", images=["mat.png"])])
    assert client.post(f"/api/projects/{pid}/tts", json={"scene": "a"}).status_code == 200
    j = wait_job(client.post(f"/api/projects/{pid}/estimate", json={}).get_json()["job"])
    assert j["state"] == "done"
    assert any(i["code"] == "image_missing" for i in j["info"]["issues"])


def test_check_endpoint(client):
    pid, _ = new_project(client, [scene("a", "x", images=["mat.png"])])
    j = client.get(f"/api/projects/{pid}/check?deep=1").get_json()
    assert j["issues"][0]["code"] == "image_missing"


# ============================================================================ cổng bận / đã chạy sẵn
def test_pick_port_skips_a_busy_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen()
    busy = s.getsockname()[1]
    try:
        port, running = A.pick_port(busy)
    finally:
        s.close()
    assert port > busy and running is False


def test_pick_port_detects_an_instance_already_running():
    srv = make_server("127.0.0.1", 0, A.app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert A.find_running(srv.server_port)
        assert A.pick_port(srv.server_port) == (srv.server_port, True)
    finally:
        srv.shutdown()


def test_pick_port_all_busy_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(A, "find_running", lambda p: False)
    monkeypatch.setattr(A, "port_free", lambda p: False)
    with pytest.raises(E.UserError) as ei:
        A.pick_port(9000, tries=3)
    assert ei.value.code == "port_busy" and "PORT" in ei.value.hint


# ============================================================================ kiểm tra máy
def test_doctor_data_dir_check(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(L, "_state", {"dir": str(tmp_path / "logs")})
    items = D.check_data_dir()
    assert [i["level"] for i in items] == ["ok", "ok"] and (tmp_path / "projects").is_dir()
    if os.name != "nt" and os.geteuid() != 0:
        os.chmod(tmp_path, 0o500)
        try:
            monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "moi")
            bad = D.check_data_dir()
            assert bad[0]["level"] == "error" and "FFV_HOME" in bad[0]["detail"]
        finally:
            os.chmod(tmp_path, 0o700)
