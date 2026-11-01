"""Giao diện, trình duyệt thật: cảnh đọc bằng giọng dự phòng được đánh dấu, hộp Cài đặt có công tắc + tình trạng giọng dự phòng,
nút tạo lại bằng giọng chính, và thông báo sau khi tạo giọng."""
import pytest

pytest.importorskip("playwright.sync_api")

import app as A  # noqa: E402
import tts as T  # noqa: E402
from test_ui import browser, env, make_project, open_app, saved  # noqa: E402,F401


class Prov:
    """Nhà cung cấp giả chỉ để /api/tts/status có thứ để liệt kê."""

    def __init__(self, name, label, ok, detail, online=True):
        self.name, self.label, self.ok, self.detail, self.online = name, label, ok, detail, online

    def status(self, voice=None):
        return self.ok, self.detail


@pytest.fixture()
def providers(monkeypatch):
    monkeypatch.setattr(T, "default_providers", lambda order=None: [
        Prov("edge", "Microsoft Edge TTS", True, "đã cài edge-tts"),
        Prov("piper", "Piper (offline)", True, "1 giọng: vi_VN-vais1000-medium", online=False),
        Prov("gtts", "Google gTTS", False, "chưa cài – pip install gTTS")])


def mark_fallback(env, pid, idx):
    """Giả lập: cảnh idx đã được đọc bằng Piper (file mô tả giọng do server ghi nên sửa thẳng project.json)."""
    p = A.load(pid)
    p["scenes"][idx]["audio"]["engine"] = "piper"
    A.save(pid, p)


def test_fallback_scenes_are_marked_in_list_and_editor(env, providers):
    pid = make_project(env.client, n=3)
    mark_fallback(env, pid, 1)
    p = open_app(env, pid)
    p.wait_for_function("S.tts.length === 3")
    rows = p.locator("#sceneList .sc")
    assert "dự phòng" not in rows.nth(0).inner_text() and "dự phòng" in rows.nth(1).inner_text()
    assert "Piper (offline)" in rows.nth(1).locator(".warn").get_attribute("title")
    rows.nth(1).click()
    p.wait_for_selector("#editor >> text=Giọng dự phòng")
    rows.nth(0).click()
    assert p.locator("#editor >> text=Giọng dự phòng").count() == 0


def test_voices_made_before_v08_have_no_engine_and_are_not_flagged(env, providers):
    pid = make_project(env.client, n=2)
    proj = A.load(pid)
    for s in proj["scenes"]:
        s["audio"].pop("engine", None)
    A.save(pid, proj)
    p = open_app(env, pid)
    p.wait_for_function("S.tts.length === 3")
    assert p.locator("#sceneList .sc >> text=dự phòng").count() == 0


def test_settings_shows_engines_toggle_and_redo_button(env, providers):
    pid = make_project(env.client, n=3)
    mark_fallback(env, pid, 0)
    mark_fallback(env, pid, 2)
    p = open_app(env, pid)
    p.click("#btnSettings")
    p.wait_for_selector("#modal >> text=Giọng chính · Microsoft Edge TTS")
    txt = p.inner_text("#modal")
    assert "Dự phòng · Piper (offline) (chạy trên máy): 1 giọng: vi_VN-vais1000-medium" in txt
    assert "Dự phòng · Google gTTS: chưa cài" in txt and "gửi lời đọc tới Google" in txt
    assert "2 cảnh đang dùng giọng dự phòng" in txt
    box = p.locator("#modal label:has-text('Tự chuyển sang giọng dự phòng') input")
    assert box.is_checked()
    box.uncheck()
    assert p.evaluate("S.proj.voice.fallback") is False
    saved(p)
    assert env.client.get(f"/api/projects/{pid}").get_json()["project"]["voice"]["fallback"] is False
    box.check()
    assert p.evaluate("S.proj.voice.fallback") is True


def test_redo_button_replaces_fallback_voices_and_clears_the_marks(env, providers):
    pid = make_project(env.client, n=3)
    mark_fallback(env, pid, 1)
    p = open_app(env, pid)
    p.wait_for_function("S.tts.length === 3 && S.proj.scenes[1].audio.engine === 'piper'")
    p.click("#btnSettings")
    p.click("#modal button:has-text('Tạo lại các cảnh đó bằng giọng chính')")
    p.wait_for_function("S.proj.scenes[1].audio.engine !== 'piper'", timeout=30000)
    assert p.locator("#sceneList .sc >> text=dự phòng").count() == 0


def test_settings_hide_redo_button_when_nothing_uses_fallback(env, providers):
    pid = make_project(env.client, n=2)
    p = open_app(env, pid)
    p.click("#btnSettings")
    p.wait_for_selector("#modal >> text=Giọng chính · Microsoft Edge TTS")
    assert p.locator("#modal button:has-text('Tạo lại các cảnh đó')").count() == 0


def test_notice_after_voice_job_is_shown_in_a_modal(env, providers, monkeypatch):
    monkeypatch.setattr(T.Chain, "summary", lambda self: "THONG-BAO-DU-PHONG: 2 cảnh đọc bằng Piper.")
    pid = make_project(env.client, n=2)
    p = open_app(env, pid)
    p.click("#btnVoices")
    p.wait_for_selector("#modal >> text=Đã dùng giọng dự phòng", timeout=30000)
    assert "THONG-BAO-DU-PHONG" in p.inner_text("#modal")
    p.click("#modal button:has-text('Đã hiểu')")
    p.wait_for_selector("#modalBg.on", state="detached") if False else p.wait_for_function("!document.querySelector('#modalBg').classList.contains('on')")


def test_no_modal_when_everything_used_the_main_voice(env, providers):
    pid = make_project(env.client, n=2)
    p = open_app(env, pid)
    p.click("#btnVoices")
    p.wait_for_selector("#toast:has-text('Đã tạo xong giọng đọc')", timeout=30000)
    assert not p.evaluate("document.querySelector('#modalBg').classList.contains('on')")
