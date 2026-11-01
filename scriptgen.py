"""Kịch bản bằng AI chạy ngay trên máy (Ollama).

Luồng: dựng lời nhắc -> hỏi Ollama (stream, ép định dạng JSON theo schema) -> tách JSON -> kiểm bằng pydantic ->
nếu hỏng (JSON lỗi, thiếu trường, quá dài, bị cắt giữa chừng, độ dài video lệch quá xa yêu cầu, hoặc nội dung mắc lỗi hay gặp của mô hình nhỏ:
lẫn chữ ngôn ngữ khác, lặp câu, còn lời dẫn thừa — xem review()) thì gửi lại kèm lý do để mô hình sửa, tối đa `attempts` lần. Kết quả chỉ gồm `title` + `narration` mỗi cảnh, đúng bằng những gì chế độ dán kịch bản hiểu,
nên đầu ra đi thẳng vào ô "Dán kịch bản" để người dùng xem lại và sửa trước khi tạo cảnh.

Chỉ dùng thư viện chuẩn (http.client) + pydantic; không thêm thư viện HTTP.
"""
import http.client
import json
import math
import os
import queue
import re
import socket
import statistics
import threading
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

import render as R

DEFAULT_URL = "http://127.0.0.1:11434"
MAX_SCENES = 30
TITLE_MAX = 90
NARR_MIN, NARR_MAX = 8, 900
TOPIC_MAX = 8000
DURATIONS = (30, 60, 90, 120, 180)
NUM_CTX, NUM_PREDICT = 8192, 4096
OFF_TARGET = (0.5, 1.8)  # độ dài video ước lượng / độ dài yêu cầu: ngoài khoảng này (và còn lượt thử) thì bắt viết lại

LANGS = {"vi": "tiếng Việt", "en": "tiếng Anh", "ja": "tiếng Nhật", "ko": "tiếng Hàn", "zh": "tiếng Trung",
         "fr": "tiếng Pháp", "de": "tiếng Đức", "es": "tiếng Tây Ban Nha"}
CHARS_PER_WORD = {"vi": 4.6, "en": 5.9}  # ký tự (gồm dấu cách) trung bình mỗi từ; ngôn ngữ khác dùng 5.5
TONES = {
    "explain": "giải thích dễ hiểu, thân thiện, như đang trò chuyện với người chưa biết gì về chủ đề",
    "story": "kể chuyện lôi cuốn, có mở đầu gợi tò mò và kết thúc đọng lại",
    "news": "ngắn gọn, nhanh, dồn dập như bản tin; đi thẳng vào ý chính",
    "fun": "vui vẻ, hóm hỉnh, hơi tếu một chút nhưng thông tin vẫn chính xác",
}


class Cancelled(Exception):
    pass


class ScriptError(Exception):
    """Lỗi đã có thông báo tiếng Việt cho người dùng."""


class OllamaUnreachable(ScriptError):
    pass


class FormatUnsupported(Exception):
    """Ollama bản cũ không hiểu schema trong `format` (chỉ nhận "json")."""


# ----------------------------------------------------------------------------- làm sạch + schema
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200d\u200b]")
_BULLET = re.compile(r"^\s*(?:#+\s*|[-*•·]\s+|\d{1,2}[.)]\s+)")
_SCENE_PREFIX = re.compile(r"^\s*(?:cảnh|scene)\s*\d+\s*[:.\-–—]\s*", re.I)
_THINK = re.compile(r"<think>.*?(?:</think>|$)", re.S | re.I)


def clean_text(s, title=False):
    """Một dòng văn bản sạch: bỏ emoji, markdown, gạch đầu dòng, dấu # đầu dòng (nếu để lại sẽ bị chế độ dán hiểu nhầm
    thành tiêu đề), ngắt dòng. Giọng đọc và phụ đề đều đọc thẳng chuỗi này."""
    s = _EMOJI.sub("", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s, flags=re.S)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", s, flags=re.S)
    s = s.replace("`", "")
    lines = [_BULLET.sub("", ln).strip() for ln in s.splitlines()]
    s = re.sub(r"\s+", " ", " ".join(ln for ln in lines if ln)).strip()
    if title:
        s = _SCENE_PREFIX.sub("", s).strip().strip("\"'“”").rstrip(".").strip()
    return s


class SceneOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field(default="", max_length=TITLE_MAX)
    narration: str = Field(min_length=NARR_MIN, max_length=NARR_MAX)

    @field_validator("title", "narration", mode="before")
    @classmethod
    def _clean(cls, v, info):
        if v is None:
            return ""
        if not isinstance(v, str):
            raise ValueError("phải là chuỗi chữ")
        return clean_text(v, title=info.field_name == "title")


class ScriptOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    scenes: list[SceneOut] = Field(min_length=1, max_length=MAX_SCENES)

    @model_validator(mode="before")
    @classmethod
    def _bare_list(cls, v):
        return {"scenes": v} if isinstance(v, list) else v  # mô hình trả thẳng mảng cảnh, không bọc {"scenes": ...}


# Viết tay (không dùng model_json_schema) vì nó sinh $defs/$ref, trình ràng buộc định dạng của Ollama xử lý kém hơn schema phẳng.
SCHEMA = {
    "type": "object",
    "properties": {"scenes": {"type": "array", "minItems": 1, "maxItems": MAX_SCENES, "items": {
        "type": "object",
        "properties": {"title": {"type": "string"}, "narration": {"type": "string"}},
        "required": ["title", "narration"]}}},
    "required": ["scenes"],
}


class BadOutput(Exception):
    """Đầu ra của mô hình không dùng được; `feedback` là lời nhắn gửi lại cho mô hình, `echo` = có kèm lại bản hỏng không."""

    def __init__(self, feedback, echo=True):
        super().__init__(feedback)
        self.feedback, self.echo = feedback, echo


def extract_json(text):
    """Lấy JSON từ đầu ra thô: bỏ khối <think>, bỏ rào ```json, và nếu còn chữ thừa quanh thì cắt lấy cụm {...} / [...]."""
    text = _THINK.sub("", text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S | re.I)
    if m:
        text = m.group(1).strip()
    if not text:
        raise BadOutput("Bạn trả về nội dung trống.", echo=False)
    try:
        return json.loads(text)
    except ValueError as e:
        err = e
    spans = [(text.find(o), o, c) for o, c in (("{", "}"), ("[", "]")) if text.find(o) >= 0]
    for i, o, c in sorted(spans):
        j = text.rfind(c)
        if j > i:
            try:
                return json.loads(text[i:j + 1])
            except ValueError as e:
                err = e
    raise BadOutput(f"Kết quả không phải JSON hợp lệ ({getattr(err, 'msg', err)}, vị trí {getattr(err, 'pos', '?')}).")


_ERR_VI = {
    "missing": "thiếu trường này",
    "string_too_long": lambda c: f"quá dài (tối đa {c.get('max_length')} ký tự)",
    "string_too_short": lambda c: "để trống hoặc quá ngắn" + (f" (tối thiểu {c['min_length']} ký tự)" if c.get("min_length") else ""),
    "too_long": lambda c: f"quá nhiều cảnh (tối đa {c.get('max_length')})",
    "too_short": "chưa có cảnh nào",
    "string_type": "phải là chuỗi chữ",
    "list_type": "phải là một mảng",
    "dict_type": "phải là một đối tượng JSON",
    "model_type": "phải là một đối tượng JSON",
}


def explain_errors(e, limit=6):
    out = []
    for er in e.errors()[:limit]:
        loc = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in er["loc"]).lstrip(".") or "(gốc)"
        r = _ERR_VI.get(er["type"])
        out.append(f"- {loc}: " + (r(er.get("ctx") or {}) if callable(r) else r or er["msg"]))
    if len(e.errors()) > limit:
        out.append(f"- … và {len(e.errors()) - limit} lỗi khác")
    return "\n".join(out)


def parse_script(text):
    data = extract_json(text)
    try:
        return ScriptOut.model_validate(data)
    except ValidationError as e:
        raise BadOutput("JSON đúng cú pháp nhưng sai cấu trúc:\n" + explain_errors(e))


# ----------------------------------------------------------------------------- kiểm tra nội dung
# Chất lượng chữ do mô hình quyết định nên không đo được "hay" hay "dở". Nhưng mô hình nhỏ chạy trên máy hay mắc vài lỗi đoán trước được;
# review() bắt những lỗi đó. Mức `bad` = đáng viết lại (gửi lại cho mô hình kèm cách sửa, tính vào điểm chọn bản tốt nhất);
# mức `warn` = chỉ báo cho người dùng biết chỗ cần xem lại. `fatal` = hết lượt thử vẫn còn thì báo lỗi thay vì đưa bản vô dụng.
LATIN_LANGS = ("vi", "en", "fr", "de", "es")
_FOREIGN = re.compile("[\u0400-\u04FF\u0590-\u05FF\u0600-\u06FF\u0900-\u097F\u0E00-\u0E7F\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uAC00-\uD7AF]")
_VI_MARKS = frozenset("ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ")
_META = re.compile(r"^\s*(?:dưới đây là|sau đây là|đây là (?:một )?(?:kịch bản|bản nháp)|chắc chắn rồi|tất nhiên rồi|here is|here's|sure[,!]|certainly)", re.I)
_PLACEHOLDER = re.compile(r"\[[^\]]{1,40}\]|lorem ipsum|\bTODO\b|\bTBD\b|<[^>\s][^>]{0,30}>", re.I)
_URL = re.compile(r"https?://|www\.|\b[a-z0-9-]{2,}\.(?:com|vn|org|net|io|dev)\b", re.I)
_NUM = re.compile(r"\d[\d.,]*\d%?|\d%?")
_SENT = re.compile(r"(?<=[.!?…])\s+")
LOOP_MIN = 4          # một câu xuất hiện từng này lần trong cả kịch bản = mô hình đang lặp
SPOKEN_WORDS = {"vi": 40}  # quá từng này từ trong một câu thì khó đọc thành tiếng (ngôn ngữ khác dùng 30)


def _scene_names(ids, cap=4):
    ids = sorted(set(ids))
    return "Cảnh " + ", ".join(map(str, ids[:cap])) + (f" và {len(ids) - cap} cảnh khác" if len(ids) > cap else "")


def _norm(s):
    return " ".join(re.sub(r"[^\w\s]", " ", s.lower()).split())


def review(scenes, topic="", lang="vi"):
    """-> list[dict(code, level, fatal, msg, fix, scenes)]. `msg` viết cho người dùng; `fix` là lời dặn gửi lại cho mô hình (chỉ mục `bad`);
    `scenes` là số thứ tự cảnh (từ 1) liên quan. Không kiểm sự thật, chỉ kiểm những dấu hiệu máy móc bắt được."""
    out = []
    L = LANGS.get(lang, "ngôn ngữ yêu cầu")

    def add(code, level, msg, fix="", ids=(), fatal=False):
        out.append(dict(code=code, level=level, fatal=fatal, msg=msg, fix=fix, scenes=sorted(set(ids))))

    texts = [(s.get("title", "") + " " + s["narration"]).strip() for s in scenes]
    narr = [s["narration"] for s in scenes]

    # 1. chữ của ngôn ngữ khác lẫn vào (mô hình Qwen hay chen chữ Hán vào tiếng Việt); giọng đọc sẽ đọc sai hoặc bỏ qua
    if lang in LATIN_LANGS:
        hit, found, share = [], [], 0.0
        for i, t in enumerate(texts, 1):
            f = _FOREIGN.findall(t)
            if f:
                hit.append(i)
                found += f
                share = max(share, len(f) / max(1, sum(c.isalpha() for c in t)))
        if hit:
            sample = "".join(dict.fromkeys(found))[:6]
            add("foreign_script", "bad", f"{_scene_names(hit)} lẫn chữ không phải {L} (“{sample}”): giọng đọc sẽ đọc sai hoặc bỏ qua.",
                f"{_scene_names(hit)} có chữ không phải {L} (“{sample}”). Chỉ viết bằng {L}, không chen chữ Hán, Nga, Thái… vào lời đọc.", hit, fatal=share >= 0.2)
    # 2. tiếng Việt không dấu hoặc thực chất là tiếng Anh
    if lang == "vi":
        joined = " ".join(narr).lower()
        letters = sum(c.isalpha() for c in joined)
        if letters >= 80 and sum(c in _VI_MARKS for c in joined) / letters < 0.08:
            add("not_vietnamese", "bad", "Lời đọc có vẻ không phải tiếng Việt có dấu (rất ít chữ có dấu).",
                "Lời đọc phải là tiếng Việt CÓ DẤU đầy đủ, không viết không dấu và không viết bằng tiếng Anh.", range(1, len(scenes) + 1), fatal=True)
    # 3. lặp: một câu lặp nhiều lần (mô hình kẹt vòng lặp) hoặc hai cảnh y hệt nhau
    sents = Counter(n for t in narr for x in _SENT.split(t) if len(n := _norm(x)) >= 12)
    loops = [x for x, c in sents.items() if c >= LOOP_MIN]
    if loops:
        ids = [i for i, t in enumerate(narr, 1) if any(_norm(x) in loops for x in _SENT.split(t))]
        add("loop", "bad", f"Một câu bị lặp lại nhiều lần ({_scene_names(ids)}): “{loops[0][:50]}…”.",
            f"Câu “{loops[0][:60]}” bị lặp lại nhiều lần. Mỗi câu chỉ xuất hiện một lần; mỗi cảnh phải có ý mới.", ids)
    seen = {}
    for i, t in enumerate(narr, 1):
        seen.setdefault(_norm(t), []).append(i)
    dups = [v for v in seen.values() if len(v) > 1]
    if dups:
        ids = [i for v in dups for i in v]
        add("duplicate_scene", "bad", f"{_scene_names(ids)} có lời đọc giống hệt nhau.", f"{_scene_names(ids)} có lời đọc giống hệt nhau. Mỗi cảnh phải khác nhau.", ids)
    # 4. lời dẫn thừa, chỗ giữ chỗ chưa điền, địa chỉ web
    meta = [i for i, t in enumerate(narr, 1) if _META.search(t)]
    hold = [i for i, t in enumerate(texts, 1) if _PLACEHOLDER.search(t)]
    if meta or hold:
        ids = meta + hold
        add("boilerplate", "bad", f"{_scene_names(ids)} còn lời dẫn của AI hoặc chỗ giữ chỗ chưa điền (VD “Dưới đây là…”, “[tên]”).",
            f"{_scene_names(ids)} còn lời dẫn của người trả lời hoặc chỗ giữ chỗ như “[…]”. Chỉ viết đúng lời đọc của video.", ids)
    urls = [i for i, t in enumerate(narr, 1) if _URL.search(t)]
    if urls:
        add("url", "warn", f"{_scene_names(urls)} có địa chỉ web: giọng đọc sẽ đọc từng chữ.", ids=urls)
    # 5. con số/năm: có thể là mô hình tự bịa; nếu người dùng dán tư liệu thì đối chiếu với tư liệu
    src = {re.sub(r"\D", "", t) for t in _NUM.findall(topic or "")}
    nums, ids = [], []
    for i, t in enumerate(narr, 1):
        for tok in _NUM.findall(t):
            d = re.sub(r"\D", "", tok)
            if len(d) >= 2 and d not in src and tok not in nums:
                nums.append(tok)
                ids.append(i)
    if nums:
        shown = ", ".join(nums[:6]) + (f" … (+{len(nums) - 6})" if len(nums) > 6 else "")
        has_src = len((topic or "").strip()) >= 200
        add("numbers", "warn", ("Con số/năm KHÔNG có trong tư liệu bạn dán, có thể AI tự thêm: " if has_src else "AI tự đưa ra các con số/năm, hãy kiểm chứng: ") + shown + ".", ids=ids)
    # 6. độ dài các cảnh lệch nhau quá nhiều
    if len(narr) >= 4:
        lens = [len(t) for t in narr]
        med = statistics.median(lens)
        long_ = [i for i, n in enumerate(lens, 1) if n > 2.5 * med and n - med > 80]
        short = [i for i, n in enumerate(lens, 1) if n < 0.3 * med and med - n > 80]
        if long_ or short:
            parts = ([f"{_scene_names(long_)} dài hơn hẳn các cảnh khác"] if long_ else []) + ([f"{_scene_names(short)} ngắn hơn hẳn"] if short else [])
            add("unbalanced", "warn", "; ".join(parts) + " nên thời lượng các cảnh sẽ lệch.", ids=long_ + short)
    # 7. câu quá dài để đọc thành tiếng một hơi
    cap = SPOKEN_WORDS.get(lang, 30)
    longs = [(i, len(x.split())) for i, t in enumerate(narr, 1) for x in _SENT.split(t) if len(x.split()) > cap]
    if longs:
        add("long_sentence", "warn", f"{_scene_names([i for i, _ in longs])} có câu dài tới {max(n for _, n in longs)} từ, khó đọc thành tiếng; nên tách câu.", ids=[i for i, _ in longs])
    return out


# ----------------------------------------------------------------------------- kế hoạch độ dài + lời nhắc
def plan(duration, lang="vi"):
    """-> (số cảnh nên viết, số từ lời đọc mỗi cảnh) để cả video ra khoảng `duration` giây theo đúng công thức ước lượng của renderer."""
    D = max(15, min(int(duration or 60), 300))
    n = max(3, min(round(D / 10), 20))
    chars = (D + (n - 1) * R.TRANS - n * (R.PRE + R.POST + 0.3)) * 14.5  # ngược lại với R.timeline khi chưa có giọng thật
    words = max(10, round(chars / n / CHARS_PER_WORD.get(lang, 5.5)))
    return n, words


def est_seconds(scenes):
    """Ước lượng thời lượng video bằng chính R.timeline (chưa có giọng thật nên dùng ~14,5 ký tự/giây)."""
    sc = [dict(narration=s["narration"], voice=True, transition="fade") for s in scenes]
    return R.timeline(dict(scenes=sc))["total"]


def build_messages(topic, duration, tone, lang, notes=""):
    n, words = plan(duration, lang)
    L = LANGS.get(lang, "ngôn ngữ của chủ đề bên dưới")
    system = (
        "Bạn là biên kịch cho video giải thích ngắn có giọng đọc. Chỉ trả về MỘT đối tượng JSON, không kèm lời giải thích, không rào markdown.\n"
        'Định dạng: {"scenes":[{"title":"...","narration":"..."}]}\n'
        "- title: tiêu đề ngắn hiện trên màn hình (tối đa 8 từ), không đánh số, không emoji.\n"
        "- narration: lời đọc của cảnh, văn nói tự nhiên, câu ngắn, một đoạn liền (không xuống dòng, không gạch đầu dòng, "
        "không markdown, không emoji, không chú thích trong ngoặc, không đọc địa chỉ web).\n"
        "- Cảnh đầu mở bằng một câu gây tò mò; cảnh cuối chốt lại ý chính.\n"
        "- Không bịa số liệu, năm hay tên riêng: chỉ nêu khi có trong tư liệu hoặc khi chắc chắn đúng; không chắc thì nói chung chung.\n"
        f"- Viết bằng {L}." + (" Không chen chữ Hán, Nga, Thái… vào lời đọc." if lang in LATIN_LANGS else ""))
    user = (f"Chủ đề hoặc tư liệu:\n{topic.strip()[:TOPIC_MAX]}\n\n"
            f"Giọng điệu: {TONES.get(tone, TONES['explain'])}.\n"
            f"Khoảng {n} cảnh, mỗi cảnh khoảng {words} từ lời đọc (cả video khi đọc dài khoảng {int(duration)} giây).")
    if notes.strip():
        user += f"\nYêu cầu thêm: {notes.strip()[:500]}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def to_paste_text(scenes):
    """Đúng định dạng ô "Dán kịch bản": cảnh cách nhau một dòng trống, dòng đầu `# tiêu đề` (nếu có), phần còn lại là lời đọc."""
    return "\n\n".join((f"# {s['title']}\n" if s["title"] else "") + s["narration"] for s in scenes)


# ----------------------------------------------------------------------------- Ollama
def normalize_url(url):
    """Nhận cả dạng OLLAMA_HOST kiểu `0.0.0.0:11434` hay `localhost`; trả về http(s)://host:port không có / cuối."""
    s = (url or "").strip() or DEFAULT_URL
    bare = "://" not in s
    if bare:
        s = "http://" + s
    try:
        u = urlparse(s)
        port = u.port
    except ValueError:
        raise ScriptError("Địa chỉ Ollama không hợp lệ. Dạng đúng: http://127.0.0.1:11434")
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ScriptError("Địa chỉ Ollama phải có dạng http://127.0.0.1:11434")
    host = "127.0.0.1" if u.hostname in ("0.0.0.0", "::") else u.hostname
    if ":" in host:
        host = f"[{host}]"
    port = port or (11434 if bare else None)  # `localhost` trần = cổng mặc định của Ollama; có ghi http(s):// mà không ghi cổng thì để 80/443
    return f"{u.scheme}://{host}" + (f":{port}" if port else "") + u.path.rstrip("/")


def _open(base, timeout):
    u = urlparse(base)
    cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
    return cls(u.hostname, u.port, timeout=timeout), u.path.rstrip("/")


def _unreachable(base):
    return OllamaUnreachable(f"Không kết nối được Ollama tại {base}. Mở ứng dụng Ollama (hoặc chạy `ollama serve`) rồi thử lại.")


def list_models(base, timeout=3.0):
    """-> [{name, size, params?, small?}] các mô hình đã tải về Ollama (bỏ mô hình embedding vì không viết chữ được)."""
    conn, prefix = _open(base, timeout)
    try:
        conn.request("GET", prefix + "/api/tags")
        r = conn.getresponse()
        body = r.read()
        if r.status != 200:
            raise ScriptError(f"Ollama trả lỗi {r.status} khi liệt kê mô hình.")
        items = json.loads(body).get("models") or []
    except (OSError, http.client.HTTPException):
        raise _unreachable(base)
    except ValueError:
        raise ScriptError(f"{base} có phản hồi nhưng không giống Ollama.")
    finally:
        conn.close()
    out = [dict(name=m.get("name") or m.get("model"), size=m.get("size", 0), **_params(m)) for m in items if isinstance(m, dict)]
    return sorted((m for m in out if m["name"] and "embed" not in m["name"].lower()), key=lambda m: m["name"])


SMALL_B = 3.5  # dưới ngần này (tỉ tham số) mô hình thường viết tiếng Việt kém, hay lẫn ngôn ngữ khác


def _params(m):
    """Ollama báo `details.parameter_size` kiểu "7.6B"/"494M" -> dict(params="7.6B", small=bool); không báo thì {} (không đoán)."""
    ps = str((m.get("details") or {}).get("parameter_size") or "").strip()
    mt = re.match(r"^([\d.]+)\s*([BM])$", ps, re.I)
    if not mt:
        return {}
    try:
        b = float(mt.group(1)) / (1 if mt.group(2).upper() == "B" else 1000)
    except ValueError:
        return {}
    return dict(params=ps, small=b < SMALL_B)


def _abort(conn):
    """Đóng kết nối, và (nơi hệ điều hành cho phép: Linux, macOS) đánh thức luôn luồng đang kẹt trong lệnh đọc."""
    try:
        conn.sock.shutdown(socket.SHUT_RDWR)
    except (OSError, AttributeError):
        pass
    conn.close()


def chat_stream(base, body, cancel=None, on_chunk=None, idle_timeout=300):
    """POST /api/chat dạng stream (từng dòng JSON). -> (toàn bộ chữ, done_reason).
    Việc đọc mạng chạy ở một luồng riêng; luồng gọi chỉ chờ hàng đợi và hỏi `cancel()` mỗi 0,3 giây rồi bỏ luồng đọc lại (daemon) khi bị huỷ.
    Không dựa vào việc ngắt socket từ luồng khác để đánh thức lệnh đọc đang chờ (VD mô hình đang nạp, chưa nhả chữ nào): shutdown()
    làm được trên Linux/macOS nhưng không làm được trên Windows, nơi lệnh đọc nằm chờ đến khi máy chủ gửi gì đó (CI: đúng 30 giây)."""
    conn, prefix = _open(base, idle_timeout)
    q = queue.Queue()

    def pump():
        try:
            conn.request("POST", prefix + "/api/chat", json.dumps(body), {"Content-Type": "application/json"})
            r = conn.getresponse()
            if r.status != 200:
                msg = r.read().decode("utf-8", "ignore")
                try:
                    msg = json.loads(msg).get("error") or msg
                except ValueError:
                    pass
                raise _http_error(r.status, str(msg), body)
            reason = None
            while True:
                line = r.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if obj.get("error"):
                    raise _http_error(500, str(obj["error"]), body)
                piece = (obj.get("message") or {}).get("content") or ""
                if piece:
                    q.put(("piece", piece))
                if obj.get("done"):
                    reason = obj.get("done_reason")
                    break
            q.put(("done", reason))
        except Exception as e:  # noqa - chuyển hết sang luồng gọi xử lý, không để rơi vào excepthook của luồng
            q.put(("error", e))

    threading.Thread(target=pump, daemon=True, name="ollama-stream").start()
    parts, reason, size = [], None, 0
    try:
        while True:
            if cancel and cancel():
                raise Cancelled()
            try:
                kind, val = q.get(timeout=0.3)
            except queue.Empty:
                continue
            if kind == "piece":
                parts.append(val)
                size += len(val)
                if on_chunk:
                    on_chunk(size)
            elif kind == "done":
                reason = val
                break
            else:
                if not isinstance(val, (OSError, http.client.HTTPException, ValueError)):
                    raise val
                if cancel and cancel():
                    raise Cancelled()
                if not parts:
                    if isinstance(val, TimeoutError):
                        raise ScriptError(f"Ollama không phản hồi sau {idle_timeout // 60} phút. Mô hình có thể quá nặng cho máy, thử mô hình nhỏ hơn.")
                    raise _unreachable(base)
                reason = "interrupted"  # đứt giữa chừng: trả phần đã nhận, bước kiểm tra JSON sẽ bắt thử lại
                break
    finally:
        _abort(conn)
    if cancel and cancel():
        raise Cancelled()
    return "".join(parts), reason


def _http_error(status, msg, body):
    low = msg.lower()
    if status == 404 or "not found" in low:
        m = body.get("model", "")
        return ScriptError(f"Ollama chưa có mô hình “{m}”. Chạy trong cửa sổ lệnh: ollama pull {m}")
    if status == 400 and isinstance(body.get("format"), dict) and "format" in low:
        return FormatUnsupported(msg)
    return ScriptError(f"Ollama báo lỗi: {msg}")


# ----------------------------------------------------------------------------- tạo kịch bản
def generate(base, model, topic, *, duration=60, tone="explain", lang="vi", notes="", attempts=3, cancel=None, progress=None):
    """-> dict(scenes=[{title, narration}], attempts, model, est_seconds, text). Ném ScriptError / Cancelled."""
    topic = (topic or "").strip()
    if len(topic) < 3:
        raise ScriptError("Hãy nhập chủ đề (hoặc dán tư liệu) để AI viết kịch bản.")
    if not model:
        raise ScriptError("Chưa chọn mô hình. Chạy `ollama pull <tên mô hình>` rồi bấm làm mới danh sách.")
    duration = max(15, min(int(duration or 60), 300))
    n_scenes, _ = plan(duration, lang)
    msgs = build_messages(topic, duration, tone, lang, notes)
    expected = duration * 14.5 + n_scenes * 60  # số ký tự JSON dự kiến, chỉ để vẽ thanh tiến độ
    fmt, best, last = SCHEMA, None, ""
    k = 0
    while k < attempts:
        k += 1
        if cancel and cancel():
            raise Cancelled()
        body = dict(model=model, messages=msgs, stream=True, format=fmt,
                    options=dict(temperature=0.7 if k == 1 else 0.3, num_ctx=NUM_CTX, num_predict=NUM_PREDICT))
        try:
            text, reason = chat_stream(base, body, cancel, (lambda n, k=k: progress and progress(k, attempts, min(n / expected, 0.97))))
        except FormatUnsupported:
            fmt, k = "json", k - 1  # Ollama cũ: chỉ ép "json" chung chung, không tính là một lần thử
            continue
        try:
            if reason == "length":
                raise BadOutput(f"Câu trả lời bị cắt giữa chừng vì quá dài. Hãy viết ngắn gọn hơn, tối đa {n_scenes + 2} cảnh.", echo=False)
            sc = [s.model_dump() for s in parse_script(text).scenes]
            secs = est_seconds(sc)
            ratio = secs / duration
            on_target = OFF_TARGET[0] <= ratio <= OFF_TARGET[1]
            issues = review(sc, topic, lang)
            bad = [i for i in issues if i["level"] == "bad"]
            # lỗi nặng (vô dụng) thua lỗi thường, lỗi nội dung thua lệch độ dài; cùng loại thì bản gần mức yêu cầu hơn thắng
            score = (any(i["fatal"] for i in bad), bool(bad), not on_target, abs(math.log(ratio)))
            if best is None or score < best[4]:
                best = (sc, ratio, secs, k, score, issues)
            problems = []
            if not on_target:
                problems.append(f"Kịch bản đọc xong chỉ khoảng {secs:.0f} giây trong khi cần khoảng {duration} giây. "
                                + ("Hãy viết dài hơn: thêm ý và thêm cảnh." if ratio < 1 else "Hãy viết ngắn lại: bớt ý và bớt cảnh."))
            if bad:
                problems.append("Nội dung còn lỗi:\n" + "\n".join("- " + i["fix"] for i in bad))
            if problems and k < attempts:
                raise BadOutput("\n".join(problems))
            break
        except BadOutput as e:
            last = e.feedback.splitlines()[0]
            if e.echo and text.strip():
                msgs.append({"role": "assistant", "content": text[:6000]})
            msgs.append({"role": "user", "content": e.feedback + "\nHãy trả lại TOÀN BỘ JSON đúng định dạng, không thêm chữ nào khác."})
    if best is None:
        raise ScriptError(f"Mô hình “{model}” trả kết quả không dùng được {attempts} lần liền ({last}). "
                          "Thử mô hình lớn hơn, hoặc rút ngắn chủ đề rồi bấm tạo lại.")
    sc, _, secs, used, _, issues = best
    fatal = [i for i in issues if i["fatal"]]
    if fatal:  # bản tốt nhất trong các lần thử vẫn vô dụng (sai ngôn ngữ): đưa ra chỉ tốn thời gian người dùng sửa
        raise ScriptError(f"Mô hình “{model}” viết sai ngôn ngữ {attempts} lần liền ({fatal[0]['msg']}) "
                          "Mô hình nhỏ thường yếu về tiếng Việt: thử mô hình lớn hơn (từ khoảng 7B tham số trở lên) rồi bấm tạo lại.")
    return dict(scenes=sc, attempts=used, model=model, est_seconds=round(secs, 1), text=to_paste_text(sc),
                warnings=[dict(code=i["code"], level=i["level"], msg=i["msg"], scenes=i["scenes"]) for i in issues],
                topic_cut=len(topic) > TOPIC_MAX)  # tư liệu dài quá bị cắt ở TOPIC_MAX ký tự: báo để người dùng biết AI chưa đọc hết


# ----------------------------------------------------------------------------- cấu hình (theo máy, không nằm trong dự án)
def load_config(path):
    cfg = {}
    try:
        d = json.loads(Path(path).read_text("utf-8"))
        cfg = d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        pass
    url = cfg.get("url") or os.environ.get("OLLAMA_HOST") or DEFAULT_URL
    try:
        url = normalize_url(url)
    except ScriptError:
        url = DEFAULT_URL
    return dict(url=url, model=cfg.get("model") or os.environ.get("FFV_OLLAMA_MODEL") or "")


def save_config(path, url, model):
    cfg = dict(url=normalize_url(url), model=(model or "").strip())
    p = Path(path)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, p)
    return cfg
