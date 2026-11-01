"""Dùng chung cho các test: dự án mẫu cố định (không cần mạng, không cần giọng thật)."""
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

os.environ["FFV_FAKE_TTS"] = "1"  # giọng giả offline, có mốc từ chính xác tuyệt đối
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import render as R  # noqa: E402

NARR1 = "Đom đóm là loài côn trùng phát sáng. Chúng nhấp nháy để gọi bạn tình, vào những đêm hè ấm áp."
NARR2 = "Ánh sáng lạnh, gần như không toả nhiệt."


def make_images(media: Path):
    """Ảnh xác định (không ngẫu nhiên) để khung hình chuẩn luôn giống nhau."""
    media.mkdir(parents=True, exist_ok=True)
    for n, (c1, c2) in enumerate([((200, 120, 40), (40, 90, 200)), ((60, 160, 220), (200, 60, 120))]):
        w, h = (1400, 900) if n == 0 else (900, 1400)
        t = np.linspace(0, 1, w, dtype=np.float32)[None, :, None]
        im = (np.array(c1, np.float32) * (1 - t) + np.array(c2, np.float32) * t) * np.ones((h, 1, 1), np.float32)
        im = np.clip(im, 0, 255).astype(np.uint8)
        cv2.circle(im, (w // 2, h // 2), min(w, h) // 4, (255, 255, 255), 14)
        cv2.imwrite(str(media / f"i{n}.jpg"), im, [cv2.IMWRITE_JPEG_QUALITY, 95])


def make_project(aspect="9:16", quality=540, fps=30, **extra):
    th = dict(R.THEMES["dom-dom-vang"])
    proj = dict(name="t", aspect=aspect, quality=quality, fps=fps, theme=th, pron="", normalize_text=False,
                voice={"name": "vi-VN-HoaiMyNeural", "rate": 0, "pitch": 0}, schema_version=2,
                scenes=[
                    dict(id="a1", title="Đom đóm là gì?", subtitle="Một phút tìm hiểu", narration=NARR1, voice=True,
                         caption=True, images=[dict(file="i0.jpg", mode="card", anim="zoom")], transition="fade"),
                    dict(id="a2", title="", subtitle="", narration=NARR2, voice=True, caption=True,
                         images=[dict(file="i1.jpg", mode="cover", anim="pan")], transition="slide"),
                    dict(id="a3", title="Hết", subtitle="Cảm ơn đã xem", narration="", voice=False, caption=False,
                         duration=3, images=[], transition="none"),
                ])
    proj.update(extra)
    return proj


def add_fake_audio(root: Path, proj):
    import media as M
    for sc in proj["scenes"]:
        if R.needs_voice(sc):
            sc["audio"] = M.tts_scene(root, proj, sc)
    return proj


@pytest.fixture(scope="session")
def root(tmp_path_factory):
    r = tmp_path_factory.mktemp("proj")
    for s in ("media", "audio", "out"):
        (r / s).mkdir()
    make_images(r / "media")
    return r


@pytest.fixture()
def proj(root):
    return add_fake_audio(root, make_project())
