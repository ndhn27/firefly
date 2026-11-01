"""Phụ đề bám mốc từ của TTS; chuẩn hoá văn bản; tô sáng từ đang đọc."""
import numpy as np

import media as M
import render as R
from conftest import NARR1, add_fake_audio, make_project


def ev(*words, step=0.3):
    return [(w, i * step, i * step + step * 0.8) for i, w in enumerate(words)]


# ---------------------------------------------------------------- align_tokens
def test_align_exact_match():
    t = R.align_tokens("Xin chào, các bạn!".split(), ev("Xin", "chào", "các", "bạn"))
    assert [round(a, 2) for a, _ in t] == [0.0, 0.3, 0.6, 0.9]


def test_align_pronunciation_dictionary_spreads_over_both_spoken_words():
    # chữ hiển thị "GitHub" (1 từ), giọng đọc "Ghít hấp" (2 từ)
    t = R.align_tokens("Dùng GitHub nhé".split(), ev("Dùng", "Ghít", "hấp", "nhé"))
    assert t[1][0] == 0.3 and abs(t[1][1] - (0.6 + 0.24)) < 1e-6
    assert t[2][0] >= t[1][1] - 1e-6  # "nhé" đứng sau


def test_align_number_expanded_to_words():
    t = R.align_tokens("Tăng 15% rồi".split(), ev("Tăng", "15", "phần", "trăm", "rồi"))
    assert t[1][0] == 0.3  # "15%" khớp với từ đọc "15"
    assert t[2][0] > t[1][0]  # "rồi" vẫn đứng sau "15%"; "phần trăm" (không có trong chữ hiển thị) bị bỏ qua


def test_align_lone_dash_is_interpolated_and_monotonic():
    t = R.align_tokens("Một — hai".split(), ev("Một", "hai"))
    starts = [a for a, _ in t]
    assert starts == sorted(starts) and len(t) == 3


def test_align_none_without_events():
    assert R.align_tokens(["a"], []) is None


# ---------------------------------------------------------------- phrases
def test_phrase_token_counts_cover_all_words():
    for text in (NARR1, "Một, hai; ba ... bốn. Năm — sáu!", "Dài " * 40 + "hết."):
        pt = R.split_phrases_tok(text, 24)
        assert sum(n for _, n in pt) == len(text.split())
        assert all(p.strip() and not p.endswith((".", ",")) for p, _ in pt)


# ---------------------------------------------------------------- chuẩn hoá tiếng Việt
def test_normalize_vi():
    n = R.normalize_vi
    assert n("Tăng 15% so với năm trước") == "Tăng 15 phần trăm so với năm trước"
    assert n("Ngày 12/10/2026 là sinh nhật") == "Ngày 12 tháng 10 năm 2026 là sinh nhật"  # không đọc "ngày ngày"
    assert n("Sinh ngày 3/4 năm nay") == "Sinh ngày 3 tháng 4 năm nay"
    assert n("Họp 05-11-2026") == "Họp ngày 5 tháng 11 năm 2026"
    assert n("Giá 1.500.000 VNĐ") == "Giá 1500000 đồng"
    assert n("Chạy 5km, nặng 70kg") == "Chạy 5 ki-lô-mét, nặng 70 ki-lô-gam"
    assert n("Nhiệt độ 36°C") == "Nhiệt độ 36 độ xê"
    assert n("Python 3.11") == "Python 3.11"  # không phải dấu phân cách hàng nghìn
    assert n("99/99/2026") == "99/99/2026"  # ngày/tháng vô lý thì giữ nguyên


def test_normalize_text_off_keeps_old_audio_hash():
    sc = {"narration": "Tăng 15%", "voice": True}
    off = dict(pron="", voice={}, normalize_text=False)
    on = dict(off, normalize_text=True)
    assert R.audio_hash(off, sc) != R.audio_hash(on, sc)
    assert R.spoken_text(off, "15%") == "15%"


# ---------------------------------------------------------------- mốc TTS -> phụ đề (đầu-cuối, giọng giả có mốc đúng tuyệt đối)
def test_tts_returns_words_inside_speech(root):
    proj = make_project()
    sc = proj["scenes"][0]
    meta = M.tts_scene(root, proj, sc)
    assert meta["wsrc"] == "word" and len(meta["words"]) == len(NARR1.split())
    w = meta["words"]
    assert abs(w[0][1] - meta["speech"][0]) < 0.05, "từ đầu phải trùng chỗ bắt đầu có tiếng đo từ chính audio"
    assert abs(w[-1][2] - meta["speech"][1]) < 0.10
    assert all(w[i][1] <= w[i + 1][1] for i in range(len(w) - 1))


def test_captions_follow_real_pauses(root):
    proj = add_fake_audio(root, make_project())
    ctx = R.Ctx(proj, root, 270, 480)
    v = ctx.view(0)
    s = ctx.tl["scenes"][0]
    assert abs(v.bounds[0] - s["speech_abs"][0]) < 0.06
    assert abs(v.bounds[-1] - s["speech_abs"][1]) < 0.15
    # chỗ đổi cụm phải rơi vào khoảng lặng thật đo từ audio (gaps_rel = tâm các chỗ ngắt hơi >= 180ms)
    for b in v.bounds[1:-1]:
        assert min(abs(b - g) for g in s["gaps_rel"]) < 0.30, f"ranh giới cụm {b:.2f}s không nằm ở chỗ ngắt hơi"


def test_fallback_when_no_word_marks(root):
    proj = add_fake_audio(root, make_project())
    for sc in proj["scenes"]:
        if sc.get("audio"):
            sc["audio"]["words"] = []
    ctx = R.Ctx(proj, root, 270, 480)
    b = ctx.view(0).bounds  # không có mốc từ thì vẫn có phụ đề
    assert len(b) == len(ctx.view(0).phr) + 1 and b == sorted(b)


def test_clean_events_rejects_inconsistent_marks():
    speech = [0.1, 3.0]
    good = [("a", 0.1, 0.5), ("b", 2.5, 3.0)]
    assert M.clean_events(good, "word", 0.0, 3.2, speech)
    bad = [("a", 5.0, 5.5), ("b", 6.0, 6.5)]  # lệch hẳn so với chỗ có tiếng
    assert M.clean_events(bad, "word", 0.0, 3.2, speech) == []


def test_sentence_marks_are_expanded_to_words():
    out = M.clean_events([("Xin chào các bạn.", 0.1, 2.1)], "sentence", 0.0, 2.3, [0.1, 2.1])
    assert [w[0] for w in out] == ["Xin", "chào", "các", "bạn."]
    assert out[0][1] == 0.1 and out[-1][2] <= 2.1


# ---------------------------------------------------------------- tô sáng từ
def test_word_highlight_changes_pixels_only_in_word_box(root):
    base = add_fake_audio(root, make_project(caption_hl=False))
    hl = add_fake_audio(root, make_project(caption_hl=True))
    W, H = 540, 960
    c0, c1 = R.Ctx(base, root, W, H), R.Ctx(hl, root, W, H)
    t = c0.tl["scenes"][0]["start"] + c0.view(0).bounds[0] + 0.7
    f0, f1 = c0.render(t), c1.render(t)
    d = np.abs(f0.astype(int) - f1.astype(int)).sum(axis=2)
    assert d.max() > 60, "chữ được tô sáng phải khác màu"
    ys, xs = np.nonzero(d > 30)
    assert ys.min() > H * 0.6, "chỉ vùng phụ đề được đổi màu"
    assert xs.max() - xs.min() < W * 0.5, "chỉ 1 từ được tô, không phải cả dòng"
