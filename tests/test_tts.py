"""Giọng đọc có dự phòng (tts.py). Không cần mạng, không cần edge-tts/Piper/gTTS thật:
các nhà cung cấp được thay bằng bản giả; Piper được thử qua một chương trình dòng lệnh giả có cùng giao diện (--model, --output_file, --length_scale)."""
import errno
import os
import stat
import sys
import textwrap
import time

import pytest

import app as A
import errors as E
import media as M
import paths
import render as R
import tts as T
from conftest import make_project


# ----------------------------------------------------------------------------- nhà cung cấp giả
class Fake:
    """Nhà cung cấp giả: `fail` là exception (hoặc None) mà synth() sẽ ném; ghi lại số lần được gọi."""

    def __init__(self, name, fail=None, ok=True, why="", tempo=1.0, events=None):
        self.name, self.label, self.online = name, name.upper(), True
        self.fail, self.ok, self.why, self.tempo, self.events = fail, ok, why, tempo, events
        self.calls = 0

    def status(self, voice=None):
        return self.ok, self.why or "ok"

    def synth(self, text, voice, rate, pitch, workdir):
        self.calls += 1
        if self.fail:
            raise self.fail
        out = os.path.join(workdir, self.name + ".wav")
        ev = M._fake_tts_wav(text, out)
        return T.Synth(out, ev if self.events is None else self.events, "word" if (ev if self.events is None else self.events) else None,
                       self.name, tempo=self.tempo)


NET = RuntimeError("Cannot connect to host speech.platform.bing.com:443 ssl:default")
DENIED = RuntimeError("Invalid response status, 403, WSServerHandshakeError")


def synth(chain, text="Xin chào các bạn."):
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        return chain.synth(text, "vi-VN-HoaiMyNeural", 0, 0, td)


# ----------------------------------------------------------------------------- Chain
def test_primary_used_when_it_works():
    a, b = Fake("edge"), Fake("piper")
    c = T.Chain([a, b])
    assert synth(c).engine == "edge" and (a.calls, b.calls) == (1, 0)
    assert c.summary() is None


def test_falls_back_when_primary_fails_and_remembers_it_is_dead():
    a, b = Fake("edge", fail=NET), Fake("piper")
    c = T.Chain([a, b])
    assert synth(c).engine == "piper" and synth(c).engine == "piper"
    assert a.calls == 1, "dịch vụ chính hỏng vì mạng: các cảnh sau không thử lại (mỗi lần thử hỏng tốn vài giây)"
    assert c.used == {"piper": 2} and "dự phòng" in c.summary() and "PIPER: 2 cảnh" in c.summary()


def test_403_also_marks_primary_dead():
    a, b = Fake("edge", fail=DENIED), Fake("gtts")
    c = T.Chain([a, b])
    synth(c), synth(c)
    assert a.calls == 1 and c.used == {"gtts": 2}


def test_unknown_library_error_falls_back_too_because_edge_may_change_any_day():
    """Microsoft đổi giao thức -> edge-tts ném lỗi lạ (không phải lỗi mạng): vẫn phải chuyển giọng, nhưng không đánh dấu 'chết' hẳn."""
    a, b = Fake("edge", fail=KeyError("Sec-MS-GEC")), Fake("piper")
    c = T.Chain([a, b])
    assert synth(c).engine == "piper"
    synth(c)
    assert a.calls == 2


def test_no_audio_for_one_scene_does_not_kill_the_primary():
    a, b = Fake("edge", fail=E.UserError(*E.MSG["tts_no_audio"], code="tts_no_audio")), Fake("piper")
    c = T.Chain([a, b])
    assert synth(c).engine == "piper"
    a.fail = None
    assert synth(c).engine == "edge"


def test_machine_errors_are_not_masked_by_fallback():
    for exc in (OSError(errno.ENOSPC, "No space left on device"), PermissionError(errno.EACCES, "denied"), MemoryError()):
        a, b = Fake("edge", fail=exc), Fake("piper")
        with pytest.raises(type(exc)):
            synth(T.Chain([a, b]))
        assert b.calls == 0


def test_fallback_switched_off_raises_the_primary_error():
    a, b = Fake("edge", fail=NET), Fake("piper")
    with pytest.raises(RuntimeError, match="Cannot connect"):
        synth(T.Chain([a, b], fallback=False))
    assert b.calls == 0


def test_everything_failing_reports_the_primary_error_not_the_last():
    a, b = Fake("edge", fail=NET), Fake("gtts", fail=KeyError("lạ"))
    with pytest.raises(RuntimeError) as ei:
        synth(T.Chain([a, b]))
    assert E.explain(ei.value, log_it=False)["code"] == "network"


def test_unavailable_providers_are_skipped_silently():
    a, b, c3 = Fake("edge", fail=NET), Fake("piper", ok=False, why="chưa có"), Fake("gtts")
    assert synth(T.Chain([a, b, c3])).engine == "gtts" and b.calls == 0


def test_nothing_usable_gives_vietnamese_user_error():
    with pytest.raises(E.UserError) as ei:
        synth(T.Chain([Fake("edge", ok=False), Fake("piper", ok=False)]))
    d = E.explain(ei.value, log_it=False)
    assert d["code"] == "tts_none" and d["hint"]
    with pytest.raises(E.UserError):
        synth(T.Chain([Fake("edge", ok=False), Fake("piper")], fallback=False))


def test_default_order_and_env_override(monkeypatch):
    monkeypatch.delenv("FFV_TTS", raising=False)
    assert [p.name for p in T.default_providers()] == ["edge", "piper", "gtts"]
    monkeypatch.setenv("FFV_TTS", "piper, edge,piper,khong-co")
    assert [p.name for p in T.default_providers()] == ["piper", "edge"]
    monkeypatch.setenv("FFV_TTS", "linh-tinh")
    assert [p.name for p in T.default_providers()] == ["edge"]


def test_project_flag_switches_fallback_off():
    assert T.make_chain({"voice": {"fallback": False}}).fallback is False
    assert T.make_chain({"voice": {}}).fallback is True and T.make_chain({}).fallback is True


def test_locale_of():
    assert T.locale_of("vi-VN-HoaiMyNeural") == "vi-VN" and T.locale_of("zh-CN-liaoning-XiaobeiNeural") == "zh-CN" and T.locale_of("") == "vi-VN"


# ----------------------------------------------------------------------------- Piper
def test_pick_piper_model_prefers_region_then_language_then_quality(tmp_path):
    m = {n: tmp_path / (n + ".onnx") for n in ("vi_VN-vivos-x_low", "vi_VN-vais1000-medium", "vi_VN-25hours_single-low", "en_US-lessac-high", "en_GB-alan-medium")}
    assert T.pick_piper_model("vi-VN", m).name == "vi_VN-vais1000-medium.onnx"
    assert T.pick_piper_model("en-GB", m).name == "en_GB-alan-medium.onnx"
    assert T.pick_piper_model("en-AU", m).name in ("en_US-lessac-high.onnx", "en_GB-alan-medium.onnx"), "đúng ngôn ngữ dù khác vùng"
    assert T.pick_piper_model("ja-JP", m) is None


def test_piper_models_need_the_json_next_to_the_onnx(tmp_path, monkeypatch):
    monkeypatch.setenv("FFV_PIPER_VOICES", str(tmp_path))
    (tmp_path / "vi_VN-a-medium.onnx").write_bytes(b"x")
    (tmp_path / "vi_VN-a-medium.onnx.json").write_text("{}")
    (tmp_path / "vi_VN-b-medium.onnx").write_bytes(b"x")  # thiếu .json
    assert list(T.piper_models()) == ["vi_VN-a-medium"]


FAKE_PIPER = textwrap.dedent('''\
    #!{py}
    import sys, wave, struct, math
    a = sys.argv[1:]
    if "--help" in a:
        print("usage: piper -m MODEL, --model MODEL [--output_file F] [--length_scale X]"); sys.exit(0)
    opt = lambda k: a[a.index(k) + 1]
    text = sys.stdin.buffer.read().decode("utf-8")
    scale = float(opt("--length_scale"))
    n = int(22050 * (0.02 * len(text.strip())) * scale)
    open(opt("--output_file") + ".args", "w").write(" ".join(a) + "\\n" + repr(text))
    with wave.open(opt("--output_file"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 20))) for i in range(n)))
    ''')


@pytest.fixture()
def piper_env(tmp_path, monkeypatch):
    """Một 'piper' giả (script Python chạy được như chương trình) + một giọng tiếng Việt giả trong piper_voices/."""
    if sys.platform == "win32":
        pytest.skip("script giả cần quyền thực thi kiểu Unix")
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.delenv("FFV_PIPER", raising=False)
    monkeypatch.delenv("FFV_PIPER_VOICES", raising=False)
    exe = tmp_path / "piper" / "piper"
    exe.parent.mkdir()
    exe.write_text(FAKE_PIPER.format(py=sys.executable), "utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    vd = tmp_path / "piper_voices"
    vd.mkdir()
    (vd / "vi_VN-vais1000-medium.onnx").write_bytes(b"x")
    (vd / "vi_VN-vais1000-medium.onnx.json").write_text("{}")
    T._piper_ok.cache_clear()
    monkeypatch.setattr(T.shutil, "which", lambda n: None)
    return tmp_path


def test_piper_runs_as_a_separate_program_and_returns_wav(piper_env, tmp_path):
    p = T.PiperProvider()
    ok, detail = p.status("vi-VN-HoaiMyNeural")
    assert ok and "vi_VN-vais1000-medium" in detail
    wd = tmp_path / "w"
    wd.mkdir()
    r = p.synth("Xin chào.\nCác bạn", "vi-VN-HoaiMyNeural", 0, 0, str(wd))
    assert r.engine == "piper" and r.events == [] and r.kind is None and os.path.getsize(r.path) > 200
    args = open(r.path + ".args", encoding="utf-8").read()
    assert "vi_VN-vais1000-medium.onnx" in args and "'Xin chào. Các bạn'" in args, "ngắt dòng bị nối lại để không cắt câu"


def test_piper_speed_maps_to_length_scale(piper_env, tmp_path):
    p, wd = T.PiperProvider(), tmp_path / "w"
    wd.mkdir()
    r = p.synth("abc", "vi-VN-HoaiMyNeural", 50, 0, str(wd))  # +50% -> nhanh hơn -> length_scale < 1
    assert "--length_scale 0.667" in open(r.path + ".args", encoding="utf-8").read()
    r = p.synth("abc", "vi-VN-HoaiMyNeural", -20, 0, str(wd))
    assert "--length_scale 1.250" in open(r.path + ".args", encoding="utf-8").read()


def test_piper_status_reasons(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.delenv("FFV_PIPER", raising=False)
    monkeypatch.delenv("FFV_PIPER_VOICES", raising=False)
    monkeypatch.setattr(T, "piper_command", lambda: None)
    ok, why = T.PiperProvider().status("vi-VN-HoaiMyNeural")
    assert not ok and "README" in why
    monkeypatch.setattr(T, "piper_command", lambda: ["piper"])
    ok, why = T.PiperProvider().status("vi-VN-HoaiMyNeural")
    assert not ok and ".onnx" in why
    with pytest.raises(T.ProviderUnavailable):
        T.PiperProvider().synth("x", "vi-VN-HoaiMyNeural", 0, 0, str(tmp_path))


def test_piper_for_a_language_without_voice_is_skipped(piper_env):
    ok, why = T.PiperProvider().status("ja-JP-NanamiNeural")
    assert not ok and "ja-JP" in why


def test_a_program_named_piper_that_is_not_the_tts_is_ignored(tmp_path, monkeypatch):
    """Trên Linux `piper` trong PATH có thể là ứng dụng cấu hình chuột cùng tên."""
    if sys.platform == "win32":
        pytest.skip("script giả cần quyền thực thi kiểu Unix")
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.delenv("FFV_PIPER", raising=False)
    exe = tmp_path / "piper" / "piper"
    exe.parent.mkdir()
    exe.write_text(f"#!{sys.executable}\nprint('Piper mouse configuration tool')\n", "utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    T._piper_ok.cache_clear()
    monkeypatch.setattr(T.shutil, "which", lambda n: None)
    monkeypatch.setattr(T, "_has", lambda m: False)
    assert T.piper_command() is None


# ----------------------------------------------------------------------------- gTTS
def test_gtts_language_resolution(monkeypatch):
    pytest.importorskip("gtts")
    g = T.GttsProvider()
    assert g._lang("vi-VN-HoaiMyNeural") == "vi"
    assert g._lang("zh-CN-XiaoxiaoNeural") == "zh-CN"
    with pytest.raises(T.ProviderUnavailable):
        g._lang("xx-YY-FooNeural")
    ok, why = g.status("xx-YY-FooNeural")
    assert not ok and "xx-YY" in why


def test_gtts_speed_is_left_to_ffmpeg(monkeypatch, tmp_path):
    gtts = pytest.importorskip("gtts")

    class Stub:
        def __init__(self, text, lang):
            self.lang = lang

        def save(self, path):
            open(path, "wb").write(b"x" * 500)
    monkeypatch.setattr(gtts, "gTTS", Stub)
    r = T.GttsProvider().synth("xin chào", "vi-VN-HoaiMyNeural", 25, 0, str(tmp_path))
    assert r.engine == "gtts" and r.events == [] and abs(r.tempo - 1.25) < 1e-9


# ----------------------------------------------------------------------------- media.tts_scene
@pytest.fixture()
def real_path(monkeypatch):
    """Tắt giọng giả offline của bộ test để đi qua Chain thật (với nhà cung cấp giả)."""
    monkeypatch.delenv("FFV_FAKE_TTS", raising=False)


def test_scene_voice_comes_from_fallback_with_engine_recorded_and_pause_alignment(real_path, root):
    proj = make_project()
    sc = proj["scenes"][0]
    meta = M.tts_scene(root, proj, sc, chain=T.Chain([Fake("edge", fail=NET), Fake("piper", events=[])]))
    assert meta["engine"] == "piper" and meta["words"] == [] and meta["wsrc"] is None and meta["dur"] > 1
    ok = M.tts_scene(root, proj, sc, chain=T.Chain([Fake("edge")]))
    assert ok["engine"] == "edge" and ok["words"] and ok["wsrc"] == "word"


def test_tempo_is_applied_by_ffmpeg(real_path, root):
    proj = make_project()
    sc = proj["scenes"][0]
    base = M.tts_scene(root, proj, sc, chain=T.Chain([Fake("gtts")]))["dur"]
    fast = M.tts_scene(root, proj, sc, chain=T.Chain([Fake("gtts", tempo=1.5)]))["dur"]
    assert 0.6 < fast / base < 0.72, (base, fast)


def test_failure_without_any_fallback_keeps_the_old_error_code(real_path, root):
    proj = make_project()
    with pytest.raises(RuntimeError) as ei:
        M.tts_scene(root, proj, proj["scenes"][0], chain=T.Chain([Fake("edge", fail=NET)]))
    assert E.explain(ei.value, log_it=False)["code"] == "network"


# ----------------------------------------------------------------------------- app: job + API
@pytest.fixture()
def client(tmp_path, monkeypatch, real_path):
    monkeypatch.setattr(A, "PROJ", tmp_path / "projects")
    A.PROJ.mkdir()
    return A.app.test_client()


def new_project(client, n=3, **voice):
    r = client.post("/api/projects", json={"name": "TTS", "voice": dict({"name": "vi-VN-HoaiMyNeural", "rate": 0, "pitch": 0}, **voice)}).get_json()
    pid, p = r["id"], r["project"]
    p["scenes"] = [dict(id=f"s{i}", title="", subtitle="", narration=f"Cảnh số {i} có lời đọc đủ dài.", voice=True, caption=True,
                        images=[], transition="fade") for i in range(n)]
    assert client.put(f"/api/projects/{pid}", json=p).status_code == 200
    return pid


def wait_job(jid, timeout=60):
    t0 = time.time()
    while A.JOBS[jid]["state"] == "running" and time.time() - t0 < timeout:
        time.sleep(0.05)
    return A.JOBS[jid]


def engines(client, pid):
    p = client.get(f"/api/projects/{pid}").get_json()["project"]
    return [s["audio"]["engine"] if s.get("audio") else None for s in p["scenes"]]


def test_new_projects_default_to_fallback_on_and_old_ones_too(client):
    pid = new_project(client)
    assert client.get(f"/api/projects/{pid}").get_json()["project"]["voice"]["fallback"] is True
    pid2 = new_project(client, fallback=False)
    assert client.get(f"/api/projects/{pid2}").get_json()["project"]["voice"]["fallback"] is False
    p = A.normalize({"voice": {"name": "en-US-AriaNeural"}})
    assert p["voice"]["fallback"] is True


def test_fallback_flag_does_not_invalidate_existing_voices(client):
    p = A.normalize(make_project())
    sc = p["scenes"][0]
    h1 = R.audio_hash(p, sc)
    p["voice"]["fallback"] = False
    assert R.audio_hash(p, sc) == h1


def test_tts_all_switches_to_fallback_mid_job_and_reports_it(client, monkeypatch):
    edge, piper = Fake("edge", fail=NET), Fake("piper")
    monkeypatch.setattr(T, "default_providers", lambda order=None: [edge, piper])
    pid = new_project(client, 3)
    j = wait_job(client.post(f"/api/projects/{pid}/tts_all", json={}).get_json()["job"])
    assert j["state"] == "done", j
    assert j["notice"] and "dự phòng" in j["notice"] and "3 cảnh" in j["notice"]
    assert edge.calls == 1, "chỉ cảnh đầu phải chờ Edge hỏng; hai cảnh sau chuyển thẳng"
    assert engines(client, pid) == ["piper"] * 3


def test_tts_one_returns_notice_and_engine(client, monkeypatch):
    monkeypatch.setattr(T, "default_providers", lambda order=None: [Fake("edge", fail=DENIED), Fake("gtts")])
    pid = new_project(client, 1)
    r = client.post(f"/api/projects/{pid}/tts", json={"scene": "s0"}).get_json()
    assert r["audio"]["engine"] == "gtts" and "dự phòng" in r["notice"]


def test_no_fallback_when_project_turns_it_off(client, monkeypatch):
    monkeypatch.setattr(T, "default_providers", lambda order=None: [Fake("edge", fail=NET), Fake("piper")])
    pid = new_project(client, 1, fallback=False)
    r = client.post(f"/api/projects/{pid}/tts", json={"scene": "s0"})
    assert r.status_code == 502 and r.get_json()["code"] == "network"


def test_redo_replaces_fallback_voices_only_with_the_primary_voice(client, monkeypatch):
    edge, piper = Fake("edge", fail=NET), Fake("piper")
    monkeypatch.setattr(T, "default_providers", lambda order=None: [edge, piper])
    pid = new_project(client, 2)
    wait_job(client.post(f"/api/projects/{pid}/tts_all", json={}).get_json()["job"])
    assert engines(client, pid) == ["piper", "piper"]

    j = wait_job(client.post(f"/api/projects/{pid}/tts_all", json={"redo_fallback": True}).get_json()["job"])
    assert j["state"] == "error" and j["code"] == "network", "giọng chính vẫn hỏng: báo lỗi, không lặng lẽ dùng giọng dự phòng lần nữa"
    assert engines(client, pid) == ["piper", "piper"], "giọng đang có được giữ nguyên"

    edge.fail = None
    j = wait_job(client.post(f"/api/projects/{pid}/tts_all", json={"redo_fallback": True}).get_json()["job"])
    assert j["state"] == "done" and not j["notice"]
    assert engines(client, pid) == ["edge", "edge"]
    j = wait_job(client.post(f"/api/projects/{pid}/tts_all", json={"redo_fallback": True}).get_json()["job"])
    assert j["state"] == "done" and edge.calls == 4, "không còn cảnh nào dùng giọng dự phòng: không làm gì thêm"


def test_status_endpoint_lists_engines_without_network(client, monkeypatch):
    monkeypatch.setattr(T, "default_providers", lambda order=None: [Fake("edge"), Fake("piper", ok=False, why="chưa có file giọng")])
    r = client.get("/api/tts/status?voice=vi-VN-HoaiMyNeural").get_json()["engines"]
    assert [(e["name"], e["ok"], e["primary"]) for e in r] == [("edge", True, True), ("piper", False, False)]
    assert r[1]["detail"] == "chưa có file giọng"


def test_doctor_reports_fallback_as_warning_never_error(monkeypatch):
    import doctor as D
    monkeypatch.setattr(T, "default_providers", lambda order=None: [Fake("edge"), Fake("piper", ok=False, why="chưa có"), Fake("gtts", ok=False, why="chưa cài")])
    items = D.check_tts_fallback()
    assert items and all(i["ok"] for i in items) and any(i["level"] == "warn" and "README" in i["detail"] for i in items)
