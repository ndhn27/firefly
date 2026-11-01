# Kịch bản AI

Quay lại [README](../README.md).

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
