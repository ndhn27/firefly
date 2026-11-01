/* Hoàn tác / làm lại (ảnh chụp project.json trong bộ nhớ trình duyệt).
   Các file trong static/js/ là script thường (không phải ES module), nạp lần lượt theo thứ tự trong index.html và dùng chung
   một phạm vi toàn cục (các test Playwright cũng gọi thẳng S, H, edit()…). Hàm chỉ được GỌI sau khi mọi file đã nạp xong. */
/* ------------------------------------------------------------ hoàn tác / làm lại
   Lịch sử là các ảnh chụp (snapshot) project.json trong bộ nhớ trình duyệt, không có trên server.
   - Gõ chữ, kéo thanh trượt: gộp thành một bước khi dừng tay HIST_PAUSE ms (touch()).
   - Thao tác rời (xoá/nhân đôi/đổi chỗ cảnh, đổi kiểu ảnh, bấm chọn trong Cài đặt…): mỗi lần một bước (edit()).
   - Giọng đọc (scene.audio) do server quản lý nên không nằm trong ảnh chụp; server tự tìm lại giọng khớp nội dung khi lưu. */
const HIST_MAX = 100, HIST_PAUSE = 700;
// base = trạng thái đã chốt gần nhất {p: chuỗi JSON, sel: id cảnh đang chọn (cập nhật theo người dùng), at: id cảnh đang chọn lúc trạng thái này được tạo ra}.
// Hoàn tác về một trạng thái thì chọn lại cảnh `sel` (nơi người dùng đang đứng ngay trước khi sửa); làm lại thì chọn cảnh `at` (nơi vừa sửa xong).
const H = { undo: [], redo: [], base: null, timer: null };
const snap = p => JSON.stringify(p, (k, v) => k === 'audio' ? undefined : v);
const selId = () => { const s = cur(); return s ? s.id : null; };
function histUI() {
  const u = $('#btnUndo'), r = $('#btnRedo'); if (!u) return;
  u.disabled = !(H.undo.length || H.timer); r.disabled = !H.redo.length;
}
function histReset() {
  clearTimeout(H.timer); H.timer = null; H.undo = []; H.redo = [];
  H.base = S.proj ? { p: snap(S.proj), sel: selId(), at: selId() } : null; histUI();
}
function commit() {  // chốt các thay đổi đang chờ thành một bước hoàn tác
  clearTimeout(H.timer); H.timer = null;
  if (!H.base || !S.proj) { histUI(); return false; }
  const p = snap(S.proj);
  if (p === H.base.p) { histUI(); return false; }
  H.undo.push(H.base); if (H.undo.length > HIST_MAX) H.undo.shift();
  H.base = { p, sel: selId(), at: selId() }; H.redo = []; histUI(); return true;
}
function edit(fn) {  // một thao tác rời = đúng một bước hoàn tác
  commit(); if (H.base) H.base.sel = selId();
  fn(); touch(); commit();
}
function restore(e, key) {
  const live = new Map(S.proj.scenes.map(s => [s.id, s.audio]));
  const p = JSON.parse(e.p);
  p.scenes.forEach(s => { s.audio = live.get(s.id) || null; });  // giọng giữ nguyên tới khi server trả lại (cảnh vừa khôi phục)
  S.proj = p; H.base = e;
  const i = p.scenes.findIndex(s => s.id === e[key]);
  S.sel = i >= 0 ? i : Math.max(0, Math.min(S.sel, p.scenes.length - 1));
  S.dirty = true; showStill(); fit(); renderSceneList(); renderEditor(); histUI();
  flush().then(() => {
    const t = S.tl.scenes[S.sel], inside = t && S.t >= t.start && S.t < t.start + t.dur;
    selectScene(S.sel, !inside);  // chỉ tua lại khi đầu phát đang nằm ngoài cảnh được chọn
  });
}
function stepHist(from, to, key) {
  if (!S.proj || $('#modalBg').classList.contains('on')) return false;  // đang mở cửa sổ: các ô trong đó đang cầm tham chiếu tới S.proj
  commit();
  const e = from.pop(); if (!e) { histUI(); return false; }
  to.push(H.base); restore(e, key); return true;
}
const undo = () => { if (stepHist(H.undo, H.redo, 'sel')) toast('↶ Đã hoàn tác'); };
const redo = () => { if (stepHist(H.redo, H.undo, 'at')) toast('↷ Đã làm lại'); };
