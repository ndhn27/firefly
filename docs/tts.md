# Giọng đọc, phụ đề và giọng dự phòng

Quay lại [README](../README.md).

## Phụ đề và giọng đọc
- Phụ đề đổi cụm đúng lúc từ đầu cụm được đọc, dựa vào mốc từng từ do edge-tts trả về (nếu dịch vụ chỉ trả mốc theo câu thì
  chia đều theo độ dài chữ trong câu; không có mốc nào thì chia theo độ dài chữ rồi hút vào chỗ ngắt hơi).
- Tuỳ chọn **Phụ đề: tô sáng từ đang đọc** trong Cài đặt.
- **Chuẩn hoá số, %, ngày, đơn vị khi đọc** (VD `15%` → "15 phần trăm", `12/10/2026` → "ngày 12 tháng 10 năm 2026", `5km` → "5 ki-lô-mét").
  Dự án mới mặc định bật; dự án có từ trước giữ tắt để giọng đã tạo không bị mất hiệu lực. Đổi mục này thì phải tạo lại giọng.
  Lưu ý: số kiểu `3.141` (đúng 3 chữ số sau dấu chấm) được hiểu là dấu phân cách hàng nghìn kiểu Việt; cần đọc khác thì dùng từ điển phát âm.

## Giọng dự phòng
Edge TTS là endpoint không chính thức của Microsoft: có thể đổi giao thức hoặc chặn bất cứ lúc nào. Giọng đọc đi qua một **chuỗi nhà cung cấp** (`tts.py`);
giọng chính hỏng thì tự chuyển sang giọng sau, video vẫn dựng được.

| Thứ tự | Tên (`FFV_TTS`) | Là gì | Cần gì |
|---|---|---|---|
| 1 | `edge` | Microsoft Edge TTS (`edge-tts`): chất lượng tốt nhất, có mốc từng từ cho phụ đề | internet; đã có trong `requirements.txt` |
| 2 | `piper` | Piper chạy ngay trên máy: offline, lời đọc không gửi đi đâu | chương trình `piper` + file giọng `.onnx` (cài bên dưới) |
| 3 | `gtts` | Google Translate TTS qua `gTTS`: cũng không chính thức, chỉ là phương án cuối | internet; `pip install gTTS` (`requirements-optional.txt`) |

- **Cách chọn giọng**: thử lần lượt; nhà cung cấp chưa cài hoặc không có giọng cho ngôn ngữ đó thì bỏ qua lặng lẽ. Lỗi mạng hoặc 403 thì đánh dấu hỏng *trong cả lượt tạo giọng*
  (chỉ cảnh đầu phải chờ Edge hỏng, các cảnh sau chuyển thẳng). Lỗi lạ của thư viện (VD Microsoft đổi giao thức) thì cảnh đó dùng giọng dự phòng nhưng cảnh sau vẫn thử lại giọng chính.
  Lỗi của chính máy (`disk_full`, `permission`, `file_missing`, `path_too_long`, `out_of_memory`, `ffmpeg_missing`) báo ngay, không đổi giọng vì đổi cũng không giúp gì.
  Tất cả đều hỏng thì báo lỗi của **giọng chính** (VD `network`); không có giọng nào dùng được thì báo `tts_none`.
- **Tên giọng vẫn là tên giọng Edge** (`vi-VN-HoaiMyNeural`); giọng dự phòng được chọn theo *ngôn ngữ* của tên đó (`vi-VN` → tiếng Việt). Piper ưu tiên đúng vùng, rồi cùng ngôn ngữ; trong một ngôn ngữ ưu tiên chất lượng `medium` > `high` > `low` > `x_low`.
- **Khác giọng chính**: không có mốc từng từ nên phụ đề đổi cụm theo chỗ ngắt hơi; không chỉnh được cao độ (chỉ Edge). Tốc độ vẫn dùng được: Piper qua `--length_scale`, gTTS qua `atempo` của ffmpeg (0,5–2,0×).
- **Báo cho người dùng**: sau lượt tạo giọng có hộp thoại *Đã dùng giọng dự phòng* nói mấy cảnh, bằng giọng nào. Cảnh đó có nhãn **🔊 dự phòng** trong danh sách và dòng ⚠ trong khung chỉnh sửa.
  Nhà cung cấp ghi trong `scene.audio.engine` (giọng không có trường này thì không bị đánh dấu).
- **Cài đặt → 4 · Giọng đọc**: công tắc *Tự chuyển sang giọng dự phòng khi giọng chính lỗi* (`voice.fallback` của dự án, mặc định bật; tắt thì giọng chính lỗi là báo lỗi ngay),
  tình trạng từng nhà cung cấp (kiểm tra trên máy, không gọi mạng), và nút **Tạo lại các cảnh đó bằng giọng chính** khi Edge chạy lại để cả video đồng nhất giọng.
  Nút này chỉ dùng giọng chính: lại hỏng thì báo lỗi và giữ nguyên giọng đang có. Công tắc không làm đổi mã giọng (`audio_hash`) nên bật/tắt không bắt tạo lại giọng.
- **Kiểm tra máy** (`python doctor.py`) liệt kê từng nhà cung cấp; chưa có giọng dự phòng chỉ là cảnh báo, không bao giờ là lỗi.

**Cài Piper (khuyên dùng làm dự phòng, hoặc làm giọng chính nếu muốn chạy hoàn toàn offline)**
1. Chương trình: `pip install piper-tts` (có lệnh `piper`), hoặc chép bản `piper` vào `piper/piper` (`piper\piper.exe` trên Windows) **cạnh app.py / cạnh file .exe**, hoặc đặt `FFV_PIPER` trỏ tới nó.
   Tool chạy Piper như một chương trình riêng (không `import`) vì Piper bản mới dùng giấy phép GPL-3.0.
2. Giọng: tải cặp file `<tên>.onnx` và `<tên>.onnx.json` (thiếu `.json` thì bị bỏ qua) vào thư mục `piper_voices/` cùng chỗ trên (hoặc `FFV_PIPER_VOICES`).
   Kho giọng: <https://huggingface.co/rhasspy/piper-voices>; tiếng Việt nằm ở `vi/vi_VN/`: `vi_VN-vais1000-medium`, `vi_VN-25hours_single-low`, `vi_VN-vivos-x_low`. Mỗi giọng có giấy phép riêng: xem model card trước khi dùng thương mại.
3. Mở **Cài đặt → 4 · Giọng đọc** hoặc chạy `python doctor.py`: dòng *Dự phòng · Piper* phải hiện ✓ cùng tên giọng.

**Biến môi trường**: `FFV_TTS` đổi thứ tự/bật tắt nhà cung cấp (VD `FFV_TTS=piper,edge` ưu tiên offline; `FFV_TTS=edge` chỉ dùng Edge); `FFV_PIPER`, `FFV_PIPER_VOICES` như trên.

**Dùng thương mại**: Edge TTS và gTTS đều là endpoint không chính thức. Muốn chắc chắn thì dùng Piper với giọng có giấy phép phù hợp, hoặc thêm một dịch vụ có điều khoản rõ ràng:
viết một lớp có `status(voice)` và `synth(text, voice, rate, pitch, workdir)` trả `tts.Synth` rồi thêm vào `REGISTRY` trong `tts.py`; phần còn lại (chuyển giọng, báo người dùng, đổi tốc độ) tự chạy.

## Ghi chú
- Giọng chính dùng `edge-tts` (endpoint đọc văn bản của Microsoft Edge, không chính thức, cần internet; có thể ngừng
  hoạt động bất cứ lúc nào) nên có giọng dự phòng Piper/gTTS (mục Giọng dự phòng). Muốn dùng thương mại chắc chắn thì dùng Piper với giọng phù hợp giấy phép hoặc dịch vụ có điều khoản rõ ràng.
