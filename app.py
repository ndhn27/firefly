"""Firefly Video – tool dựng video giải thích (nền đom đóm, giọng Edge TTS có giọng dự phòng, xuất tới 2K 60fps).
Chạy:  python app.py   rồi mở http://localhost:8765
"""
import hashlib
import json
import logging
import multiprocessing
import os
import re
import shutil
import socket
import sys
import threading
import time
import unicodedata
import urllib.request
import uuid
import webbrowser
from pathlib import Path

import cv2
from flask import Flask, Response, abort, jsonify, request, send_file, send_from_directory
from werkzeug.exceptions import HTTPException

import checks as C
import doctor as D
import errors as E
import logsetup as L
import media as M
import paths
import render as R
import scriptgen as G
import tts as T
from version import APP_NAME, __version__

log = logging.getLogger("ffv.app")
ROOT = paths.DATA_DIR  # nơi ghi: projects/, logs/, ai_settings.json (cạnh file .exe khi chạy bản đóng gói)
PROJ = ROOT / "projects"
app = Flask(__name__, static_folder=str(paths.RES_DIR / "static"), static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 400 * 1024 * 1024
LOCK = threading.RLock()
JOBS = {}

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
AUD_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}
DEFAULT_VOICE = "vi-VN-HoaiMyNeural"
SCHEMA_VERSION = 2  # 2: thêm normalize_text, caption_hl, export_tier; dự án cũ (không có số này = 1) giữ nguyên cách đọc cũ
ENCODERS = ("auto", "cpu", "nvenc", "qsv", "amf")
FALLBACK_VOICES = [
    {"name": "vi-VN-HoaiMyNeural", "gender": "Nữ", "locale": "vi-VN"},
    {"name": "vi-VN-NamMinhNeural", "gender": "Nam", "locale": "vi-VN"},
    {"name": "en-US-AriaNeural", "gender": "Nữ", "locale": "en-US"},
    {"name": "en-US-GuyNeural", "gender": "Nam", "locale": "en-US"},
]


# ----------------------------------------------------------------------------- project store
def slug(s):
    s = unicodedata.normalize("NFKD", s.replace("đ", "d").replace("Đ", "D")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:30] or "du-an"


def pdir(pid):
    if not re.fullmatch(r"[a-z0-9\-]{3,60}", pid or ""):
        abort(404)
    d = PROJ / pid
    if not (d / "project.json").exists():
        abort(404)
    return d


def load(pid):
    """Đọc project.json. Hỏng (mất điện giữa chừng, sửa tay sai...) thì tự khôi phục từ project.json.bak."""
    p = pdir(pid) / "project.json"
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, ValueError) as e:
        bak = p.with_suffix(".json.bak")
        try:
            data = json.loads(bak.read_text("utf-8"))
        except (OSError, ValueError):
            log.error("project.json hỏng (%s) và không có bản sao lưu dùng được: %s", e, p)
            raise E.UserError("File dự án bị hỏng và không có bản lưu trước đó để khôi phục.",
                              f"Mở thư mục {p.parent} xem file project.json (và project.json.bak). Ảnh trong media/ vẫn còn: "
                              "tạo dự án mới rồi thêm lại ảnh.", code="project_corrupt")
        keep = p.with_name(f"project.json.hong-{time.strftime('%Y%m%d-%H%M%S')}")
        try:
            os.replace(p, keep)
        except OSError:
            pass
        shutil.copyfile(bak, p)
        log.warning("project.json hỏng (%s) -> đã khôi phục từ project.json.bak (bản hỏng giữ ở %s)", e, keep.name)
        return data


def save(pid, proj):
    """Ghi nguyên tử (file tạm + đổi tên) + fsync, và giữ lại bản trước đó ở project.json.bak."""
    p = PROJ / pid / "project.json"
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(proj, ensure_ascii=False, indent=1))
        f.flush()
        os.fsync(f.fileno())
    if p.exists():
        try:
            json.loads(p.read_text("utf-8"))  # chỉ sao lưu bản còn đọc được, để không ghi đè bản tốt bằng bản hỏng
            shutil.copyfile(p, p.with_suffix(".json.bak"))
        except (OSError, ValueError):
            pass
    os.replace(tmp, p)


QUALITIES = (720, 1080, 1440)  # cạnh ngắn của video xuất ra; 1440 = "2K"
FPS_CHOICES = (24, 30, 60)
LUFS_TARGETS = (-16, -14)  # mức âm lượng đích khi chuẩn hoá (LUFS)
LOGO_POS = ("tl", "tr", "bl", "br")
IMG_MODES = ("card", "fit", "cover")
IMG_ANIMS = ("zoom", "zoom_out", "pan", "none")


def nearest(v, allowed, default):
    """Giá trị lạ (file sửa tay, bản cũ) bị đưa về mức hợp lệ gần nhất, không để lọt vào renderer."""
    try:
        v = int(v)
    except (TypeError, ValueError):
        return default
    return min(allowed, key=lambda a: abs(a - v))


def clampf(v, lo, hi, default):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def migrate(p):
    """Nâng dự án cũ lên SCHEMA_VERSION mà không làm đổi kết quả đã có."""
    v = int(p.get("schema_version") or 1)
    if v < 2:
        # v1 chưa có chuẩn hoá số/%/ngày: để TẮT để giọng đã tạo vẫn còn hiệu lực (bật thì hash đổi, phải tạo lại giọng)
        p.setdefault("normalize_text", False)
    p["schema_version"] = SCHEMA_VERSION
    return p


def normalize(p):
    migrate(p)
    p.setdefault("name", "Video mới")
    p["aspect"] = p.get("aspect") if p.get("aspect") in R.ASPECTS else "9:16"
    p["quality"] = nearest(p.get("quality"), QUALITIES, 1080)
    p["fps"] = nearest(p.get("fps"), FPS_CHOICES, 30)
    th = dict(R.THEMES[R.DEFAULT_THEME], preset=R.DEFAULT_THEME)
    th.update(p.get("theme") or {})
    p["theme"] = th
    v = {"name": DEFAULT_VOICE, "rate": 0, "pitch": 0}
    v.update(p.get("voice") or {})
    v["fallback"] = v.get("fallback") is not False  # tự chuyển sang giọng dự phòng khi giọng chính lỗi (mặc định bật; không vào audio_hash)
    p["voice"] = v
    p.setdefault("pron", "")
    bg = {"file": None, "volume": 0.12}
    bg.update(p.get("bgm") or {})
    p["bgm"] = bg
    p["encoder"] = p.get("encoder") if p.get("encoder") in ENCODERS else "auto"
    p["export_tier"] = p.get("export_tier") if p.get("export_tier") in M.TIERS else "standard"
    an = {"mode": "lufs", "target": -14}
    an.update(p.get("audio_norm") or {})
    p["audio_norm"] = {"mode": an["mode"] if an["mode"] in ("off", "lufs") else "lufs",
                       "target": nearest(an.get("target"), LUFS_TARGETS, -14)}
    lg = {"file": None, "pos": "tr", "size": 0.14, "opacity": 0.9}
    lg.update(p.get("logo") or {})
    lg["pos"] = lg["pos"] if lg["pos"] in LOGO_POS else "tr"
    lg["size"] = clampf(lg.get("size"), 0.04, 0.4, 0.14)
    lg["opacity"] = clampf(lg.get("opacity"), 0.1, 1.0, 0.9)
    p["logo"] = lg
    p["normalize_text"] = bool(p.get("normalize_text", True))
    p["caption_hl"] = bool(p.get("caption_hl", False))
    p.setdefault("scenes", [])
    for s in p["scenes"]:
        s.setdefault("id", "s" + uuid.uuid4().hex[:6])
        s["layout"] = s.get("layout") if s.get("layout") in ("stack", "split") else "stack"
        s["image_side"] = s.get("image_side") if s.get("image_side") in ("left", "right") else "right"
        for im in s.get("images") or []:
            im["mode"] = im.get("mode") if im.get("mode") in IMG_MODES else "card"
            im["anim"] = im.get("anim") if im.get("anim") in IMG_ANIMS else "zoom"
    return p


def issues_light(proj, d):
    """Vấn đề rẻ để phát hiện (thiếu file ảnh/nhạc/logo, cảnh trống) – chạy mỗi lần lưu để UI đánh dấu ngay."""
    return [i for i in C.preflight(proj, d) if i["code"] != "no_scenes"]


def tl_json(proj):
    tl = R.timeline(proj)
    return dict(total=tl["total"], scenes=[dict(id=s["id"], start=s["start"], dur=s["dur"], T=s["T"],
                                                estimated=s["estimated"]) for s in tl["scenes"]])


# ----------------------------------------------------------------------------- pages / projects
@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/themes")
def themes():
    return jsonify({k: dict(v, preset=k) for k, v in R.THEMES.items()})


_voices = {}


@app.get("/api/voices")
def voices():
    if "v" not in _voices:
        try:
            lst = [{"name": v["ShortName"], "gender": "Nữ" if v["Gender"] == "Female" else "Nam",
                    "locale": v["Locale"]} for v in M.list_voices()]
            lst.sort(key=lambda v: (v["locale"] != "vi-VN", v["locale"] != "en-US", v["locale"], v["name"]))
            _voices["v"] = lst or FALLBACK_VOICES
        except Exception:  # noqa
            return jsonify(FALLBACK_VOICES)
    return jsonify(_voices["v"])


@app.get("/api/tts/status")
def tts_status():
    """Tình trạng từng nhà cung cấp giọng (chính trước, dự phòng sau). Chỉ kiểm tra máy này, không gọi mạng."""
    return jsonify(engines=T.status(request.args.get("voice") or None))


@app.get("/api/projects")
def projects():
    out = []
    for p in sorted(PROJ.glob("*/project.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            d = json.loads(p.read_text("utf-8"))
            out.append(dict(id=p.parent.name, name=d.get("name", p.parent.name), aspect=d.get("aspect")))
        except Exception:  # noqa
            pass
    return jsonify(out)


@app.post("/api/projects")
def create_project():
    d = request.get_json(force=True)
    pid = f"{slug(d.get('name', ''))}-{uuid.uuid4().hex[:4]}"
    for sub in ("media", "audio", "out"):
        (PROJ / pid / sub).mkdir(parents=True, exist_ok=True)
    base = {k: d[k] for k in ("name", "aspect", "quality", "fps", "theme", "voice") if k in d}
    base["schema_version"] = SCHEMA_VERSION  # dự án mới: bật chuẩn hoá văn bản ngay từ đầu
    proj = normalize(base)
    save(pid, proj)
    return jsonify(id=pid, project=proj, tl=tl_json(proj))


@app.get("/api/projects/<pid>")
def get_project(pid):
    proj = normalize(load(pid))
    return jsonify(project=proj, tl=tl_json(proj), issues=issues_light(proj, pdir(pid)))


def recover_audio(d, proj, sc):
    """Giọng đã tạo trước đây cho đúng nội dung này (file tên <id cảnh>_<hash>.wav + file mô tả .wav.json bên cạnh).
    Nhờ vậy hoàn tác xoá cảnh / sửa lời đọc không bắt tạo lại giọng. Server tự tra theo hash, không tin dữ liệu từ trình duyệt."""
    if not R.needs_voice(sc):
        return None
    name = f"{sc['id']}_{R.audio_hash(proj, sc)}.wav"
    try:
        meta = json.loads((d / "audio" / (name + ".json")).read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict) or meta.get("file") != name or not (d / "audio" / name).is_file():
        return None
    return meta


@app.put("/api/projects/<pid>")
def put_project(pid):
    new = normalize(request.get_json(force=True))
    d = pdir(pid)
    with LOCK:
        old = {s["id"]: s.get("audio") for s in normalize(load(pid))["scenes"]}
        for s in new["scenes"]:  # audio do server quản lý
            s["audio"] = old.get(s["id"])
            if R.needs_voice(s) and not R.scene_audio(new, s):  # giọng đang giữ không khớp nội dung -> thử tìm giọng cũ khớp
                s["audio"] = recover_audio(d, new, s) or s["audio"]
        save(pid, new)
    return jsonify(tl=tl_json(new), audio={s["id"]: s["audio"] for s in new["scenes"]}, issues=issues_light(new, d))


@app.post("/api/projects/<pid>/upload")
def upload(pid):
    d = pdir(pid)
    f = request.files.get("file")
    if not f:
        return jsonify(error="Thiếu file"), 400
    ext = Path(f.filename or "").suffix.lower()
    if ext not in IMG_EXT | AUD_EXT:
        return jsonify(error=f"Không hỗ trợ định dạng {ext}"), 400
    name = uuid.uuid4().hex[:10] + ext
    (d / "media").mkdir(exist_ok=True)
    f.save(str(d / "media" / name))
    log.info("Tải lên %s (%s, %.1f MB) vào dự án %s", name, f.filename, (d / "media" / name).stat().st_size / 1e6, pid)
    return jsonify(file=name)


@app.get("/files/<pid>/<kind>/<path:name>")
def files(pid, kind, name):
    if kind not in ("media", "audio", "out"):
        abort(404)
    return send_from_directory(pdir(pid) / kind, name, as_attachment=bool(request.args.get("dl")))


# ----------------------------------------------------------------------------- vùng an toàn + dọn file
@app.get("/api/safe")
def safe_zones():
    """Đúng bảng SAFE mà renderer dùng, để đường kẻ trên preview không bao giờ lệch khỏi video xuất ra."""
    return jsonify(R.SAFE)


CLEAN_GRACE = 60  # giây: file mới tạo chưa chắc đã kịp được lưu vào project.json (đang tải lên, đang chờ lưu) nên giữ lại


def used_files(proj):
    """Tên file media/ và audio/ mà project.json còn tham chiếu (ảnh cảnh, nhạc nền, logo, giọng từng cảnh)."""
    media = {im["file"] for s in proj["scenes"] for im in s.get("images") or [] if im.get("file")}
    media |= {(proj.get(k) or {}).get("file") for k in ("bgm", "logo")} - {None, ""}
    audio = {s["audio"]["file"] for s in proj["scenes"] if isinstance(s.get("audio"), dict) and s["audio"].get("file")}
    return media, audio


def scan_unused(d, proj, grace=CLEAN_GRACE):
    """-> (danh sách file không còn được dùng, số file vừa tạo được giữ lại). Chỉ xét media/ và audio/, không đụng out/."""
    used = dict(zip(("media", "audio"), used_files(proj)))
    now = time.time()
    items, recent = [], 0
    for kind in ("media", "audio"):
        folder = d / kind
        if not folder.is_dir():
            continue
        for f in sorted(folder.iterdir()):
            if not f.is_file() or f.name.startswith("."):
                continue
            base = f.name[:-5] if kind == "audio" and f.name.endswith(".wav.json") else f.name  # file mô tả đi theo file giọng
            if base in used[kind]:
                continue
            try:
                st = f.stat()
            except OSError:
                continue
            if now - st.st_mtime < grace:
                recent += 1
                continue
            items.append(dict(kind=kind, name=f.name, size=st.st_size))
    return items, recent


@app.get("/api/projects/<pid>/unused")
def unused_files(pid):
    d = pdir(pid)
    with LOCK:
        items, recent = scan_unused(d, normalize(load(pid)))
    return jsonify(items=items, bytes=sum(i["size"] for i in items), recent=recent)


@app.post("/api/projects/<pid>/cleanup")
def cleanup(pid):
    """Xoá file không còn dùng. Danh sách xoá luôn do server tính lại; `files` (nếu có) chỉ để thu hẹp về đúng những gì
    người dùng đã xem ("media/ten.png"), nên không thể xoá file đang dùng hay file ngoài media/ và audio/."""
    d = pdir(pid)
    if any(j["state"] == "running" for j in JOBS.values()):
        return jsonify(error="Đang tạo giọng hoặc xuất video. Đợi xong rồi dọn nhé."), 409
    want = (request.get_json(force=True, silent=True) or {}).get("files")
    with LOCK:
        items, _ = scan_unused(d, normalize(load(pid)))
        if isinstance(want, list):
            want = {str(x) for x in want}
            items = [i for i in items if f"{i['kind']}/{i['name']}" in want]
        deleted = freed = failed = 0
        for i in items:
            try:
                (d / i["kind"] / i["name"]).unlink()
                deleted += 1
                freed += i["size"]
            except OSError:
                failed += 1
    return jsonify(deleted=deleted, bytes=freed, failed=failed)


# ----------------------------------------------------------------------------- preview frame
_ctxs = {}
_render_lock = threading.Lock()


@app.get("/api/projects/<pid>/preview.jpg")
def preview(pid):
    try:
        proj = normalize(load(pid))
        t = float(request.args.get("t", 0))
        h = max(240, min(int(request.args.get("h", 540)), 1080))
        W, H = R.frame_size(proj["aspect"], h)
        key = (pid, hashlib.md5(json.dumps(proj, sort_keys=True).encode()).hexdigest(), W, H)
        with _render_lock:
            ctx = _ctxs.get(key)
            if ctx is None:
                while len(_ctxs) >= 2:
                    _ctxs.pop(next(iter(_ctxs)))
                ctx = _ctxs[key] = R.Ctx(proj, pdir(pid), W, H)
            frame = ctx.render(t)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
        return Response(buf.tobytes(), mimetype="image/jpeg", headers={"Cache-Control": "no-store"})
    except HTTPException:
        raise
    except Exception as e:  # noqa
        return jsonify(E.explain(e, where="dựng khung xem trước")), 500


# ----------------------------------------------------------------------------- TTS + jobs
def friendly(e):
    """Giữ lại cho code cũ: chỉ lấy câu thông báo. Mới dùng E.explain() để có thêm hint và mã tra nhật ký."""
    return E.explain(e, log_it=False)["error"]


def store_audio(pid, sid, meta):
    with LOCK:
        proj = normalize(load(pid))
        for s in proj["scenes"]:
            if s["id"] == sid:
                s["audio"] = meta
        save(pid, proj)
        try:  # file mô tả cạnh file giọng, để recover_audio() tìm lại được sau khi hoàn tác
            (PROJ / pid / "audio" / (meta["file"] + ".json")).write_text(json.dumps(meta, ensure_ascii=False), "utf-8")
        except (OSError, KeyError):
            pass


@app.post("/api/projects/<pid>/tts")
def tts_one(pid):
    sid = request.get_json(force=True).get("scene")
    proj = normalize(load(pid))
    sc = next((s for s in proj["scenes"] if s["id"] == sid), None)
    if not sc or not R.needs_voice(sc):
        return jsonify(error="Cảnh này không có lời đọc."), 400
    chain = T.make_chain(proj)
    try:
        meta = M.tts_scene(pdir(pid), proj, sc, chain=chain)
    except Exception as e:  # noqa
        return jsonify(E.explain(e, where=f"tạo giọng cảnh {sid}")), 502
    store_audio(pid, sid, meta)
    return jsonify(audio=meta, tl=tl_json(normalize(load(pid))), notice=chain.summary())


def ensure_voices(job, pid, lo, hi, redo_fallback=False):
    """Tạo giọng cho các cảnh còn thiếu. Dùng MỘT chuỗi giọng cho cả lượt: giọng chính hỏng ở cảnh đầu thì các cảnh sau chuyển thẳng
    sang giọng dự phòng (khỏi chờ thử lại), và cuối lượt `job["notice"]` báo cho người dùng biết cảnh nào nghe khác.
    redo_fallback: đọc lại các cảnh đang dùng giọng dự phòng bằng giọng chính. Chỉ dùng giọng chính: lại hỏng thì báo lỗi và giữ giọng đang có."""
    proj = normalize(load(pid))
    if redo_fallback:
        chain = T.Chain(fallback=False)
        todo = [s for s in proj["scenes"] if R.needs_voice(s) and R.scene_audio(proj, s) and is_fallback_audio(s["audio"], chain.primary)]
    else:
        chain = T.make_chain(proj)
        todo = [s for s in proj["scenes"] if R.needs_voice(s) and not R.scene_audio(proj, s)]
    for i, sc in enumerate(todo):
        if job.get("cancel"):
            raise M.Cancelled()
        job.update(stage=f"Tạo giọng đọc ({i + 1}/{len(todo)})", progress=lo + (hi - lo) * i / max(len(todo), 1))
        meta = M.tts_scene(pdir(pid), proj, sc, chain=chain)  # lỗi để nổi lên: start_job dịch sang tiếng Việt + ghi nhật ký
        store_audio(pid, sc["id"], meta)
    job["notice"] = chain.summary()
    job["progress"] = hi


def is_fallback_audio(audio, primary):
    """Giọng này do nhà cung cấp dự phòng đọc? Giọng không ghi engine và giọng giả khi test không tính."""
    eng = (audio or {}).get("engine")
    return bool(eng) and eng not in ("fake", primary)


def start_job(fn, *a, kind=None):
    jid = uuid.uuid4().hex[:8]
    job = dict(id=jid, state="running", progress=0.0, stage="", message="", file=None, error=None, cancel=False, kind=kind, notice=None)
    JOBS[jid] = job

    def run():
        t0, name = time.time(), kind or getattr(fn, "__name__", "job")
        log.info("Job %s (%s) bắt đầu", jid, name)
        try:
            fn(job, *a)
            job.update(state="done", progress=1.0)
            log.info("Job %s (%s) xong sau %.1fs", jid, name, time.time() - t0)
        except M.Cancelled:
            job["state"] = "cancelled"
            log.info("Job %s (%s) bị huỷ sau %.1fs", jid, name, time.time() - t0)
        except Exception as e:  # noqa
            d = E.explain(e, where=f"job {jid} {name}")
            job.update(state="error", error=d["error"], hint=d["hint"], code=d["code"], ref=d["ref"])

    threading.Thread(target=run, daemon=True).start()
    return jid


@app.post("/api/projects/<pid>/tts_all")
def tts_all(pid):
    pdir(pid)
    redo = bool((request.get_json(silent=True) or {}).get("redo_fallback"))
    return jsonify(job=start_job(lambda job, p: ensure_voices(job, p, 0.0, 1.0, redo), pid))


def run_preflight(job, pid, d):
    """Kiểm tra dự án trước khi xuất: có lỗi thì dừng ngay với lời giải thích cụ thể; cảnh báo thì gửi kèm kết quả."""
    issues = C.preflight(normalize(load(pid)), d, deep=True)
    bad = C.blocking(issues)
    if bad:
        more = f" (và {len(bad) - 1} lỗi khác)" if len(bad) > 1 else ""
        raise E.UserError(bad[0]["msg"] + more, bad[0]["hint"], code="preflight")
    for i in issues:
        log.warning("Cảnh báo trước khi xuất [%s]: %s", i["code"], i["msg"])
    job["issues"] = issues


def export_job(job, pid, mode):
    preview_mode = mode == "preview"
    run_preflight(job, pid, pdir(pid))
    ensure_voices(job, pid, 0.0, 0.15)
    proj = normalize(load(pid))
    short = min(proj["quality"], 540) if preview_mode else proj["quality"]
    fps = min(proj["fps"], 30) if preview_mode else proj["fps"]
    name = "preview.mp4" if preview_mode else \
        f"{slug(proj['name'])}_{proj['aspect'].replace(':', 'x')}_{short}p{fps}_{time.strftime('%H%M%S')}.mp4"
    out = pdir(pid) / "out" / name
    tier = "preview" if preview_mode else proj["export_tier"]
    info = M.run_export(job, proj, pdir(pid), out, short, fps, tier, proj["encoder"], p0=0.15)
    job["file"] = f"/files/{pid}/out/{name}"
    job["info"] = info


@app.post("/api/projects/<pid>/render")
def render_video(pid):
    pdir(pid)
    mode = request.get_json(force=True).get("mode", "final")
    return jsonify(job=start_job(export_job, pid, mode))


def estimate_job(job, pid):
    proj = normalize(load(pid))
    info = M.estimate_export(job, proj, pdir(pid), proj["quality"], proj["fps"], proj["export_tier"], proj["encoder"])
    info["tier"] = proj["export_tier"]
    d = pdir(pid)
    info["issues"] = C.preflight(proj, d, deep=True)
    try:  # cần chỗ cho đoạn dựng tạm + file ghép + file kết quả
        free, need = shutil.disk_usage(d).free, info["mb"] * 1e6 * 3
        if need > free:
            info["issues"].append(dict(level="error", code="disk_low", scene=None,
                                       msg=f"Không đủ chỗ trống: cần khoảng {need / 1e9:.1f} GB, ổ đĩa còn {free / 1e9:.1f} GB.",
                                       hint="Giải phóng chỗ trống hoặc hạ chất lượng/fps rồi thử lại."))
    except OSError:
        pass
    info["voices_missing"] = sum(1 for s in proj["scenes"] if R.needs_voice(s) and not R.scene_audio(proj, s))
    job["info"] = info


@app.post("/api/projects/<pid>/estimate")
def estimate(pid):
    pdir(pid)
    return jsonify(job=start_job(estimate_job, pid))


# ----------------------------------------------------------------------------- kịch bản AI bằng Ollama
AI_CFG = ROOT / "ai_settings.json"  # theo máy (địa chỉ Ollama + mô hình), không nằm trong dự án nên không lẫn vào hoàn tác/xuất dự án


def ai_busy():
    return any(j.get("kind") == "ai" and j["state"] == "running" for j in JOBS.values())


@app.get("/api/ai/status")
def ai_status():
    """Địa chỉ + mô hình đang dùng và danh sách mô hình Ollama đã tải. `?url=` để thử một địa chỉ khác mà chưa lưu."""
    cfg = G.load_config(AI_CFG)
    out = dict(url=cfg["url"], model=cfg["model"], models=[], error=None)
    try:
        if request.args.get("url"):
            out["url"] = G.normalize_url(request.args["url"])
        out["models"] = G.list_models(out["url"])
    except G.ScriptError as e:
        out["error"] = str(e)
    names = [m["name"] for m in out["models"]]
    if names and out["model"] not in names:
        out["model"] = names[0]
    return jsonify(out)


@app.put("/api/ai/config")
def ai_config():
    d = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(G.save_config(AI_CFG, d.get("url"), d.get("model")))
    except G.ScriptError as e:
        return jsonify(error=str(e)), 400


def ai_script_job(job, base, model, req):
    def prog(k, n, frac):
        job.update(stage=f"AI đang viết kịch bản ({req['duration']} giây, mô hình {model})", progress=((k - 1) + frac) / n,
                   message="" if k == 1 else f"Lần {k - 1} chưa dùng được, đang viết lại (lần {k}/{n})…")

    try:
        res = G.generate(base, model, req["topic"], duration=req["duration"], tone=req["tone"], lang=req["lang"],
                         notes=req["notes"], cancel=lambda: job.get("cancel"), progress=prog)
    except G.Cancelled:
        raise M.Cancelled()
    job["script"] = res
    job["text"] = res["text"]


@app.post("/api/ai/script")
def ai_script():
    d = request.get_json(force=True, silent=True) or {}
    topic = d.get("topic") if isinstance(d.get("topic"), str) else ""
    if len(topic.strip()) < 3:
        return jsonify(error="Hãy nhập chủ đề (hoặc dán tư liệu) để AI viết kịch bản."), 400
    if ai_busy():
        return jsonify(error="AI đang viết một kịch bản khác. Đợi xong hoặc huỷ rồi thử lại."), 409
    lang = d.get("lang") if re.fullmatch(r"[a-z]{2}", str(d.get("lang") or "")) else "vi"
    req = dict(topic=topic, duration=nearest(d.get("duration"), G.DURATIONS, 60), lang=lang,
               tone=d.get("tone") if d.get("tone") in G.TONES else "explain",
               notes=d.get("notes") if isinstance(d.get("notes"), str) else "")
    cfg = G.load_config(AI_CFG)
    try:
        base = G.normalize_url(d.get("url") or cfg["url"])
        model = (d.get("model") or cfg["model"] or "").strip()
        if not model:  # chưa chọn: dùng mô hình đầu tiên đang có (đồng thời kiểm tra luôn Ollama có chạy không)
            models = G.list_models(base)
            if not models:
                return jsonify(error="Ollama chưa có mô hình nào. Chạy trong cửa sổ lệnh: ollama pull qwen2.5:7b (hoặc mô hình khác bạn thích)."), 400
            model = models[0]["name"]
    except G.OllamaUnreachable as e:
        return jsonify(error=str(e)), 502
    except G.ScriptError as e:
        return jsonify(error=str(e)), 400
    return jsonify(job=start_job(ai_script_job, base, model, req, kind="ai"))


@app.get("/api/doctor")
def doctor():
    return jsonify(D.run_checks())


@app.get("/api/jobs/<jid>")
def job_status(jid):
    j = JOBS.get(jid)
    return jsonify(j) if j else (jsonify(error="Không có job"), 404)


@app.post("/api/jobs/<jid>/cancel")
def job_cancel(jid):
    if jid in JOBS:
        JOBS[jid]["cancel"] = True
    return jsonify(ok=True)


# ----------------------------------------------------------------------------- nhật ký, kiểm tra, xử lý lỗi
HTTP_STATUS = dict(network=502, tts_denied=502, tts_no_audio=502, tts_none=502, not_found=404, bad_request=400, upload_too_large=413,
                   upload_type=400, no_scenes=400, preflight=400)


@app.errorhandler(Exception)
def on_error(exc):
    """Mọi lỗi trong route trả JSON {error, hint, code, ref} bằng tiếng Việt (không để lộ trang lỗi HTML/traceback)."""
    if isinstance(exc, HTTPException):
        status = exc.code or 500
        return jsonify(E.http_error(status, f"{request.method} {request.path}")), status
    d = E.explain(exc, where=f"{request.method} {request.path}")
    return jsonify(d), HTTP_STATUS.get(d["code"], 500)


@app.after_request
def log_bad_requests(resp):
    if resp.status_code >= 400 and request.path != "/favicon.ico":
        log.warning("HTTP %s %s %s", resp.status_code, request.method, request.path)
    return resp


@app.get("/api/ping")
def ping():
    return jsonify(app="firefly-video", version=__version__)


@app.get("/api/logs")
def logs_tail():
    try:
        n = max(1, min(int(request.args.get("lines", 300)), 2000))
    except ValueError:
        n = 300
    return jsonify(path=str(L.log_path()), lines=L.tail(n))


@app.get("/api/logs/download")
def logs_download():
    p = L.log_path()
    if not p.is_file():
        abort(404)
    return send_file(p, as_attachment=True, download_name="firefly.log", mimetype="text/plain")


CLIENT_LOG = dict(n=0)
CLIENT_LOG_MAX = 50  # mỗi lần chạy: một trang bị lặp lỗi không được làm đầy nhật ký


@app.post("/api/client-log")
def client_log():
    """Lỗi JavaScript trong trình duyệt (nếu có) cũng được ghi vào nhật ký để còn truy ra."""
    if CLIENT_LOG["n"] >= CLIENT_LOG_MAX:
        return jsonify(ok=False), 429
    CLIENT_LOG["n"] += 1
    d = request.get_json(force=True, silent=True) or {}
    one = lambda v, n: " ".join(str(v or "").split())[:n]  # noqa: E731
    log.warning("Lỗi giao diện (trình duyệt): %s | %s | %s", one(d.get("msg"), 500), one(d.get("src"), 200),
                one(d.get("stack"), 1500))
    return jsonify(ok=True)


@app.get("/api/projects/<pid>/check")
def project_check(pid):
    d = pdir(pid)
    return jsonify(issues=C.preflight(normalize(load(pid)), d, deep=request.args.get("deep") == "1"))


# ----------------------------------------------------------------------------- main
def find_running(port):
    """Đã có một Firefly Video khác chạy ở cổng này chưa (hỏi /api/ping)."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=0.7) as r:
            return json.loads(r.read()).get("app") == "firefly-video"
    except Exception:  # noqa
        return False


def port_free(port):
    with socket.socket() as sk:
        try:
            sk.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def pick_port(preferred, tries=10):
    """-> (cổng, đã_có_bản_đang_chạy). Cổng bận bởi chương trình khác thì thử cổng kế tiếp."""
    for p in range(preferred, preferred + tries):
        if find_running(p):
            return p, True
        if port_free(p):
            return p, False
    raise E.UserError(f"Các cổng {preferred}–{preferred + tries - 1} đều đang bận.",
                      "Tắt bớt chương trình đang chiếm cổng, hoặc chạy với cổng khác: đặt biến môi trường PORT=9000.", code="port_busy")


def startup_info():
    info = {}
    try:
        import subprocess
        exe = M.ffmpeg_exe()
        ver = subprocess.run([exe, "-version"], capture_output=True, timeout=10, **M.NOWIN).stdout.decode("utf-8", "ignore")
        info["FFmpeg"] = f"{(ver.splitlines() or [exe])[0]} ({exe})"
    except Exception as e:  # noqa
        info["FFmpeg"] = f"KHÔNG chạy được ({e})"
    return info


def open_browser(url):
    """Mở trình duyệt vào tool. Không có trình duyệt (máy chủ, WSL không có wslview, SSH…) thì chỉ nhắc địa chỉ, không làm tool hỏng.
    Đặt FFV_NO_BROWSER=1 để không bao giờ tự mở (chạy ngầm, CI)."""
    if os.environ.get("FFV_NO_BROWSER"):
        return False
    try:
        ok = webbrowser.open(url)
    except Exception:  # noqa
        ok = False
    if not ok:
        log.info("Không tự mở được trình duyệt")
        print(f"  Không tự mở được trình duyệt. Hãy mở địa chỉ này bằng tay: {url}\n")
    return ok


def utf8_stdio():
    """In tiếng Việt ra stdout/stderr mà không bao giờ ném lỗi mã hoá.
    Bản .exe PyInstaller bỏ qua PYTHONUTF8/PYTHONIOENCODING, nên khi stdout/stderr là pipe hay file (không phải cửa sổ lệnh) Windows dùng bảng mã
    ANSI (cp1252): "đ", "Ỗ"… không mã hoá được -> UnicodeEncodeError ngay ở dòng in địa chỉ, rồi lỗi thứ hai trong chính khối báo lỗi
    -> "Failed to execute script 'app'". Cửa sổ lệnh thật thì Python đã ghi bằng UTF-8, chỉ cần không văng lỗi vì một ký tự."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass  # không có stream (bản không cửa sổ lệnh) hoặc không phải TextIOWrapper


def main():
    multiprocessing.freeze_support()
    PROJ.mkdir(parents=True, exist_ok=True)
    L.setup()
    L.banner(startup_info())
    R.ensure_fonts()
    try:
        pref = int(os.environ.get("PORT", 8765))
        port, running = pick_port(pref)
    except ValueError:
        port, running, pref = 8765, False, 8765
    url = f"http://localhost:{port}"
    if running:
        print(f"\n  {APP_NAME} đã chạy sẵn ở {url} – đang mở trình duyệt vào đó.\n")
        log.info("Đã có bản đang chạy ở cổng %s, mở trình duyệt và thoát", port)
        open_browser(url)
        return 0
    if port != pref:
        log.warning("Cổng %s đang bận, dùng cổng %s", pref, port)
    threading.Timer(1.2, lambda: open_browser(url)).start()
    print(f"\n  {APP_NAME} v{__version__} đang chạy tại {url}  (Ctrl+C để tắt)")
    print(f"  Nhật ký: {L.log_path()}\n")
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False)
    return 0


if __name__ == "__main__":
    utf8_stdio()
    try:
        sys.exit(main())
    except E.UserError as e:
        log.error("[%s] %s %s", e.code, e.message, e.hint)
        print(f"\n  LỖI: {e.message}\n  {e.hint}\n")
    except Exception as e:  # noqa
        d = E.explain(e, where="khởi động")
        print(f"\n  LỖI: {d['error']}\n  {d['hint']}\n")
    if getattr(sys, "frozen", False) and sys.platform == "win32" and sys.stdin is not None and sys.stdin.isatty():
        try:
            input("Bấm Enter để đóng cửa sổ…")  # bản .exe: giữ cửa sổ lại để người dùng kịp đọc lỗi (chỉ khi có người ngồi trước cửa sổ lệnh)
        except (EOFError, OSError):
            pass
    sys.exit(1)
