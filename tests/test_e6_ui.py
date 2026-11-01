"""Giao diện: nút ✨ AI -> hộp thoại -> job -> kịch bản đổ vào ô "Dán kịch bản" -> tạo cảnh (một bước hoàn tác).
Chạy trình duyệt thật + Ollama giả; cần Playwright + Chromium như tests/test_ui.py (không có thì tự bỏ qua)."""
import pytest

pytest.importorskip("playwright.sync_api")

import app as A  # noqa: E402
from test_e6 import Fake, scenes_json  # noqa: E402
from test_ui import browser, env, ids, make_project, open_app  # noqa: E402,F401


@pytest.fixture()
def fake(tmp_path, monkeypatch):
    f = Fake()
    monkeypatch.setattr(A, "AI_CFG", tmp_path / "ai.json")
    monkeypatch.setattr(A, "JOBS", {})
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("FFV_OLLAMA_MODEL", raising=False)
    yield f
    f.close()


def use(env, fake):
    assert env.client.put("/api/ai/config", json=dict(url=fake.url, model="qwen2.5:7b")).status_code == 200
    pid = make_project(env.client, n=1, voices=False)
    return open_app(env, pid)


MODELS_LOADED = "(() => { const s = document.querySelectorAll('#modal select')[2]; return !!s && s.options.length > 0; })()"


def open_ai(p):
    p.click("#btnAI")
    p.wait_for_function(MODELS_LOADED)  # danh sách mô hình đã nạp xong (<option> trong ô chọn đóng không bao giờ "visible" nên không dùng wait_for_selector)


def test_ai_script_flows_into_paste_box_then_creates_scenes_as_one_undo_step(env, fake):
    p = use(env, fake)
    open_ai(p)
    assert p.locator("#modal select").nth(2).input_value() == "qwen2.5:7b"
    assert p.locator("#modal select").nth(2).locator("option").count() == 2  # mô hình embedding bị ẩn
    fake.replies = [scenes_json(6)]
    p.fill("#modal textarea", "Đom đóm là gì và vì sao chúng phát sáng?")
    p.select_option("#modal select >> nth=0", "90")
    p.get_by_role("button", name="Viết kịch bản").click()
    p.wait_for_function("document.querySelector('#modal textarea') && document.querySelector('#modal textarea').value.startsWith('# Ý 1')", timeout=20000)
    assert "AI (qwen2.5:7b) đã viết 6 cảnh" in p.inner_text("#modal")
    req = fake.requests[0]["messages"][1]["content"]
    assert "Đom đóm là gì" in req and "90 giây" in req  # độ dài chọn trên giao diện tới được lời nhắc
    # người dùng sửa bản nháp ngay trong ô dán rồi mới tạo cảnh
    p.fill("#modal textarea", p.input_value("#modal textarea").replace("# Ý 1", "# Tiêu đề do tôi sửa", 1))
    p.get_by_role("button", name="Tạo cảnh").click()
    p.wait_for_function("S.proj.scenes.length === 7")
    titles = p.evaluate("S.proj.scenes.map(s => s.title)")
    assert titles[1] == "Tiêu đề do tôi sửa" and titles[2] == "Ý 2"
    assert p.evaluate("S.proj.scenes[1].narration").startswith("Đây là câu số 1")
    assert len(set(ids(p))) == 7
    p.click("#btnUndo")
    p.wait_for_function("S.proj.scenes.length === 1")  # cả 6 cảnh AI tạo ra lùi về trong đúng một bước


def test_ai_failure_reopens_dialog_with_topic_kept(env, fake):
    p = use(env, fake)
    open_ai(p)
    fake.replies = ["không phải json"] * 3
    p.fill("#modal textarea", "Chủ đề dài tôi không muốn gõ lại")
    p.get_by_role("button", name="Viết kịch bản").click()
    p.wait_for_selector("#toast.err", state="visible", timeout=20000)
    assert "3 lần" in p.inner_text("#toast")
    p.wait_for_function(MODELS_LOADED)  # hộp thoại AI tự mở lại
    assert p.input_value("#modal textarea") == "Chủ đề dài tôi không muốn gõ lại"
    assert p.evaluate("S.proj.scenes.length") == 1  # lỗi thì không đụng gì tới dự án


def test_ollama_not_running_is_explained_and_blocks_the_button(env, fake):
    p = use(env, fake)
    fake.close()  # tắt Ollama giả
    p.click("#btnAI")
    p.wait_for_function("document.querySelector('#modal') && document.querySelector('#modal').innerText.includes('Không kết nối được Ollama')")
    assert p.get_by_role("button", name="Viết kịch bản").is_disabled()
    assert "ollama serve" in p.inner_text("#modal")


# ----------------------------------------------------------------------------- cảnh báo chất lượng
def test_review_warnings_are_listed_above_the_draft_in_the_paste_box(env, fake):
    p = use(env, fake)
    open_ai(p)
    import json
    data = json.loads(scenes_json(6))
    data["scenes"][0]["narration"] = "Đom đóm xuất hiện từ năm 1947 theo ghi chép. " + data["scenes"][0]["narration"]
    fake.replies = [json.dumps(data, ensure_ascii=False)]
    p.fill("#modal textarea", "Đom đóm là gì và vì sao chúng phát sáng?")
    p.get_by_role("button", name="Viết kịch bản").click()
    p.wait_for_selector("#aiWarn", timeout=20000)
    txt = p.inner_text("#aiWarn")
    assert "Nên xem lại" in txt and "1947" in txt and "kiểm chứng" in txt
    assert p.input_value("#modal textarea").startswith("# Ý 1"), "cảnh báo nằm ngoài ô dán, không lẫn vào kịch bản"


def test_no_warning_box_when_the_review_finds_nothing(env, fake):
    p = use(env, fake)
    open_ai(p)
    fake.replies = [scenes_json(6)]
    p.fill("#modal textarea", "Đom đóm là gì?")
    p.get_by_role("button", name="Viết kịch bản").click()
    p.wait_for_function("document.querySelector('#modal textarea') && document.querySelector('#modal textarea').value.startsWith('# Ý 1')", timeout=20000)
    assert p.locator("#aiWarn").count() == 0


def test_small_model_gets_a_hint_and_big_model_does_not(env, fake):
    fake.details = {"qwen2.5:7b": {"parameter_size": "1.5B"}, "llama3.1:8b": {"parameter_size": "8.0B"}}
    p = use(env, fake)
    open_ai(p)
    sel = p.locator("#modal select").nth(2)
    p.wait_for_function("document.querySelector('#modal').innerText.includes('Mô hình nhỏ (1.5B)')")
    assert sel.locator("option", has_text="qwen2.5:7b").inner_text() == "qwen2.5:7b (1.5B, 4.0 GB)"  # danh sách xếp theo tên nên llama đứng trước
    sel.select_option("llama3.1:8b")
    p.wait_for_function("!document.querySelector('#modal').innerText.includes('Mô hình nhỏ')")
