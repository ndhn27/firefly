"""Biến lỗi kỹ thuật (FFmpeg, hệ điều hành, mạng, thư viện) thành thông báo tiếng Việt kèm cách xử lý.
explain(exc) -> dict(error, hint, code, ref):
  error: chuyện gì xảy ra · hint: làm gì tiếp · code: nhóm lỗi (README có bảng) · ref: mã tra trong logs/firefly.log.
Lỗi nào chưa biết thì báo chung kèm mã ref; toàn bộ chi tiết kỹ thuật chỉ nằm trong nhật ký, không đẩy lên màn hình."""
import errno
import logging
import re
import uuid

import logsetup as L

log = logging.getLogger("ffv.errors")
STDERR_TAIL = 400


class UserError(Exception):
    """Lỗi đã biết, đã có lời giải thích sẵn cho người dùng."""

    def __init__(self, message, hint="", code="user"):
        super().__init__(message)
        self.message, self.hint, self.code = message, hint, code

    def __reduce__(self):  # ném qua tiến trình con (pickle) mà không mất hint/code
        return (UserError, (self.message, self.hint, self.code))


class FFmpegError(RuntimeError):
    """FFmpeg thoát với lỗi. `where` = đang làm gì; `stderr` = phần cuối thông báo của FFmpeg (để nhận diện nguyên nhân)."""

    def __init__(self, where, stderr=""):
        tail = (stderr or "").strip()[-STDERR_TAIL:]
        super().__init__(f"FFmpeg lỗi khi {where}" + (f": {tail}" if tail else ""))
        self.where, self.stderr = where, (stderr or "")

    def __reduce__(self):
        return (FFmpegError, (self.where, self.stderr))


# (code, thông báo, cách xử lý). {file} {ref} {log} được điền khi hiển thị.
MSG = {
    "disk_full": ("Ổ đĩa đã đầy nên không ghi tiếp được.",
                  "Giải phóng chỗ trống (xoá file xuất cũ trong projects/<dự án>/out/, hoặc Cài đặt → Dọn file không dùng) rồi xuất lại. Đoạn đã dựng được giữ nên lần sau chạy tiếp."),
    "permission": ("Không ghi được file{file}: bị chặn quyền hoặc file đang được mở ở chương trình khác.",
                   "Đóng chương trình đang mở file đó (trình phát video?), kiểm tra thư mục không ở chế độ chỉ đọc hoặc bị phần mềm diệt virus chặn, rồi thử lại."),
    "file_missing": ("Không tìm thấy file{file}.",
                     "File có thể đã bị xoá hoặc di chuyển. Thêm lại file đó vào cảnh rồi thử lại."),
    "ffmpeg_missing": ("Không chạy được FFmpeg (phần mềm dựng video).",
                       "Chạy `python doctor.py` để xem chi tiết. Cài bằng `pip install imageio-ffmpeg` hoặc `winget install Gyan.FFmpeg`, rồi mở lại tool."),
    "path_too_long": ("Đường dẫn file quá dài (Windows giới hạn khoảng 260 ký tự).",
                      "Đặt thư mục tool ở chỗ ngắn hơn, ví dụ C:\\firefly, hoặc đặt tên dự án ngắn hơn."),
    "out_of_memory": ("Máy hết bộ nhớ (RAM) khi dựng.",
                      "Đóng bớt chương trình khác, hạ chất lượng (2K → 1080p) hoặc fps (60 → 30) trong Cài đặt, hoặc dùng ảnh nhỏ hơn rồi xuất lại."),
    "worker_died": ("Một tiến trình dựng hình bị tắt đột ngột giữa chừng.",
                    "Thường do thiếu RAM hoặc phần mềm diệt virus chặn. Hạ chất lượng/fps trong Cài đặt rồi xuất lại; đoạn đã dựng xong vẫn được giữ."),
    "image_corrupt": ("Có ảnh hỏng hoặc không đọc được{file}.",
                      "Mở ảnh bằng chương trình khác, lưu lại thành PNG hoặc JPG rồi thêm lại vào cảnh."),
    "image_huge": ("Ảnh quá lớn{file} nên bị từ chối vì lý do an toàn bộ nhớ.",
                   "Thu nhỏ ảnh (cạnh dài dưới khoảng 8000 px) rồi thêm lại."),
    "gpu_encoder": ("Card đồ hoạ / bộ mã hoá GPU không chạy được trên máy này.",
                    "Vào Cài đặt → Bộ mã hoá, chọn CPU (x264) rồi xuất lại. Muốn dùng GPU thì cập nhật driver card đồ hoạ."),
    "encoder_missing": ("Bản FFmpeg đang dùng thiếu bộ mã hoá H.264 cần thiết.",
                        "Chạy `python doctor.py`; cài lại bằng `pip install -U imageio-ffmpeg` hoặc dùng bản FFmpeg đầy đủ."),
    "bad_media": ("File âm thanh/nhạc nền không đọc được.",
                  "Vào Cài đặt → Nhạc nền, bỏ file này hoặc chọn file MP3/WAV khác."),
    "network": ("Không kết nối được dịch vụ giọng đọc. Kiểm tra internet rồi thử lại.",
                "Giọng Edge TTS cần internet. Nếu đang bật VPN/proxy, thử tắt đi. Mạng đã ổn mà vẫn lỗi thì thử lại sau ít phút. Muốn tạo giọng được cả khi mất mạng: cài giọng dự phòng Piper (xem README, mục Giọng dự phòng)."),
    "tts_denied": ("Dịch vụ giọng đọc từ chối yêu cầu (lỗi 403).",
                   "Hay do đồng hồ máy lệch giờ: bật đồng bộ ngày giờ tự động của hệ điều hành. Nếu không phải, cập nhật thư viện: `pip install -U edge-tts`."),
    "tts_no_audio": ("Dịch vụ giọng đọc không trả về âm thanh.",
                     "Thử lại. Nếu cảnh này vẫn lỗi, kiểm tra lời đọc có ký tự lạ/biểu tượng không, hoặc đổi giọng khác trong Cài đặt."),
    "unexpected": ("Có lỗi không mong muốn.",
                   "Mã lỗi {ref}. Chi tiết đã ghi vào {log}. Gửi file nhật ký (nút “Nhật ký” trong Kiểm tra máy) khi cần hỗ trợ."),
}


def _file(exc):
    name = getattr(exc, "filename", None)
    if not name:
        m = re.search(r"['\"]([^'\"]+\.[A-Za-z0-9]{2,5})['\"]", str(exc))
        name = m.group(1) if m else None
    return f" “{str(name).replace(chr(92), '/').split('/')[-1]}”" if name else ""


def _mro(exc):
    return {c.__name__ for c in type(exc).__mro__}


def classify(exc):
    """-> (code, thông báo, hint) hoặc code 'unexpected'. Thông báo/hint có thể còn {file} {ref} {log}."""
    if isinstance(exc, UserError):
        return exc.code, exc.message, exc.hint
    names = _mro(exc)
    if "ScriptError" in names:  # lỗi Ollama/kịch bản AI: đã là tiếng Việt, đủ ý, giữ nguyên
        return "ai", str(exc), ""
    text = f"{type(exc).__name__}: {exc}".lower()
    if isinstance(exc, FFmpegError):
        text += " " + exc.stderr.lower()
    # --- theo loại lỗi / mã hệ điều hành
    if isinstance(exc, OSError):
        en, we = getattr(exc, "errno", None), getattr(exc, "winerror", None)
        if en == errno.ENOSPC or we == 112:
            return ("disk_full",) + MSG["disk_full"]
        if isinstance(exc, FileNotFoundError):
            if "ffmpeg" in text:
                return ("ffmpeg_missing",) + MSG["ffmpeg_missing"]
            return ("file_missing",) + MSG["file_missing"]
        if isinstance(exc, PermissionError) or en in (errno.EACCES, errno.EPERM) or we in (5, 32, 33):
            return ("permission",) + MSG["permission"]
        if en == errno.ENAMETOOLONG or we == 206:
            return ("path_too_long",) + MSG["path_too_long"]
    if isinstance(exc, MemoryError):
        return ("out_of_memory",) + MSG["out_of_memory"]
    if "BrokenProcessPool" in names:
        return ("worker_died",) + MSG["worker_died"]
    if "UnidentifiedImageError" in names or "cannot identify image file" in text:
        return ("image_corrupt",) + MSG["image_corrupt"]
    if "DecompressionBombError" in names or "decompression bomb" in text:
        return ("image_huge",) + MSG["image_huge"]
    if "NoAudioReceived" in names or "no audio was received" in text:
        return ("tts_no_audio",) + MSG["tts_no_audio"]
    # --- theo nội dung thông báo (stderr của FFmpeg, thư viện mạng...)
    if "no space left on device" in text or "disk full" in text:
        return ("disk_full",) + MSG["disk_full"]
    if re.search(r"cannot load libcuda|no nvenc capable|openencodesessionex failed|cuda_error|nvenc.*(error|fail)|"
                 r"mfx session|h264_qsv.*(error|fail)|h264_amf.*(error|fail)|amf.*(failed|initialization)", text):
        return ("gpu_encoder",) + MSG["gpu_encoder"]
    if re.search(r"unknown encoder|encoder .{0,40}not found|unrecognized option 'profile", text):
        return ("encoder_missing",) + MSG["encoder_missing"]
    if "permission denied" in text:
        return ("permission",) + MSG["permission"]
    if isinstance(exc, FFmpegError):
        if "invalid data found when processing input" in text or "moov atom not found" in text:
            return ("bad_media",) + MSG["bad_media"]
        if "no such file or directory" in text or "error opening input" in text:
            return ("file_missing",) + MSG["file_missing"]
    if "403" in text and re.search(r"invalid response status|handshake|websocket|forbidden", text):
        return ("tts_denied",) + MSG["tts_denied"]
    if re.search(r"cannot connect to host|getaddrinfo|name or service not known|temporary failure in name resolution|"
                 r"network is unreachable|connection (reset|refused|aborted)|timed? ?out|timeout|ssl|clientconnector|"
                 r"clientoserror|connectionerror", text):
        return ("network",) + MSG["network"]
    if re.search(r"std::bad_alloc|cannot allocate memory|insufficient memory|out of memory", text):
        return ("out_of_memory",) + MSG["out_of_memory"]
    return ("unexpected",) + MSG["unexpected"]


def explain(exc, where="", log_it=True):
    """-> dict(error, hint, code, ref). Ghi nhật ký (kèm traceback) trừ các lỗi mong đợi (UserError, kịch bản AI)."""
    ref = uuid.uuid4().hex[:6]
    code, msg, hint = classify(exc)
    fmt = dict(file=_file(exc), ref=ref, log=str(L.log_path()))
    out = dict(error=msg.format(**fmt), hint=hint.format(**fmt), code=code, ref=ref)
    if log_it:
        if code in ("user", "ai", "preflight", "no_scenes", "not_found", "bad_request", "upload_type", "upload_too_large"):
            log.warning("[%s] %s ref=%s%s", code, out["error"], ref, f" ({where})" if where else "")
        else:
            extra = f"\n  stderr: {exc.stderr.strip()[-1500:]}" if isinstance(exc, FFmpegError) and exc.stderr.strip() else ""
            log.log(logging.ERROR if code == "unexpected" else logging.WARNING, "[%s] %s ref=%s%s | %s: %s%s",
                    code, out["error"], ref, f" ({where})" if where else "", type(exc).__name__, str(exc)[:600], extra,
                    exc_info=exc)
    return out


def http_error(status, where=""):
    """Mô tả lỗi HTTP chuẩn (404, 413...) bằng tiếng Việt cho các route API."""
    table = {
        400: ("bad_request", "Yêu cầu không hợp lệ.", "Tải lại trang rồi thử lại."),
        404: ("not_found", "Không tìm thấy mục này (dự án hoặc file có thể đã bị xoá).", "Tải lại trang và chọn lại dự án."),
        405: ("bad_request", "Thao tác không được hỗ trợ.", "Tải lại trang rồi thử lại."),
        413: ("upload_too_large", "File quá lớn (giới hạn 400 MB mỗi lần tải lên).", "Chọn file nhỏ hơn: ảnh dưới vài chục MB, nhạc dưới 400 MB."),
    }
    code, msg, hint = table.get(status, ("unexpected", MSG["unexpected"][0], MSG["unexpected"][1]))
    ref = uuid.uuid4().hex[:6]
    out = dict(error=msg, hint=hint.format(ref=ref, log=str(L.log_path())), code=code, ref=ref)
    if status >= 500:
        log.error("HTTP %s ref=%s %s", status, ref, where)
    return out
