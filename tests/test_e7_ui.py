"""Giao diện, trình duyệt thật: cảnh có vấn đề được đánh dấu, lỗi hiện kèm cách xử lý và mã tra nhật ký,
xem được nhật ký, mất kết nối báo rõ, lỗi JavaScript được ghi vào nhật ký."""
import errno
import json
import time

import pytest

pytest.importorskip("playwright.sync_api")

import app as A  # noqa: E402
import logsetup as L  # noqa: E402
import media as M  # noqa: E402
from test_ui import browser, env, make_project, open_app  # noqa: E402,F401


@pytest.fixture()
def logs(tmp_path):
    L.setup(log_dir=tmp_path / "logs", level="INFO", console=False)
    yield
    L.teardown()


def put_missing_image(client, pid, scene_idx=0):
    p = client.get(f"/api/projects/{pid}").get_json()["project"]
    p["scenes"][scene_idx]["images"] = [dict(file="mat-tieu.png", mode="card", anim="zoom")]
    assert client.put(f"/api/projects/{pid}", json=p).status_code == 200


def test_missing_image_is_flagged_and_blocks_export(env):
    pid = make_project(env.client, n=2)
    put_missing_image(env.client, pid)
    page = open_app(env, pid)
    page.wait_for_selector("#sceneList .sc .err")
    assert "vấn đề" in page.inner_text("#sceneList .sc:nth-child(1)")
    assert "vấn đề" not in page.inner_text("#sceneList .sc:nth-child(2)")
    page.wait_for_selector("#editor .issues")
    assert "mat-tieu.png" in page.inner_text("#editor .issues")
    page.click("#btnExport")
    page.wait_for_selector("#modal >> text=Xuất video?")
    assert "mat-tieu.png" in page.inner_text("#modal")
    assert page.locator("#modal button.pri").count() == 0, "có lỗi thì không được có nút Xuất"


def test_issue_disappears_after_removing_the_image(env):
    pid = make_project(env.client, n=1)
    put_missing_image(env.client, pid)
    page = open_app(env, pid)
    page.wait_for_selector("#editor .issues")
    page.click("#editor .imgrow button:has-text('✕')")
    page.wait_for_selector("#editor .issues", state="detached")
    page.wait_for_function("!S.dirty && !S.saving")
    assert page.locator("#sceneList .err").count() == 0


def test_job_error_shows_hint_ref_and_opens_the_log(env, logs, monkeypatch):
    pid = make_project(env.client, n=1, voices=False)

    def boom(*a, **k):
        raise OSError(errno.ENOSPC, "No space left on device")
    monkeypatch.setattr(M, "tts_scene", boom)
    page = open_app(env, pid)
    page.click("#btnVoices")
    page.wait_for_selector("#modal >> text=không thành công")
    txt = page.inner_text("#modal")
    assert "Ổ đĩa đã đầy" in txt and "Giải phóng chỗ trống" in txt and "Mã tra nhật ký" in txt
    ref = txt.split("Mã tra nhật ký:")[1].split()[0]
    page.click("#modal >> text=Xem nhật ký")
    page.wait_for_selector("#modal pre.log")
    assert "disk_full" in page.inner_text("#modal pre.log") and ref in page.inner_text("#modal pre.log")
    assert page.locator("#modal a[href='/api/logs/download']").count() == 1


def test_server_error_with_hint_is_shown_in_toast(env):
    pid = make_project(env.client, n=1, voices=False)
    page = open_app(env, pid)
    body = json.dumps(dict(error="Không kết nối được dịch vụ giọng đọc.", hint="Thử tắt VPN.", code="network", ref="abc123"))
    page.route("**/api/projects/*/tts", lambda r: r.fulfill(status=502, content_type="application/json", body=body))
    page.click("#editor button:has-text('Tạo giọng cảnh này')")
    page.wait_for_selector("#toast >> text=Không kết nối được dịch vụ giọng đọc")
    assert "Thử tắt VPN." in page.inner_text("#toast")


def test_unreachable_server_says_so_in_vietnamese(env):
    pid = make_project(env.client, n=1, voices=False)
    page = open_app(env, pid)
    page.route("**/api/**", lambda r: r.abort())
    page.click("#btnVoices")
    page.wait_for_selector("#toast >> text=Không nối được tới tool")
    assert "F5" in page.inner_text("#toast")


def test_js_errors_are_reported_to_the_log(env, logs, monkeypatch):
    monkeypatch.setitem(A.CLIENT_LOG, "n", 0)
    pid = make_project(env.client, n=1, voices=False)
    page = open_app(env, pid)
    page.evaluate("window.dispatchEvent(new ErrorEvent('error', {message: 'ErrEvt-thử', filename: 'a.js', lineno: 3}))")
    page.evaluate("window.dispatchEvent(new PromiseRejectionEvent('unhandledrejection', {promise: Promise.resolve(), reason: new Error('RejEvt-thử')}))")
    t0 = time.time()
    while time.time() - t0 < 10:
        text = "\n".join(L.tail(50))
        if "ErrEvt-thử" in text and "RejEvt-thử" in text:
            break
        time.sleep(0.1)
    assert "ErrEvt-thử" in text and "a.js:3" in text and "RejEvt-thử" in text
