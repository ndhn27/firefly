# Firefly Video

[![test](https://github.com/ndhn27/firefly/actions/workflows/test.yml/badge.svg)](https://github.com/ndhn27/firefly/actions/workflows/test.yml)
[![Giấy phép: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Tool dựng video giải thích: nền động đom đóm/ánh sáng, giọng đọc Edge TTS (miễn phí, có giọng dự phòng),
thêm ảnh, chuyển cảnh, phụ đề tự chia câu, xuất tới 2K 60fps.

## Chạy
Cần Python 3.10 trở lên (hoặc dùng bản đóng gói bên dưới, không cần Python). Tool tự mở trình duyệt tại http://localhost:8765; không mở được (máy chủ, WSL, SSH…) thì in địa chỉ ra để bạn mở tay.
Không cần cài ffmpeg riêng (đã kèm qua `imageio-ffmpeg`; nếu máy đã có ffmpeg thì dùng cái đó).
- **Windows**: bấm đúp `run.bat`.
- **macOS**: bấm đúp `FireflyVideo.command` (mở trong Terminal; đóng cửa sổ Terminal là tắt tool). Lần đầu macOS có thể chặn vì file tải từ internet: bấm chuột phải → *Mở* → *Mở*.
  Chưa có Python 3.10+ thì cài bằng `brew install python` hoặc bản cài ở python.org.
- **Linux / WSL**: `./run.sh`. Muốn có biểu tượng trong menu ứng dụng để bấm một cú: `./install_linux_shortcut.sh` (thêm `--desktop` để có cả ngoài màn hình nền, `--remove` để gỡ).
  Ubuntu/Debian có thể cần `sudo apt install python3 python3-venv` trước.
- `run.sh` / `FireflyVideo.command` **tự tạo môi trường riêng `.venv`** cạnh `app.py` và cài thư viện vào đó (lần đầu cần internet, khoảng 1 phút; các lần sau khởi động dưới 1 giây vì chỉ cài lại khi `requirements.txt` đổi).
  Không đụng Python của hệ thống và không cần quyền quản trị; Python mới của Ubuntu/Debian/Homebrew từ chối `pip install` thẳng vào hệ thống nên tool dùng môi trường riêng. Muốn cài lại từ đầu thì xoá thư mục `.venv`.
- Biến môi trường: `PORT` (cổng, mặc định 8765; bận thì tự dùng cổng kế), `FFV_HOME` (nơi lưu dự án/nhật ký), `FFV_NO_BROWSER=1` (không tự mở trình duyệt).

### Bản đóng gói (.exe, không cần cài Python)
Chạy `build_exe.bat` (Windows) hoặc `./build_exe.sh` trên máy có Python, ra `dist/FireflyVideo/FireflyVideo.exe` kèm cả FFmpeg và font. Xem mục *Đóng gói* bên dưới.

## Quy trình
1. **Dự án mới** → chọn khung hình (9:16, 16:9, 1:1, 4:5), chất lượng (720p/1080p/2K), fps (24/30/60), kiểu nền.
2. **Dán kịch bản**: mỗi đoạn cách nhau 1 dòng trống = 1 cảnh; dòng bắt đầu bằng `#` là tiêu đề hiện trên màn hình.
   Chưa có kịch bản thì bấm **✨ AI** để nhờ AI chạy trên máy bạn viết bản nháp (xem mục *Kịch bản AI* bên dưới).
3. Chọn từng cảnh để sửa: tiêu đề, lời đọc, ảnh (chọn file, kéo thả, hoặc Ctrl+V dán ảnh chụp màn hình),
   kiểu ảnh (thẻ nổi / vừa khung + nền mờ / toàn màn hình), hiệu ứng ảnh, bố cục chữ-ảnh (chuẩn / chia đôi), kiểu chuyển cảnh.
4. **Cài đặt**: giọng, tốc độ, từ điển phát âm (VD `GitHub=Ghít hấp`), nhạc nền, âm lượng cuối, logo, kiểu và màu nền động, bộ mã hoá.
5. **Tạo giọng tất cả** → kéo thanh thời gian xem từng khung → **Xem thử có tiếng** → **Xuất video**.

File xuất nằm ở `projects/<tên dự án>/out/`. Dự án tự lưu; tắt tool mở lại vẫn còn.

## Kiểm tra máy
- `python doctor.py` (hoặc **Cài đặt → Kiểm tra máy**) báo FFmpeg, các encoder CPU/GPU, font, kết nối dịch vụ giọng đọc, ổ đĩa.

## Xuất video
- Bấm **Xuất video** → tool dựng thử vài khung rồi báo *thời gian và dung lượng dự kiến* (ước tính, có thể lệch ±30%) trước khi chạy thật.
- **Cài đặt → Xuất video**: mức chất lượng Nháp / Chuẩn / Cao; bộ mã hoá Tự động / CPU / NVIDIA NVENC / Intel QSV / AMD AMF
  (Tự động thử GPU theo thứ tự đó, không được thì dùng CPU).
- **Chạy tiếp khi bị gián đoạn**: huỷ giữa chừng hoặc lỗi thì các đoạn đã dựng được giữ trong `projects/<tên>/out/.cache/`;
  bấm xuất lại (dự án chưa đổi hình ảnh) sẽ dùng lại, không dựng lại từ đầu. Xuất xong thì tự dọn.

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

## Âm lượng
- Âm lượng cuối của video được **chuẩn hoá** về -14 LUFS (mức YouTube/Facebook dùng) hoặc -16 LUFS (êm hơn), hoặc tắt (chỉ chặn đỉnh).
  Chỉnh ở **Cài đặt → Âm lượng cuối**. Giọng và nhạc nền được tăng/giảm cùng một mức nên tương quan giữa chúng không đổi (nhạc vẫn tự nhỏ lại khi có lời).
- Có bộ chặn đỉnh ở -1.5 dBFS để không vỡ tiếng; do chặn đỉnh làm âm lượng tụt nhẹ nên tool đo lại và bù tối đa 3 vòng. Xuất xong báo mức đo được.
- Cần FFmpeg có bộ lọc `loudnorm` và `alimiter` (bản kèm theo `imageio-ffmpeg` có; `python doctor.py` kiểm tra giúp).
- Đổi cài đặt này không làm mất các đoạn video đã dựng (resume vẫn dùng được).

## Hình ảnh
- **Vừa khung + nền mờ**: ảnh nằm trọn trong khung, nền là chính ảnh đó làm mờ và tối đi. Hợp với ảnh chụp màn hình lệch tỉ lệ.
  Kiểu **Toàn màn hình** tự chuyển sang kiểu này khi phải cắt mất hơn ~40% diện tích ảnh (VD ảnh dọc trên khung 16:9);
  ảnh gần đúng tỉ lệ khung vẫn phủ kín.
- **Bố cục chia đôi** (theo từng cảnh): khung ngang/vuông thì chữ một cột, ảnh một cột (chọn bên trái/phải); khung dọc thì ảnh ở trên, chữ ở dưới.
- **Nền động thứ hai**: *Bokeh ấm* (đốm mờ to hình đĩa) và *Tia sáng* (chùm tia chiếu chéo + bụi sáng); chỉnh được độ đậm tia sáng và bật/tắt bokeh cho bất kỳ theme nào.
- **Logo / watermark**: ảnh PNG nền trong suốt, 4 góc, chỉnh cỡ và độ đậm. Khung 9:16 nên đặt ở trên (phía dưới bị giao diện Reels/Shorts/TikTok che).
- **Vùng an toàn** theo tỉ lệ khung (bảng `SAFE` trong `render.py`): tiêu đề, ảnh, phụ đề và logo nằm trong vùng không bị app che.
  Mỗi tỉ lệ có số liệu riêng (4:5 không dùng chung với 9:16).

## Giao diện
- **Hoàn tác / làm lại**: nút ↶ ↷ trên thanh trên cùng, hoặc `Ctrl+Z` và `Ctrl+Shift+Z` (`Ctrl+Y`; Mac dùng `Cmd`).
  - Bao gồm sửa chữ, ảnh, thêm/xoá/nhân đôi/đổi chỗ cảnh, dán kịch bản, và mọi mục trong Cài đặt (kể cả đổi khung hình).
  - Gõ chữ hoặc kéo thanh trượt liên tục được gộp thành **một** bước (chốt khi dừng tay khoảng 0,7 giây); mỗi lần bấm chọn là một bước riêng.
  - Đang gõ trong một ô chữ/số thì `Ctrl+Z` hoàn tác chữ của chính ô đó (việc của trình duyệt, vẫn được ghi vào lịch sử); muốn hoàn tác thao tác khác thì bấm ra ngoài ô hoặc dùng nút ↶. Đang mở cửa sổ (Cài đặt, xuất video…) thì hoàn tác bị khoá.
  - Lịch sử nằm trong trình duyệt, tối đa 100 bước, mất khi tải lại trang, đổi dự án hoặc sau khi dọn file.
  - **Giọng đọc không mất khi hoàn tác**: server cất lại mô tả của mỗi giọng đã tạo (`audio/<id cảnh>_<mã>.wav.json`) và tự tìm lại đúng giọng khớp nội dung khi lưu.
    Hoàn tác xoá cảnh hay sửa lại lời đọc về như cũ thì giọng quay về, không phải tạo lại.
- **Kéo thả đổi thứ tự cảnh**: kéo cả hàng cảnh trong danh sách bên trái; vạch vàng cho biết sẽ chèn vào đâu (nửa trên hàng = trước hàng, nửa dưới = sau hàng, khoảng trống dưới cùng = cuối danh sách).
  Nút ↑ ↓ cũng đổi chỗ cảnh. Sau khi đổi chỗ, thanh thời gian tua tới cảnh vừa chuyển để preview đúng cảnh đang chọn.
- **Vùng an toàn**: nút **▦ Vùng an toàn** dưới thanh thời gian vẽ đè lên preview (và cả video xem thử); nhớ lựa chọn bật/tắt.
  Khung nét đứt xanh là vùng tiêu đề, ảnh, phụ đề và logo nên nằm trong; vạch vàng là đáy phụ đề; vùng sọc đỏ là lề và chỗ giao diện app che mất.
  Số liệu lấy thẳng từ bảng `SAFE` của renderer (`/api/safe`) nên không lệch; chỉ là lớp phủ trên trang, **không** có trong video xuất.
- **Dọn file không dùng**: **Cài đặt → 8 · Dọn dẹp**. Liệt kê ảnh, nhạc, logo trong `media/` và giọng trong `audio/` mà dự án không còn tham chiếu, kèm dung lượng; bấm xoá mới xoá (xoá hẳn, không có thùng rác).
  - Không đụng tới `out/` (video đã xuất). File vừa tạo dưới 1 phút được giữ lại (có thể đang chờ lưu). Đang tạo giọng/xuất video thì từ chối dọn.
  - Giọng cũ của lời đọc đã sửa thường chỉ còn là file thừa sau khi tạo lại giọng; còn giọng mà cảnh vẫn tham chiếu (kể cả đã lỗi thời) thì được giữ.
  - Sau khi dọn, lịch sử hoàn tác bị xoá vì các bước cũ có thể trỏ tới file đã bị xoá.

## Mã giao diện
`static/index.html` chỉ là khung HTML (~3 KB); CSS và JavaScript nằm ở file riêng:
- `static/css/app.css` (~6,7 KB): toàn bộ giao diện tối, biến màu ở `:root`.
- `static/js/` (nạp đúng thứ tự dưới đây): `core.js` (~5 KB: tiện ích `$`, `h()`, `api()`, toast, trạng thái `S`, cửa sổ) → `history.js` (~3,8 KB: hoàn tác/làm lại) → `save.js` (~1,4 KB: tự lưu) →
  `stage.js` (~3,6 KB: khung xem trước, vùng an toàn, thanh thời gian) → `scenes.js` (~5,1 KB: danh sách cảnh, kéo thả) → `editor.js` (~8 KB: chỉnh cảnh) → `settings.js` (~15,3 KB: Cài đặt, dọn file, dự án mới) →
  `script.js` (~6,2 KB: kịch bản AI/dán) → `jobs.js` (~8,4 KB: tạo giọng, xem thử, xuất video, lỗi, nhật ký) → `main.js` (~5,6 KB: khởi động, **phải nạp cuối**).
- Là script thường (không phải ES module), dùng chung một phạm vi toàn cục, nên các test Playwright vẫn gọi thẳng `S`, `H`, `edit()`. Hàm chỉ được *gọi* sau khi mọi file đã nạp xong, nhưng `const`/`let` ở mức cao nhất
  chạy ngay khi nạp, nên thứ tự trong `index.html` là bắt buộc. Thêm tính năng lớn (VD timeline nhiều track): tạo file mới và thêm một dòng `<script>` **trước** `main.js`.
- Cố ý không dùng bundler hay framework để tool vẫn chạy từ mã nguồn mà không cần Node. Khi giao diện lớn hơn nữa, bước tiếp theo hợp lý là ES module (`<script type="module">`); việc đó đòi hỏi sửa các test đang gọi biến toàn cục.

## Kịch bản AI
Bấm **✨ AI** (thanh đầu danh sách cảnh) để nhờ một mô hình chạy bằng [Ollama](https://ollama.com) trên chính máy bạn viết kịch bản. **Tuỳ chọn**: không cài Ollama thì mọi thứ khác vẫn chạy bình thường.
- **Chuẩn bị một lần**: cài Ollama, rồi tải một mô hình viết được tiếng Việt, ví dụ `ollama pull qwen2.5:7b` (tên chỉ là ví dụ; mô hình càng lớn thì tiếng Việt càng tự nhiên, nhưng càng nặng máy).
  Ollama không có sẵn thì hộp thoại báo rõ và khoá nút; `python doctor.py` cũng có một dòng kiểm tra (chỉ là cảnh báo, không bao giờ là lỗi).
- **Cách dùng**: nhập chủ đề, *hoặc dán cả bài viết/ghi chú làm tư liệu* (tới 8000 ký tự), chọn độ dài video (30 giây – 3 phút), giọng điệu, yêu cầu thêm, mô hình. Tool tự tính số cảnh và số từ mỗi cảnh
  để video ra gần đúng độ dài đã chọn (dùng đúng công thức ước lượng của renderer lúc chưa có giọng thật).
- **AI chỉ viết bản nháp**: kết quả không tạo cảnh ngay mà đổ vào ô **Dán kịch bản** (kèm dòng cho biết số cảnh, thời lượng ước tính, số lần thử). Bạn sửa chữ thoải mái rồi mới bấm *Tạo cảnh*;
  các cảnh vào dự án như dán tay: **một bước hoàn tác**, có tuỳ chọn thay thế toàn bộ cảnh.
- **Kết quả là JSON, được kiểm lại**: tool ép Ollama trả JSON đúng schema (`scenes[].title`, `scenes[].narration`), rồi kiểm bằng pydantic. JSON hỏng, thiếu trường, cảnh quá dài, câu trả lời bị cắt giữa chừng,
  hoặc kịch bản đọc xong lệch quá xa độ dài yêu cầu (dưới 0,5× hoặc trên 1,8×) thì tool gửi lại cho mô hình **kèm lý do cụ thể** (VD “scenes[2].narration: quá dài”), tối đa 3 lần. Hết 3 lần vẫn hỏng mới báo lỗi;
  riêng trường hợp chỉ lệch độ dài thì giữ bản gần yêu cầu nhất thay vì báo lỗi. Ollama bản cũ không hiểu schema thì tự lùi về chế độ `json` chung.
- **Kiểm tra nội dung**: ngoài cấu trúc JSON và độ dài, tool soát những lỗi *máy móc bắt được* của mô hình nhỏ chạy trên máy (không đánh giá được văn hay hay dở, và không kiểm được sự thật):
  - **Gửi lại cho mô hình kèm đúng chỗ sai** (tối đa 3 lần): chữ ngôn ngữ khác lẫn vào (hay gặp: chữ Hán chen giữa tiếng Việt, giọng đọc sẽ đọc sai hoặc bỏ qua), lặp một câu từ 4 lần trở lên, hai cảnh giống hệt nhau,
    còn lời dẫn của AI (“Dưới đây là kịch bản…”, “Chắc chắn rồi!”) hoặc chỗ giữ chỗ chưa điền (`[tên kênh]`). Bản không lỗi luôn thắng bản có lỗi khi chọn kết quả tốt nhất.
  - **Báo lỗi thay vì đưa bản vô dụng**: sau 3 lần vẫn viết tiếng Việt không dấu / bằng tiếng Anh (hoặc chữ lạ chiếm từ 20% chữ cái), tool báo “mô hình viết sai ngôn ngữ” và gợi ý dùng mô hình lớn hơn.
  - **Chỉ cảnh báo, hiện thành khung “⚠ Nên xem lại” phía trên ô dán** (không lẫn vào kịch bản): con số/năm từ 2 chữ số trở lên (nếu bạn dán tư liệu thì chỉ liệt kê số *không có trong tư liệu*, vì đó là chỗ AI dễ tự thêm; nếu chỉ nhập chủ đề ngắn thì liệt kê tất cả để kiểm chứng),
    địa chỉ web (giọng đọc đọc từng chữ), cảnh dài hoặc ngắn hơn hẳn các cảnh khác, câu dài trên 40 từ (tiếng Việt) khó đọc một hơi.
  - Lời nhắc có thêm hai quy tắc: không bịa số liệu/năm/tên riêng, và không chen chữ Hán, Nga, Thái vào lời đọc. Chữ lạ nếu còn sót được giữ nguyên trong ô dán để bạn thấy và sửa, không bị xoá lặng lẽ.
- **Gợi ý chọn mô hình**: danh sách mô hình hiện kèm số tham số (VD `qwen2.5:7b (7.6B, 4.7 GB)`). Mô hình dưới khoảng 3,5 tỉ tham số thường viết tiếng Việt kém hoặc lẫn ngôn ngữ khác nên có dòng ⚠ nhắc ngay khi chọn.
  Con số 3,5B là ngưỡng kinh nghiệm chứ không phải kết quả đo; chỉ thử với mô hình bạn dùng mới biết chắc.
- **Làm sạch trước khi vào ô dán**: bỏ emoji, markdown, gạch đầu dòng, “Cảnh 1:” ở đầu tiêu đề, ngắt dòng; dấu `#` đầu dòng bị bỏ vì chế độ dán sẽ hiểu nhầm là tiêu đề.
- **Huỷ** được ngay cả khi mô hình đang nạp (chưa nhả chữ nào). Mỗi lúc chỉ chạy một việc AI.
- **Cài đặt** (địa chỉ Ollama, mô hình đã chọn) lưu theo máy ở `ai_settings.json` cạnh `app.py`, không nằm trong dự án. Địa chỉ mặc định `http://127.0.0.1:11434`; nếu máy đặt biến `OLLAMA_HOST` thì dùng nó; biến `FFV_OLLAMA_MODEL` đặt mô hình mặc định.
  Ngôn ngữ kịch bản theo giọng đọc của dự án (VD giọng `en-US` thì viết tiếng Anh).
- **Giới hạn cần biết**: chất lượng chữ, độ đúng sự thật và tiếng Việt hoàn toàn do mô hình quyết định; bước kiểm tra ở trên giảm bớt lỗi dễ thấy nhưng **không thay được việc đọc lại** trước khi xuất, nhất là số liệu và tên riêng (khung cảnh báo chỉ chỉ ra *chỗ nên kiểm*, không nói chỗ đó đúng hay sai).
  Các test dùng Ollama giả nên chứng minh được đường ống kiểm tra và thử lại, không chứng minh được mô hình thật sẽ viết hay. AI chưa gợi ý ảnh cho từng cảnh.
  Mô hình “có suy nghĩ” (hiện khối `<think>`) được xử lý: khối đó bị bỏ đi, nhưng chúng chậm hơn nhiều.

## Nhật ký và xử lý lỗi
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
| `network`, `tts_denied`, `tts_no_audio` | giọng Edge TTS: mất mạng, lỗi 403 (hay do lệch giờ máy), không trả âm thanh | kiểm tra mạng/VPN, bật đồng bộ giờ, `pip install -U edge-tts`; có giọng dự phòng thì tool tự chuyển (xem mục Giọng dự phòng) |
| `tts_none` | không có giọng đọc nào dùng được (hoặc giọng chính lỗi mà công tắc giọng dự phòng đang tắt) | cài Piper/gTTS theo mục Giọng dự phòng, hoặc bật lại công tắc trong Cài đặt |
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

## Đóng gói (.exe)
- Cần máy có Python 3.10+ để *build*; máy *chạy* thì không cần. Windows: bấm `build_exe.bat`. Linux/macOS: `./build_exe.sh`. Cùng một file `firefly.spec`.
- Kết quả là **thư mục** `dist/FireflyVideo/` (chép cả thư mục đi, chạy `FireflyVideo.exe`; khoảng 400 MB vì có OpenCV, NumPy, FFmpeg). Cửa sổ lệnh hiện ra là bình thường: đóng nó là tắt tool.
- Dự án, `logs/`, `ai_settings.json` được ghi **cạnh file .exe** (không nằm trong thư mục tạm của bản đóng gói) nên cập nhật bản mới chỉ cần chép đè các file, giữ nguyên `projects/`.
  Đặt tool ở thư mục ghi được (không phải `Program Files`), hoặc đặt biến `FFV_HOME` để đưa dữ liệu sang chỗ khác. `python doctor.py`/Kiểm tra máy báo nếu không ghi được.
- Có thể bị phần mềm diệt virus nghi ngờ (đặc điểm chung của file đóng gói bằng PyInstaller); nếu gặp, thêm thư mục vào ngoại lệ hoặc chạy bằng `run.bat` từ mã nguồn.
- **Linux/macOS**: `./build_exe.sh` (tự tạo `.venv-build` và cài PyInstaller vào đó, không đụng Python hệ thống) ra `dist/FireflyVideo/FireflyVideo`. Bản build chỉ chạy trên đúng hệ điều hành đã build (muốn bản Windows thì build trên Windows).
  Đã build và chạy thử trên Linux (cả hai kiểu tiến trình con). **macOS chưa thử được** vì không có máy Mac: nhị phân không ký tên có thể bị Gatekeeper chặn lần đầu (chuột phải → Mở); chưa có gói `.app`, nên trên Mac cách bấm đúp ổn định nhất vẫn là `FireflyVideo.command` chạy từ mã nguồn.
- `.github/workflows/test.yml`: chạy toàn bộ test và test đóng gói trên Windows, macOS và Linux mỗi lần đẩy mã lên GitHub.
- `FFV_TEST_PACK=1 python -m pytest tests/test_pack.py` build rồi chạy thử bản đóng gói như người dùng (PATH để trống để buộc dùng FFmpeg kèm theo, cả hai kiểu tiến trình con: mặc định và `spawn` của Windows).

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

## Ghi chú
- Giọng chính dùng `edge-tts` (endpoint đọc văn bản của Microsoft Edge, không chính thức, cần internet; có thể ngừng
  hoạt động bất cứ lúc nào) nên có giọng dự phòng Piper/gTTS (mục Giọng dự phòng). Muốn dùng thương mại chắc chắn thì dùng Piper với giọng phù hợp giấy phép hoặc dịch vụ có điều khoản rõ ràng.
- Xuất 2K60 chạy song song trên nhiều nhân CPU; có GPU NVIDIA thì chọn "Tự động" để dùng NVENC.
- Font chữ: Be Vietnam Pro (SIL OFL, trong thư mục `fonts/`).
- Giấy phép: mã nguồn của tool theo **MIT** (file `LICENSE`). Các thư viện và font đi kèm giữ giấy phép riêng của chúng (VD `edge-tts` là LGPL-3.0; font là SIL OFL).
  Bản FFmpeg do `imageio-ffmpeg` kèm theo là bản build GPL (`--enable-gpl`); tool chỉ gọi nó như chương trình riêng nên mã của tool vẫn là MIT, nhưng nếu bạn **phát hành lại bản đóng gói** (`dist/FireflyVideo/`, có chứa FFmpeg) thì phần FFmpeg phải theo điều kiện GPL của nó.
