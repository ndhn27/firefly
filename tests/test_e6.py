"""Kịch bản bằng AI qua Ollama. Dùng một máy chủ Ollama GIẢ (giao thức giống thật: GET /api/tags, POST /api/chat trả từng dòng JSON)
nên chạy offline, nhưng không thay được việc thử với mô hình thật (chất lượng chữ do mô hình quyết định)."""
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import app as A
import doctor as D
import render as R
import scriptgen as G


# ----------------------------------------------------------------------------- Ollama giả
class Fake:
    def __init__(self, models=("qwen2.5:7b", "nomic-embed-text:latest", "llama3.1:8b")):
        self.models, self.replies, self.requests = list(models), [], []
        self.details = {}  # tên mô hình -> {"parameter_size": "7.6B"}: Ollama thật có trường này trong /api/tags
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code, obj):
                b = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                if self.path == "/api/tags":
                    return self._json(200, {"models": [dict({"name": m, "size": 4_000_000_000}, **({"details": fake.details[m]} if m in fake.details else {}))
                                                       for m in fake.models]})
                self._json(404, {"error": "no"})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append(body)
                r = fake.replies.pop(0) if fake.replies else dict(content="")
                if isinstance(r, str):
                    r = dict(content=r)
                if r.get("status"):
                    return self._json(r["status"], {"error": r["error"]})
                if r.get("only_json_format") and isinstance(body.get("format"), dict):
                    return self._json(400, {"error": "invalid format: expected \"json\" or a JSON schema"})
                time.sleep(r.get("delay", 0))
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                text = r["content"]
                try:
                    for i in range(0, len(text), 25):
                        self.wfile.write((json.dumps({"message": {"role": "assistant", "content": text[i:i + 25]}, "done": False}) + "\n").encode())
                        self.wfile.flush()
                    self.wfile.write((json.dumps({"message": {"role": "assistant", "content": ""}, "done": True,
                                                  "done_reason": r.get("done_reason", "stop")}) + "\n").encode())
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture()
def fake():
    f = Fake()
    yield f
    f.close()


def scenes_json(n=6, chars=110, **kw):
    """n cảnh, mỗi cảnh ~`chars` ký tự lời đọc (mặc định tương đương video ~60 giây)."""
    sc = [dict(title=f"Ý {i + 1}", narration=(f"Đây là câu số {i + 1}, nói về đom đóm. " * 20)[:chars].strip()) for i in range(n)]
    return json.dumps(dict(scenes=sc, **kw), ensure_ascii=False)


def gen(fake, **kw):
    return G.generate(fake.url, "qwen2.5:7b", "Đom đóm là gì?", **dict(dict(duration=60), **kw))


# ----------------------------------------------------------------------------- làm sạch + tách JSON
def test_clean_text_strips_everything_that_would_break_paste_or_speech():
    assert G.clean_text("## Tiêu đề\n- ý một\n* ý hai") == "Tiêu đề ý một ý hai"
    assert G.clean_text("Đom đóm **rất** đẹp 🌟✨ và *lạ*.") == "Đom đóm rất đẹp và lạ."
    assert G.clean_text("#hashtag đầu dòng") == "hashtag đầu dòng"  # '#' đầu dòng sẽ bị chế độ dán hiểu là tiêu đề
    assert G.clean_text("Cảnh 3: Mở đầu.", title=True) == "Mở đầu"
    assert G.clean_text("Hai\n\nđoạn\r\n  nối") == "Hai đoạn nối"


@pytest.mark.parametrize("wrap", [
    lambda j: j,
    lambda j: "```json\n" + j + "\n```",
    lambda j: "Chắc chắn rồi! Đây là kịch bản:\n" + j + "\nChúc bạn thành công.",
    lambda j: "<think>để mình nghĩ {xem sao}...</think>" + j,
    lambda j: json.dumps(json.loads(j)["scenes"], ensure_ascii=False),  # mảng trần, không bọc {"scenes": ...}
])
def test_extract_and_validate_tolerates_common_model_habits(wrap):
    out = G.parse_script(wrap(scenes_json(3)))
    assert len(out.scenes) == 3 and out.scenes[0].title == "Ý 1"


def test_validation_feedback_names_the_exact_field():
    bad = json.dumps({"scenes": [dict(title="a", narration="x" * 100), dict(title="b", narration="")]})
    with pytest.raises(G.BadOutput) as e:
        G.parse_script(bad)
    assert "scenes[1].narration" in e.value.feedback and "ngắn" in e.value.feedback
    with pytest.raises(G.BadOutput) as e:
        G.parse_script(json.dumps({"scenes": [dict(title="a")]}))
    assert "scenes[0].narration" in e.value.feedback and "thiếu" in e.value.feedback
    with pytest.raises(G.BadOutput) as e:
        G.parse_script(json.dumps({"scenes": [dict(title="t" * 200, narration="x" * 50)]}))
    assert "quá dài" in e.value.feedback
    with pytest.raises(G.BadOutput) as e:
        G.parse_script('{"scenes": [')
    assert "JSON" in e.value.feedback
    with pytest.raises(G.BadOutput):
        G.parse_script("")


def test_hand_written_schema_matches_the_pydantic_model():
    item = G.SCHEMA["properties"]["scenes"]["items"]
    assert set(item["properties"]) == set(G.SceneOut.model_fields) and set(item["required"]) == {"title", "narration"}
    assert "$defs" not in json.dumps(G.SCHEMA) and "$ref" not in json.dumps(G.SCHEMA)


# ----------------------------------------------------------------------------- kế hoạch độ dài
@pytest.mark.parametrize("dur", G.DURATIONS)
def test_plan_lands_near_requested_duration_by_the_renderers_own_estimate(dur):
    n, words = G.plan(dur, "vi")
    sc = [dict(narration="x" * round(words * 4.6)) for _ in range(n)]
    assert abs(G.est_seconds(sc) - dur) <= dur * 0.12, (n, words, G.est_seconds(sc))


# ----------------------------------------------------------------------------- generate + retry
def test_happy_path_uses_schema_and_returns_paste_ready_text(fake):
    fake.replies = [scenes_json(6)]
    r = gen(fake)
    assert r["attempts"] == 1 and len(r["scenes"]) == 6 and 40 <= r["est_seconds"] <= 80
    req = fake.requests[0]
    assert req["format"] == G.SCHEMA and req["stream"] is True and req["model"] == "qwen2.5:7b"
    assert req["messages"][0]["role"] == "system" and "Đom đóm là gì?" in req["messages"][1]["content"]
    assert "tiếng Việt" in req["messages"][0]["content"]


def test_overlong_source_material_is_cut_and_flagged_not_silently_dropped(fake):
    fake.replies = [scenes_json(6), scenes_json(6)]
    ok = G.generate(fake.url, "m", "đom đóm " * 100, duration=60)
    cut = G.generate(fake.url, "m", "đom đóm " * 2000, duration=60)
    assert ok["topic_cut"] is False and cut["topic_cut"] is True
    sent = fake.requests[1]["messages"][1]["content"]
    assert len(sent) < G.TOPIC_MAX + 400


def test_broken_json_is_retried_with_the_error_fed_back(fake):
    fake.replies = ['{"scenes": [{"title": "A", "narration": "chưa đóng', scenes_json(6)]
    r = gen(fake)
    assert r["attempts"] == 2 and len(fake.requests) == 2
    m = fake.requests[1]["messages"]
    assert m[-2]["role"] == "assistant" and "chưa đóng" in m[-2]["content"]  # bản hỏng được gửi lại để mô hình thấy lỗi của mình
    assert m[-1]["role"] == "user" and "JSON" in m[-1]["content"]
    assert fake.requests[1]["options"]["temperature"] < fake.requests[0]["options"]["temperature"]


def test_gives_up_after_attempts_with_a_clear_vietnamese_message(fake):
    fake.replies = ["không phải json"] * 3
    with pytest.raises(G.ScriptError) as e:
        gen(fake, attempts=3)
    assert "3 lần" in str(e.value) and "qwen2.5:7b" in str(e.value) and len(fake.requests) == 3


def test_script_far_too_short_is_asked_again_but_best_effort_is_kept_at_the_end(fake):
    short = scenes_json(2, chars=40)
    fake.replies = [short, scenes_json(6)]
    r = gen(fake)
    assert r["attempts"] == 2 and "chỉ khoảng" in fake.requests[1]["messages"][-1]["content"]
    fake.replies = [short, short, short]
    r = gen(fake, attempts=3)  # lượt cuối vẫn lệch -> vẫn trả bản dùng được thay vì báo lỗi
    assert len(fake.requests) == 5 and len(r["scenes"]) == 2


def test_truncated_output_asks_for_shorter_without_echoing_the_cut_text(fake):
    fake.replies = [dict(content='{"scenes": [{"title": "A", "narr', done_reason="length"), scenes_json(6)]
    r = gen(fake)
    m = fake.requests[1]["messages"]
    assert r["attempts"] == 2 and m[-1]["role"] == "user" and "cắt giữa chừng" in m[-1]["content"] and m[-2]["role"] == "user"


def test_old_ollama_without_schema_support_falls_back_to_plain_json_without_using_up_an_attempt(fake):
    fake.replies = [dict(only_json_format=True, content=""), dict(only_json_format=True, content=scenes_json(6))]
    r = gen(fake, attempts=1)
    assert r["attempts"] == 1 and fake.requests[0]["format"] == G.SCHEMA and fake.requests[1]["format"] == "json"


def test_missing_model_and_dead_server_give_actionable_messages(fake):
    fake.replies = [dict(status=404, error="model 'qwen2.5:7b' not found")]
    with pytest.raises(G.ScriptError, match="ollama pull qwen2.5:7b"):
        gen(fake)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        dead = f"http://127.0.0.1:{s.getsockname()[1]}"
    with pytest.raises(G.OllamaUnreachable, match="ollama serve"):
        G.generate(dead, "m", "chủ đề", duration=60)
    with pytest.raises(G.OllamaUnreachable):
        G.list_models(dead)


def test_cancel_interrupts_a_model_that_is_still_loading(fake):
    fake.replies = [dict(content=scenes_json(6), delay=30)]  # "đang nạp mô hình", chưa nhả chữ nào
    flag = {"c": False}
    threading.Timer(0.6, lambda: flag.update(c=True)).start()
    t0 = time.time()
    with pytest.raises(G.Cancelled):
        G.generate(fake.url, "m", "chủ đề", duration=60, cancel=lambda: flag["c"])
    assert time.time() - t0 < 5


def test_input_validation():
    with pytest.raises(G.ScriptError, match="chủ đề"):
        G.generate("http://127.0.0.1:1", "m", "  ")
    with pytest.raises(G.ScriptError, match="mô hình"):
        G.generate("http://127.0.0.1:1", "", "đom đóm")


def test_models_list_hides_embedding_models(fake):
    assert [m["name"] for m in G.list_models(fake.url)] == ["llama3.1:8b", "qwen2.5:7b"]


# ----------------------------------------------------------------------------- khớp với chế độ dán
def js_paste_parse(text):
    """Bản Python của bộ tách trong openPaste() (index.html): tách theo dòng trống; dòng đầu bắt đầu bằng # là tiêu đề, phần còn lại nối bằng dấu cách."""
    import re
    out = []
    for b in [b.strip() for b in re.split(r"\n\s*\n", text)]:
        if not b:
            continue
        lines = [l.strip() for l in b.split("\n") if l.strip()]
        title = ""
        if lines[0].startswith("#"):
            title = re.sub(r"^#+\s*", "", lines.pop(0))
        out.append((title, " ".join(lines)))
    return out


def test_generated_text_round_trips_through_paste_mode_exactly():
    nasty = json.dumps({"scenes": [
        dict(title="## Cảnh 1: Mở đầu", narration="# Đây là lời đọc\n\nvới dòng trống và\n- gạch đầu dòng."),
        dict(title="", narration="Cảnh không có tiêu đề, vẫn đọc được."),
        dict(title="Kết", narration="Hết rồi, cảm ơn bạn đã xem video này nhé."),
    ]}, ensure_ascii=False)
    sc = [s.model_dump() for s in G.parse_script(nasty).scenes]
    assert js_paste_parse(G.to_paste_text(sc)) == [(s["title"], s["narration"]) for s in sc]
    assert len(sc) == 3 and not any(s["narration"].startswith("#") for s in sc)


# ----------------------------------------------------------------------------- cấu hình + API
def test_config_roundtrip_and_env(tmp_path, monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("FFV_OLLAMA_MODEL", raising=False)
    p = tmp_path / "ai.json"
    assert G.load_config(p) == dict(url=G.DEFAULT_URL, model="")
    monkeypatch.setenv("OLLAMA_HOST", "0.0.0.0:11500")
    assert G.load_config(p)["url"] == "http://127.0.0.1:11500"
    G.save_config(p, "localhost", " qwen2.5:7b ")
    assert G.load_config(p) == dict(url="http://localhost:11434", model="qwen2.5:7b")
    with pytest.raises(G.ScriptError):
        G.save_config(p, "ftp://x", "m")


@pytest.fixture()
def client(tmp_path, monkeypatch, fake):
    monkeypatch.setattr(A, "PROJ", tmp_path / "projects")
    monkeypatch.setattr(A, "AI_CFG", tmp_path / "ai.json")
    monkeypatch.setattr(A, "JOBS", {})
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("FFV_OLLAMA_MODEL", raising=False)
    A.PROJ.mkdir()
    c = A.app.test_client()
    assert c.put("/api/ai/config", json=dict(url=fake.url, model="qwen2.5:7b")).status_code == 200
    return c


def wait_job(c, jid, timeout=15):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = c.get(f"/api/jobs/{jid}").get_json()
        if j["state"] != "running":
            return j
        time.sleep(0.05)
    raise AssertionError("job không xong")


def test_api_status_script_job_and_paste_text(client, fake):
    st = client.get("/api/ai/status").get_json()
    assert st["error"] is None and st["model"] == "qwen2.5:7b" and [m["name"] for m in st["models"]] == ["llama3.1:8b", "qwen2.5:7b"]
    fake.replies = [scenes_json(6)]
    r = client.post("/api/ai/script", json=dict(topic="Đom đóm là gì?", duration=60, tone="story", lang="vi", notes="cho học sinh"))
    assert r.status_code == 200
    j = wait_job(client, r.get_json()["job"])
    assert j["state"] == "done" and j["kind"] == "ai" and len(j["script"]["scenes"]) == 6 and j["text"].startswith("# Ý 1\n")
    user = fake.requests[0]["messages"][1]["content"]
    assert "kể chuyện" in user and "cho học sinh" in user


def test_api_status_probe_other_url_and_error(client):
    st = client.get("/api/ai/status?url=127.0.0.1:1").get_json()
    assert "Không kết nối" in st["error"] and st["models"] == []


def test_api_rejects_bad_requests_and_parallel_jobs(client, fake):
    assert client.post("/api/ai/script", json=dict(topic=" ")).status_code == 400
    assert client.put("/api/ai/config", json=dict(url="ftp://x")).status_code == 400
    fake.replies = [dict(content=scenes_json(6), delay=1.0)]
    first = client.post("/api/ai/script", json=dict(topic="đom đóm")).get_json()["job"]
    second = client.post("/api/ai/script", json=dict(topic="đom đóm 2"))
    assert second.status_code == 409
    assert wait_job(client, first)["state"] == "done"


def test_api_cancel_and_failure_surface_as_job_states(client, fake):
    fake.replies = [dict(content=scenes_json(6), delay=30)]
    jid = client.post("/api/ai/script", json=dict(topic="đom đóm")).get_json()["job"]
    time.sleep(0.4)
    client.post(f"/api/jobs/{jid}/cancel")
    assert wait_job(client, jid, 8)["state"] == "cancelled"
    fake.replies = ["rác"] * 3
    j = wait_job(client, client.post("/api/ai/script", json=dict(topic="đom đóm")).get_json()["job"])
    assert j["state"] == "error" and "3 lần" in j["error"]


def test_api_picks_first_installed_model_when_none_chosen(tmp_path, monkeypatch, fake):
    monkeypatch.setattr(A, "AI_CFG", tmp_path / "none.json")
    monkeypatch.setattr(A, "JOBS", {})
    monkeypatch.setenv("OLLAMA_HOST", fake.url)
    monkeypatch.delenv("FFV_OLLAMA_MODEL", raising=False)
    fake.replies = [scenes_json(6)]
    c = A.app.test_client()
    j = wait_job(c, c.post("/api/ai/script", json=dict(topic="đom đóm")).get_json()["job"])
    assert j["state"] == "done" and fake.requests[0]["model"] == "llama3.1:8b"
    fake.models = []
    assert "pull" in c.post("/api/ai/script", json=dict(topic="đom đóm")).get_json()["error"]


def test_doctor_reports_ollama_as_optional_never_an_error(fake, monkeypatch, tmp_path):
    res = D.run_checks()
    it = next(i for i in res["items"] if i["name"].startswith("Ollama"))
    assert it["level"] in ("ok", "warn") and it["ok"] is True
    monkeypatch.setenv("OLLAMA_HOST", fake.url)
    monkeypatch.setattr(D, "HERE", tmp_path)  # không có ai_settings.json -> dùng OLLAMA_HOST
    it = D.check_ollama()
    assert it["level"] == "ok" and "qwen2.5:7b" in it["detail"]
