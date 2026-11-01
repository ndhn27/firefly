/* Khung xem trước: ảnh/video preview, vùng an toàn, thanh thời gian, chọn cảnh.
   Các file trong static/js/ là script thường (không phải ES module), nạp lần lượt theo thứ tự trong index.html và dùng chung
   một phạm vi toàn cục (các test Playwright cũng gọi thẳng S, H, edit()…). Hàm chỉ được GỌI sau khi mọi file đã nạp xong. */
let prevBusy = false, prevPending = false;
function refreshPreview() {
  if (!S.pid) return;
  if (prevBusy) { prevPending = true; return; }
  prevBusy = true;
  const im = $('#prev');
  im.onload = im.onerror = () => { prevBusy = false; if (prevPending) { prevPending = false; refreshPreview(); } };
  im.src = `/api/projects/${S.pid}/preview.jpg?t=${S.t.toFixed(2)}&h=600&_=${Date.now()}`;
}
function showStill() { const v = $('#vid'); if (!v.hidden) { v.pause(); v.hidden = true; $('#prev').hidden = false; $('#btnStill').hidden = true; } }
function showVideo(url) { const v = $('#vid'); v.src = url + '?v=' + Date.now(); v.hidden = false; $('#prev').hidden = true; $('#btnStill').hidden = false; v.play().catch(() => {}); }
function fit() {
  if (!S.proj) return;
  const box = $('#stageBox'), [w, hh] = frameSize(S.proj.aspect, 1080);
  const s = Math.min((box.clientWidth - 24) / w, (box.clientHeight - 24) / hh);
  const sc = $('#screen'); sc.style.width = Math.max(40, w * s) + 'px'; sc.style.height = Math.max(40, hh * s) + 'px';
  drawSafe();
}
/* ------------------------------------------------------------ vùng an toàn (chỉ vẽ đè lên preview, không vào video xuất) */
function drawSafe() {
  const el = $('#safe'), z = S.safe && S.proj && S.safe[S.proj.aspect], on = !!(z && S.showSafe);
  $('#btnSafe').classList.toggle('on', S.showSafe); $('#btnSafe').setAttribute('aria-pressed', String(S.showSafe));
  if (!on) { el.hidden = true; return; }
  const pc = v => (v * 100).toFixed(3) + '%';
  const box = (cls, l, t, r, b) => h('div', { class: cls, style: `left:${pc(l)};top:${pc(t)};width:${pc(r - l)};height:${pc(b - t)}` });
  el.replaceChildren(
    box('sz-shade', 0, 0, 1, z.top), box('sz-shade', 0, z.bottom, 1, 1),
    box('sz-shade', 0, z.top, z.mx, z.bottom), box('sz-shade', 1 - z.mx, z.top, 1, z.bottom),
    box('sz-frame', z.mx, z.top, 1 - z.mx, z.bottom),
    h('div', { class: 'sz-cap', style: `left:${pc(z.mx)};width:${pc(1 - 2 * z.mx)};top:${pc(z.cap)}` }, h('span', {}, 'đáy phụ đề')),
    (1 - z.bottom) > 0.06 ? h('div', { class: 'sz-lbl', style: `top:${pc(z.bottom)};height:${pc(1 - z.bottom)}` }, 'giao diện app che vùng này') : null);
  el.hidden = false;
}
function toggleSafe() { S.showSafe = !S.showSafe; try { localStorage.setItem('ffv_safe', S.showSafe ? '1' : '0'); } catch (e) {} drawSafe(); }
function updateScrub() {
  const sl = $('#scrub'), tot = S.tl.total || 0;
  sl.max = Math.max(tot, 0.1); sl.value = Math.min(S.t, tot); sl.disabled = !tot;
  $('#timeLbl').textContent = fmt(S.t) + ' / ' + fmt(tot);
  const tk = $('#ticks'); tk.replaceChildren();
  S.tl.scenes.forEach((s, i) => tk.append(h('i', { class: i === S.sel ? 'cur' : '', style: `left:${tot ? s.start / tot * 100 : 0}%` })));
}
function selectScene(i, seek = true) {
  commit();
  if (!S.proj.scenes.length) { renderSceneList(); renderEditor(); updateScrub(); refreshPreview(); return; }
  S.sel = Math.max(0, Math.min(i, S.proj.scenes.length - 1));
  if (H.base) H.base.sel = selId();
  const e = S.tl.scenes[S.sel];
  if (seek && e) S.t = e.start + Math.max(0.1, Math.min(Math.max(e.dur * 0.55, 1.4), e.dur - 0.3));
  renderSceneList(); renderEditor(); updateScrub(); refreshPreview();
}
