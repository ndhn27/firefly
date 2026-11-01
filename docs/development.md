# Phát triển

Quay lại [README](../README.md).

## Mã giao diện
`static/index.html` chỉ là khung HTML (~3 KB); CSS và JavaScript nằm ở file riêng:
- `static/css/app.css` (~6,7 KB): toàn bộ giao diện tối, biến màu ở `:root`.
- `static/js/` (nạp đúng thứ tự dưới đây): `core.js` (~5 KB: tiện ích `$`, `h()`, `api()`, toast, trạng thái `S`, cửa sổ) → `history.js` (~3,8 KB: hoàn tác/làm lại) → `save.js` (~1,4 KB: tự lưu) →
  `stage.js` (~3,6 KB: khung xem trước, vùng an toàn, thanh thời gian) → `scenes.js` (~5,1 KB: danh sách cảnh, kéo thả) → `editor.js` (~8 KB: chỉnh cảnh) → `settings.js` (~15,3 KB: Cài đặt, dọn file, dự án mới) →
  `script.js` (~6,2 KB: kịch bản AI/dán) → `jobs.js` (~8,4 KB: tạo giọng, xem thử, xuất video, lỗi, nhật ký) → `main.js` (~5,6 KB: khởi động, **phải nạp cuối**).
- Là script thường (không phải ES module), dùng chung một phạm vi toàn cục, nên các test Playwright vẫn gọi thẳng `S`, `H`, `edit()`. Hàm chỉ được *gọi* sau khi mọi file đã nạp xong, nhưng `const`/`let` ở mức cao nhất
  chạy ngay khi nạp, nên thứ tự trong `index.html` là bắt buộc. Thêm tính năng lớn (VD timeline nhiều track): tạo file mới và thêm một dòng `<script>` **trước** `main.js`.
- Cố ý không dùng bundler hay framework để tool vẫn chạy từ mã nguồn mà không cần Node. Khi giao diện lớn hơn nữa, bước tiếp theo hợp lý là ES module (`<script type="module">`); việc đó đòi hỏi sửa các test đang gọi biến toàn cục.

## Kiểm thử
```
pip install -r requirements-dev.txt
python -m pytest tests
```
- `tests/test_tts.py`: giọng dự phòng không cần mạng (nhà cung cấp giả + một chương trình `piper` giả cùng cờ dòng lệnh): chuyển giọng, nhớ dịch vụ hỏng, lỗi của máy không bị che, tốc độ qua ffmpeg, công tắc, tạo lại bằng giọng chính, `/api/tts/status`, doctor.
- `tests/test_tts_ui.py`: Chromium thật: nhãn 🔊 dự phòng, công tắc + tình trạng trong Cài đặt, nút tạo lại, hộp thoại thông báo.
- `tests/test_e7.py`: nhật ký (file, xoay vòng, log từ tiến trình con kể cả kiểu `spawn` của Windows, lỗi trong luồng nền), hơn 20 kiểu lỗi → thông báo tiếng Việt (có test không lộ traceback/đường dẫn),
  lỗi trong route trả JSON, file dự án hỏng, kiểm tra trước khi xuất, cổng bận/đã chạy sẵn, đường dẫn bản đóng gói, xuất video thật bằng tiến trình `spawn`.
- `tests/test_e7_ui.py`: Chromium thật: ⚠ cảnh có vấn đề (và biến mất sau khi sửa), chặn xuất, hộp thoại lỗi có cách xử lý + mã + nút Xem nhật ký, mất kết nối, lỗi JS vào nhật ký.
- `tests/test_pack.py`: bản đóng gói chạy thật (bỏ qua nếu không đặt `FFV_TEST_PACK=1`).
- `tests/test_e6.py`: kịch bản AI với một **Ollama giả** (cùng giao thức stream): tách/kiểm JSON, thử lại kèm lý do, bị cắt giữa chừng, Ollama cũ, huỷ khi mô hình đang nạp, API, doctor, và đầu ra khớp đúng bộ tách của ô dán.
- `tests/test_e6_ui.py`: luồng ✨ AI trên Chromium thật (viết → sửa trong ô dán → tạo cảnh → hoàn tác một bước; lỗi giữ lại chủ đề; Ollama tắt; khung cảnh báo; nhắc mô hình nhỏ).
- `tests/test_aiquality.py`: kiểm tra nội dung kịch bản AI (chữ Hán lẫn vào, không dấu/tiếng Anh, lặp câu, lời dẫn thừa, con số so với tư liệu, cảnh lệch…) và việc thử lại/chọn bản tốt nhất với Ollama giả.
- `tests/test_launchers.py`: chạy thật `run.sh`, `FireflyVideo.command`, `install_linux_shortcut.sh` bằng bash (Python/pip giả, không cần mạng): chọn Python ≥ 3.10, tạo `.venv`, chỉ cài khi requirements đổi, thư mục có dấu cách, mở trình duyệt thất bại không làm hỏng tool.
- `tests/test_e5.py`: vùng an toàn khớp renderer, dọn file (chỉ xoá file thừa, không thoát khỏi `media/` `audio/`), khôi phục giọng khi hoàn tác.
- `tests/test_ui.py`: thử giao diện bằng Chromium thật (hoàn tác/làm lại, kéo thả, vùng an toàn, hộp thoại dọn file). Cần `pip install playwright && playwright install chromium`; không có thì tự bỏ qua.
- `tests/test_e34.py`: âm lượng (đo LUFS thật bằng FFmpeg), nền mờ, chia đôi, logo, bokeh/tia sáng, vùng an toàn + 5 ảnh chuẩn `tests/golden/e4_*.png`.
- `tests/test_golden.py`: so khung hình với ảnh chuẩn ở 4 tỉ lệ. Cố ý đổi giao diện thì chạy `UPDATE_GOLDEN=1 python -m pytest tests/test_golden.py`
  rồi xem lại ảnh trong `tests/golden/`.
- Test dùng giọng giả offline (`FFV_FAKE_TTS=1`) nên không cần mạng.
- Dự án có `schema_version` (hiện là 2; các trường như `voice.fallback` và `scene.audio.engine` đều có mặc định nên không phải đổi số này); dự án cũ tự được nâng khi mở.
- Các test kịch bản AI **không** gọi mô hình thật; chúng kiểm đường ống quanh mô hình. Chất lượng chữ chỉ biết được khi thử với mô hình bạn dùng.
