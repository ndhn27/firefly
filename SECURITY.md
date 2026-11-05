# Chính sách bảo mật

## Phiên bản được hỗ trợ

Firefly Video là dự án cá nhân. Chỉ bản phát hành mới nhất được vá lỗi bảo mật.

| Phiên bản | Được hỗ trợ |
| --- | --- |
| 0.9.x (mới nhất) | ✅ |
| Cũ hơn | ❌ |

## Cách báo lỗ hổng

**Xin đừng mở issue công khai cho vấn đề bảo mật.**

Hãy dùng báo cáo riêng tư của GitHub:

1. Mở tab **Security** của repository.
2. Chọn **Report a vulnerability**.
3. Mô tả vấn đề và cách tái hiện.

(Liên kết trực tiếp: <https://github.com/ndhn27/firefly/security/advisories/new>)

Thông tin hữu ích:

- bạn tìm thấy gì, và kẻ tấn công làm được gì với nó;
- hệ điều hành, trình duyệt, phiên bản Firefly Video, chạy từ mã nguồn hay bản đóng gói;
- một bản tái hiện tối giản, ví dụ một file ảnh, nhạc hay dự án `.json` **tự tạo**. Xin đừng gửi video, kịch bản hay dự án thật của bạn.

Đây là dự án làm trong thời gian rảnh. Mình cố gắng phản hồi xác nhận trong **7 ngày** và cho biết hướng xử lý trong **30 ngày**, nhưng đó là mục tiêu chứ không phải cam kết. Nếu bạn đồng ý, mình sẽ ghi nhận tên bạn khi phát hành bản vá.

## Phạm vi

Tool là một máy chủ web cục bộ (Flask, chỉ lắng nghe `127.0.0.1`, mặc định cổng 8765) và nó đọc những file bạn đưa vào rồi ghi vào thư mục dự án. Vì vậy những vấn đề đáng báo nằm ở chỗ đó.

**Trong phạm vi**

- **Yêu cầu từ trang web khác tới máy chủ cục bộ.** Máy chủ không có đăng nhập, nên một trang web bạn mở trong trình duyệt (CSRF, DNS rebinding, thiếu kiểm tra `Origin`/`Host`) hay một tiến trình khác trên máy không được phép đọc dự án, xoá file, đổi cài đặt (ví dụ địa chỉ Ollama) hay kích hoạt xuất video.
- **Đường dẫn và file.** Đọc hoặc ghi ngoài thư mục dự án: qua mã dự án, tên file, đường dẫn trong `/files/...`, tải lên, dán ảnh, chức năng dọn file, hay file dự án `.json` được tạo sẵn.
- **Chạy lệnh ngoài ý muốn.** Dữ liệu từ dự án, cài đặt hoặc biến môi trường (đường dẫn Piper, bộ mã hoá, tên file) chen được vào lệnh `ffmpeg` / `piper` hoặc làm chạy chương trình khác.
- **Xử lý file không tin cậy.** Ảnh, logo, nhạc nền hay dự án độc hại làm tool treo, ngốn hết bộ nhớ hoặc ổ đĩa, hay đọc được file ngoài ý muốn.
- **Lộ thông tin.** Thông báo lỗi hoặc nhật ký làm lộ đường dẫn, nội dung kịch bản hay thông tin cấu hình mà lẽ ra không hiện; hoặc dữ liệu bị gửi đi nơi bạn không chọn.
- **Script khởi chạy và đóng gói.** `run.sh`, `run.bat`, `FireflyVideo.command`, `install_linux_shortcut.sh`, `build_exe.*` và bản đóng gói PyInstaller, chẳng hạn xử lý thư mục tạm không an toàn, hoặc bản đóng gói chứa mã khác với mã nguồn.

**Ngoài phạm vi**

- **Mở tool ra mạng.** Tool được thiết kế để chạy cục bộ và không có xác thực. Việc bạn đổi địa chỉ lắng nghe, đặt sau reverse proxy hay chuyển tiếp cổng ra ngoài không phải là lỗ hổng của tool.
- **Lỗi của thư viện hay chương trình bên thứ ba** như Flask, FFmpeg, OpenCV, Pillow, `edge-tts`, Piper hay Ollama. Hãy báo cho nơi phát triển chúng; nếu Firefly Video làm lỗi đó dễ bị khai thác hơn thì phần đó thuộc phạm vi.
- **Edge TTS và gTTS ngừng hoạt động hay bị chặn.** Đây là endpoint không chính thức, đã được ghi rõ trong tài liệu; đó là vấn đề tương thích chứ không phải lỗ hổng.
- **Người đã chạy được mã trên máy bạn.** Họ đọc được `projects/` và chạy được `ffmpeg` mà không cần tool này.
- **Nội dung video bạn làm** (bản quyền của ảnh, nhạc, giọng đọc).
- **Báo cáo không có tác động thực tế**, chẳng hạn kết quả công cụ quét mà không chỉ ra cách kích hoạt.

## Quyền riêng tư và an toàn khi dùng

- **Lời đọc có thể rời khỏi máy bạn.** Edge TTS gửi văn bản tới Microsoft, gTTS gửi tới Google. Piper chạy offline và không gửi đi đâu ([docs/tts.md](docs/tts.md)). Với nội dung nhạy cảm, đặt `FFV_TTS=piper` để chỉ dùng Piper (`FFV_TTS=piper,edge` vẫn quay về Edge khi Piper lỗi, nên văn bản vẫn có thể bị gửi đi).
- **Kịch bản AI chạy qua Ollama.** Mặc định là `http://127.0.0.1:11434` trên máy bạn. Nếu bạn trỏ sang máy khác, kịch bản sẽ đi qua mạng giữa hai máy.
- **Chỉ chạy tool khi cần**, và đừng mở cổng 8765 ra mạng (đừng port-forward, đừng đổi địa chỉ lắng nghe). Tool không có đăng nhập: ai truy cập được cổng đó đều dùng được nó.
- **Không đưa dữ liệu của bạn lên git.** `projects/`, `logs/`, `ai_settings.json` và `.env` đã nằm trong `.gitignore`. Nhật ký có thể chứa đường dẫn và đoạn kịch bản, hãy che đi trước khi đăng lên issue.
- **Tải mã từ nguồn bạn tin.** `run.sh` và `FireflyVideo.command` tự tạo `.venv` và `pip install` từ `requirements.txt` lần đầu chạy. Hãy xem lại mã nếu bạn tải từ nơi không phải repository này.
- Nếu bạn đã lỡ commit dữ liệu riêng tư, xoá nó khỏi cây thư mục là chưa đủ: nó vẫn nằm trong lịch sử git.

## Công bố

Sau khi phát hành bản vá, mình sẽ đăng một GitHub security advisory nêu vấn đề, các phiên bản bị ảnh hưởng và phiên bản đã sửa. Nếu bạn muốn đăng bài phân tích riêng, xin cho mình một khoảng thời gian hợp lý để phát hành bản vá trước.
