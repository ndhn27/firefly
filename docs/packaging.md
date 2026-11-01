# Đóng gói (.exe)

Quay lại [README](../README.md).

- Cần máy có Python 3.10+ để *build*; máy *chạy* thì không cần. Windows: bấm `build_exe.bat`. Linux/macOS: `./build_exe.sh`. Cùng một file `firefly.spec`.
- Kết quả là **thư mục** `dist/FireflyVideo/` (chép cả thư mục đi, chạy `FireflyVideo.exe`; khoảng 400 MB vì có OpenCV, NumPy, FFmpeg). Cửa sổ lệnh hiện ra là bình thường: đóng nó là tắt tool.
- Dự án, `logs/`, `ai_settings.json` được ghi **cạnh file .exe** (không nằm trong thư mục tạm của bản đóng gói) nên cập nhật bản mới chỉ cần chép đè các file, giữ nguyên `projects/`.
  Đặt tool ở thư mục ghi được (không phải `Program Files`), hoặc đặt biến `FFV_HOME` để đưa dữ liệu sang chỗ khác. `python doctor.py`/Kiểm tra máy báo nếu không ghi được.
- Có thể bị phần mềm diệt virus nghi ngờ (đặc điểm chung của file đóng gói bằng PyInstaller); nếu gặp, thêm thư mục vào ngoại lệ hoặc chạy bằng `run.bat` từ mã nguồn.
- **Linux/macOS**: `./build_exe.sh` (tự tạo `.venv-build` và cài PyInstaller vào đó, không đụng Python hệ thống) ra `dist/FireflyVideo/FireflyVideo`. Bản build chỉ chạy trên đúng hệ điều hành đã build (muốn bản Windows thì build trên Windows).
  Đã build và chạy thử trên Linux (cả hai kiểu tiến trình con). **macOS chưa thử được** vì không có máy Mac: nhị phân không ký tên có thể bị Gatekeeper chặn lần đầu (chuột phải → Mở); chưa có gói `.app`, nên trên Mac cách bấm đúp ổn định nhất vẫn là `FireflyVideo.command` chạy từ mã nguồn.
- `.github/workflows/test.yml`: chạy toàn bộ test và test đóng gói trên Windows, macOS và Linux mỗi lần đẩy mã lên GitHub.
- `FFV_TEST_PACK=1 python -m pytest tests/test_pack.py` build rồi chạy thử bản đóng gói như người dùng (PATH để trống để buộc dùng FFmpeg kèm theo, cả hai kiểu tiến trình con: mặc định và `spawn` của Windows).
