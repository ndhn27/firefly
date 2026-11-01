# Nhật ký và xử lý lỗi

Quay lại [README](../README.md).

- Mọi thứ được ghi vào `logs/firefly.log` (xoay vòng 5 file × 1 MB): khởi động (phiên bản, FFmpeg, hệ điều hành), từng việc dài (tạo giọng, xuất video) và thời gian
  chạy, encoder được chọn, đoạn dựng được dùng lại, cảnh báo, và lỗi kèm traceback. Lỗi của tiến trình dựng song song và lỗi JavaScript trong trình duyệt
  cũng về chung file này. Tool không chủ ý ghi nội dung kịch bản/lời đọc (chỉ số liệu và tên file), nhưng thông báo lỗi của thư viện đôi khi kèm vài ký tự, nên đọc lướt nhật ký trước khi gửi cho người khác.
- **Cài đặt → Kiểm tra máy → 📄 Nhật ký** xem 300 dòng cuối và tải file về để gửi khi cần hỗ trợ. Hộp thoại lỗi cũng có nút **Xem nhật ký** và *mã tra nhật ký*
  (6 ký tự) để tìm đúng dòng.
- Muốn chi tiết hơn (có cả lệnh FFmpeg và thời gian từng bước): đặt biến môi trường `FFV_LOG_LEVEL=DEBUG` trước khi chạy.
- Lỗi hiện bằng tiếng Việt kèm **cách xử lý**; chi tiết kỹ thuật chỉ nằm trong nhật ký. Các nhóm lỗi tool nhận diện được:

| Mã | Khi nào | Gợi ý tool đưa ra |
|---|---|---|
| `disk_full` | ổ đĩa đầy | giải phóng chỗ; đoạn đã dựng được giữ nên lần sau chạy tiếp |
| `permission` | file đang mở ở chương trình khác / bị chặn quyền | đóng trình phát video, kiểm tra diệt virus |
| `file_missing` | ảnh/file bị xoá hoặc di chuyển | thêm lại file |
| `ffmpeg_missing`, `encoder_missing` | không chạy được FFmpeg / thiếu H.264 | `python doctor.py`, cài lại FFmpeg |
| `gpu_encoder` | NVENC/QSV/AMF không chạy được | chọn CPU (x264) trong Cài đặt, cập nhật driver |
| `out_of_memory`, `worker_died` | hết RAM, tiến trình dựng bị tắt đột ngột | hạ 2K→1080p hoặc 60→30 fps |
| `image_corrupt`, `image_huge`, `bad_media` | ảnh/nhạc hỏng hoặc quá lớn | lưu lại thành PNG/JPG, chọn file khác |
| `network`, `tts_denied`, `tts_no_audio` | giọng Edge TTS: mất mạng, lỗi 403 (hay do lệch giờ máy), không trả âm thanh | kiểm tra mạng/VPN, bật đồng bộ giờ, `pip install -U edge-tts`; có giọng dự phòng thì tool tự chuyển (xem [tts.md](tts.md)) |
| `tts_none` | không có giọng đọc nào dùng được (hoặc giọng chính lỗi mà công tắc giọng dự phòng đang tắt) | cài Piper/gTTS theo [tts.md](tts.md), hoặc bật lại công tắc trong Cài đặt |
| `project_corrupt` | `project.json` hỏng và không có bản lưu | xem `project.json.bak`; ảnh trong `media/` vẫn còn |
| `preflight` | kiểm tra trước khi xuất phát hiện lỗi | xem mục dưới |
| `unexpected` | lỗi chưa gặp | gửi nhật ký kèm mã lỗi |

- **Kiểm tra trước khi xuất**: tool xem cảnh nào thiếu/hỏng ảnh, nhạc nền hoặc logo biến mất, cảnh trống, ổ đĩa không đủ chỗ cho video sắp xuất. Lỗi chặn xuất và nói rõ
  *cảnh số mấy, file nào*; cảnh báo thì hiện trong hộp xác nhận. Cảnh có vấn đề được đánh dấu ⚠ ngay trong danh sách và đầu khung chỉnh sửa, cập nhật sau mỗi lần lưu.
- **File dự án**: ghi nguyên tử và giữ bản trước đó ở `project.json.bak`. `project.json` hỏng (mất điện giữa chừng, sửa tay sai) thì tự khôi phục từ bản đó và giữ bản hỏng
  thành `project.json.hong-<giờ>` để xem. Bản sao lưu không bao giờ bị ghi đè bằng bản hỏng.
- **Cổng bận**: cổng 8765 đang bị chương trình khác dùng thì tool tự thử 8766…8774. Nếu chính Firefly Video đã chạy sẵn thì chỉ mở trình duyệt vào đó rồi thoát (không chạy hai bản
  cùng ghi một thư mục dự án). Muốn ép cổng khác: `PORT=9000`.
- **Mất kết nối tới tool** (đã tắt cửa sổ lệnh?) báo rõ trong trình duyệt thay vì im lặng; dự án đã lưu vẫn còn.
