"""schema_version + migrate, giá trị ngoài giới hạn bị chặn, API cơ bản, doctor."""
import json

import pytest

import app as A
import doctor as D


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "PROJ", tmp_path)
    return A.app.test_client()


def test_new_project_is_current_schema_with_text_normalization(client):
    r = client.post("/api/projects", json={"name": "Thử", "aspect": "16:9", "quality": 1440, "fps": 60}).get_json()
    p = r["project"]
    assert p["schema_version"] == A.SCHEMA_VERSION
    assert p["normalize_text"] is True and p["caption_hl"] is False and p["export_tier"] == "standard"
    saved = json.loads((A.PROJ / r["id"] / "project.json").read_text("utf-8"))
    assert saved["schema_version"] == A.SCHEMA_VERSION  # load/save không làm mất dữ liệu


def test_old_project_migrates_without_changing_voice(client):
    old = {"name": "Cũ", "aspect": "9:16", "quality": 1080, "fps": 30, "scenes": [
        {"id": "s1", "narration": "Tăng 15%", "voice": True, "images": []}]}
    (A.PROJ / "cu-1234").mkdir()
    (A.PROJ / "cu-1234" / "project.json").write_text(json.dumps(old), "utf-8")
    p = client.get("/api/projects/cu-1234").get_json()["project"]
    assert p["schema_version"] == 2
    assert p["normalize_text"] is False, "dự án cũ giữ cách đọc cũ để không phải tạo lại giọng"


def test_out_of_range_values_are_clamped():
    p = A.normalize({"aspect": "21:9", "quality": 5000, "fps": 144, "encoder": "xyz", "export_tier": "ultra"})
    assert p["aspect"] == "9:16" and p["quality"] == 1440 and p["fps"] == 60
    assert p["encoder"] == "auto" and p["export_tier"] == "standard"
    q = A.normalize({"quality": "abc", "fps": None})
    assert q["quality"] == 1080 and q["fps"] == 30
    assert A.normalize({"quality": 700, "fps": 25})["quality"] == 720


def test_put_keeps_server_managed_audio(client):
    r = client.post("/api/projects", json={"name": "A"}).get_json()
    pid, p = r["id"], r["project"]
    p["scenes"] = [{"id": "s1", "narration": "xin chào", "voice": True, "images": []}]
    client.put(f"/api/projects/{pid}", json=p)
    client.put(f"/api/projects/{pid}", json=dict(p, scenes=[dict(p["scenes"][0], audio={"hack": 1})]))
    got = client.get(f"/api/projects/{pid}").get_json()["project"]
    assert not got["scenes"][0].get("audio")


def test_doctor_report_shape():
    res = D.run_checks()
    assert isinstance(res["ok"], bool) and res["items"]
    names = [i["name"] for i in res["items"]]
    assert "FFmpeg" in names and any("libx264" in n for n in names)
    assert all(i["level"] in ("ok", "warn", "error") for i in res["items"])
