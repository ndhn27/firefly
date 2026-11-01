"""Âm lượng + hình ảnh: chuẩn hoá LUFS, nền mờ cho ảnh lệch tỉ lệ, bố cục chia đôi, logo,
nền bokeh / tia sáng, vùng an toàn theo tỉ lệ khung."""
import copy
import json
import os

import cv2
import numpy as np
import pytest

import app as A
import media as M
import render as R
from conftest import add_fake_audio, make_project
from test_golden import GOLD, MEAN_TOL, P99_TOL, diff

ASPECTS = ["16:9", "9:16", "1:1", "4:5"]


def ctx_for(root, proj, aspect="9:16", short=270):
    W, H = R.frame_size(aspect, short)
    return R.Ctx(proj, root, W, H)


def sample(root, aspect="9:16", **extra):
    return add_fake_audio(root, make_project(aspect, **extra))


# ============================================================================ âm lượng
def _mix(root, proj, **an):
    p = copy.deepcopy(proj)
    p["audio_norm"] = an
    out = root / "out" / f"mix_{abs(hash(json.dumps(an, sort_keys=True)))}.wav"
    info = {}
    assert M.build_audio(p, root, R.timeline(p), out, info)
    return out, info


@pytest.mark.parametrize("target", [-14, -16])
def test_loudness_hits_target(root, proj, target):
    out, info = _mix(root, proj, mode="lufs", target=target)
    m = M.measure_loudness(out)
    assert abs(m["I"] - target) <= 0.5, m
    assert m["TP"] <= -1.0, m
    assert abs(info["loudness"]["after"] - m["I"]) < 0.2


def test_loudness_off_only_limits_peak(root, proj):
    out, info = _mix(root, proj, mode="off")
    assert np.abs(M.read_wav(out)).max() <= 0.971
    assert info["loudness"]["target"] is None


def test_loudness_with_bgm(root, proj):
    sr = M.SR
    x = (0.3 * np.sin(2 * np.pi * 220 * np.arange(sr * 5) / sr)).astype(np.float32)
    M.write_wav(root / "media" / "bgm_t.wav", np.stack([x, x], 1))
    p = copy.deepcopy(proj)
    p["bgm"] = {"file": "bgm_t.wav", "volume": 0.2}
    out, _ = _mix(root, p, mode="lufs", target=-14)
    assert abs(M.measure_loudness(out)["I"] + 14) <= 0.5


def _wav(tmp_path, name, x):
    p = tmp_path / name
    M.write_wav(p, np.stack([x, x], 1).astype(np.float32))
    return p


def test_limiter_keeps_peaks_under_ceiling(tmp_path):
    """Tín hiệu nhỏ nhưng có đỉnh nhọn: tăng tới -14 LUFS thì đỉnh vượt trần -> bộ chặn đỉnh phải giữ ở LIMIT_TP."""
    n = M.SR * 8
    t = np.arange(n) / M.SR
    x = 0.03 * np.sin(2 * np.pi * 200 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))
    for k in range(0, n, M.SR // 2):
        x[k:k + 20] = 0.85 * np.hanning(20)
    src, dst = _wav(tmp_path, "s.wav", x), tmp_path / "d.wav"
    res = M.normalize_loudness(src, dst, -14)
    m = M.measure_loudness(dst)
    assert abs(m["I"] + 14) <= 0.5 and m["TP"] <= M.LIMIT_TP + 0.2, (res, m)


def test_silence_is_left_alone(tmp_path):
    src, dst = _wav(tmp_path, "z.wav", np.zeros(M.SR * 2)), tmp_path / "o.wav"
    assert M.normalize_loudness(src, dst, -14) is None
    assert dst.exists() and np.abs(M.read_wav(dst)).max() == 0


def test_audio_norm_does_not_invalidate_cached_video_chunks(proj):
    key = lambda p: M.export_key(p, 540, 960, 30, "libx264", [])  # noqa: E731
    assert key(proj) == key(dict(proj, audio_norm={"mode": "off", "target": -14}))
    assert key(proj) != key(dict(proj, logo={"file": "x.png", "pos": "tr", "size": 0.14, "opacity": 0.9}))


def test_normalize_sanitizes_new_settings():
    p = A.normalize({"audio_norm": {"mode": "x", "target": -3},
                     "logo": {"pos": "zz", "size": 9, "opacity": "abc"},
                     "scenes": [{"layout": "wat", "image_side": 5, "images": [{"file": "a.png", "mode": "??", "anim": "??"}]}]})
    assert p["audio_norm"] == {"mode": "lufs", "target": -14}
    assert p["logo"]["pos"] == "tr" and p["logo"]["size"] == 0.4 and p["logo"]["opacity"] == 0.9
    sc = p["scenes"][0]
    assert (sc["layout"], sc["image_side"]) == ("stack", "right")
    assert (sc["images"][0]["mode"], sc["images"][0]["anim"]) == ("card", "zoom")
    d = A.normalize({})
    assert d["audio_norm"] == {"mode": "lufs", "target": -14} and d["logo"]["file"] is None


# ============================================================================ ảnh lệch tỉ lệ -> nền mờ
def test_cover_falls_back_to_blur_fit_when_crop_is_heavy(root):
    c = ctx_for(root, sample(root, "16:9"), "16:9")  # ảnh dọc 900x1400 làm 'cover' trên khung ngang: phải cắt gần 64%
    imgs = c.view(1).imgs
    assert [d["mode"] for d in imgs] == ["cover", "card"]
    cw, ch = imgs[1]["out"]
    assert abs(cw / ch - 900 / 1400) < 0.02, "ảnh 'fit' phải giữ nguyên tỉ lệ, không bị cắt"
    c2 = ctx_for(root, sample(root, "9:16"), "9:16")  # gần đúng tỉ lệ khung dọc: vẫn phủ kín
    assert [d["mode"] for d in c2.view(1).imgs] == ["cover"]


def test_blur_backdrop_is_darker_and_smoother_than_image(root):
    img = cv2.imread(str(root / "media" / "i1.jpg"))
    bd = R.blurred_backdrop(img, 480, 270)
    ref = cv2.resize(img, (bd.shape[1], bd.shape[0]))
    lap = lambda a: cv2.Laplacian(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()  # noqa: E731
    assert bd.shape[1] >= 480 and bd.shape[0] >= 270
    assert bd.mean() < ref.mean() * 0.6
    assert lap(bd) < lap(ref) * 0.2


# ============================================================================ bố cục chia đôi
def _split_ctx(root, aspect, side):
    p = sample(root, aspect)
    p["scenes"][0].update(layout="split", image_side=side)
    return ctx_for(root, p, aspect)


@pytest.mark.parametrize("aspect", ["16:9", "1:1"])
def test_split_columns_do_not_overlap(root, aspect):
    for side in ("right", "left"):
        c = _split_ctx(root, aspect, side)
        v = c.view(0)
        card = next(d for d in v.imgs if d["mode"] == "card")
        pad = 40 * c.k  # sprite chữ có vùng đệm trong suốt cho glow
        t0, t1 = v.title_cx - v.title.shape[1] / 2, v.title_cx + v.title.shape[1] / 2
        c0, c1 = card["cx"] - card["out"][0] / 2, card["cx"] + card["out"][0] / 2
        assert (v.title_cx < c.W / 2) == (side == "right")
        assert (t1 - pad <= c0) if side == "right" else (c1 <= t0 + pad), (side, t0, t1, c0, c1)
        assert t0 >= 0 and t1 <= c.W and c0 >= 0 and c1 <= c.W


@pytest.mark.parametrize("aspect", ["9:16", "4:5"])
def test_split_portrait_puts_image_above_text(root, aspect):
    c = _split_ctx(root, aspect, "right")
    v = c.view(0)
    card = next(d for d in v.imgs if d["mode"] == "card")
    assert card["y"] + card["out"][1] <= v.title_y + 45 * c.k
    assert abs(card["cx"] - c.W / 2) < 1 and v.title_cx == c.W / 2


# ============================================================================ logo
def _logo_png(root, name="logo_t.png"):
    a = np.zeros((100, 200, 4), np.uint8)
    a[..., 2] = 255  # đỏ (BGR)
    a[..., 3] = 255
    cv2.imwrite(str(root / "media" / name), a)
    return name


@pytest.mark.parametrize("pos", ["tl", "tr", "bl", "br"])
def test_logo_appears_in_chosen_corner(root, pos):
    name = _logo_png(root)
    base = sample(root, "16:9")
    W, H = R.frame_size("16:9", 270)
    f0 = R.Ctx(base, root, W, H).render(1.6)
    f1 = R.Ctx(dict(base, logo=dict(file=name, pos=pos, size=0.2, opacity=1.0)), root, W, H).render(1.6)
    d = np.abs(f1.astype(int) - f0.astype(int)).sum(axis=2) > 30
    ys, xs = np.nonzero(d)
    assert len(xs) > 50
    assert (xs.mean() < W / 2) == (pos[1] == "l") and (ys.mean() < H / 2) == (pos[0] == "t")
    assert f1[d][:, 2].mean() > 200 and f1[d][:, 0].mean() < 60, "logo phải đúng màu gốc (đỏ), không bị đảo kênh"


def test_missing_logo_file_is_ignored(root):
    base = sample(root, "9:16")
    W, H = R.frame_size("9:16", 270)
    a = R.Ctx(base, root, W, H).render(1.6)
    b = R.Ctx(dict(base, logo=dict(file="khong_co.png", pos="tr", size=0.14, opacity=0.9)), root, W, H).render(1.6)
    assert np.array_equal(a, b)


# ============================================================================ nền bokeh / tia sáng
@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("name", ["bokeh-am", "tia-sang"])
def test_new_styles_render_at_every_aspect(root, aspect, name):
    W, H = R.frame_size(aspect, 270)
    base = sample(root, aspect)
    f = R.Ctx(dict(base, theme=dict(R.THEMES[name])), root, W, H).render(1.6)
    ref = R.Ctx(base, root, W, H).render(1.6)
    assert f.shape == (H, W, 3) and f.dtype == np.uint8
    assert diff(f, ref)[0] > 3, "kiểu nền mới phải khác nền đom đóm"


def test_rays_come_from_top_left():
    W, H = 480, 270
    on = dict(R.THEMES["tia-sang"])
    a = R.Background(on, W, H).frame(5.0).astype(int)
    b = R.Background(dict(on, rays=0.0), W, H).frame(5.0).astype(int)
    d = (a - b).sum(axis=2)
    tl, br = d[:H // 2, :W // 2].mean(), d[H // 2:, W // 2:].mean()
    assert tl > 2 and tl > 2 * br


def test_bokeh_discs_are_much_bigger_than_fireflies():
    W, H = 480, 270
    big = R.Fireflies(R.THEMES["bokeh-am"], W, H).r.mean()
    small = R.Fireflies(R.THEMES["dom-dom-vang"], W, H).r.mean()
    assert big > 3 * small


# ============================================================================ vùng an toàn
def test_safe_for_picks_nearest_aspect():
    for a in ASPECTS:
        assert R.safe_for(*R.frame_size(a, 1080)) is R.SAFE[a]


@pytest.mark.parametrize("aspect", ASPECTS)
def test_content_stays_inside_safe_zone(root, aspect):
    c = ctx_for(root, sample(root, aspect), aspect)
    sz = R.SAFE[aspect]
    assert c.safe is sz
    v = c.view(0)
    card = next(d for d in v.imgs if d["mode"] == "card")
    assert v.cap_bottom <= c.H * sz["bottom"] + 1
    assert v.title_y >= c.H * sz["top"] - 1 and card["y"] >= c.H * sz["top"]
    assert card["y"] + card["out"][1] <= v.cap_bottom
    assert card["cx"] - card["out"][0] / 2 >= c.W * sz["mx"] - 1
    assert card["cx"] + card["out"][0] / 2 <= c.W * (1 - sz["mx"]) + 1


# ============================================================================ golden cho các khung mới
def _mut_split(p):
    p["scenes"][0].update(layout="split", image_side="right")


E4_GOLD = [
    ("e4_split_wide", "16:9", _mut_split),
    ("e4_split_portrait", "9:16", _mut_split),
    ("e4_fit", "9:16", lambda p: p["scenes"][0]["images"][0].update(mode="fit")),
    ("e4_bokeh", "16:9", lambda p: p.update(theme=dict(R.THEMES["bokeh-am"]))),
    ("e4_rays", "16:9", lambda p: p.update(theme=dict(R.THEMES["tia-sang"]))),
]


@pytest.mark.parametrize("name,aspect,mutate", E4_GOLD, ids=[g[0] for g in E4_GOLD])
def test_e4_golden(root, name, aspect, mutate):
    p = sample(root, aspect)
    mutate(p)
    frame = ctx_for(root, p, aspect).render(1.6)
    path = GOLD / f"{name}.png"
    if os.environ.get("UPDATE_GOLDEN"):
        cv2.imwrite(str(path), frame)
        return
    assert path.exists(), f"Chưa có ảnh chuẩn {path.name}. Chạy với UPDATE_GOLDEN=1 để tạo."
    mean, p99 = diff(frame, cv2.imread(str(path)))
    assert mean <= MEAN_TOL and p99 <= P99_TOL, f"{path.name} lệch: mean={mean:.2f} p99={p99:.1f}"
