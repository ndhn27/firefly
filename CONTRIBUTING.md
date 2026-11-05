# Đóng góp cho Firefly Video

Cảm ơn bạn đã quan tâm! Firefly Video là tool dựng video giải thích chạy hoàn toàn trên máy người dùng và mở bằng trình duyệt. Tài liệu này nói ngắn gọn cách chạy từ mã nguồn, cách kiểm thử và những quy ước của dự án.

## Bạn có thể giúp bằng cách nào

- **Báo lỗi**: mở [issue](../../issues) kèm thông tin ở mục [Báo lỗi](#báo-lỗi).
- **Thử trên nhiều máy**: tool chạy trên Windows, macOS và Linux/WSL. Lỗi chỉ xảy ra ở một hệ điều hành (đường dẫn có dấu cách hoặc tiếng Việt, tiến trình con kiểu `spawn`, bản đóng gói) rất đáng báo.
- **Sửa lỗi, cải thiện tài liệu, thêm test.**
- **Tính năng mới**: vui lòng mở issue trước để thống nhất hướng đi. Tool cố ý giữ nhỏ gọn: chạy offline được, không cần cài FFmpeg riêng, không cần Node.

## Chạy từ mã nguồn

Cần Python 3.10 trở lên.

```bash
git clone https://github.com/ndhn27/firefly.git
cd firefly
./run.sh              # Linux / WSL; Windows: run.bat; macOS: FireflyVideo.command
```

`run.sh` / `FireflyVideo.command` tự tạo `.venv` cạnh `app.py` và chỉ cài lại thư viện khi `requirements.txt` đổi. Nếu bạn muốn tự quản lý môi trường:

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python app.py                                          # mở http://localhost:8765
```

Biến môi trường hữu ích khi phát triển: `PORT` (cổng), `FFV_HOME` (nơi lưu dự án và nhật ký, nên trỏ sang thư mục tạm khi thử), `FFV_NO_BROWSER=1` (không tự mở trình duyệt).

## Chạy test

```bash
pip install -r requirements-dev.txt
python -m pytest tests
```

- Test dùng giọng đọc giả và Ollama giả nên **không cần mạng** và không gọi mô hình thật.
- Test giao diện (`test_ui.py`, `test_e6_ui.py`, `test_e7_ui.py`, `test_tts_ui.py`) cần Chromium thật: `pip install playwright && playwright install chromium`. Không có thì các file đó tự bỏ qua. CI luôn cài Playwright và `gTTS`, nên hãy cài nếu bạn sửa giao diện.
- `tests/test_pack.py` chạy bản đóng gói thật (chậm), chỉ chạy khi đặt `FFV_TEST_PACK=1` và cần `pip install -r requirements-pack.txt`.
- Mỗi file test làm gì được liệt kê trong [docs/development.md](docs/development.md). Khi thêm file test mới, hãy thêm một dòng mô tả vào đó.

CI (`.github/workflows/test.yml`) chạy toàn bộ test trên **Ubuntu, Windows và macOS**, và một job `pack` dựng bản đóng gói rồi chạy thật. PR chỉ được nhận khi các job này xanh.

### Ảnh chuẩn (golden)

`tests/test_golden.py` so khung hình xuất ra với ảnh trong `tests/golden/` ở 4 tỉ lệ. Nếu bạn **cố ý** đổi cách vẽ, cập nhật ảnh chuẩn rồi tự xem lại bằng mắt:

```bash
UPDATE_GOLDEN=1 python -m pytest tests/test_golden.py
```

Trong PR, nói rõ ảnh nào đổi và vì sao. Đừng cập nhật ảnh chuẩn chỉ để làm test xanh.

## Quy ước mã

- **Giao diện không dùng bundler hay framework.** `static/index.html` chỉ là khung HTML; JavaScript là các script thường (không phải ES module) dùng chung một phạm vi toàn cục, và test Playwright gọi thẳng `S`, `H`, `edit()`. Thứ tự nạp trong `index.html` là bắt buộc. Thêm file JS mới thì thêm một dòng `<script>` **trước** `main.js`. Chi tiết: [docs/development.md](docs/development.md).
- **Thông báo cho người dùng bằng tiếng Việt, và không lộ traceback hay đường dẫn máy.** Lỗi mới nên đi qua `errors.py` (có mã lỗi và cách xử lý) kèm test; xem `tests/test_e7.py` để biết các kiểu lỗi đã được phủ.
- **Dự án người dùng phải mở lại được.** Trường mới trong dự án cần có giá trị mặc định để dự án cũ vẫn mở bình thường. Chỉ tăng `schema_version` khi thay đổi không tương thích, và thêm bước nâng cấp.
- **Gọi chương trình ngoài bằng danh sách đối số**, không dùng `shell=True` hay ghép chuỗi lệnh. Nhớ dùng `NOWIN` để không bật cửa sổ console trên Windows.
- **Ghi file chỉ trong thư mục dự án.** Chức năng dọn file chỉ được xoá trong `media/` và `audio/` của dự án; đường dẫn đến từ người dùng hay dữ liệu dự án phải được kiểm tra.
- **Thư viện mới**: hỏi trước. Nó phải có bản cho Windows, macOS và Linux, đóng gói được bằng PyInstaller, và giấy phép tương thích (xem [mục giấy phép](#giấy-phép-và-tài-nguyên)). Nếu đổi `requirements.txt`, `run.sh` sẽ cài lại cho mọi người, nên đừng thêm gói chỉ để dùng một hàm nhỏ.
- **Giọng đọc**: Edge TTS và gTTS là endpoint không chính thức và có thể hỏng bất cứ lúc nào. Mã mới liên quan đến giọng đọc phải giữ được chuỗi giọng dự phòng ([docs/tts.md](docs/tts.md)).

## Pull request

- Mỗi PR một việc. Sửa lỗi và tái cấu trúc là hai PR.
- Có test cho mọi thay đổi hành vi hoặc lỗi đã sửa. Lỗi tìm thấy ở máy thật nên có test hồi quy fail khi chưa sửa.
- Cập nhật tài liệu liên quan trong `README.md` hoặc `docs/`.
- Chạy `python -m pytest tests` trên máy bạn trước khi mở PR; nếu sửa giao diện thì chạy cả test Playwright.
- Tin nhắn commit: dòng đầu ngắn gọn, thể mệnh lệnh (`Sửa lỗi phụ đề lệch ở cảnh cuối`); phần thân giải thích *vì sao* nếu chưa rõ.

### Đừng đưa vào repo

`.gitignore` đã chặn những thứ này, đừng `git add -f`:

- `projects/`, `logs/`, `ai_settings.json`, `.env`, `piper_voices/`, `piper/`, `.venv/`, `dist/`, `build/`;
- ảnh, nhạc, giọng đọc hay video của bạn. Các file này có thể chứa thông tin riêng hoặc có bản quyền.

## Báo lỗi

Hãy cho biết:

- hệ điều hành, phiên bản Python (hoặc bản đóng gói), trình duyệt, và phiên bản Firefly Video (`/api/ping` hoặc `version.py`);
- chạy từ mã nguồn hay bản đóng gói `.exe`;
- kết quả `python doctor.py` (hoặc **Cài đặt → Kiểm tra máy**);
- **mã lỗi** hiện trong hộp thoại lỗi, và tệp nhật ký (nút **Xem nhật ký**, hoặc `/api/logs/download`; bảng mã lỗi ở [docs/troubleshooting.md](docs/troubleshooting.md));
- các bước để tái hiện lỗi, và giọng đọc nào đã được dùng (Edge, Piper hay gTTS).

Nhật ký có thể chứa đường dẫn trên máy và đoạn kịch bản của bạn. Hãy xem lại và che những chỗ riêng tư trước khi đăng.

**Lỗ hổng bảo mật** thì đừng đăng công khai, xem [SECURITY.md](SECURITY.md).

## Giấy phép và tài nguyên

Mã nguồn theo [MIT](LICENSE). Khi đóng góp, bạn đồng ý đóng góp của mình cũng theo giấy phép MIT.

Các thành phần đi kèm giữ giấy phép riêng: font Be Vietnam Pro (SIL OFL), `edge-tts` (LGPL-3.0), và bản FFmpeg do `imageio-ffmpeg` kèm theo là bản build GPL. Điều đó quan trọng khi **phát hành lại bản đóng gói**, xem phần giấy phép trong [README](README.md). Đừng thêm font, giọng đọc, nhạc hay ảnh mà bạn không chắc về giấy phép.
