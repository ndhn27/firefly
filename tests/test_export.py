"""Xuất ổn định – resume theo đoạn, mức chất lượng, chọn encoder, ước lượng."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import media as M
from conftest import add_fake_audio, make_images, make_project


def probe(path):
    r = subprocess.run([M.ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True)
    return r.stderr.decode("utf-8", "ignore")


@pytest.fixture()
def small(tmp_path):
    root = tmp_path / "p"
    for s in ("media", "audio", "out"):
        (root / s).mkdir(parents=True)
    make_images(root / "media")
    proj = make_project("9:16", quality=360, fps=24)
    proj["scenes"] = proj["scenes"][1:]  # 2 cảnh ngắn để test nhanh
    return root, add_fake_audio(root, proj)


def test_export_ok_and_cache_cleaned(small):
    root, proj = small
    out = root / "out" / "a.mp4"
    info = M.run_export({}, proj, root, out, 360, 24, "standard", "cpu")
    txt = probe(out)
    assert "Video: h264" in txt and "Audio: aac" in txt and "360x640" in txt
    assert info["resumed"] == 0
    assert not any((root / "out" / ".cache").glob("*/seg_*")), "xuất xong phải dọn đoạn tạm"
    assert not list((root / "out").glob("tmp_*"))


def test_resume_reuses_finished_segments(small):
    root, proj = small
    out = root / "out" / "r.mp4"
    job = {"cancel": True}  # huỷ ngay sau khi xong đoạn đầu tiên
    with pytest.raises(M.Cancelled):
        M.run_export(job, proj, root, out, 360, 24, "standard", "cpu")
    segs = list((root / "out" / ".cache").glob("*/seg_*.h264"))
    assert segs and not list((root / "out" / ".cache").glob("*/*.part")), "đoạn đã xong phải được giữ lại, không còn file dở"
    info = M.run_export({}, proj, root, out, 360, 24, "standard", "cpu")
    assert info["resumed"] >= 1
    assert "Video: h264" in probe(out)
    # kết quả sau resume phải đúng thời lượng như xuất một lèo
    full = root / "out" / "full.mp4"
    shutil.rmtree(root / "out" / ".cache", ignore_errors=True)
    M.run_export({}, proj, root, full, 360, 24, "standard", "cpu")
    dur = lambda p: [l for l in probe(p).splitlines() if "Duration" in l][0].split(",")[0]
    assert dur(out) == dur(full)


def test_changed_project_does_not_reuse_old_segments(small):
    root, proj = small
    with pytest.raises(M.Cancelled):
        M.run_export({"cancel": True}, proj, root, root / "out" / "x.mp4", 360, 24, "standard", "cpu")
    proj["theme"]["c1"] = (10, 200, 255)  # đổi màu -> khung hình khác -> không được dùng lại đoạn cũ
    info = M.run_export({}, proj, root, root / "out" / "y.mp4", 360, 24, "standard", "cpu")
    assert info["resumed"] == 0


def test_export_key_ignores_audio_only_and_name_changes(small):
    root, proj = small
    k = lambda p: M.export_key(p, 360, 640, 24, "libx264", ["x"])
    base = k(proj)
    p2 = json.loads(json.dumps(proj))
    p2["name"], p2["bgm"] = "đổi tên", {"file": "nhac.mp3", "volume": 0.3}
    assert k(p2) == base  # tên và nhạc nền không làm đổi hình ảnh
    p2["scenes"][0]["title"] = "Tiêu đề khác"
    assert k(p2) != base


def test_tiers_change_quality_and_size(small):
    root, proj = small
    crf = lambda tier: M.enc_args("libx264", 30, tier)[M.enc_args("libx264", 30, tier).index("-crf") + 1]
    assert int(crf("draft")) > int(crf("standard")) > int(crf("high"))
    sizes = {}
    for tier in ("draft", "high"):
        out = root / "out" / f"{tier}.mp4"
        M.run_export({}, proj, root, out, 360, 24, tier, "cpu")
        sizes[tier] = out.stat().st_size
    assert sizes["high"] > sizes["draft"]


def test_encoder_selection():
    assert M.pick_encoder("cpu") == "libx264"
    assert M.pick_encoder("khong-co") == "libx264"
    assert M.pick_encoder("auto") in ("libx264", "h264_nvenc", "h264_qsv", "h264_amf")
    for enc, flag in (("h264_nvenc", "-cq"), ("h264_qsv", "-global_quality"), ("h264_amf", "-qp_i")):
        for tier in M.QUALITY:
            assert flag in M.enc_args(enc, 60, tier)
    assert "-colorspace" in M.enc_args("libx264", 60, "standard")  # luôn gắn tag bt709


def test_estimate_export(small):
    root, proj = small
    job = {}
    e = M.estimate_export(job, proj, root, 360, 24, "standard", "cpu")
    assert e["W"] == 360 and e["H"] == 640 and e["frames"] > 24
    assert e["seconds"] >= 5 and e["mb"] > 0 and e["render_ms"] > 0 and e["enc_ms"] > 0
    # ước tính phải cùng bậc với thực tế (không đòi chính xác; máy test có thể bận)
    real = M.run_export({}, proj, root, root / "out" / "e.mp4", 360, 24, "standard", "cpu")["seconds"]
    actual_mb = (root / "out" / "e.mp4").stat().st_size / 1e6
    assert 0.2 * actual_mb <= e["mb"] <= 5 * actual_mb, (e["mb"], actual_mb)
    assert 0.1 * real <= e["seconds"] <= 10 * real + 10, (e["seconds"], real)
