"""Giọng đọc (qua tts.py: Edge TTS + giọng dự phòng), trộn âm thanh, xuất video song song bằng ffmpeg."""
import concurrent.futures as cf
import hashlib
import json
import logging
import math
import multiprocessing
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

import errors as E
import logsetup as L
import render as R
import tts as T
from version import __version__

log = logging.getLogger("ffv.media")
SR = 48000
NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


class Cancelled(Exception):
    pass


def mp_context():
    """Cách tạo tiến trình con. Mặc định theo hệ điều hành; FFV_MP=spawn ép kiểu của Windows/macOS để thử trên Linux."""
    return multiprocessing.get_context(os.environ.get("FFV_MP") or None)


def ffmpeg_exe():
    p = shutil.which("ffmpeg")
    if p:
        return p
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run_ff(args):
    cmd = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error"] + args
    log.debug("ffmpeg: %s", " ".join(str(a) for a in cmd))
    r = subprocess.run(cmd, capture_output=True, **NOWIN)
    if r.returncode != 0:
        raise E.FFmpegError("xử lý âm thanh", r.stderr.decode("utf-8", "ignore"))


# ----------------------------------------------------------------------------- wav helpers
def read_wav(path):
    with wave.open(str(path), "rb") as w:
        ch, n = w.getnchannels(), w.getnframes()
        data = np.frombuffer(w.readframes(n), np.int16).astype(np.float32) / 32768.0
    return data.reshape(-1, ch) if ch == 2 else np.repeat(data.reshape(-1, 1), 2, axis=1)


def write_wav(path, arr):
    pcm = (np.clip(arr, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def analyze_trim(arr):
    """Cắt lặng đầu/cuối, trả (audio, [bắt đầu, kết thúc] giọng, [các chỗ ngắt hơi], offset đã cắt ở đầu).
    Mốc tính theo audio đã cắt; offset để đổi mốc từ của TTS (tính theo audio gốc) sang audio đã cắt."""
    win = SR // 50  # 20ms
    mono = arr.mean(axis=1)
    n = len(mono) // win
    if n < 2:
        return arr, [0.0, len(arr) / SR], [], 0.0
    rms = np.sqrt((mono[:n * win].reshape(n, win) ** 2).mean(axis=1))
    peak = float(np.percentile(rms, 95))
    act = rms > max(0.06 * peak, 1e-4)
    idx = np.nonzero(act)[0]
    if len(idx) == 0:
        return arr, [0.0, len(arr) / SR], [], 0.0
    s, e = idx[0] * 0.02, (idx[-1] + 1) * 0.02
    gaps, run = [], 0
    for i in range(idx[0], idx[-1] + 1):
        if not act[i]:
            run += 1
        else:
            if run >= 9:  # >= 180ms
                gaps.append((i - run / 2) * 0.02)
            run = 0
    a0 = max(0.0, s - 0.06)
    a1 = min(len(arr) / SR, e + 0.10)
    out = arr[int(a0 * SR):int(a1 * SR)]
    return out, [s - a0, e - a0], [g - a0 for g in gaps], a0


# ----------------------------------------------------------------------------- TTS
def _fake_tts_wav(text, path):
    """Chỉ để test offline (FFV_FAKE_TTS=1): tạo tiếng 'ù ù' có ngắt hơi theo dấu câu.
    Trả về mốc từng từ [(từ, bắt đầu, kết thúc)] chính xác tuyệt đối -> dùng để kiểm thử căn phụ đề."""
    t, parts, events, cur = 0.12, [], [], None
    for ch in text:
        d = 0.06 if ch != " " else 0.03
        seg = np.zeros(int(d * SR), np.float32)
        if ch.isalpha():
            x = np.arange(len(seg)) / SR
            seg = 0.25 * np.sin(2 * np.pi * (140 + 8 * (ord(ch) % 9)) * x) * np.hanning(len(seg))
        elif ch in ".,!?;:":
            d = 0.35 if ch in ".!?" else 0.22
            seg = np.zeros(int(d * SR), np.float32)
        if ch == " ":
            if cur:
                events.append(cur)
                cur = None
        else:
            if cur is None:
                cur = [ch, t, t + d]
            else:
                cur[0] += ch
                if ch.isalpha():
                    cur[2] = t + d
        t += d
        parts.append(seg)
    if cur:
        events.append(cur)
    a = np.concatenate([np.zeros(int(0.12 * SR), np.float32)] + parts + [np.zeros(int(0.2 * SR), np.float32)])
    write_wav(path, np.stack([a, a], axis=1))
    return [(w, a0, a1) for w, a0, a1 in events]


def _expand_sentences(ev):
    """Mốc theo câu -> mốc từng từ giả lập (chia theo độ dài chữ trong câu). Đủ chính xác cho cụm phụ đề."""
    out = []
    for text, a, b in ev:
        toks = text.split()
        if not toks:
            continue
        w = [len(t) + 1 for t in toks]
        tot, acc = float(sum(w)), 0.0
        for t, wi in zip(toks, w):
            out.append([t, a + (b - a) * acc / tot, a + (b - a) * (acc + wi - 0.5) / tot])
            acc += wi
    return out


def clean_events(ev, kind, off, dur, speech):
    """Đổi mốc TTS (theo audio gốc) sang mốc theo audio đã cắt lặng + kiểm tra hợp lý.
    Trả list [từ, bắt đầu, kết thúc]; [] nếu mốc không đáng tin (khi đó chia theo độ dài chữ rồi hút vào chỗ ngắt hơi)."""
    out = []
    for text, a, b in ev:
        text = (text or "").strip()
        if not text:
            continue
        a, b = a - off, b - off
        if b <= 0 or a >= dur:
            continue
        out.append([text, a, b])
    if not out:
        return []
    if kind == "sentence":
        out = _expand_sentences(out)
    prev = 0.0
    for e in out:  # không cho mốc đi lùi
        e[1] = min(max(e[1], prev, 0.0), dur)
        e[2] = min(max(e[2], e[1] + 0.02), dur)
        prev = e[1]
    if abs(out[0][1] - speech[0]) > 0.6 or abs(out[-1][2] - speech[1]) > 0.9:
        return []  # mốc lệch hẳn so với chỗ thật sự có tiếng -> bỏ
    return [[t, round(a, 3), round(b, 3)] for t, a, b in out]


def list_voices():
    """Danh sách giọng Edge (cần internet). Giọng dự phòng không có danh sách riêng: chọn theo ngôn ngữ của giọng Edge đã chọn."""
    return T.edge_voices()


def _to_wav(res, wav):
    """File của nhà cung cấp (mp3/wav, tần số bất kỳ) -> wav 48 kHz stereo cho phần còn lại của tool.
    Tốc độ nhà cung cấp chưa áp dụng (res.tempo, VD gTTS) được ffmpeg `atempo` làm nốt; mốc từ (nếu có) co theo.
    -> (mốc từ, kiểu mốc, tên nhà cung cấp)."""
    tempo = res.tempo if abs(res.tempo - 1.0) > 1e-3 else 1.0
    args = ["-i", res.path, "-ar", str(SR), "-ac", "2"]
    if tempo != 1.0:
        args += ["-filter:a", f"atempo={tempo:.4f}"]
    run_ff(args + ["-c:a", "pcm_s16le", wav])
    return [(t, a / tempo, b / tempo) for t, a, b in res.events], res.kind, res.engine


def tts_scene(root, proj, sc, chain=None):
    """Tạo giọng cho 1 cảnh -> metadata audio (file, hash, dur, speech, gaps, words, wsrc, engine).
    `chain` (tts.Chain): truyền vào khi tạo nhiều cảnh để nhớ dịch vụ nào đã hỏng; bỏ trống thì tạo chuỗi theo dự án.
    Giọng chính hỏng mà dự án cho phép thì tự chuyển sang giọng dự phòng; `engine` ghi lại nhà cung cấp đã đọc cảnh này."""
    text = R.spoken_text(proj, sc["narration"].strip())
    h = R.audio_hash(proj, sc)
    v = proj.get("voice", {})
    adir = Path(root) / "audio"
    adir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "a.wav")
        if os.environ.get("FFV_FAKE_TTS"):
            events, kind, engine = _fake_tts_wav(text, wav), "word", "fake"
        else:
            res = (chain or T.make_chain(proj)).synth(text, v.get("name", "vi-VN-HoaiMyNeural"), v.get("rate", 0), v.get("pitch", 0), td)
            events, kind, engine = _to_wav(res, wav)
        arr = read_wav(wav)
    arr, speech, gaps, off = analyze_trim(arr)
    dur = len(arr) / SR
    words = clean_events(events, kind, off, dur, speech)
    name = f"{sc['id']}_{h}.wav"
    write_wav(adir / name, arr)
    return dict(file=name, hash=h, dur=dur, speech=speech, gaps=gaps, words=words, wsrc=kind if words else None, engine=engine)


# ----------------------------------------------------------------------------- loudness
LIMIT_TP = -1.5   # dBFS: đỉnh tối đa sau khi chuẩn hoá (chừa chỗ cho AAC và đỉnh giữa các mẫu)
LUFS_TOL = 0.3    # sai số chấp nhận được so với mức đích


def measure_loudness(wav):
    """Đo âm lượng tích hợp (LUFS, theo ITU-R BS.1770) và đỉnh bằng bộ lọc loudnorm của FFmpeg.
    Trả {I, TP} hoặc None nếu quá nhỏ/quá ngắn (< 400ms) không đo được."""
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-nostats", "-i", str(wav), "-af",
                        "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, **NOWIN)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr.decode("utf-8", "ignore"), re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        i, tp = float(d["input_i"]), float(d["input_tp"])
    except (ValueError, KeyError):
        return None
    return dict(I=i, TP=tp) if math.isfinite(i) and i > -69 else None


def normalize_loudness(src, dst, target):
    """Tăng/giảm đều cả đoạn (giữ nguyên tương quan giọng – nhạc) tới `target` LUFS, có bộ chặn đỉnh ở LIMIT_TP.
    Chặn đỉnh làm âm lượng tụt nhẹ nên đo lại và bù tối đa 3 vòng. Trả thông tin để báo cho người dùng, hoặc None nếu không đo được."""
    m = measure_loudness(src)
    if m is None:
        shutil.copyfile(src, dst)
        return None
    lim = 10 ** (LIMIT_TP / 20)
    gain = max(-24.0, min(24.0, target - m["I"]))
    out = None
    for _ in range(3):
        run_ff(["-i", str(src), "-af", f"volume={gain:.3f}dB,alimiter=limit={lim:.4f}:attack=5:release=80:level=0:latency=1",
                "-ar", str(SR), "-ac", "2", "-c:a", "pcm_s16le", str(dst)])
        out = measure_loudness(dst)
        if out is None or abs(out["I"] - target) <= LUFS_TOL:
            break
        gain = max(-24.0, min(24.0, gain + target - out["I"]))
    return dict(before=round(m["I"], 1), after=round(out["I"], 1) if out else None,
                peak=round(out["TP"], 1) if out else None, target=target)


# ----------------------------------------------------------------------------- audio mix
def build_audio(proj, root, tl, out_wav, info=None):
    """Trộn giọng từng cảnh + nhạc nền (tự hạ nhỏ khi có người nói), rồi chuẩn hoá âm lượng (audio_norm).
    Trả True nếu có âm thanh; thông tin âm lượng đo được ghi vào info[\"loudness\"]."""
    total = tl["total"]
    n = int(math.ceil(total * SR))
    mix = np.zeros((n, 2), np.float32)
    env = np.zeros(int(total * 100) + 4, np.float32)
    has = False
    for s in tl["scenes"]:
        a = s["audio"]
        if not a:
            continue
        data = read_wav(Path(root) / "audio" / a["file"])
        st = int(round(s["audio_start"] * SR))
        end = min(n, st + len(data))
        if end > st:
            mix[st:end] += data[:end - st]
            has = True
        e0 = int((s["audio_start"] + a["speech"][0]) * 100)
        e1 = int((s["audio_start"] + a["speech"][1]) * 100) + 1
        env[e0:e1] = 1.0
    bg = proj.get("bgm") or {}
    bpath = Path(root) / "media" / bg["file"] if bg.get("file") else None
    if bpath and bpath.exists():
        r = subprocess.run([ffmpeg_exe(), "-v", "error", "-i", str(bpath), "-f", "f32le", "-ac", "2", "-ar", str(SR),
                            "-"], capture_output=True, **NOWIN)
        m = np.frombuffer(r.stdout, np.float32)
        m = m[:len(m) // 2 * 2].reshape(-1, 2)
        if len(m) > SR:
            m = np.tile(m, (math.ceil(n / len(m)), 1))[:n]
            envs = np.convolve(env, np.ones(40) / 40, mode="same")
            gain100 = 1 - 0.65 * np.clip(envs * 1.5, 0, 1)
            ts = np.arange(n) / SR
            g = np.interp(ts * 100, np.arange(len(gain100)), gain100)
            g *= np.clip(ts / 1.0, 0, 1) * np.clip((total - ts) / 1.8, 0, 1)
            mix += m * (float(bg.get("volume", 0.12)) * g)[:, None].astype(np.float32)
            has = True
    if not has:
        return False
    an = proj.get("audio_norm") or {}
    peak = float(np.abs(mix).max())
    if an.get("mode", "lufs") == "lufs":
        if peak > 0.9:  # chỉ để file trung gian 16-bit không bị vỡ; âm lượng cuối do bước chuẩn hoá quyết định
            mix *= 0.9 / peak
        raw = Path(out_wav).with_name("mix_raw.wav")
        write_wav(raw, mix)
        res = normalize_loudness(raw, out_wav, float(an.get("target", -14)))
        raw.unlink(missing_ok=True)
    else:  # tắt chuẩn hoá: chỉ chặn đỉnh
        if peak > 0.97:
            mix *= 0.97 / peak
        write_wav(out_wav, mix)
        m = measure_loudness(out_wav)
        res = dict(before=None, after=round(m["I"], 1), peak=round(m["TP"], 1), target=None) if m else None
    if info is not None:
        info["loudness"] = res
    return True


# ----------------------------------------------------------------------------- export
HW_ENC = {"nvenc": "h264_nvenc", "qsv": "h264_qsv", "amf": "h264_amf"}
TIERS = ("draft", "standard", "high")
_ENC_CACHE = {}


def probe_encoder(name):
    """Thử mã hoá 1 khung nhỏ để biết encoder chạy được trên máy này không -> (ok, chi tiết). Có nhớ kết quả."""
    if name in _ENC_CACHE:
        return _ENC_CACHE[name]
    ok, detail = False, ""
    try:
        r = subprocess.run([ffmpeg_exe(), "-v", "error", "-f", "lavfi", "-i", "color=black:s=256x256:d=0.1",
                            "-frames:v", "1", "-c:v", name, "-f", "null", "-"], capture_output=True, timeout=25, **NOWIN)
        ok = r.returncode == 0
        lines = [l for l in r.stderr.decode("utf-8", "ignore").splitlines() if l.strip()]
        bad = [l for l in lines if "Nothing was written" not in l]  # dòng này chỉ là hệ quả, lỗi thật nằm ở dòng trước
        detail = "" if ok else ((bad or lines or ["không chạy được"])[0][:160])
    except Exception as e:  # noqa
        detail = str(e)[:160]
    _ENC_CACHE[name] = (ok, detail)
    log.info("Dò encoder %s: %s%s", name, "dùng được" if ok else "KHÔNG dùng được", f" ({detail})" if detail else "")
    return _ENC_CACHE[name]


def pick_encoder(pref="auto"):
    """pref: auto (thử NVENC -> QSV -> AMF), cpu, nvenc, qsv, amf. Không dùng được thì rơi về libx264."""
    if pref == "cpu":
        return "libx264"
    order = ["nvenc", "qsv", "amf"] if pref in (None, "auto") else [pref]
    for k in order:
        name = HW_ENC.get(k)
        if name and probe_encoder(name)[0]:
            return name
    if pref not in (None, "auto"):
        log.warning("Đã chọn bộ mã hoá %s nhưng máy không chạy được -> dùng CPU (libx264)", pref)
    return "libx264"


# (preset, mức chất lượng) cho từng encoder ở mỗi mức. "preview" chỉ dùng cho bản xem thử nhỏ.
QUALITY = {
    "preview":  dict(x264=("ultrafast", 28), nvenc=("p4", 30), qsv=("veryfast", 30), amf=("speed", 30)),
    "draft":    dict(x264=("ultrafast", 26), nvenc=("p3", 28), qsv=("veryfast", 28), amf=("speed", 28)),
    "standard": dict(x264=("veryfast", 18), nvenc=("p5", 21), qsv=("medium", 21), amf=("balanced", 21)),
    "high":     dict(x264=("medium", 15), nvenc=("p6", 17), qsv=("slower", 17), amf=("quality", 17)),
}


def enc_args(enc, fps, tier="standard"):
    q = QUALITY.get(tier, QUALITY["standard"])
    color = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]
    vf = ["-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p"]
    if enc == "h264_nvenc":
        pr, cq = q["nvenc"]
        c = ["-c:v", "h264_nvenc", "-preset", pr, "-rc", "vbr", "-cq", str(cq), "-b:v", "0", "-profile:v", "high"]
    elif enc == "h264_qsv":
        pr, gq = q["qsv"]
        c = ["-c:v", "h264_qsv", "-preset", pr, "-global_quality", str(gq), "-profile:v", "high"]
    elif enc == "h264_amf":
        pr, qp = q["amf"]
        c = ["-c:v", "h264_amf", "-quality", pr, "-rc", "cqp", "-qp_i", str(qp), "-qp_p", str(qp + 2), "-profile:v", "high"]
    else:
        pr, crf = q["x264"]
        c = ["-c:v", "libx264", "-preset", pr, "-crf", str(crf), "-profile:v", "high", "-threads", "2"]
    return vf + c + ["-g", str(int(fps * 2)), "-bf", "0"] + color


def seg_cmd(W, H, fps, ffargs, out_path):
    return [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s",
            f"{W}x{H}", "-r", str(fps), "-i", "-", "-an"] + ffargs + ["-f", "h264", out_path]


def n_workers(enc):
    w = max(1, min((os.cpu_count() or 2) - 1, 8))
    return min(w, 3) if enc != "libx264" else w  # GPU: tối đa vài phiên mã hoá song song


_CTX = None


def _init_worker(proj_json, root, W, H, log_queue=None, log_level=logging.INFO):
    global _CTX
    L.worker_init(log_queue, log_level)
    t0 = time.time()
    _CTX = R.Ctx(json.loads(proj_json), root, W, H)
    log.debug("Tiến trình dựng %s sẵn sàng (%dx%d) sau %.2fs", os.getpid(), W, H, time.time() - t0)


def _render_segment(args):
    """Dựng 1 đoạn -> ghi ra file .part rồi đổi tên (nguyên tử): file seg_*.h264 có mặt nghĩa là đoạn đã xong."""
    idx, f0, f1, fps, W, H, path, ffargs = args
    part = path + ".part"
    p = subprocess.Popen(seg_cmd(W, H, fps, ffargs, part), stdin=subprocess.PIPE, stderr=subprocess.PIPE, **NOWIN)
    try:
        for f in range(f0, f1):
            fr = np.ascontiguousarray(_CTX.render(f / fps))
            p.stdin.write(memoryview(fr))
        p.stdin.close()
    except (BrokenPipeError, OSError):
        pass
    err = p.stderr.read().decode("utf-8", "ignore")
    if p.wait() != 0:
        if os.path.exists(part):
            os.remove(part)
        raise E.FFmpegError(f"dựng đoạn {idx}", err)
    os.replace(part, path)
    return idx


def export_key(proj, W, H, fps, enc, ffargs):
    """Mã nhận diện 'các khung hình này có giống lần trước không' -> quyết định dùng lại đoạn đã dựng (resume)."""
    p = {k: v for k, v in proj.items() if k not in ("name", "bgm", "encoder", "quality", "export_tier", "schema_version", "audio_norm")}
    try:
        code = hashlib.sha1(Path(R.__file__).read_bytes()).hexdigest()
    except OSError:  # bản đóng gói: mã nằm trong file nén, không có render.py để đọc -> dùng số phiên bản
        code = f"v{__version__}"
    raw = json.dumps([p, W, H, fps, enc, ffargs, code, "seg3"], sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def purge_cache(cache_root, keep, days=3):
    """Xoá bộ nhớ đệm đoạn cũ (quá `days` ngày) và file .part dở dang."""
    if not cache_root.exists():
        return
    for d in cache_root.iterdir():
        try:
            if d.is_dir() and d.name != keep and time.time() - d.stat().st_mtime > days * 86400:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass
    for f in (cache_root / keep).glob("*.part") if (cache_root / keep).exists() else []:
        f.unlink(missing_ok=True)


def run_export(job, proj, root, out_path, short, fps, tier="standard", enc_pref="auto", p0=0.0):
    root = Path(root)
    tl = R.timeline(proj)
    if not tl["scenes"]:
        raise E.UserError("Chưa có cảnh nào để xuất.", "Thêm cảnh (nút + Cảnh) hoặc dán kịch bản rồi xuất lại.", code="no_scenes")
    W, H = R.frame_size(proj["aspect"], short)
    nfr = int(math.ceil(tl["total"] * fps))
    enc = pick_encoder(enc_pref)
    workers = n_workers(enc)
    fa = enc_args(enc, fps, tier)
    seg_len = max(int(fps * 3), 1)
    segs = [(i, f0, min(f0 + seg_len, nfr)) for i, f0 in enumerate(range(0, nfr, seg_len))]
    (root / "out").mkdir(exist_ok=True)
    key = export_key(proj, W, H, fps, enc, fa)
    cache_root = root / "out" / ".cache"
    cache = cache_root / key
    cache.mkdir(parents=True, exist_ok=True)
    purge_cache(cache_root, key)
    tmp = Path(tempfile.mkdtemp(prefix="tmp_", dir=root / "out"))
    t0 = time.time()
    ex = None
    ok = False
    ainfo = {}
    stop_log = lambda: None  # noqa: E731
    log.info("Xuất video: %dx%d · %dfps · %d khung (%.1fs) · %s x%d · mức %s · %d cảnh", W, H, fps, nfr, tl["total"],
             enc, workers, tier, len(tl["scenes"]))
    try:
        job.update(stage="Trộn và chuẩn hoá âm thanh", message="", progress=p0)
        wav = tmp / "mix.wav"
        has_audio = build_audio(proj, root, tl, wav, ainfo)
        todo = [(i, f0, f1) for i, f0, f1 in segs if not (cache / f"seg_{i:05d}.h264").exists()]
        resumed = len(segs) - len(todo)
        done = resumed
        job["stage"] = f"Render {W}x{H} · {fps}fps · {'GPU' if enc != 'libx264' else 'CPU'} x{workers}" + \
                       (f" · dùng lại {resumed}/{len(segs)} đoạn đã dựng" if resumed else "")
        if todo:
            mpc = mp_context()
            lq, stop_log = L.attach_queue(mpc)
            ex = cf.ProcessPoolExecutor(max_workers=workers, mp_context=mpc, initializer=_init_worker,
                                        initargs=(json.dumps(proj), str(root), W, H, lq,
                                                  logging.getLogger("ffv").getEffectiveLevel()))
            futs = [ex.submit(_render_segment, (i, f0, f1, fps, W, H, str(cache / f"seg_{i:05d}.h264"), fa))
                    for i, f0, f1 in todo]
            t1 = time.time()
            for fut in cf.as_completed(futs):
                fut.result()
                done += 1
                frames = min(done * seg_len, nfr)
                eta = (time.time() - t1) / max(done - resumed, 1) * (len(segs) - done)
                job["progress"] = p0 + (0.97 - p0) * done / len(segs)
                job["message"] = f"{frames}/{nfr} khung · còn khoảng {int(eta)}s"
                if job.get("cancel"):
                    raise Cancelled()
            ex.shutdown(wait=True)
            ex = None
        job.update(stage="Ghép video + âm thanh", message="")
        with open(tmp / "all.h264", "wb") as dst:  # nối thẳng các đoạn H.264 (cùng thông số, mỗi đoạn mở đầu bằng IDR)
            for i, _, _ in segs:
                with open(cache / f"seg_{i:05d}.h264", "rb") as srcf:
                    shutil.copyfileobj(srcf, dst, 1 << 22)
        cmd = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-framerate", str(fps), "-f", "h264", "-i",
               "all.h264"]
        if has_audio:
            cmd += ["-i", "mix.wav", "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "192k"]
        cmd += ["-c:v", "copy", "-movflags", "+faststart", str(Path(out_path).resolve())]
        r = subprocess.run(cmd, cwd=str(tmp), capture_output=True, **NOWIN)
        if r.returncode != 0:
            raise E.FFmpegError("ghép video và âm thanh", r.stderr.decode("utf-8", "ignore"))
        ok = True
    finally:
        if ex is not None:
            ex.shutdown(wait=True, cancel_futures=True)
        stop_log()
        shutil.rmtree(tmp, ignore_errors=True)
        if ok:  # xong hẳn mới xoá đoạn đã dựng; huỷ/lỗi thì giữ lại để lần sau chạy tiếp
            shutil.rmtree(cache, ignore_errors=True)
    secs = round(time.time() - t0, 1)
    try:
        mb = Path(out_path).stat().st_size / 1e6
    except OSError:
        mb = 0.0
    log.info("Xuất xong sau %.1fs (%.1f khung/giây) · %.1f MB · dùng lại %d/%d đoạn · âm lượng %s → %s", secs,
             nfr / max(secs, 0.01), mb, resumed, len(segs), (ainfo.get("loudness") or {}).get("before"),
             (ainfo.get("loudness") or {}).get("after"))
    return dict(W=W, H=H, fps=fps, frames=nfr, seconds=secs, encoder=enc, resumed=resumed,
                loudness=ainfo.get("loudness"))


# ----------------------------------------------------------------------------- ước lượng trước khi xuất
def _encode_bench(frames, W, H, fps, ffargs):
    """Mã hoá thử danh sách khung -> (giây, số byte)."""
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "b.h264")
        t0 = time.time()
        p = subprocess.Popen(seg_cmd(W, H, fps, ffargs, out), stdin=subprocess.PIPE, stderr=subprocess.PIPE, **NOWIN)
        try:
            for f in frames:
                p.stdin.write(memoryview(f))
            p.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        err = p.stderr.read().decode("utf-8", "ignore")
        if p.wait() != 0:
            raise E.FFmpegError("mã hoá thử", err or "không mã hoá thử được")
        return time.time() - t0, os.path.getsize(out)


def estimate_export(job, proj, root, short, fps, tier="standard", enc_pref="auto"):
    """Dựng thử vài khung + mã hoá thử một đoạn ngắn để dự đoán thời gian xuất và dung lượng (ước tính, có thể lệch ~±30%)."""
    root = Path(root)
    tl = R.timeline(proj)
    if not tl["scenes"]:
        raise E.UserError("Chưa có cảnh nào để ước lượng.", "Thêm cảnh rồi thử lại.", code="no_scenes")
    total = tl["total"]
    W, H = R.frame_size(proj["aspect"], short)
    nfr = int(math.ceil(total * fps))
    enc = pick_encoder(enc_pref)
    workers = n_workers(enc)
    fa = enc_args(enc, fps, tier)
    job.update(stage="Dựng thử vài khung…", progress=0.1)
    ctx = R.Ctx(proj, root, W, H)
    dts = []
    for u in (0.1, 0.3, 0.5, 0.7, 0.9):  # 5 điểm trải đều; khung đầu mỗi điểm để khởi động (dựng sprite chữ, ảnh)
        t = min(total * u, max(total - 2.0 / fps, 0.0))
        ctx.render(t)
        t1 = time.time()
        ctx.render(t + 1.0 / fps)
        dts.append(time.time() - t1)
    render_s = float(np.median(dts))
    job.update(stage="Mã hoá thử một đoạn ngắn…", progress=0.5)
    n = int(max(8, min(fps, 150e6 / (W * H * 3))))  # giới hạn bộ nhớ ~150MB
    mid = max(total * 0.5 - n / fps / 2, 0.0)
    clip = [np.ascontiguousarray(ctx.render(mid + k / fps)) for k in range(n)]
    ta, sa = _encode_bench(clip, W, H, fps, fa)
    tb, sb = _encode_bench(clip + clip[::-1], W, H, fps, fa)  # chiều xuôi + chiều ngược: chuyển động liền mạch, không bị cắt cảnh
    enc_s = max((tb - ta) / n, 1e-4)
    p_bytes = max((sb - sa) / n, 1.0)  # byte/khung P
    i_bytes = max(sa - (n - 1) * p_bytes, p_bytes)  # khung I
    size = nfr * p_bytes + math.ceil(nfr / (fps * 2)) * (i_bytes - p_bytes) + 192e3 / 8 * total
    cpu = os.cpu_count() or 1
    if enc == "libx264":
        sec = nfr * (render_s + min(1.7, cpu) * enc_s) / max(1.0, min(cpu * 0.9, workers * 2.5))  # x264 dùng ~1.7 luồng/tiến trình
    else:
        sec = max(nfr * render_s / max(1.0, min(cpu * 0.9, workers)), nfr * enc_s / min(workers, 3))
    sec += 5 + total * 0.05  # trộn âm thanh + ghép file
    warn = []
    if W * H * fps >= 2560 * 1440 * 50 and total > 120:
        warn.append("2K 60fps với video dài hơn 2 phút: render sẽ lâu. Có thể xuất 1440p 30fps hoặc 1080p 60fps để nhanh hơn.")
    if enc == "libx264" and sec > 1800:
        warn.append("Ước tính trên 30 phút bằng CPU. Nếu máy có GPU, chọn bộ mã hoá GPU trong Cài đặt.")
    job["progress"] = 1.0
    return dict(W=W, H=H, fps=fps, frames=nfr, total=round(total, 1), encoder=enc, workers=workers, cpus=cpu,
                render_ms=round(render_s * 1000, 1), enc_ms=round(enc_s * 1000, 1), seconds=int(sec),
                mb=round(size / 1e6, 1), warnings=warn)
