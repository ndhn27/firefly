"""Giọng đọc có dự phòng: nhiều nhà cung cấp (provider) xếp thành một chuỗi, giọng chính hỏng thì tự chuyển sang giọng sau.

Thứ tự mặc định (đổi bằng biến môi trường FFV_TTS, VD `FFV_TTS=piper,edge`):
  edge   Microsoft Edge TTS (thư viện edge-tts). Chất lượng tốt nhất, có mốc thời gian từng từ cho phụ đề. Endpoint KHÔNG chính thức:
         Microsoft có thể đổi hoặc chặn bất cứ lúc nào – đó là lý do có file này.
  piper  Piper chạy ngay trên máy (offline, không gửi chữ đi đâu). Tuỳ chọn: cần chương trình piper + file giọng .onnx, xem README.
  gtts   Google Translate TTS qua thư viện gTTS. Cũng không chính thức, cần internet; chỉ là phương án cuối.

Giọng dự phòng không có mốc từng từ: phụ đề dùng cách căn theo chỗ ngắt hơi (đã có sẵn trong media.py). Cao độ (pitch) chỉ Edge hỗ trợ.
Tên giọng trong dự án vẫn là tên giọng Edge (VD vi-VN-HoaiMyNeural); giọng dự phòng được chọn theo NGÔN NGỮ của tên đó (vi-VN → tiếng Việt).

Module này không import media.py (media.py import module này)."""
import asyncio
import functools
import importlib.util
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import errors as E
import paths

log = logging.getLogger("ffv.tts")
NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}

DEFAULT_ORDER = "edge,piper,gtts"
# Lỗi của chính máy (đầy ổ đĩa, thiếu quyền, hết RAM…): đổi nhà cung cấp không giúp gì nên báo ngay, không chuyển giọng.
FATAL = {"disk_full", "permission", "file_missing", "path_too_long", "out_of_memory", "ffmpeg_missing"}
# Dịch vụ không tới được / từ chối: trong phần còn lại của lượt tạo giọng này khỏi thử lại (mỗi lần thử hỏng tốn vài giây chờ).
DEAD = {"network", "tts_denied"}


class ProviderUnavailable(Exception):
    """Nhà cung cấp này không dùng được lúc này (chưa cài, thiếu file giọng cho ngôn ngữ, ngôn ngữ không hỗ trợ)."""


@dataclass
class Synth:
    path: str            # file âm thanh vừa tạo (mp3 hoặc wav)
    events: list         # [(chữ, bắt đầu, kết thúc)] tính theo audio gốc; [] nếu nhà cung cấp không có mốc
    kind: str            # "word" | "sentence" | None
    engine: str          # tên nhà cung cấp đã dùng
    tempo: float = 1.0   # tốc độ CHƯA được áp dụng (>1 nhanh hơn); media.py nhờ ffmpeg `atempo` khi đổi sang wav


def locale_of(voice):
    """'vi-VN-HoaiMyNeural' -> 'vi-VN'."""
    return "-".join((voice or "").split("-")[:2]) or "vi-VN"


def _has(mod):
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def _tempo(rate):
    """Tốc độ Edge (+/-%) -> hệ số atempo của ffmpeg (0.5–2.0)."""
    try:
        return min(2.0, max(0.5, 1.0 + float(rate) / 100.0))
    except (TypeError, ValueError):
        return 1.0


# ----------------------------------------------------------------------------- Edge TTS
_BOUNDARY = None  # "WordBoundary" / "SentenceBoundary": kiểu mốc dịch vụ trả được (nhớ sau lần dò đầu)


def _edge_stream(text, voice, rate, pitch, out, mode):
    import edge_tts

    async def run():
        kw = dict(rate=f"{int(rate):+d}%", pitch=f"{int(pitch):+d}Hz")
        try:
            comm = edge_tts.Communicate(text, voice, boundary=mode, **kw)
        except TypeError:  # edge-tts cũ (<7) không có tham số boundary, luôn trả WordBoundary
            comm = edge_tts.Communicate(text, voice, **kw)
        audio, ev = bytearray(), []
        async for ch in comm.stream():
            t = ch.get("type")
            if t == "audio":
                audio += ch["data"]
            elif t in ("WordBoundary", "SentenceBoundary"):
                ev.append((ch.get("text", ""), ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7, t))
        Path(out).write_bytes(bytes(audio))
        return ev

    return asyncio.run(run())


def _edge_save(text, voice, rate, pitch, out):
    """Tạo mp3 + mốc thời gian. Thử mốc từng từ trước; dịch vụ không trả thì dùng mốc từng câu;
    cả hai đều không có thì trả [] (phía trên sẽ căn theo chỗ ngắt hơi)."""
    global _BOUNDARY
    modes = [_BOUNDARY] if _BOUNDARY else ["WordBoundary", "SentenceBoundary"]
    ev = []
    for mode in modes:
        ev = _edge_stream(text, voice, rate, pitch, out, mode)
        if ev:
            _BOUNDARY = mode
            break
    kinds = {e[3] for e in ev}
    kind = "word" if kinds == {"WordBoundary"} else "sentence" if ev else None
    return [(t, a, b) for t, a, b, _ in ev], kind


def edge_voices():
    import edge_tts
    return asyncio.run(edge_tts.list_voices())


class EdgeProvider:
    name, label, online = "edge", "Microsoft Edge TTS", True

    def status(self, voice=None):
        return (True, "đã cài edge-tts") if _has("edge_tts") else (False, "chưa cài – pip install edge-tts")

    def synth(self, text, voice, rate, pitch, workdir):
        out = os.path.join(workdir, "edge.mp3")
        events, kind = _edge_save(text, voice, rate, pitch, out)
        if not os.path.exists(out) or os.path.getsize(out) < 200:
            raise E.UserError(*E.MSG["tts_no_audio"], code="tts_no_audio")
        return Synth(out, events, kind, self.name)


# ----------------------------------------------------------------------------- Piper (offline)
def piper_voice_dirs():
    """Nơi tìm file giọng Piper: $FFV_PIPER_VOICES, rồi piper_voices/ trong thư mục dữ liệu (cạnh app.py hoặc cạnh file .exe)."""
    dirs = []
    if os.environ.get("FFV_PIPER_VOICES"):
        dirs.append(Path(os.environ["FFV_PIPER_VOICES"]).expanduser())
    dirs.append(paths.DATA_DIR / "piper_voices")
    return dirs


def piper_models():
    """{tên giọng: đường dẫn .onnx} – chỉ tính giọng có đủ file .onnx.json đi kèm."""
    out = {}
    for d in piper_voice_dirs():
        if d.is_dir():
            for f in sorted(d.glob("*.onnx")):
                if f.with_name(f.name + ".json").is_file():
                    out.setdefault(f.stem, f)
    return out


_QUALITY = ("medium", "high", "low", "x_low")  # chất lượng ưu tiên khi một ngôn ngữ có nhiều giọng


def pick_piper_model(locale, models):
    """Giọng Piper hợp nhất cho locale kiểu Edge ('vi-VN'): đúng vùng trước, cùng ngôn ngữ sau. None nếu không có."""
    want = locale.replace("-", "_").lower()
    lang = want.split("_")[0]
    pool = [n for n in models if n.lower().startswith(want + "-")] or [n for n in models if n.lower().startswith(lang + "_")]

    def rank(n):
        q = next((i for i, k in enumerate(_QUALITY) if n.lower().endswith("-" + k)), len(_QUALITY))
        return q, n
    return models[min(pool, key=rank)] if pool else None


def piper_command():
    """Lệnh chạy Piper dưới dạng list, hoặc None. Luôn chạy như một chương trình riêng (không import) – Piper bản mới dùng giấy phép GPL-3.0.
    Thứ tự: $FFV_PIPER, piper/piper(.exe) trong thư mục dữ liệu, `piper` trong PATH, rồi `python -m piper` (chỉ khi chạy từ mã nguồn)."""
    exe = "piper.exe" if sys.platform == "win32" else "piper"
    cands = []
    if os.environ.get("FFV_PIPER"):
        cands.append(Path(os.environ["FFV_PIPER"]).expanduser())
    cands.append(paths.DATA_DIR / "piper" / exe)
    which = shutil.which("piper")
    if which:
        cands.append(Path(which))
    for c in cands:
        if c.is_file() and _piper_ok((str(c),)):
            return [str(c)]
    if not getattr(sys, "frozen", False) and _has("piper") and _piper_ok((sys.executable, "-m", "piper")):
        return [sys.executable, "-m", "piper"]
    return None


@functools.lru_cache(maxsize=16)
def _piper_ok(cmd):
    """Đúng là Piper đọc văn bản? (trên Linux, `piper` trong PATH có thể là ứng dụng cấu hình chuột cùng tên.)"""
    try:
        r = subprocess.run(list(cmd) + ["--help"], capture_output=True, timeout=30, **NOWIN)
        return b"--model" in (r.stdout + r.stderr)
    except (OSError, subprocess.SubprocessError):
        return False


def piper_status():
    """-> dict(command, models) cho doctor và /api/tts/status."""
    cmd = piper_command()
    return dict(command=cmd, models=sorted(piper_models()))


class PiperProvider:
    name, label, online = "piper", "Piper (offline)", False

    def status(self, voice=None):
        if not piper_command():
            return False, "chưa có chương trình piper – xem README, mục Giọng dự phòng"
        models = piper_models()
        if not models:
            return False, "chưa có file giọng .onnx trong piper_voices/"
        if voice and not pick_piper_model(locale_of(voice), models):
            return False, f"chưa có giọng Piper cho {locale_of(voice)} (đang có: {', '.join(sorted(models))})"
        return True, f"{len(models)} giọng: " + ", ".join(sorted(models))

    def synth(self, text, voice, rate, pitch, workdir):
        ok, why = self.status(voice)
        if not ok:
            raise ProviderUnavailable(why)
        cmd, model = piper_command(), pick_piper_model(locale_of(voice), piper_models())
        out = os.path.join(workdir, "piper.wav")
        length = min(2.0, max(0.5, 1.0 / _tempo(rate)))  # length_scale > 1 là chậm hơn
        args = cmd + ["--model", str(model), "--output_file", out, "--length_scale", f"{length:.3f}"]
        line = " ".join(text.split())  # mỗi dòng stdin là một câu; ngắt dòng giữa chừng sẽ cắt câu
        try:
            r = subprocess.run(args, input=line.encode("utf-8"), capture_output=True, timeout=max(90, len(line) * 0.5), **NOWIN)
        except FileNotFoundError as e:
            raise ProviderUnavailable(f"không chạy được piper ({e})")
        if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 200:
            raise RuntimeError("piper không tạo được âm thanh: " + r.stderr.decode("utf-8", "ignore").strip()[-300:])
        return Synth(out, [], None, self.name)


# ----------------------------------------------------------------------------- gTTS (Google Translate, cần internet)
class GttsProvider:
    name, label, online = "gtts", "Google gTTS", True

    def _lang(self, voice):
        from gtts.lang import tts_langs
        langs, loc = tts_langs(), locale_of(voice)
        for c in (loc, loc.split("-")[0]):
            if c in langs:
                return c
        raise ProviderUnavailable(f"gTTS không hỗ trợ ngôn ngữ {loc}")

    def status(self, voice=None):
        if not _has("gtts"):
            return False, "chưa cài – pip install gTTS"
        if voice:
            try:
                self._lang(voice)
            except ProviderUnavailable as e:
                return False, str(e)
        return True, "đã cài gTTS"

    def synth(self, text, voice, rate, pitch, workdir):
        import gtts
        out = os.path.join(workdir, "gtts.mp3")
        gtts.gTTS(text, lang=self._lang(voice)).save(out)
        if not os.path.exists(out) or os.path.getsize(out) < 200:
            raise E.UserError(*E.MSG["tts_no_audio"], code="tts_no_audio")
        return Synth(out, [], None, self.name, tempo=_tempo(rate))  # gTTS không có tham số tốc độ -> ffmpeg chỉnh sau


REGISTRY = {"edge": EdgeProvider, "piper": PiperProvider, "gtts": GttsProvider}


def default_providers(order=None):
    names = [n.strip().lower() for n in (order or os.environ.get("FFV_TTS") or DEFAULT_ORDER).split(",")]
    seen, out = set(), []
    for n in names:
        if n in REGISTRY and n not in seen:
            seen.add(n)
            out.append(REGISTRY[n]())
    return out or [EdgeProvider()]


class Chain:
    """Thử lần lượt từng nhà cung cấp. Dùng MỘT Chain cho cả lượt tạo giọng (nhiều cảnh) để nhớ dịch vụ nào đã hỏng
    và các cảnh sau khỏi chờ thử lại; `used` đếm số cảnh mỗi nhà cung cấp đã đọc, `summary()` kể lại cho người dùng."""

    def __init__(self, providers=None, fallback=True):
        self.providers = providers or default_providers()
        self.fallback = fallback
        self.dead = {}  # tên -> mã lỗi: dịch vụ đã hỏng trong lượt này
        self.used = {}  # tên -> số cảnh đã đọc

    @property
    def primary(self):
        return self.providers[0].name

    def synth(self, text, voice, rate, pitch, workdir):
        first_exc = None
        for p in (self.providers if self.fallback else self.providers[:1]):
            if p.name in self.dead:
                continue
            ok, why = p.status(voice)
            if not ok:
                log.debug("Bỏ qua giọng %s: %s", p.name, why)
                continue
            try:
                res = p.synth(text, voice, rate, pitch, workdir)
            except Exception as e:  # noqa
                code = E.classify(e)[0]
                if code in FATAL:
                    raise
                log.warning("Giọng %s lỗi [%s]: %s: %s", p.name, code, type(e).__name__, str(e)[:300])
                first_exc = first_exc or e
                if code in DEAD:
                    self.dead[p.name] = code
                continue
            self.used[p.name] = self.used.get(p.name, 0) + 1
            if p.name != self.primary:
                log.warning("Dùng giọng dự phòng %s (giọng chính %s lỗi)", p.name, self.primary)
            return res
        if first_exc is not None:
            raise first_exc  # giữ nguyên lỗi của giọng chính để E.explain() nói đúng nguyên nhân
        raise E.UserError("Không có giọng đọc nào dùng được trên máy này." if self.fallback else
                          "Giọng chính không dùng được và chế độ giọng dự phòng đang tắt.",
                          "Cài edge-tts (pip install -r requirements.txt) hoặc làm theo mục Giọng dự phòng trong README, rồi thử lại.",
                          code="tts_none")

    def summary(self):
        """Câu báo cho người dùng nếu có cảnh phải dùng giọng dự phòng; None nếu mọi cảnh dùng giọng chính."""
        fb = {k: v for k, v in self.used.items() if k != self.primary}
        if not fb:
            return None
        label = {p.name: p.label for p in self.providers}
        what = ", ".join(f"{label.get(k, k)}: {v} cảnh" for k, v in fb.items())
        return (f"Giọng chính ({label.get(self.primary, self.primary)}) bị lỗi nên có cảnh đọc bằng giọng dự phòng ({what}). "
                "Giọng dự phòng nghe khác giọng chính. Khi giọng chính chạy lại, bấm “Tạo lại giọng dự phòng” trong Cài đặt để đồng nhất.")


def make_chain(proj=None):
    """Chain theo dự án: `voice.fallback` = false thì chỉ dùng giọng chính (mặc định bật)."""
    v = (proj or {}).get("voice") or {}
    return Chain(fallback=bool(v.get("fallback", True)))


def status(voice=None):
    """Tình trạng từng nhà cung cấp (không gọi mạng) cho giao diện và doctor."""
    order = default_providers()
    out = []
    for i, p in enumerate(order):
        ok, detail = p.status(voice)
        out.append(dict(name=p.name, label=p.label, online=p.online, ok=ok, detail=detail, primary=i == 0))
    return out
