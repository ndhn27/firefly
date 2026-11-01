"""Giao diện: chạy trình duyệt thật (Playwright + Chromium) trên server thật, giọng giả offline.
Kiểm: hoàn tác/làm lại, kéo thả đổi thứ tự cảnh, đường kẻ vùng an toàn, dọn file không dùng.
Cần:  pip install playwright && playwright install chromium   (không có thì cả file này được bỏ qua)."""
import os
import threading
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

import app as A  # noqa: E402
import render as R  # noqa: E402

PAUSE = 0.95  # giây: lâu hơn HIST_PAUSE (0.7s) trong index.html để các lần gõ được chốt thành một bước


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        try:
            b = pw.chromium.launch()
        except Exception as e:  # noqa
            pytest.skip(f"Không mở được Chromium: {str(e)[:120]}")
        yield b
        b.close()


@pytest.fixture()
def env(tmp_path, monkeypatch, browser):
    monkeypatch.setattr(A, "PROJ", tmp_path)
    srv = make_server("127.0.0.1", 0, A.app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("dialog", lambda d: d.accept())
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    e = type("Env", (), {})()
    e.client, e.page, e.url, e.errors = A.app.test_client(), page, f"http://127.0.0.1:{srv.server_port}/", errors
    yield e
    ctx.close()
    srv.shutdown()
    assert not errors, f"Lỗi JavaScript trong trang: {errors}"


def make_project(client, n=4, aspect="9:16", name="UI", voices=True):
    r = client.post("/api/projects", json={"name": name, "aspect": aspect}).get_json()
    pid, p = r["id"], r["project"]
    p["scenes"] = [dict(id=f"s{i}", title=f"Tiêu đề {i}", subtitle="", narration=f"Cảnh số {i} có lời đọc đủ dài để có thời lượng.",
                        voice=True, caption=True, images=[], transition="fade") for i in range(n)]
    client.put(f"/api/projects/{pid}", json=p)
    if voices:
        for i in range(n):
            assert client.post(f"/api/projects/{pid}/tts", json={"scene": f"s{i}"}).status_code == 200
    return pid


def open_app(env, pid):
    p = env.page
    p.goto(env.url)
    p.evaluate(f"localStorage.setItem('ffv_last', '{pid}')")
    p.reload()
    p.wait_for_function("typeof S !== 'undefined' && S.proj !== null && S.tl.scenes.length > 0")
    try:
        p.wait_for_selector("#editor textarea", timeout=10000)
    except Exception:  # noqa
        # S.proj đã có nhưng khung chỉnh sửa chưa/không vẽ ra (boot() nuốt lỗi và chỉ hiện toast): in đủ thông tin để truy
        info = p.evaluate("() => ({pid: S.pid, sel: S.sel, scenes: S.proj && S.proj.scenes.length, toast: document.querySelector('#toast').innerText, editor: document.querySelector('#editor').innerHTML.slice(0, 200)})")
        raise AssertionError(f"Khung chỉnh sửa không được vẽ sau khi mở dự án: {info}") from None
    return p


def saved(p):
    p.wait_for_function("!S.dirty && !S.saving")


def ids(p):
    return p.evaluate("S.proj.scenes.map(s => s.id)")


def server_ids(env, pid):
    return [s["id"] for s in env.client.get(f"/api/projects/{pid}").get_json()["project"]["scenes"]]


def title_box(p):
    return p.locator("#editor textarea").first


def blur(p):
    p.locator("#stageBox").click(position={"x": 5, "y": 5})  # bấm ra vùng trống: bỏ focus khỏi ô chữ


def drag_row(p, src, dst, where=0.8):
    rows = p.locator("#sceneList .sc")
    box = rows.nth(dst).bounding_box()
    rows.nth(src).drag_to(rows.nth(dst), target_position={"x": 100, "y": box["height"] * where})


# ----------------------------------------------------------------------------- vùng an toàn
@pytest.mark.parametrize("aspect", sorted(R.ASPECTS))
def test_safe_overlay_matches_renderer_table(env, aspect):
    pid = make_project(env.client, 1, aspect, voices=False)
    p = open_app(env, pid)
    assert p.locator("#safe").is_hidden(), "mặc định tắt"
    p.locator("#btnSafe").click()
    assert p.locator("#safe").is_visible()
    z = R.SAFE[aspect]
    scr, frame, cap = (p.locator(s).bounding_box() for s in ("#screen", ".sz-frame", ".sz-cap"))
    tol = 0.004
    assert abs((frame["x"] - scr["x"]) / scr["width"] - z["mx"]) < tol
    assert abs((frame["y"] - scr["y"]) / scr["height"] - z["top"]) < tol
    assert abs((frame["x"] + frame["width"] - scr["x"]) / scr["width"] - (1 - z["mx"])) < tol
    assert abs((frame["y"] + frame["height"] - scr["y"]) / scr["height"] - z["bottom"]) < tol
    assert abs((cap["y"] - scr["y"]) / scr["height"] - z["cap"]) < tol
    assert p.eval_on_selector("#safe", "e => getComputedStyle(e).pointerEvents") == "none", "không được chặn thao tác với preview/video"
    p.reload()
    p.wait_for_function("S.proj !== null")
    assert p.locator("#safe").is_visible(), "nhớ lựa chọn sau khi tải lại trang"
    p.locator("#btnSafe").click()
    assert p.locator("#safe").is_hidden()


def test_safe_overlay_follows_aspect_change_and_is_not_in_the_exported_frame(env):
    pid = make_project(env.client, 1, "9:16", voices=False)
    p = open_app(env, pid)
    p.locator("#btnSafe").click()
    p.locator("#btnSettings").click()
    p.locator(".asp button", has_text="Ngang 16:9").click()
    p.locator("#modal button.pri", has_text="Xong").click()
    saved(p)
    scr, frame = p.locator("#screen").bounding_box(), p.locator(".sz-frame").bounding_box()
    assert abs((frame["y"] - scr["y"]) / scr["height"] - R.SAFE["16:9"]["top"]) < 0.004
    # ảnh preview do server dựng không chứa đường kẻ: byte y hệt khi bật/tắt
    url = f"{env.url}api/projects/{pid}/preview.jpg?t=1.0&h=300"
    a = p.request.get(url).body()
    p.locator("#btnSafe").click()
    assert p.request.get(url).body() == a


# ----------------------------------------------------------------------------- kéo thả
def test_drag_scene_to_new_position_and_undo(env):
    pid = make_project(env.client, 4, voices=False)
    p = open_app(env, pid)
    drag_row(p, 0, 2)  # thả vào nửa dưới hàng 3 -> s1 s2 s0 s3
    saved(p)
    assert ids(p) == ["s1", "s2", "s0", "s3"] == server_ids(env, pid)
    assert p.evaluate("S.proj.scenes[S.sel].id") == "s0", "chọn cảnh vừa chuyển"
    assert p.locator("#sceneList .sc.sel .t").inner_text() == "Tiêu đề 0"
    p.keyboard.press("Control+z")
    saved(p)
    assert ids(p) == ["s0", "s1", "s2", "s3"] == server_ids(env, pid)
    p.keyboard.press("Control+Shift+z")
    saved(p)
    assert ids(p) == ["s1", "s2", "s0", "s3"] == server_ids(env, pid)


def test_drag_upper_half_inserts_before_and_empty_area_means_end_and_noop_drops(env):
    pid = make_project(env.client, 4, voices=False)
    p = open_app(env, pid)
    drag_row(p, 3, 1, where=0.2)  # nửa trên hàng 2 -> chèn trước nó
    saved(p)
    assert ids(p) == ["s0", "s3", "s1", "s2"]
    p.locator("#sceneList .sc").nth(0).drag_to(p.locator("#scenes"), target_position={"x": 100, "y": 700})  # khoảng trống dưới danh sách
    saved(p)
    assert ids(p) == ["s3", "s1", "s2", "s0"]
    before = p.evaluate("H.undo.length")
    drag_row(p, 1, 1, where=0.9)   # thả lại đúng chỗ cũ (sau chính nó): không đổi, không thêm bước hoàn tác
    drag_row(p, 1, 0, where=0.9)   # thả vào nửa dưới hàng ngay trên: vẫn đúng chỗ cũ
    assert ids(p) == ["s3", "s1", "s2", "s0"] and p.evaluate("H.undo.length") == before
    assert p.locator("#sceneList .drop-before, #sceneList .drop-after, #sceneList .dragging").count() == 0, "dấu chèn phải được dọn sau khi thả"


def test_dropping_a_file_outside_the_editor_does_not_navigate_away(env):
    pid = make_project(env.client, 2, voices=False)
    p = open_app(env, pid)
    p.evaluate("""() => { const dt = new DataTransfer(); dt.items.add(new File(['x'], 'a.png', {type: 'image/png'}));
      document.querySelector('#scenes').dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true})); }""")
    assert p.url == env.url and ids(p) == ["s0", "s1"]


# ----------------------------------------------------------------------------- hoàn tác / làm lại
def test_typing_is_one_step_and_shortcuts_work(env):
    pid = make_project(env.client, 3, voices=False)
    p = open_app(env, pid)
    assert p.locator("#btnUndo").is_disabled() and p.locator("#btnRedo").is_disabled()
    box = title_box(p)
    box.fill("")
    box.press_sequentially("Tiêu đề mới", delay=25)
    p.wait_for_timeout(PAUSE * 1000)
    assert p.locator("#btnUndo").is_enabled()
    box.press_sequentially(" thêm", delay=25)
    p.wait_for_timeout(PAUSE * 1000)
    blur(p)
    p.keyboard.press("Control+z")  # lần gõ thứ hai (" thêm") là một bước
    assert title_box(p).input_value() == "Tiêu đề mới"
    p.keyboard.press("Control+z")  # xoá sạch rồi gõ "Tiêu đề mới" (nhiều phím liên tiếp) cũng chỉ là một bước: về "Tiêu đề 0"
    assert title_box(p).input_value() == "Tiêu đề 0"
    assert p.locator("#btnUndo").is_disabled() and p.locator("#btnRedo").is_enabled()
    p.keyboard.press("Control+Shift+z")
    assert title_box(p).input_value() == "Tiêu đề mới"
    p.keyboard.press("Control+y")
    assert title_box(p).input_value() == "Tiêu đề mới thêm"
    saved(p)
    assert env.client.get(f"/api/projects/{pid}").get_json()["project"]["scenes"][0]["title"] == "Tiêu đề mới thêm"


def test_new_edit_after_undo_clears_redo(env):
    pid = make_project(env.client, 2, voices=False)
    p = open_app(env, pid)
    title_box(p).fill("A")
    p.wait_for_timeout(PAUSE * 1000)
    p.locator("#btnUndo").click()
    assert p.locator("#btnRedo").is_enabled()
    title_box(p).fill("B")
    p.wait_for_timeout(PAUSE * 1000)
    assert p.locator("#btnRedo").is_disabled()


def test_toolbar_buttons_and_undo_selects_the_scene_that_changed(env):
    pid = make_project(env.client, 3, voices=False)
    p = open_app(env, pid)
    p.locator("#sceneList .sc").nth(2).click()
    title_box(p).fill("Chỉ cảnh 3 đổi")
    p.wait_for_timeout(PAUSE * 1000)
    p.locator("#sceneList .sc").nth(0).click()
    assert p.evaluate("S.sel") == 0
    p.locator("#btnUndo").click()  # bấm nút (không phụ thuộc focus) -> quay về cảnh 3 và chữ cũ
    saved(p)
    assert p.evaluate("S.sel") == 2 and title_box(p).input_value() == "Tiêu đề 2"
    p.locator("#btnRedo").click()
    assert title_box(p).input_value() == "Chỉ cảnh 3 đổi"


def test_ctrl_z_inside_a_text_field_is_left_to_the_browser(env):
    pid = make_project(env.client, 3, voices=False)
    p = open_app(env, pid)
    p.locator("#sceneList .sc").nth(1).hover()
    p.locator("#sceneList .sc").nth(1).locator("button[title='Xoá']").click()
    assert len(ids(p)) == 2
    title_box(p).click()
    p.keyboard.press("Control+z")  # đang ở trong ô chữ: không được khôi phục cảnh đã xoá
    assert len(ids(p)) == 2
    blur(p)
    p.keyboard.press("Control+z")
    assert len(ids(p)) == 3


def test_each_discrete_action_is_its_own_step(env):
    pid = make_project(env.client, 2, voices=False)
    p = open_app(env, pid)
    p.locator("#editor .chk", has_text="Hiện phụ đề").locator("input").uncheck()
    p.locator("#editor select").last.select_option("dip")  # đổi chuyển cảnh ngay sau đó (chưa tới 0.7s)
    assert p.evaluate("[S.proj.scenes[0].caption, S.proj.scenes[0].transition]") == [False, "dip"]
    p.locator("#btnUndo").click()
    assert p.evaluate("[S.proj.scenes[0].caption, S.proj.scenes[0].transition]") == [False, "fade"]
    p.locator("#btnUndo").click()
    assert p.evaluate("[S.proj.scenes[0].caption, S.proj.scenes[0].transition]") == [True, "fade"]


def test_undo_delete_brings_back_scene_and_its_voice(env):
    pid = make_project(env.client, 3, voices=True)
    p = open_app(env, pid)
    assert p.evaluate("S.proj.scenes.every(s => s.audio)") and p.locator("#sceneList .warn").count() == 0
    p.locator("#sceneList .sc").nth(1).hover()
    p.locator("#sceneList .sc").nth(1).locator("button[title='Xoá']").click()
    saved(p)
    assert ids(p) == ["s0", "s2"] == server_ids(env, pid)
    blur(p)
    p.keyboard.press("Control+z")
    saved(p)
    assert ids(p) == ["s0", "s1", "s2"] == server_ids(env, pid)
    assert p.evaluate("S.proj.scenes[1].audio !== null"), "giọng của cảnh được khôi phục từ server"
    assert p.locator("#sceneList .warn").count() == 0, "không có cảnh nào bị báo thiếu giọng"
    assert p.evaluate("S.tl.scenes[1].estimated") is False
    assert env.client.get(f"/api/projects/{pid}").get_json()["project"]["scenes"][1]["audio"]["file"].startswith("s1_")
    p.keyboard.press("Control+Shift+z")
    saved(p)
    assert ids(p) == ["s0", "s2"]


def test_paste_script_replace_all_is_one_undo_step(env):
    pid = make_project(env.client, 3, voices=False)
    p = open_app(env, pid)
    p.locator("#btnPaste").click()
    p.locator("#modal textarea").fill("# Mới 1\nLời một.\n\n# Mới 2\nLời hai.")
    p.locator("#modal label.chk input").check()
    p.locator("#modal button.pri", has_text="Tạo cảnh").click()
    saved(p)
    assert len(ids(p)) == 2 and p.evaluate("S.proj.scenes[0].title") == "Mới 1"
    blur(p)
    p.keyboard.press("Control+z")
    saved(p)
    assert ids(p) == ["s0", "s1", "s2"]


def test_undo_aspect_change_from_settings_and_blocked_while_modal_open(env):
    pid = make_project(env.client, 1, "9:16", voices=False)
    p = open_app(env, pid)
    p.locator("#btnSettings").click()
    p.locator(".asp button", has_text="Ngang 16:9").click()
    assert p.evaluate("S.proj.aspect") == "16:9"
    p.keyboard.press("Control+z")  # cửa sổ đang mở: bị chặn
    assert p.evaluate("S.proj.aspect") == "16:9"
    p.locator("#modal button.pri", has_text="Xong").click()
    saved(p)
    p.locator("#btnUndo").click()
    saved(p)
    assert p.evaluate("S.proj.aspect") == "9:16"
    scr = p.locator("#screen").bounding_box()
    assert scr["height"] > scr["width"], "khung preview đổi lại theo tỉ lệ dọc"
    assert env.client.get(f"/api/projects/{pid}").get_json()["project"]["aspect"] == "9:16"


def test_history_is_cleared_when_switching_project(env):
    a = make_project(env.client, 2, name="Một", voices=False)
    b = make_project(env.client, 2, name="Hai", voices=False)
    p = open_app(env, a)
    title_box(p).fill("Đã sửa")
    p.wait_for_timeout(PAUSE * 1000)
    assert p.locator("#btnUndo").is_enabled()
    p.locator("#projSel").select_option(b)
    p.wait_for_function(f"S.pid === '{b}'")
    assert p.locator("#btnUndo").is_disabled() and p.locator("#btnRedo").is_disabled()


def test_history_keeps_at_most_100_steps(env):
    pid = make_project(env.client, 1, voices=False)
    p = open_app(env, pid)
    n = p.evaluate("""() => { for (let i = 0; i < 130; i++) edit(() => { S.proj.scenes[0].extra = i + 1; }); return H.undo.length; }""")
    assert n == 100


# ----------------------------------------------------------------------------- dọn file không dùng
def test_cleanup_dialog_deletes_orphans_clears_history_and_keeps_used(env, tmp_path):
    pid = make_project(env.client, 2, voices=True)
    d = tmp_path / pid
    keep = d / "media" / "dung.png"
    gone = d / "media" / "thua.png"
    for f, size in ((keep, 10), (gone, 3 * 1024 * 1024)):
        f.write_bytes(b"x" * size)
        t = time.time() - 3600
        os.utime(f, (t, t))
    proj = env.client.get(f"/api/projects/{pid}").get_json()["project"]
    proj["scenes"][0]["images"] = [dict(file="dung.png", mode="card", anim="zoom")]
    env.client.put(f"/api/projects/{pid}", json=proj)
    p = open_app(env, pid)
    title_box(p).fill("sửa để có lịch sử")
    p.wait_for_timeout(PAUSE * 1000)
    assert p.locator("#btnUndo").is_enabled()
    p.locator("#btnSettings").click()
    p.locator("#modal button", has_text="Dọn file không dùng").click()
    p.wait_for_selector("#modal h3:has-text('Dọn file không dùng')")
    body = p.locator("#modal").inner_text()
    assert "media/thua.png" in body and "3.0 MB" in body and "dung.png" not in body
    assert "audio/" not in body, "giọng đang dùng không được liệt kê"
    p.locator("#modal button.pri", has_text="Xoá 1 file").click()
    p.wait_for_selector("#toast:has-text('Đã dọn 1 file')")
    assert not gone.exists() and keep.exists()
    assert all((d / "audio" / s["audio"]["file"]).exists() for s in env.client.get(f"/api/projects/{pid}").get_json()["project"]["scenes"])
    assert p.locator("#btnUndo").is_disabled(), "lịch sử bị xoá vì các bước cũ có thể trỏ tới file đã dọn"
    p.locator("#btnSettings").click()
    p.locator("#modal button", has_text="Dọn file không dùng").click()
    p.wait_for_selector("#modal:has-text('Không có file thừa')")
