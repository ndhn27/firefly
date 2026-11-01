"""Renderer. Mỗi khung hình là hàm thuần của thời gian t -> render song song / xem trước tuỳ ý được."""
import bisect
import difflib
import hashlib
import json
import logging
import math
import re
import unicodedata
import urllib.request
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

import paths

log = logging.getLogger("ffv.render")
HERE = Path(__file__).resolve().parent
FONT_DIR = paths.DATA_DIR / "fonts"  # nơi tải font về (ghi được)
FONT_DIRS = [FONT_DIR, paths.RES_DIR / "fonts"]  # nơi tìm font: bản tải thêm trước, font kèm theo sau

ASPECTS = {"16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1), "4:5": (4, 5)}
PRE, POST, TRANS = 0.45, 0.70, 0.60  # giây: lặng trước giọng, lặng sau giọng, thời gian chuyển cảnh

THEMES = {
    "dom-dom-vang": dict(label="Đom đóm vàng", bg_top=(5, 12, 10), bg_bottom=(12, 28, 18), c1=(255, 205, 90),
                         c2=(150, 255, 120), count=60, size=1.0, speed=1.0, glow=1.0, pulse=0.85, blobs=0.7,
                         flowx=0.0, flowy=0.0, bokeh=0.0, rays=0.0),
    "dem-xanh": dict(label="Đêm xanh", bg_top=(4, 8, 22), bg_bottom=(10, 26, 56), c1=(120, 210, 255),
                     c2=(140, 120, 255), count=70, size=1.0, speed=1.0, glow=1.0, pulse=0.5, blobs=1.0,
                     flowx=0.0, flowy=0.0, bokeh=0.0, rays=0.0),
    "tim-hong": dict(label="Tím hồng", bg_top=(14, 6, 28), bg_bottom=(38, 10, 46), c1=(255, 130, 200),
                     c2=(150, 120, 255), count=60, size=1.1, speed=0.9, glow=1.0, pulse=0.6, blobs=1.0,
                     flowx=0.0, flowy=0.0, bokeh=0.0, rays=0.0),
    "rung-sau": dict(label="Rừng sâu", bg_top=(3, 12, 14), bg_bottom=(6, 28, 30), c1=(90, 255, 220),
                     c2=(120, 200, 255), count=80, size=0.9, speed=1.0, glow=1.0, pulse=0.9, blobs=0.8,
                     flowx=0.0, flowy=0.0, bokeh=0.0, rays=0.0),
    "than-hong": dict(label="Than hồng bay lên", bg_top=(14, 6, 4), bg_bottom=(34, 12, 6), c1=(255, 150, 60),
                      c2=(255, 90, 40), count=55, size=1.0, speed=1.0, glow=1.0, pulse=0.6, blobs=0.8,
                      flowx=0.004, flowy=-0.03, bokeh=0.0, rays=0.0),
    "toi-gian": dict(label="Tối giản", bg_top=(10, 10, 12), bg_bottom=(24, 24, 30), c1=(230, 235, 255),
                     c2=(180, 190, 220), count=45, size=0.8, speed=0.8, glow=0.9, pulse=0.2, blobs=0.4,
                     flowx=0.0, flowy=0.0, bokeh=0.0, rays=0.0),
    "bokeh-am": dict(label="Bokeh ấm", bg_top=(16, 8, 6), bg_bottom=(36, 17, 11), c1=(255, 190, 110),
                     c2=(255, 140, 165), count=34, size=2.4, speed=0.6, glow=0.6, pulse=0.12, blobs=1.0,
                     flowx=0.0, flowy=-0.004, bokeh=1.0, rays=0.0),
    "tia-sang": dict(label="Tia sáng", bg_top=(4, 10, 24), bg_bottom=(8, 32, 46), c1=(190, 225, 255),
                     c2=(255, 236, 190), count=55, size=0.55, speed=0.7, glow=0.9, pulse=0.15, blobs=0.45,
                     flowx=0.0, flowy=-0.006, bokeh=0.0, rays=1.0),
}
DEFAULT_THEME = "dom-dom-vang"


# Vùng an toàn theo tỉ lệ khung (tỉ lệ so với khung). mx: lề ngang; top: nơi tiêu đề bắt đầu; cap: đáy phụ đề;
# bottom: phía dưới mức này là chỗ giao diện app (Reels/Shorts/TikTok) che mất -> đừng đặt gì quan trọng.
SAFE = {
    "9:16": dict(mx=0.08, top=0.09, cap=0.78, bottom=0.80),
    "4:5": dict(mx=0.08, top=0.07, cap=0.86, bottom=0.90),
    "1:1": dict(mx=0.08, top=0.07, cap=0.88, bottom=0.92),
    "16:9": dict(mx=0.08, top=0.07, cap=0.92, bottom=0.95),
}


def safe_for(W, H):
    r = W / H
    return SAFE[min(ASPECTS, key=lambda a: abs(math.log(r / (ASPECTS[a][0] / ASPECTS[a][1]))))]


def frame_size(aspect, short):
    a, b = ASPECTS.get(aspect, (16, 9))
    if a >= b:
        h = int(short)
        w = int(round(short * a / b / 2) * 2)
    else:
        w = int(short)
        h = int(round(short * b / a / 2) * 2)
    return w - w % 2, h - h % 2


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


# ----------------------------------------------------------------------------- fonts
FONT_FILES = {"bold": "BeVietnamPro-Bold.ttf", "semi": "BeVietnamPro-SemiBold.ttf", "reg": "BeVietnamPro-Regular.ttf"}
FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/bevietnampro/"
FONT_FALLBACK = {
    "bold": ["C:/Windows/Fonts/segoeuib.ttf", "/mnt/c/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "semi": ["C:/Windows/Fonts/seguisb.ttf", "/mnt/c/Windows/Fonts/seguisb.ttf", "C:/Windows/Fonts/segoeuib.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "reg": ["C:/Windows/Fonts/segoeui.ttf", "/mnt/c/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
}


def ensure_fonts():
    """Tải Be Vietnam Pro (OFL) về lần đầu; lỗi mạng thì dùng font hệ thống."""
    FONT_DIR.mkdir(exist_ok=True)
    for f in FONT_FILES.values():
        p = FONT_DIR / f
        if not p.exists():
            try:
                urllib.request.urlretrieve(FONT_URL + f, str(p))
            except Exception as e:  # noqa
                log.warning("Không tải được font %s (%s) – dùng font hệ thống, dấu tiếng Việt có thể lệch", f, e)
                if p.exists():
                    p.unlink()


@lru_cache(maxsize=64)
def get_font(weight, size):
    cands = [d / FONT_FILES[weight] for d in FONT_DIRS] + [Path(p) for p in FONT_FALLBACK[weight]]
    for p in cands:
        if p.exists():
            return ImageFont.truetype(str(p), int(size))
    return ImageFont.load_default()


# ----------------------------------------------------------------------------- text
def wrap_lines(text, font, max_w):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for w in para.split(" "):
            test = (cur + " " + w) if cur else w
            if not cur or font.getlength(test) <= max_w:
                cur = test
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def _compose_bgra(m, fill, glow_a=None, glow_col=None, box_a=None, box_col=None):
    """Chồng các lớp (hộp -> glow -> chữ) thành BGRA uint8. m, glow_a, box_a: float 0..1."""
    h, w = m.shape
    col = np.zeros((h, w, 3), np.float32)
    a = np.zeros((h, w), np.float32)
    layers = []
    if box_a is not None:
        layers.append((box_a, np.array(box_col, np.float32)))
    if glow_a is not None:
        layers.append((glow_a, np.array(glow_col, np.float32)))
    layers.append((m, np.array(fill, np.float32)))
    for la, lc in layers:
        a_out = la + a * (1 - la)
        col = (lc * la[..., None] + col * (a * (1 - la))[..., None]) / np.maximum(a_out[..., None], 1e-4)
        a = a_out
    return np.dstack([col[..., ::-1], a * 255]).clip(0, 255).astype(np.uint8)


def text_sprite(text, font, max_w, fill=(255, 255, 255), glow=None, glow_r=0, line_gap=1.22):
    lines = wrap_lines(text, font, max_w)
    lh = int(font.size * line_gap)
    lw = [font.getlength(s) for s in lines]
    pad = int(glow_r * 2.2 + 6)
    w = int(max(lw)) + 2 * pad
    h = lh * len(lines) + 2 * pad + int(font.size * 0.3)
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    for n, s in enumerate(lines):
        d.text(((w - lw[n]) / 2, pad + n * lh), s, font=font, fill=255)
    m = np.asarray(mask, np.float32) / 255
    g = None
    if glow is not None and glow_r > 0:
        g = np.clip(np.asarray(mask.filter(ImageFilter.GaussianBlur(glow_r)), np.float32) / 255 * 1.5, 0, 1) * 0.85
    return _compose_bgra(m, fill, g, glow), h - 2 * pad


def hl_color(c):
    """Màu tô sáng từ đang đọc: lấy màu ánh sáng của theme nếu đủ rực, không thì dùng vàng ấm (để luôn nổi trên nền)."""
    mx, mn = max(c), min(c)
    return tuple(int(x) for x in c) if mx and (mx - mn) / mx >= 0.35 else (255, 214, 102)


def caption_sprite(text, font, max_w, hl=None):
    """Sprite phụ đề dạng viên thuốc. Nếu hl (màu RGB) được đưa vào: trả (sprite, sprite chữ màu tô sáng, ô chữ từng từ)."""
    padx, pady = int(font.size * 0.7), int(font.size * 0.42)
    lines = wrap_lines(text, font, max_w - 2 * padx)
    lh = int(font.size * 1.28)
    lw = [font.getlength(s) for s in lines]
    w = int(max(lw)) + 2 * padx
    h = lh * len(lines) + 2 * pady
    S = 3
    big = Image.new("L", (w * S, h * S), 0)
    ImageDraw.Draw(big).rounded_rectangle([0, 0, w * S - 1, h * S - 1], radius=int(font.size * 0.62) * S, fill=255)
    box = np.asarray(big.resize((w, h), Image.LANCZOS), np.float32) / 255 * 0.62
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    boxes = []
    for n, s in enumerate(lines):
        x0, y0 = (w - lw[n]) / 2, pady + n * lh - int(font.size * 0.04)
        d.text((x0, y0), s, font=font, fill=255)
        words = s.split(" ")
        for k, wd in enumerate(words):
            bx = x0 + (font.getlength(" ".join(words[:k]) + " ") if k else 0.0)
            boxes.append((max(int(bx) - 2, 0), min(int(bx + font.getlength(wd)) + 3, w),
                          max(int(y0), 0), min(int(y0 + lh), h)))
    m = np.asarray(mask, np.float32) / 255
    base = _compose_bgra(m, (255, 255, 255), None, None, box, (6, 8, 14))
    if hl is None:
        return base
    return base, _compose_bgra(m, hl), boxes


def blit(dst, spr, x, y, alpha=1.0):
    """Trộn sprite BGRA lên canvas BGR (có cắt biên)."""
    h, w = spr.shape[:2]
    H, W = dst.shape[:2]
    x, y = int(x), int(y)
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, W), min(y + h, H)
    if x1 <= x0 or y1 <= y0 or alpha <= 0.003:
        return
    s = spr[y0 - y:y1 - y, x0 - x:x1 - x]
    d = dst[y0:y1, x0:x1]
    a = s[..., 3:4].astype(np.float32) * (alpha / 255.0)
    d[...] = (d * (1.0 - a) + s[..., :3] * a + 0.5).astype(np.uint8)


# ----------------------------------------------------------------------------- phrases (phụ đề)
def split_phrases_tok(text, maxc):
    """Chia lời đọc thành các cụm phụ đề. Trả [(cụm, số từ gốc của cụm)] – số từ dùng để đối chiếu với mốc từ của TTS."""
    text = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    if not text:
        return []
    out = []
    for sent in re.split(r"(?<=[.!?…])\s+", text):
        if len(sent) <= maxc:
            out.append(sent)
            continue
        cur = ""
        for cl in re.split(r"(?<=[,;:—–])\s+", sent):
            if len(cl) > maxc:  # mệnh đề quá dài: chia đều theo từ
                if cur:
                    out.append(cur)
                    cur = ""
                words = cl.split(" ")
                n = math.ceil(len(cl) / maxc)
                per = math.ceil(len(words) / n)
                out += [" ".join(words[i:i + per]) for i in range(0, len(words), per)]
            elif cur and len(cur) + 1 + len(cl) > maxc:
                out.append(cur)
                cur = cl
            else:
                cur = (cur + " " + cl) if cur else cl
        if cur:
            out.append(cur)
    merged = []
    for p in out:
        if merged and len(p) < 10 and len(merged[-1]) + 1 + len(p) <= maxc * 1.2:
            merged[-1] += " " + p
        else:
            merged.append(p)
    res, pending = [], 0
    for p in merged:
        raw = p.strip()
        if not raw:
            continue
        n = len(raw.split())
        clean = raw.rstrip(".,;:").strip()
        if not clean:  # cụm chỉ gồm dấu câu: không hiện, nhưng vẫn tính số từ để các cụm sau không bị lệch
            if res:
                res[-1][1] += n
            else:
                pending += n
            continue
        res.append([clean, n + pending])
        pending = 0
    return [(a, b) for a, b in res]


def split_phrases(text, maxc):
    return [p for p, _ in split_phrases_tok(text, maxc)]


def phrase_bounds(phrases, t0, t1, gaps):
    """Chia [t0,t1] theo độ dài chữ, rồi hút ranh giới vào chỗ ngắt hơi thật trong audio (gaps)."""
    wts = [len(p) + 4 for p in phrases]
    tot = float(sum(wts))
    b, acc = [t0], 0.0
    for w in wts:
        acc += w
        b.append(t0 + (t1 - t0) * acc / tot)
    for i in range(1, len(b) - 1):
        near = [g for g in gaps if abs(g - b[i]) <= 0.45 and g > b[i - 1] + 0.25]
        if near:
            b[i] = min(near, key=lambda g: abs(g - b[i]))
    return b


def _norm_tok(t):
    return re.sub(r"^[\W_]+|[\W_]+$", "", unicodedata.normalize("NFC", t).lower())


def align_tokens(tokens, events):
    """Gán (bắt đầu, kết thúc) cho từng từ của lời đọc theo mốc từ do TTS trả về.
    Đối chiếu bằng difflib nên chịu được chỗ giọng đọc khác chữ hiển thị (từ điển phát âm, số, ngày, %...).
    tokens: list chữ hiển thị; events: [(từ, t0, t1)]. Trả None nếu không có mốc."""
    if not tokens or not events:
        return None
    a = [_norm_tok(t) for t in tokens]
    b = [_norm_tok(e[0]) for e in events]
    res = [None] * len(tokens)
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                res[i1 + k] = (events[j1 + k][1], events[j1 + k][2])
        elif op == "replace":  # chữ hiển thị != chữ đọc: rải đều theo độ dài chữ trên khoảng thời gian của các từ đọc
            t0, t1 = events[j1][1], events[j2 - 1][2]
            w = [max(len(a[i]), 1) for i in range(i1, i2)]
            tot, acc = float(sum(w)), 0.0
            for k, i in enumerate(range(i1, i2)):
                res[i] = (t0 + (t1 - t0) * acc / tot, t0 + (t1 - t0) * (acc + w[k]) / tot)
                acc += w[k]
    i = 0
    while i < len(res):  # từ không có mốc (vd dấu "—" đứng riêng): nội suy giữa hai từ có mốc gần nhất
        if res[i] is not None:
            i += 1
            continue
        j = i
        while j < len(res) and res[j] is None:
            j += 1
        lo = res[i - 1][1] if i > 0 else events[0][1]
        hi = res[j][0] if j < len(res) else events[-1][2]
        hi = max(hi, lo)
        for k in range(i, j):
            res[k] = (lo + (hi - lo) * (k - i) / (j - i), lo + (hi - lo) * (k - i + 1) / (j - i))
        i = j
    prev = 0.0
    out = []
    for t0, t1 in res:  # không cho mốc đi lùi
        t0 = max(t0, prev)
        out.append((t0, max(t1, t0)))
        prev = t0
    return out


# ----------------------------------------------------------------------------- timeline
_UNIT_WORDS = [  # chỉ đổi khi đứng ngay sau chữ số, vd "5km"
    ("km/h", "ki-lô-mét trên giờ"), ("m/s", "mét trên giây"), ("km", "ki-lô-mét"), ("kg", "ki-lô-gam"),
    ("cm", "xen-ti-mét"), ("mm", "mi-li-mét"), ("GB", "ghi-ga-bai"), ("MB", "mê-ga-bai"), ("°C", "độ xê"),
    ("USD", "đô la Mỹ"), ("VNĐ", "đồng"), ("VND", "đồng"),
]


def normalize_vi(text):
    """Viết lại số/%/ngày/đơn vị thành dạng dễ đọc cho giọng TTS tiếng Việt (chỉ ảnh hưởng giọng, phụ đề giữ nguyên)."""
    def date(m):
        pre, d, mo, y = m.group(1) or "", int(m.group(2)), int(m.group(3)), int(m.group(4))
        if not (1 <= d <= 31 and 1 <= mo <= 12):
            return m.group(0)
        return f"{pre}{'' if pre else 'ngày '}{d} tháng {mo} năm {y}"  # đã có chữ "ngày" đứng trước thì không thêm lần nữa

    out = re.sub(r"(?<![\d/.\-])((?:ngày|Ngày)\s+)?(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})(?![\d/])", date, text)
    out = re.sub(r"(?<=ngày )(\d{1,2})/(\d{1,2})(?![\d/])", r"\1 tháng \2", out)
    out = re.sub(r"(?<=tháng )(\d{1,2})/(\d{4})(?!\d)", r"\1 năm \2", out)
    out = re.sub(r"(?<![\d.])\d{1,3}(?:\.\d{3})+(?![\d.]*\d)", lambda m: m.group(0).replace(".", ""), out)  # 1.000.000 -> 1000000
    out = re.sub(r"(?<![\d,])\d{1,3}(?:,\d{3}){2,}(?![\d,])", lambda m: m.group(0).replace(",", ""), out)  # 1,000,000
    out = re.sub(r"(?<=\d)\s*%", " phần trăm", out)
    for k, v in _UNIT_WORDS:
        out = re.sub(r"(?<=\d)\s?" + re.escape(k) + r"(?![\w/])", " " + v, out)
    out = re.sub(r"\bTP\.?\s?HCM\b", "Thành phố Hồ Chí Minh", out)
    out = re.sub(r"\s*&\s*", " và ", out)
    return out


def spoken_text(proj, text):
    out = text
    for line in sorted((proj.get("pron") or "").splitlines(), key=len, reverse=True):
        if "=" in line:
            a, b = line.split("=", 1)
            a, b = a.strip(), b.strip()
            if a:
                out = re.sub(r"(?<!\w)" + re.escape(a) + r"(?!\w)", b, out, flags=re.I)
    return normalize_vi(out) if proj.get("normalize_text") else out


def audio_hash(proj, sc):
    v = proj.get("voice", {})
    key = json.dumps([spoken_text(proj, sc.get("narration", "").strip()), v.get("name"), v.get("rate", 0),
                      v.get("pitch", 0)], ensure_ascii=False)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def needs_voice(sc):
    return bool(sc.get("voice", True) and sc.get("narration", "").strip())


def scene_audio(proj, sc):
    a = sc.get("audio")
    if needs_voice(sc) and a and a.get("hash") == audio_hash(proj, sc):
        return a
    return None


def timeline(proj):
    scenes = proj.get("scenes", [])
    out, t = [], 0.0
    for i, sc in enumerate(scenes):
        text = sc.get("narration", "").strip()
        a = scene_audio(proj, sc)
        gaps, words = [], []
        if needs_voice(sc):
            alen = a["dur"] if a else max(1.0, len(text) / 14.5 + 0.3)
            speech = list(a["speech"]) if a else [0.1, alen - 0.1]
            gaps = list(a.get("gaps", [])) if a else []
            words = [(w[0], PRE + w[1], PRE + w[2]) for w in a.get("words", [])] if a else []
            dur = PRE + alen + POST + float(sc.get("extra", 0) or 0)
            t_start = PRE
        else:
            dur = max(1.0, float(sc.get("duration", 4.0) or 4.0))
            alen, speech, t_start = 0.0, [0.0, max(0.5, dur - 1.2)], 0.4
        trans = sc.get("transition", "fade") if i < len(scenes) - 1 else "none"
        T = 0.0 if trans == "none" else min(TRANS, dur * 0.45)
        out.append(dict(id=sc.get("id"), start=t, dur=dur, T=T, trans=trans, audio=a, alen=alen,
                        audio_start=t + PRE, speech_abs=(t_start + speech[0], t_start + speech[1]),
                        gaps_rel=[t_start + g for g in gaps], words_rel=words, estimated=bool(needs_voice(sc) and not a)))
        t += dur - T
    total = (out[-1]["start"] + out[-1]["dur"]) if out else 0.0
    return dict(scenes=out, total=total)


# ----------------------------------------------------------------------------- images
_IMG_CACHE = OrderedDict()


def load_image(path, maxdim=3000):
    """Đọc ảnh (xoay theo EXIF, dán nền tối nếu có trong suốt) -> BGR uint8."""
    p = Path(path)
    try:
        key = (str(p), p.stat().st_mtime_ns)
    except OSError:
        return None
    if key in _IMG_CACHE:
        _IMG_CACHE.move_to_end(key)
        return _IMG_CACHE[key]
    try:
        im = ImageOps.exif_transpose(Image.open(p))
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bgc = Image.new("RGBA", im.size, (22, 26, 36, 255))
            im = Image.alpha_composite(bgc, im)
        im = im.convert("RGB")
        if max(im.size) > maxdim:
            s = maxdim / max(im.size)
            im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
        arr = np.ascontiguousarray(np.asarray(im)[..., ::-1])
    except Exception as e:  # noqa
        log.warning("Không đọc được ảnh %s (%s: %s) – bỏ qua ảnh này", p.name, type(e).__name__, e)
        return None
    _IMG_CACHE[key] = arr
    while len(_IMG_CACHE) > 12:
        _IMG_CACHE.popitem(last=False)
    return arr


def corner_masks(r):
    ys, xs = np.mgrid[0:r, 0:r].astype(np.float32)
    d = np.sqrt((r - 0.5 - xs) ** 2 + (r - 0.5 - ys) ** 2)
    q = np.clip(r - d + 0.5, 0, 1)[..., None]  # góc trên-trái
    return q


def rounded_mask(w, h, r):
    S = 2
    im = Image.new("L", (w * S, h * S), 0)
    ImageDraw.Draw(im).rounded_rectangle([0, 0, w * S - 1, h * S - 1], radius=r * S, fill=255)
    return np.asarray(im.resize((w, h), Image.LANCZOS), np.float32) / 255


def make_glow(w, h, r, color_bgr, blur, strength):
    pad = int(blur * 2.2)
    mask = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
    ImageDraw.Draw(mask).rounded_rectangle([pad, pad, pad + w, pad + h], radius=r, fill=255)
    g = np.asarray(mask.filter(ImageFilter.GaussianBlur(blur)), np.float32)[..., None] / 255 * strength
    return np.clip(g * np.array(color_bgr, np.float32), 0, 255).astype(np.uint8), pad


def affine_view(src_w, src_h, out_w, out_h, base_scale, zoom, panx, pany):
    """Ma trận biến ảnh work (src) -> khung (out) với zoom quanh tâm + pan trong phạm vi cho phép."""
    s = base_scale * zoom
    slack_x = max(0.0, (src_w - out_w / s) / 2)
    slack_y = max(0.0, (src_h - out_h / s) / 2)
    cx = src_w / 2 + panx * slack_x
    cy = src_h / 2 + pany * slack_y
    return np.array([[s, 0, out_w / 2 - s * cx], [0, s, out_h / 2 - s * cy]], np.float32)


def anim_params(anim, u, j):
    u = ease_io(u)
    if anim == "zoom_out":
        return 1.0 + 0.10 * (1 - u), 0.0, 0.0
    if anim == "pan":
        d = 1 if j % 2 == 0 else -1
        return 1.12, d * (-0.9 + 1.8 * u), 0.0
    if anim == "none":
        return 1.0, 0.0, 0.0
    return 1.0 + 0.10 * u, 0.0, 0.0  # zoom vào


# ----------------------------------------------------------------------------- background
def _bgr(c):
    return np.array(c[::-1], np.float32)


class Background:
    def __init__(self, th, W, H):
        self.W, self.H = W, H
        self.th = th
        top, bot = _bgr(th["bg_top"]), _bgr(th["bg_bottom"])
        ys = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
        base = (top * (1 - ys) + bot * ys) * np.ones((1, W, 1), np.float32)
        gy, gx = np.mgrid[0:max(H // 8, 8), 0:max(W // 8, 8)].astype(np.float32)
        gy /= gy.max()
        gx /= gx.max()
        vig = 1 - 0.55 * (((gx - 0.5) * 1.5) ** 2 + ((gy - 0.5) * 1.5) ** 2)
        vig = cv2.resize(np.clip(vig, 0.35, 1).astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR)
        rng = np.random.default_rng(3)
        grain = rng.integers(-2, 3, (H, W, 1)).astype(np.float32)  # dither chống banding
        self.base = np.clip(base * vig[..., None] + grain + 1, 0, 255).astype(np.uint8)
        div = 8 if W > 1600 else 4
        self.sw, self.sh = max(W // div, 16), max(H // div, 16)
        yy, xx = np.mgrid[0:self.sh, 0:self.sw].astype(np.float32)
        self.gx, self.gy = xx / self.sw * (W / H), yy / self.sh
        self.aspect = W / H
        rg = np.random.default_rng(11)
        self.blobs = [dict(w=rg.uniform(0.04, 0.10, 2), p=rg.uniform(0, 6.28, 2), r=rg.uniform(0.28, 0.5),
                           ci=i % 2) for i in range(4)]
        self.cols = [_bgr(th["c1"]), _bgr(th["c2"])]
        self.rays = float(th.get("rays", 0.0))
        if self.rays > 0:  # chùm tia chiếu chéo từ góc trên trái, đung đưa chậm
            ox, oy = -0.12 * self.aspect, -0.30
            dx_, dy_ = self.gx - ox, self.gy - oy
            self.r_ang = np.arctan2(dx_, dy_)  # 0 = thẳng xuống, dương = nghiêng sang phải
            self.r_fall = np.exp(-np.hypot(dx_, dy_) * 0.85).astype(np.float32)
            amax = math.atan2(self.aspect - ox, 1 - oy)
            rr = np.random.default_rng(21)
            self.beams = [dict(th=amax * (n + 0.5) / 6, sg=amax * rr.uniform(0.05, 0.10), w=rr.uniform(0.15, 0.4, 2),
                               p=rr.uniform(0, 6.28, 2), a=rr.uniform(0.6, 1.0)) for n in range(6)]
            self.ray_col = self.cols[0] * 0.7 + self.cols[1] * 0.3

    def frame(self, t):
        acc = np.zeros((self.sh, self.sw, 3), np.float32)
        k = 0.14 * float(self.th.get("blobs", 1.0))
        for b in self.blobs:
            cx = (0.5 + 0.42 * math.sin(b["w"][0] * t + b["p"][0])) * self.aspect
            cy = 0.5 + 0.36 * math.sin(b["w"][1] * t + b["p"][1])
            g = np.exp(-(((self.gx - cx) ** 2 + (self.gy - cy) ** 2) / (2 * b["r"] ** 2)))
            acc += g[..., None] * self.cols[b["ci"]] * k * (0.8 + 0.2 * math.sin(0.3 * t + b["p"][0]))
        if self.rays > 0:
            r = np.zeros_like(self.r_fall)
            for b in self.beams:
                th_ = b["th"] + 0.05 * math.sin(b["w"][0] * t + b["p"][0])
                r += b["a"] * (0.55 + 0.45 * math.sin(b["w"][1] * t + b["p"][1])) * np.exp(-((self.r_ang - th_) / b["sg"]) ** 2)
            acc += (r * self.r_fall)[..., None] * self.ray_col * (0.50 * self.rays)
        small = np.clip(acc, 0, 255).astype(np.uint8)
        big = cv2.resize(small, (self.W, self.H), interpolation=cv2.INTER_LINEAR)
        return cv2.add(self.base, big)


class Fireflies:
    def __init__(self, th, W, H):
        self.W, self.H, self.th = W, H, th
        k = min(W, H) / 1080.0
        n = int(th["count"])
        rng = np.random.default_rng(12345)
        self.n = n
        self.depth = rng.random(n)
        self.x0, self.y0 = rng.random(n), rng.random(n)
        ang = rng.random(n) * 2 * math.pi
        sp = (0.004 + 0.016 * self.depth) * float(th["speed"])
        self.vx = np.cos(ang) * sp + float(th.get("flowx", 0)) * (0.4 + self.depth) * float(th["speed"])
        self.vy = np.sin(ang) * sp + float(th.get("flowy", 0)) * (0.4 + self.depth) * float(th["speed"])
        self.wa = (0.012 + 0.03 * rng.random(n)) * (0.5 + self.depth)
        self.wf = 0.12 + 0.35 * rng.random((n, 2))
        self.ph = rng.random((n, 3)) * 2 * math.pi
        self.pf = (0.10 + 0.28 * rng.random(n)) * float(th["speed"] ** 0.5 if th["speed"] > 0 else 1)
        self.ci = rng.integers(0, 2, n)
        self.bokeh = float(th.get("bokeh", 0.0)) > 0.5  # đốm mờ to hình đĩa, viền sáng hơn (kiểu ống kính xoá phông)
        base_r = (24.0 + 62.0 * self.depth ** 1.2) if self.bokeh else (4.0 + 30.0 * self.depth ** 1.6)
        self.r = base_r * k * float(th["size"])
        self.cols = [_bgr(th["c1"]), _bgr(th["c2"])]
        self._spr = {}

    def sprite(self, ci, r, depth):
        key = (int(ci), int(round(r)))
        s = self._spr.get(key)
        if s is None and self.bokeh:
            R = int(r * 1.15) + 2
            ys, xs = np.mgrid[-R:R + 1, -R:R + 1].astype(np.float32)
            d = np.sqrt(xs ** 2 + ys ** 2)
            disc = np.clip((r - d) / (0.14 * r), 0, 1)  # mép mềm
            rim = np.exp(-(((d - 0.9 * r) / (0.07 * r)) ** 2)) * 0.6
            inten = np.clip(disc * (0.5 + rim), 0, 1) * (0.55 + 0.45 * (1 - depth))
            col = self.cols[ci] * 0.9 + 255 * 0.1
            s = np.ascontiguousarray((inten[..., None] * col).astype(np.uint8))
            self._spr[key] = s
        elif s is None:
            R = int(r * 3.4) + 2
            ys, xs = np.mgrid[-R:R + 1, -R:R + 1].astype(np.float32)
            d = np.sqrt(xs ** 2 + ys ** 2)
            core = np.exp(-(d / (0.24 * r)) ** 2)
            halo = np.exp(-(d / (1.25 * r)) ** 2) * 0.55
            inten = np.clip(core + halo, 0, 1) * (1.0 - 0.4 * depth)
            mix = (core ** 2 * 0.65)[..., None]
            col = self.cols[ci] * (1 - mix) + 255 * mix
            s = np.ascontiguousarray((inten[..., None] * col).astype(np.uint8))
            self._spr[key] = s
        return s

    def draw(self, canvas, t):
        W, H = self.W, self.H
        m = 0.12
        sx = (self.x0 + self.vx * t + self.wa * np.sin(self.wf[:, 0] * t + self.ph[:, 0]) * (H / W))
        sy = (self.y0 + self.vy * t + self.wa * np.sin(self.wf[:, 1] * t + self.ph[:, 1]))
        px = (((sx + m) % (1 + 2 * m)) - m) * W
        py = (((sy + m) % (1 + 2 * m)) - m) * H
        pd = float(self.th["pulse"])
        ph = (t * self.pf + self.ph[:, 2] / (2 * math.pi)) % 1.0
        pulse = np.where(ph < 0.55, np.sin(np.pi * np.clip(ph / 0.55, 0, 1)) ** 2, 0.0)
        bright = ((1 - pd) * 0.75 + pd * (0.10 + 0.90 * pulse)) * float(self.th["glow"])
        order = np.argsort(self.depth)
        for i in order:
            b = float(bright[i])
            if b < 0.03:
                continue
            spr = self.sprite(self.ci[i], self.r[i], self.depth[i])
            h, w = spr.shape[:2]
            x, y = int(px[i]) - w // 2, int(py[i]) - h // 2
            x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, W), min(y + h, H)
            if x1 <= x0 or y1 <= y0:
                continue
            roi = canvas[y0:y1, x0:x1]
            cv2.addWeighted(roi, 1.0, spr[y0 - y:y1 - y, x0 - x:x1 - x], min(b, 1.6), 0, dst=roi)


# ----------------------------------------------------------------------------- scene view
CARD_MODES = ("card", "fit")


def effective_mode(mode, arr, W, H):
    """Ảnh 'toàn màn hình' mà lệch tỉ lệ khung nhiều (cắt mất hơn ~40% diện tích) thì chuyển sang 'fit':
    ảnh nằm trọn trong khung, nền là chính ảnh đó làm mờ. Ảnh gần đúng tỉ lệ vẫn phủ kín."""
    mode = mode if mode in ("card", "fit", "cover") else "card"
    if mode == "cover":
        ih, iw = arr.shape[:2]
        a_img, a_fr = iw / ih, W / H
        if min(a_img / a_fr, a_fr / a_img) < 0.6:
            return "fit"
    return mode


def blurred_backdrop(arr, W, H, dim=0.45):
    """Nền mờ tối từ chính ảnh (phủ kín khung) – dùng sau ảnh 'fit'."""
    ih, iw = arr.shape[:2]
    s0 = max(W / iw, H / ih)
    small = cv2.resize(arr, (max(int(iw * s0 / 6), 4), max(int(ih * s0 / 6), 4)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), 3.0)
    big = cv2.resize(small, (math.ceil(iw * s0), math.ceil(ih * s0)), interpolation=cv2.INTER_CUBIC)
    return (big * dim).astype(np.uint8)


class SceneView:
    """Mọi thứ đã dựng sẵn của 1 cảnh (sprite chữ, ảnh đã scale, vị trí)."""

    def __init__(self, ctx, i):
        P, W, H, k = ctx.proj, ctx.W, ctx.H, ctx.k
        sc = P["scenes"][i]
        self.s = ctx.tl["scenes"][i]
        self.W, self.H, self.k = W, H, k
        sz = ctx.safe
        portrait = H > W * 1.1
        landscape = W > H * 1.1
        mx = W * sz["mx"]
        title = (sc.get("title") or "").strip()
        sub = (sc.get("subtitle") or "").strip()
        narr = (sc.get("narration") or "").strip()
        self.has_caption = bool(narr) and sc.get("caption", True)
        loaded = []
        for im in sc.get("images", []):
            if not im.get("file"):
                continue
            arr = load_image(ctx.root / "media" / im["file"])
            if arr is not None:
                loaded.append((im, arr, effective_mode(im.get("mode", "card"), arr, W, H)))
        has_card = any(m in CARD_MODES for _, _, m in loaded)
        hero = not has_card
        split = has_card and sc.get("layout") == "split"
        wide_split = split and not portrait  # ngang/vuông: chữ một cột, ảnh một cột; dọc: ảnh trên, chữ dưới
        c1 = ctx.th["c1"]
        self.title = self.sub = None
        self.title_cx = self.sub_cx = W / 2
        media_x = (mx, W - mx)
        text_w = W - 2 * mx
        if wide_split:
            inner = W - 2 * mx
            tw, mw, gap = inner * 0.42, inner * 0.54, inner * 0.04
            if sc.get("image_side", "right") == "left":
                media_x, tx0 = (mx, mx + mw), mx + mw + gap
            else:
                media_x, tx0 = (mx + tw + gap, W - mx), mx
            text_w = tw
            self.title_cx = self.sub_cx = tx0 + tw / 2
        # --- tiêu đề
        tfont_px = 96 if hero else 72
        spr = None
        for px in (tfont_px, tfont_px * 0.82, tfont_px * 0.68, tfont_px * 0.56):
            font = get_font("bold", round(px * k))
            if title:
                spr, _ = text_sprite(title, font, text_w, (255, 255, 255), c1, 14 * k)
                if spr.shape[0] <= H * (0.3 if hero else 0.4 if wide_split else 0.22) + 40 * k:
                    break
        if title:
            self.title = spr
        # --- vùng phụ đề
        cap_px = round((44 if not portrait else 46) * k)
        self.cap_font = get_font("semi", cap_px)
        self.cap_w = W - 2 * mx
        cap_bottom = H * sz["cap"]
        cap_h = cap_px * 1.28 * 2 + cap_px * 0.84
        cap_top = cap_bottom - cap_h if self.has_caption else H * 0.93
        self.cap_bottom = cap_bottom
        top = H * sz["top"]
        if sub:
            self.sub, _ = text_sprite(sub, get_font("reg", round((40 if hero else 36) * k)), text_w, (225, 232, 240))
        # --- bố cục
        self.media = (0.0, 0.0)
        if hero:
            ty = H * 0.36
            if self.title is not None:
                self.title_y = ty - self.title.shape[0] / 2
                bottom = self.title_y + self.title.shape[0]
            else:
                self.title_y, bottom = ty, ty
            self.sub_y = bottom + 6 * k
        elif not split:  # tiêu đề trên, ảnh giữa, phụ đề dưới
            self.title_y = top
            media_top = top + (self.title.shape[0] if self.title is not None else 0) + 0.02 * H
            self.sub_y = media_top - 10 * k
            if self.sub is not None:
                media_top += self.sub.shape[0] * 0.8
            media_bottom = cap_top - 0.03 * H
            self.media = (media_top, max(media_bottom, media_top + 0.2 * H))
        else:
            z0, z1 = top, max(cap_top - 0.03 * H, top + 0.3 * H)
            if wide_split:
                m0, m1, t0, t1 = z0, z1, z0, z1
            else:
                cut = z0 + (z1 - z0) * 0.58
                m0, m1, t0, t1 = z0, cut, cut + 0.03 * H, z1
            th_ = self.title.shape[0] if self.title is not None else 0
            sh_ = self.sub.shape[0] * 0.8 if self.sub is not None else 0
            y0 = (t0 + t1 - th_ - sh_) / 2 if th_ + sh_ <= t1 - t0 else t0
            self.title_y, self.sub_y = y0, y0 + th_ - 6 * k
            self.media = (m0, max(m1, m0 + 0.2 * H))
        # --- ảnh
        n = len(loaded)
        seg = self.s["dur"] / max(n, 1)
        f = min(0.45, seg * 0.4)
        self.imgs = []
        mt, mb = self.media
        for j, (im, arr, mode) in enumerate(loaded):
            ih, iw = arr.shape[:2]
            start = j * seg - (f if j > 0 else 0)
            end = (j + 1) * seg + (f if j < n - 1 else 9999)
            d = dict(anim=im.get("anim", "zoom"), j=j, start=start, end=end, fin=(f if j > 0 else 0.7), fout=f)
            if mode == "cover":
                s0 = max(W / iw, H / ih)
                work = cv2.resize((arr * 0.42).astype(np.uint8), (math.ceil(iw * s0), math.ceil(ih * s0)),
                                  interpolation=cv2.INTER_AREA if s0 < 1 else cv2.INTER_CUBIC)
                self.imgs.append(dict(d, mode="cover", work=work, out=(W, H), base=1.0))
                continue
            if mode == "fit":  # nền mờ phủ kín (vẽ ở lớp dưới) + ảnh nguyên vẹn nằm trên
                self.imgs.append(dict(d, mode="cover", anim="zoom", work=blurred_backdrop(arr, W, H), out=(W, H), base=1.0))
                maxw = min((media_x[1] - media_x[0]) * (1.0 if wide_split else 1.1), W * 0.94)
                r, glow_s = int(16 * k), 0.2
            else:
                maxw, r, glow_s = media_x[1] - media_x[0], int(26 * k), 0.42
            sc_ = min(maxw / iw, (mb - mt) / ih)
            cw, ch = max(int(iw * sc_) // 2 * 2, 4), max(int(ih * sc_) // 2 * 2, 4)
            ws = min(1.0, 1.15 * sc_) if sc_ < 1 else 1.0
            work = cv2.resize(arr, (max(int(iw * ws), 2), max(int(ih * ws), 2)), interpolation=cv2.INTER_AREA
                              if ws < 1 else cv2.INTER_LINEAR)
            r = max(2, min(r, cw // 2 - 1, ch // 2 - 1))
            glow, gpad = make_glow(cw, ch, r, _bgr(c1), 38 * k, glow_s)
            self.imgs.append(dict(d, mode="card", work=work, out=(cw, ch), base=cw / work.shape[1], r=r,
                                  q=corner_masks(r), glow=glow, gpad=gpad, cx=(media_x[0] + media_x[1]) / 2,
                                  y=mt + (mb - mt - ch) / 2))
        # --- caption phrases
        self.phr, self.bounds, self.cap_spr, self.wst = [], [], {}, []
        self.hl = hl_color(ctx.th["c1"]) if P.get("caption_hl") else None
        if self.has_caption:
            cpl = max(18, int(self.cap_w / (cap_px * 0.5)))
            pt = split_phrases_tok(narr, int(cpl * (1.05 if landscape else 1.6)))
            self.phr = [p for p, _ in pt]
            s0, s1 = self.s["speech_abs"]
            toks = narr.split()
            tt = align_tokens(toks, self.s.get("words_rel") or []) if sum(n for _, n in pt) == len(toks) else None
            if tt:  # có mốc từ thật từ TTS: mỗi cụm bắt đầu đúng lúc từ đầu cụm được đọc
                k, starts = 0, []
                for p_, n in pt:
                    starts.append(tt[k][0])
                    self.wst.append([tt[j][0] for j in range(k, k + n)] if len(p_.split()) == n else None)
                    k += n
                self.bounds = starts + [max(tt[-1][1], starts[-1] + 0.3)]
            else:  # không có mốc từ: chia theo độ dài chữ rồi hút vào chỗ ngắt hơi
                self.bounds = phrase_bounds(self.phr, s0, max(s1, s0 + 0.5), self.s["gaps_rel"])
                self.wst = [None] * len(self.phr)

    def caption(self, lt):
        if not self.phr:
            return None
        if lt < self.bounds[0] - 0.05 or lt > self.bounds[-1] + 0.45:
            return None
        idx = max(0, bisect.bisect_right(self.bounds, lt) - 1)
        idx = min(idx, len(self.phr) - 1)
        c = self.cap_spr.get(idx)
        if c is None:
            r = caption_sprite(self.phr[idx], self.cap_font, self.cap_w, self.hl)
            c = self.cap_spr[idx] = r if self.hl is not None else (r, None, None)
        base, hls, boxes = c
        a = ease_out((lt - self.bounds[idx] + 0.05) / 0.16)
        if idx == len(self.phr) - 1:
            a *= clamp((self.bounds[-1] + 0.45 - lt) / 0.25)
        hl, ws = None, self.wst[idx] if idx < len(self.wst) else None
        if hls is not None and ws and len(ws) == len(boxes):  # từ đang đọc = từ cuối cùng đã bắt đầu
            hl = (hls, boxes[max(0, bisect.bisect_right(ws, lt) - 1)])
        return base, a, (1 - a) * 14 * self.k, hl

    def img_alpha(self, d, lt):
        a = clamp((lt - d["start"]) / d["fin"]) if d["fin"] > 0 else 1.0
        if d["end"] < 9000:
            a *= clamp((d["end"] - lt) / d["fout"])
        return ease_io(a)


# ----------------------------------------------------------------------------- context
class Ctx:
    def __init__(self, proj, root, W, H):
        self.proj, self.root, self.W, self.H = proj, Path(root), W, H
        self.k = min(W, H) / 1080.0
        th = dict(THEMES[DEFAULT_THEME])
        th.update({k: v for k, v in (proj.get("theme") or {}).items() if k in th and k != "label"})
        for key in ("bg_top", "bg_bottom", "c1", "c2"):
            th[key] = tuple(int(x) for x in th[key])
        self.th = th
        self.tl = timeline(proj)
        self.safe = safe_for(W, H)
        self.logo = self._load_logo()
        self.bg = Background(th, W, H)
        self.ff = Fireflies(th, W, H)
        self._views = OrderedDict()

    def _load_logo(self):
        lg = self.proj.get("logo") or {}
        if not lg.get("file"):
            return None
        try:
            im = ImageOps.exif_transpose(Image.open(self.root / "media" / lg["file"])).convert("RGBA")
            w = max(16, int(min(self.W, self.H) * clamp(float(lg.get("size", 0.14)), 0.04, 0.4)))
            im = im.resize((w, max(8, int(im.height * w / im.width))), Image.LANCZOS)
        except Exception as e:  # noqa
            log.warning("Không đọc được logo %s (%s: %s)", lg.get("file"), type(e).__name__, e)
            return None
        pos = lg.get("pos") if lg.get("pos") in ("tl", "tr", "bl", "br") else "tr"
        return np.ascontiguousarray(np.asarray(im)[..., [2, 1, 0, 3]]), pos, clamp(float(lg.get("opacity", 0.9)), 0.1, 1.0)

    def draw_logo(self, canvas):
        spr, pos, op = self.logo
        h, w = spr.shape[:2]
        mxp = self.W * 0.05
        x = mxp if pos[1] == "l" else self.W - mxp - w
        y = self.H * self.safe["top"] * 0.45 if pos[0] == "t" else self.H * self.safe["bottom"] - h
        blit(canvas, spr, x, y, op)

    def view(self, i):
        v = self._views.get(i)
        if v is None:
            v = SceneView(self, i)
            self._views[i] = v
            while len(self._views) > 3:
                self._views.popitem(last=False)
        else:
            self._views.move_to_end(i)
        return v

    def img_progress(self, d, lt, v):
        end = d["end"] if d["end"] < 9000 else v.s["dur"]
        return clamp((lt - d["start"]) / max(end - d["start"], 1e-3))

    # -- vẽ từng lớp
    def draw_covers(self, canvas, i, lt, alpha, dx):
        v = self.view(i)
        for d in v.imgs:
            if d["mode"] != "cover":
                continue
            a = v.img_alpha(d, lt) * alpha
            if a < 0.004:
                continue
            u = self.img_progress(d, lt, v)
            z, px, py = anim_params(d["anim"], u, d["j"])
            work = d["work"]
            M = affine_view(work.shape[1], work.shape[0], self.W, self.H, 1.0, z, px, py)
            M[0, 2] += dx
            img = cv2.warpAffine(work, M, (self.W, self.H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            cv2.addWeighted(img, a, canvas, 1 - a, 0, dst=canvas)

    def draw_card(self, canvas, v, d, lt, alpha, dx):
        a = v.img_alpha(d, lt) * alpha
        if a < 0.004:
            return
        cw, ch = d["out"]
        u = self.img_progress(d, lt, v)
        z, px, py = anim_params(d["anim"], u, d["j"])
        work = d["work"]
        M = affine_view(work.shape[1], work.shape[0], cw, ch, d["base"], z, px, py)
        img = cv2.warpAffine(work, M, (cw, ch), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        slide = (1 - ease_out((lt - 0.15) / 0.8)) * 40 * self.k if d["j"] == 0 else 0
        bob = math.sin(lt * 0.9) * 5 * self.k
        x = int(d["cx"] - cw / 2 + dx)
        y = int(d["y"] + slide + bob)
        # glow
        g, gp = d["glow"], d["gpad"]
        gx, gy = x - gp, y - gp
        gx0, gy0, gx1, gy1 = max(gx, 0), max(gy, 0), min(gx + g.shape[1], self.W), min(gy + g.shape[0], self.H)
        if gx1 > gx0 and gy1 > gy0:
            roi = canvas[gy0:gy1, gx0:gx1]
            cv2.addWeighted(roi, 1.0, g[gy0 - gy:gy1 - gy, gx0 - gx:gx1 - gx], a * 0.9, 0, dst=roi)
        # thẻ bo góc
        r, q = d["r"], d["q"]
        if x < 0 or y < 0 or x + cw > self.W or y + ch > self.H:
            m = rounded_mask(cw, ch, r)
            spr = np.dstack([img, (m * 255).astype(np.uint8)])
            blit(canvas, spr, x, y, a)
            return
        roi = canvas[y:y + ch, x:x + cw]
        corners = [(slice(0, r), slice(0, r), q), (slice(0, r), slice(cw - r, cw), q[:, ::-1]),
                   (slice(ch - r, ch), slice(0, r), q[::-1]), (slice(ch - r, ch), slice(cw - r, cw), q[::-1, ::-1])]
        saved = [roi[ys, xs].copy() for ys, xs, _ in corners]
        cv2.addWeighted(img, a, roi, 1 - a, 0, dst=roi)
        for (ys, xs, qq), orig in zip(corners, saved):
            mm = qq * a
            roi[ys, xs] = (orig * (1 - mm) + img[ys, xs] * mm + 0.5).astype(np.uint8)

    def draw_fg(self, canvas, i, lt, alpha, dx):
        v = self.view(i)
        for d in v.imgs:
            if d["mode"] == "card":
                self.draw_card(canvas, v, d, lt, alpha, dx)
        W, k = self.W, self.k
        if v.title is not None:
            p = ease_out((lt - 0.12) / 0.7)
            blit(canvas, v.title, v.title_cx - v.title.shape[1] / 2 + dx, v.title_y + (1 - p) * 30 * k, alpha * p)
        if v.sub is not None:
            p = ease_out((lt - 0.4) / 0.7)
            blit(canvas, v.sub, v.sub_cx - v.sub.shape[1] / 2 + dx, v.sub_y + (1 - p) * 24 * k, alpha * p)
        cap = v.caption(lt)
        if cap is not None:
            spr, a, off, hl = cap
            cx, cy = (W - spr.shape[1]) / 2 + dx, v.cap_bottom - spr.shape[0] + off
            blit(canvas, spr, cx, cy, alpha * a)
            if hl is not None:  # phủ chữ màu lên đúng ô của từ đang đọc
                hs, (bx0, bx1, by0, by1) = hl
                blit(canvas, hs[by0:by1, bx0:bx1], cx + bx0, cy + by0, alpha * a)

    def compose(self, layers, t):
        canvas = self.bg.frame(t)
        for i, lt, a, dx in layers:
            self.draw_covers(canvas, i, lt, a, dx)
        self.ff.draw(canvas, t)
        for i, lt, a, dx in layers:
            self.draw_fg(canvas, i, lt, a, dx)
        return canvas

    def render(self, t):
        canvas = self._render_scenes(t)
        if self.logo is not None:
            self.draw_logo(canvas)
        return canvas

    def _render_scenes(self, t):
        sc = self.tl["scenes"]
        total = self.tl["total"]
        if not sc:
            canvas = self.bg.frame(t)
            self.ff.draw(canvas, t)
            return canvas
        t = min(max(t, 0.0), max(total - 1e-3, 0.0))
        act = [i for i, s in enumerate(sc) if s["start"] <= t < s["start"] + s["dur"]] or [len(sc) - 1]
        g = 1.0
        if t < 0.7:
            g *= ease_io(t / 0.7)
        if total - t < 0.9:
            g *= ease_io((total - t) / 0.9)
        if len(act) == 1:
            i = act[0]
            return self.compose([(i, t - sc[i]["start"], g, 0.0)], t)
        A, B = act[0], act[1]
        T = max(sc[A]["T"], 1e-3)
        p = ease_io((t - sc[B]["start"]) / T)
        la, lb = t - sc[A]["start"], t - sc[B]["start"]
        kind = sc[A]["trans"]
        if kind == "fade":
            fa = self.compose([(A, la, g, 0.0)], t)
            fb = self.compose([(B, lb, g, 0.0)], t)
            return cv2.addWeighted(fa, 1 - p, fb, p, 0)
        d = 0.07 * self.W if kind == "slide" else 0.0
        return self.compose([(A, la, g * (1 - p), -p * d), (B, lb, g * p, (1 - p) * d)], t)
