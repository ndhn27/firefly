"""Golden-frame: khung hình dựng ra phải khớp ảnh chuẩn ở cả 4 tỉ lệ khung.
Cố ý đổi giao diện/hiệu ứng thì cập nhật ảnh chuẩn:  UPDATE_GOLDEN=1 python -m pytest tests/test_golden.py
rồi xem lại các ảnh trong tests/golden/ trước khi commit. Ảnh chuẩn được dựng với bộ dàn chữ BASIC (xem conftest.pinned_layout)."""
import os
from pathlib import Path

import cv2
import numpy as np
import pytest

import render as R
from conftest import add_fake_audio, make_project

pytestmark = pytest.mark.usefixtures("pinned_layout")  # cả file: bố cục chữ phải giống nhau ở mọi máy (xem conftest.pinned_layout)
GOLD = Path(__file__).parent / "golden"
ASPECTS = ["16:9", "9:16", "1:1", "4:5"]
# (nhãn, hàm tính thời điểm từ timeline): cảnh 1 (thẻ ảnh + tiêu đề + phụ đề), giữa lúc chuyển cảnh 1->2, cảnh 2 (ảnh phủ kín)
TIMES = [("s1", lambda tl: 1.6),
         ("trans", lambda tl: tl["scenes"][1]["start"] + tl["scenes"][0]["T"] * 0.5),
         ("s2", lambda tl: tl["scenes"][1]["start"] + 1.8)]
MEAN_TOL, P99_TOL = 1.5, 40  # chênh lệch trung bình / phân vị 99 (thang 0-255); đủ rộng cho nhiễu số học nhỏ giữa các máy (bộ dàn chữ đã ghim, nên không còn lệch kerning)


def render(root, aspect, t, **extra):
    proj = add_fake_audio(root, make_project(aspect, **extra))
    W, H = R.frame_size(aspect, 270)
    return R.Ctx(proj, root, W, H).render(t)


def diff(a, b):
    if a.shape != b.shape:
        return 255.0, 255.0
    d = np.abs(a.astype(np.int16) - b.astype(np.int16))
    return float(d.mean()), float(np.percentile(d, 99))


@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("label,when", TIMES)
def test_golden_frame(root, aspect, label, when):
    name = GOLD / f"{aspect.replace(':', 'x')}_{label}.png"
    proj = add_fake_audio(root, make_project(aspect))
    W, H = R.frame_size(aspect, 270)
    ctx = R.Ctx(proj, root, W, H)
    frame = ctx.render(when(ctx.tl))
    if os.environ.get("UPDATE_GOLDEN"):
        GOLD.mkdir(exist_ok=True)
        cv2.imwrite(str(name), frame)
        return
    assert name.exists(), f"Chưa có ảnh chuẩn {name.name}. Chạy với UPDATE_GOLDEN=1 để tạo."
    mean, p99 = diff(frame, cv2.imread(str(name)))
    assert mean <= MEAN_TOL and p99 <= P99_TOL, f"{name.name} lệch: mean={mean:.2f} p99={p99:.1f}"


def test_golden_catches_changes(root):
    """Kiểm tra chính bộ test: đổi màu ánh sáng của theme thì phải bị báo lệch."""
    base = render(root, "9:16", 1.6)
    th = dict(R.THEMES["dom-dom-vang"], c1=(60, 120, 255), c2=(255, 60, 120))
    changed = render(root, "9:16", 1.6, theme=th)
    mean, p99 = diff(base, changed)
    assert mean > MEAN_TOL or p99 > P99_TOL


def test_frame_sizes_even_and_bounded():
    for a in ASPECTS:
        for q in (720, 1080, 1440):
            W, H = R.frame_size(a, q)
            assert W % 2 == 0 and H % 2 == 0 and max(W, H) <= 2560
