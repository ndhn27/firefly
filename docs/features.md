# Tính năng chi tiết

Quay lại [README](../README.md).

## Xuất video
- Bấm **Xuất video** → tool dựng thử vài khung rồi báo *thời gian và dung lượng dự kiến* (ước tính, có thể lệch ±30%) trước khi chạy thật.
- **Cài đặt → Xuất video**: mức chất lượng Nháp / Chuẩn / Cao; bộ mã hoá Tự động / CPU / NVIDIA NVENC / Intel QSV / AMD AMF
  (Tự động thử GPU theo thứ tự đó, không được thì dùng CPU).
- **Chạy tiếp khi bị gián đoạn**: huỷ giữa chừng hoặc lỗi thì các đoạn đã dựng được giữ trong `projects/<tên>/out/.cache/`;
  bấm xuất lại (dự án chưa đổi hình ảnh) sẽ dùng lại, không dựng lại từ đầu. Xuất xong thì tự dọn.
- Xuất 2K60 chạy song song trên nhiều nhân CPU; có GPU NVIDIA thì chọn "Tự động" để dùng NVENC.

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
