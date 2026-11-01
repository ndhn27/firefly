"""Phía server: bảng vùng an toàn cho preview, dọn file không dùng, và giữ lại giọng đã tạo để hoàn tác không mất giọng."""
import json
import os
import time

import pytest

import app as A
import render as R


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "PROJ", tmp_path)
    return A.app.test_client()


def new_project(client, scenes, **extra):
    r = client.post("/api/projects", json={"name": "E5"}).get_json()
    pid, p = r["id"], r["project"]
    p["scenes"] = scenes
    p.update(extra)
    client.put(f"/api/projects/{pid}", json=p)
    return pid, p


def scene(sid, narr="", images=(), **kw):
    return dict(id=sid, title="", subtitle="", narration=narr, voice=bool(narr), caption=True,
                images=[dict(file=f, mode="card", anim="zoom") for f in images], transition="fade", **kw)


def put_file(client, pid, kind, name, size=100, age=3600):
    f = A.PROJ / pid / kind / name
    f.write_bytes(b"x" * size)
    t = time.time() - age
    os.utime(f, (t, t))
    return f


def tts(client, pid, sid):
    r = client.post(f"/api/projects/{pid}/tts", json={"scene": sid})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["audio"]


def project(client, pid):
    return client.get(f"/api/projects/{pid}").get_json()["project"]


# ----------------------------------------------------------------------------- vùng an toàn
def test_safe_endpoint_is_the_renderers_table(client):
    got = client.get("/api/safe").get_json()
    assert got == json.loads(json.dumps(R.SAFE))
    assert set(got) == set(R.ASPECTS)


@pytest.mark.parametrize("aspect", sorted(R.ASPECTS))
@pytest.mark.parametrize("quality", [720, 1080, 1440])
def test_safe_zone_matches_what_the_renderer_uses(aspect, quality):
    """Preview tra bảng theo khung của dự án; renderer tra theo kích thước ảnh thật. Hai đường phải ra cùng một số."""
    W, H = R.frame_size(aspect, quality)
    assert R.safe_for(W, H) == R.SAFE[aspect]


@pytest.mark.parametrize("aspect", sorted(R.ASPECTS))
def test_safe_zone_numbers_are_sane_for_the_overlay(aspect):
    z = R.SAFE[aspect]
    assert 0 < z["mx"] < 0.25 and 0 <= z["top"] < z["cap"] <= z["bottom"] <= 1


# ----------------------------------------------------------------------------- dọn file không dùng
def setup_cleanup(client):
    pid, p = new_project(client, [scene("s1", "Xin chào các bạn.", ["used1.png"]), scene("s2", "", ["used2.jpg"], duration=3)],
                         bgm={"file": "music.mp3", "volume": 0.1}, logo={"file": "logo.png", "pos": "tr", "size": 0.14, "opacity": 0.9})
    for n in ("used1.png", "used2.jpg", "music.mp3", "logo.png", "old.png", "old2.jpg"):
        put_file(client, pid, "media", n, size=1000 if n.startswith("old") else 10)
    a = tts(client, pid, "s1")
    put_file(client, pid, "audio", "s9_deadbeef00.wav", size=500)
    put_file(client, pid, "audio", "s9_deadbeef00.wav.json", size=20)
    return pid, a


def test_unused_lists_only_orphans(client):
    pid, a = setup_cleanup(client)
    r = client.get(f"/api/projects/{pid}/unused").get_json()
    names = {(i["kind"], i["name"]) for i in r["items"]}
    assert names == {("media", "old.png"), ("media", "old2.jpg"), ("audio", "s9_deadbeef00.wav"), ("audio", "s9_deadbeef00.wav.json")}
    assert r["bytes"] == 1000 + 1000 + 500 + 20 and r["recent"] == 0
    assert ("audio", a["file"]) not in names and ("audio", a["file"] + ".json") not in names, "giọng đang dùng và file mô tả của nó phải được giữ"


def test_recent_files_are_kept_and_reported(client):
    pid, _ = setup_cleanup(client)
    put_file(client, pid, "media", "just-uploaded.png", age=2)
    r = client.get(f"/api/projects/{pid}/unused").get_json()
    assert "just-uploaded.png" not in {i["name"] for i in r["items"]} and r["recent"] == 1
    client.post(f"/api/projects/{pid}/cleanup", json={})
    assert (A.PROJ / pid / "media" / "just-uploaded.png").exists()


def test_cleanup_deletes_orphans_and_nothing_else(client):
    pid, a = setup_cleanup(client)
    d = A.PROJ / pid
    r = client.post(f"/api/projects/{pid}/cleanup", json={}).get_json()
    assert r == dict(deleted=4, bytes=2520, failed=0)
    left = {p.name for p in (d / "media").iterdir()} | {p.name for p in (d / "audio").iterdir()}
    assert left == {"used1.png", "used2.jpg", "music.mp3", "logo.png", a["file"], a["file"] + ".json"}
    assert (d / "project.json").exists() and (d / "out").is_dir()
    assert client.get(f"/api/projects/{pid}/unused").get_json()["items"] == []
    assert project(client, pid)["scenes"][0]["audio"]["file"] == a["file"]


def test_cleanup_only_removes_what_the_user_saw_and_never_a_used_or_outside_file(client):
    pid, a = setup_cleanup(client)
    d = A.PROJ / pid
    want = ["media/old.png", "media/used1.png", "audio/" + a["file"], "../project.json", "media/../project.json",
            "project.json", "out", "media/nope.png"]
    r = client.post(f"/api/projects/{pid}/cleanup", json={"files": want}).get_json()
    assert r["deleted"] == 1 and r["bytes"] == 1000
    assert not (d / "media" / "old.png").exists() and (d / "media" / "old2.jpg").exists()
    assert (d / "media" / "used1.png").exists() and (d / "audio" / a["file"]).exists() and (d / "project.json").exists()


def test_cleanup_refused_while_a_job_is_running(client, monkeypatch):
    pid, _ = setup_cleanup(client)
    monkeypatch.setitem(A.JOBS, "busy", dict(state="running"))
    r = client.post(f"/api/projects/{pid}/cleanup", json={})
    assert r.status_code == 409 and (A.PROJ / pid / "media" / "old.png").exists()


def test_cleanup_unknown_project_is_404(client):
    assert client.get("/api/projects/khong-co-1234/unused").status_code == 404
    assert client.post("/api/projects/khong-co-1234/cleanup", json={}).status_code == 404


def test_used_files_counts_every_reference():
    p = A.normalize(dict(scenes=[scene("a", "x", ["i1.png", "i2.png"]), scene("b", "", ["i1.png"])],
                         bgm={"file": "m.mp3"}, logo={"file": "l.png"}))
    p["scenes"][0]["audio"] = {"file": "a_1.wav"}
    assert A.used_files(p) == ({"i1.png", "i2.png", "m.mp3", "l.png"}, {"a_1.wav"})
    assert A.used_files(A.normalize({})) == (set(), set())


# ----------------------------------------------------------------------------- giữ giọng khi hoàn tác
def test_put_returns_audio_map(client):
    pid, _ = new_project(client, [scene("s1", "Xin chào.")])
    a = tts(client, pid, "s1")
    p = project(client, pid)
    r = client.put(f"/api/projects/{pid}", json=p).get_json()
    assert r["audio"]["s1"]["file"] == a["file"] and "tl" in r


def test_voice_comes_back_after_scene_is_deleted_and_restored(client):
    pid, p = new_project(client, [scene("s1", "Xin chào các bạn."), scene("s2", "Cảnh hai.")])
    a1 = tts(client, pid, "s1")
    tts(client, pid, "s2")
    keep = project(client, pid)
    s1 = dict(keep["scenes"][0], audio=None)  # trình duyệt không gửi giọng
    client.put(f"/api/projects/{pid}", json=dict(keep, scenes=[keep["scenes"][1]]))  # xoá cảnh 1
    assert [s["id"] for s in project(client, pid)["scenes"]] == ["s2"]
    r = client.put(f"/api/projects/{pid}", json=dict(keep, scenes=[s1, keep["scenes"][1]])).get_json()  # hoàn tác
    assert r["audio"]["s1"] == a1
    assert R.scene_audio(project(client, pid), project(client, pid)["scenes"][0]) is not None
    assert not r["tl"]["scenes"][0]["estimated"], "thời lượng phải lấy từ giọng thật, không phải ước lượng"


def test_voice_comes_back_after_regenerate_then_revert_text(client):
    pid, _ = new_project(client, [scene("s1", "Lời đọc gốc.")])
    a1 = tts(client, pid, "s1")
    p = project(client, pid)
    p["scenes"][0]["narration"] = "Lời đọc đã sửa, dài hơn một chút."
    client.put(f"/api/projects/{pid}", json=p)
    now = project(client, pid)
    assert R.scene_audio(now, now["scenes"][0]) is None, "sửa lời đọc thì giọng cũ không còn khớp"
    a2 = tts(client, pid, "s1")
    assert a2["file"] != a1["file"]
    p = project(client, pid)
    p["scenes"][0]["narration"] = "Lời đọc gốc."
    r = client.put(f"/api/projects/{pid}", json=p).get_json()
    assert r["audio"]["s1"]["file"] == a1["file"], "hoàn tác phải lấy lại giọng cũ từ file mô tả, không bắt tạo lại"


def test_stale_voice_is_kept_when_nothing_matches_and_never_taken_from_the_browser(client):
    pid, _ = new_project(client, [scene("s1", "Xin chào.")])
    a1 = tts(client, pid, "s1")
    p = project(client, pid)
    p["scenes"][0]["narration"] = "Khác hẳn."
    r = client.put(f"/api/projects/{pid}", json=p).get_json()
    assert r["audio"]["s1"]["file"] == a1["file"]  # giữ như trước (đã lỗi thời), không mất nếu người dùng sửa lại chữ
    forged = scene("zz", "Xin chào.", audio=a1)  # cảnh mới tự xưng có giọng của cảnh khác
    r = client.put(f"/api/projects/{pid}", json=dict(p, scenes=[forged])).get_json()
    assert r["audio"]["zz"] is None


def test_recover_audio_rejects_tampered_or_missing_files(client, tmp_path):
    pid, _ = new_project(client, [scene("s1", "Xin chào.")])
    a1 = tts(client, pid, "s1")
    d = A.PROJ / pid
    proj = project(client, pid)
    sc = proj["scenes"][0]
    assert A.recover_audio(d, proj, sc)["file"] == a1["file"]
    side = d / "audio" / (a1["file"] + ".json")
    side.write_text(json.dumps(dict(a1, file="../project.json")), "utf-8")
    assert A.recover_audio(d, proj, sc) is None, "tên file trong file mô tả phải khớp đúng tên suy ra từ id + hash"
    side.write_text("{ hỏng", "utf-8")
    assert A.recover_audio(d, proj, sc) is None
    side.write_text(json.dumps(a1), "utf-8")
    (d / "audio" / a1["file"]).unlink()
    assert A.recover_audio(d, proj, sc) is None, "file giọng đã bị xoá thì không còn gì để khôi phục"
    assert A.recover_audio(d, proj, scene("s1", "")) is None, "cảnh không cần giọng thì khỏi tìm"
