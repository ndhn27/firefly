"""Kiểm tra dự án trước khi xuất, để lỗi hiện ra bằng lời dễ hiểu (cảnh nào, file nào) thay vì video sai lặng lẽ
hoặc FFmpeg chết giữa chừng. preflight() trả danh sách vấn đề: dict(level=error|warn, code, scene, msg, hint).
  error: xuất sẽ sai/không chạy được -> chặn xuất.   warn: xuất được nhưng nên biết."""
import shutil
from pathlib import Path

GB = 1e9
LONG_NARRATION = 2500  # ký tự


def _issue(level, code, scene, msg, hint=""):
    return dict(level=level, code=code, scene=scene, msg=msg, hint=hint)


def preflight(proj, d, deep=False):
    """deep=False: chỉ kiểm tra file còn tồn tại (rẻ, chạy mỗi lần lưu). deep=True: mở thử từng ảnh + kiểm tra ổ đĩa."""
    d = Path(d)
    out = []
    scenes = proj.get("scenes") or []
    if not scenes:
        out.append(_issue("error", "no_scenes", None, "Chưa có cảnh nào.", "Thêm cảnh (nút + Cảnh) hoặc dán kịch bản rồi xuất lại."))
    seen = set()
    for n, sc in enumerate(scenes, 1):
        empty = not any((sc.get(k) or "").strip() for k in ("title", "subtitle", "narration")) and not sc.get("images")
        if empty:
            out.append(_issue("warn", "empty_scene", n, f"Cảnh {n} trống: không có chữ, ảnh hay lời đọc (chỉ thấy nền).",
                              "Thêm nội dung hoặc xoá cảnh này."))
        if len((sc.get("narration") or "")) > LONG_NARRATION:
            out.append(_issue("warn", "long_narration", n, f"Lời đọc cảnh {n} rất dài ({len(sc['narration'])} ký tự).",
                              "Nên tách thành nhiều cảnh để phụ đề và ảnh đổi nhịp hơn."))
        for im in sc.get("images") or []:
            f = im.get("file")
            if not f or (n, f) in seen:
                continue
            seen.add((n, f))
            p = d / "media" / f
            if not p.is_file():
                out.append(_issue("error", "image_missing", n, f"Cảnh {n}: không tìm thấy ảnh “{f}”.",
                                  "File ảnh đã bị xoá hoặc di chuyển. Xoá ảnh này khỏi cảnh hoặc thêm lại ảnh."))
            elif deep:
                try:
                    from PIL import Image
                    with Image.open(p) as im_:
                        w, h = im_.size
                        im_.verify()
                    if max(w, h) > 12000:
                        out.append(_issue("warn", "image_huge", n, f"Cảnh {n}: ảnh “{f}” rất lớn ({w}×{h}), dựng sẽ chậm và tốn RAM.",
                                          "Thu nhỏ ảnh (cạnh dài dưới khoảng 6000 px)."))
                except Exception:  # noqa
                    out.append(_issue("error", "image_corrupt", n, f"Cảnh {n}: ảnh “{f}” hỏng hoặc không đọc được.",
                                      "Mở bằng chương trình khác, lưu lại thành PNG/JPG rồi thêm lại."))
    for key, label in (("bgm", "Nhạc nền"), ("logo", "Logo")):
        f = (proj.get(key) or {}).get("file")
        if f and not (d / "media" / f).is_file():
            out.append(_issue("warn", f"{key}_missing", None, f"{label} đã chọn nhưng file không còn, video sẽ không có {label.lower()}.",
                              f"Vào Cài đặt chọn lại {label.lower()} hoặc bỏ mục này."))
    if deep:
        try:
            free = shutil.disk_usage(d).free / GB
        except OSError:
            free = None
        if free is not None and free < 0.5:
            out.append(_issue("error", "disk_low", None, f"Ổ đĩa gần đầy (còn {free:.2f} GB).",
                              "Giải phóng chỗ trống rồi xuất lại: xuất video cần chỗ cho các đoạn dựng tạm và file kết quả."))
        elif free is not None and free < 3:
            out.append(_issue("warn", "disk_low", None, f"Ổ đĩa còn ít chỗ trống ({free:.1f} GB).",
                              "Video dài hoặc 2K 60fps có thể cần vài GB. Nên dọn bớt trước khi xuất."))
    return out


def blocking(issues):
    return [i for i in issues if i["level"] == "error"]
