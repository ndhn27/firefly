/* Danh sách cảnh bên trái: thêm/xoá/nhân đôi/đổi chỗ, kéo thả.
   Các file trong static/js/ là script thường (không phải ES module), nạp lần lượt theo thứ tự trong index.html và dùng chung
   một phạm vi toàn cục (các test Playwright cũng gọi thẳng S, H, edit()…). Hàm chỉ được GỌI sau khi mọi file đã nạp xong. */
/* ------------------------------------------------------------ danh sách cảnh */
function renderSceneList() {
  const box = $('#sceneList'); if (!S.proj) return; box.replaceChildren();
  if (!S.proj.scenes.length) box.append(h('p', { class: 'hint', style: 'padding:14px' }, 'Chưa có cảnh. Bấm “+ Cảnh” hoặc “Dán kịch bản” để bắt đầu.'));
  S.proj.scenes.forEach((sc, i) => {
    const e = S.tl.scenes[i] || {};
    const label = sc.title || sc.narration || '(cảnh trống)';
    const needV = sc.voice && sc.narration.trim();
    const iss = (S.issues || []).filter(x => x.scene === i + 1);
    const badge = [needV ? (e.estimated ? h('span', { class: 'warn' }, '⚠ chưa có giọng') : isFallbackVoice(sc.audio) ? h('span', { class: 'warn', title: 'Cảnh này đọc bằng giọng dự phòng (' + ttsLabel(sc.audio.engine) + ') vì giọng chính bị lỗi lúc tạo.' }, '🔊 dự phòng') : h('span', { class: 'ok' }, '🔊')) : '',
      iss.length ? h('span', { class: iss.some(x => x.level === 'error') ? 'err' : 'warn', title: iss.map(x => x.msg).join('\n') }, ' ⚠ ' + iss.length + ' vấn đề') : ''];
    box.append(h('div', {
      class: 'sc' + (i === S.sel ? ' sel' : ''), onclick: () => selectScene(i), draggable: 'true',
      ondragstart: ev => { dragFrom = i; ev.dataTransfer.effectAllowed = 'move'; ev.dataTransfer.setData(SC_MIME, sc.id); const row = ev.currentTarget; setTimeout(() => row.classList.add('dragging'), 0); },
      ondragend: () => { dragFrom = null; markDrop(null); sceneRows().forEach(e => e.classList.remove('dragging')); }
    },
      h('div', { class: 'n', title: 'Kéo thả cả hàng để đổi thứ tự cảnh' }, i + 1),
      h('div', {}, h('div', { class: 't' }, label), h('div', { class: 'm' }, (e.estimated ? '~' : '') + (e.dur || 0).toFixed(1) + 's · ' + (sc.images.length ? sc.images.length + ' ảnh · ' : ''), badge)),
      h('div', { class: 'ops' },
        h('button', { class: 'sm', title: 'Lên', onclick: ev => { ev.stopPropagation(); moveScene(i, -1); } }, '↑'),
        h('button', { class: 'sm', title: 'Xuống', onclick: ev => { ev.stopPropagation(); moveScene(i, 1); } }, '↓'),
        h('button', { class: 'sm', title: 'Nhân đôi', onclick: ev => { ev.stopPropagation(); dupScene(i); } }, '⧉'),
        h('button', { class: 'sm', title: 'Xoá', onclick: ev => { ev.stopPropagation(); delScene(i); } }, '✕'))));
  });
  if (S.proj.scenes.length > 1) box.append(h('div', { class: 'tip' }, 'Kéo thả một cảnh để đổi thứ tự · Ctrl+Z để hoàn tác'));
}
function addScenes(list, at, replace) {
  let pos = 0;
  edit(() => {
    if (replace) S.proj.scenes = [];
    const arr = S.proj.scenes; pos = replace ? 0 : at == null ? arr.length : at;
    arr.splice(pos, 0, ...list);
  });
  flush().then(() => selectScene(pos));
}
function reorderScene(from, to) {
  const a = S.proj.scenes; if (!a[from] || to < 0 || to >= a.length || from === to) return;
  edit(() => { a.splice(to, 0, a.splice(from, 1)[0]); S.sel = to; });
  flush().then(() => selectScene(to, true));  // tua tới cảnh vừa đổi chỗ để preview đúng cảnh đang chọn
}
function moveScene(i, d) { reorderScene(i, i + d); }
function dupScene(i) { const c = JSON.parse(JSON.stringify(S.proj.scenes[i])); c.id = rid(); c.audio = null; addScenes([c], i + 1); }
function delScene(i) { if (!confirm('Xoá cảnh này?')) return; edit(() => { S.proj.scenes.splice(i, 1); }); flush().then(() => selectScene(Math.max(0, Math.min(S.sel, S.proj.scenes.length - 1)))); }

/* kéo thả đổi thứ tự cảnh (HTML5 drag & drop; chỉ nhận hàng cảnh của chính danh sách này, không đụng tới kéo-thả ảnh vào khung chỉnh sửa) */
const SC_MIME = 'application/x-ffv-scene';
let dragFrom = null;
const sceneRows = () => [...$('#sceneList').children].filter(e => e.classList.contains('sc'));
function dropIndex(ev) {  // vị trí chèn 0..n theo con trỏ: nửa trên của hàng = trước hàng, nửa dưới = sau hàng
  const rows = sceneRows(); if (!rows.length) return null;
  if (ev.target.closest('.ahead')) return 0;
  const row = ev.target.closest('.sc'); if (!row) return rows.length;  // khoảng trống dưới danh sách = cuối danh sách
  const r = row.getBoundingClientRect();
  return rows.indexOf(row) + (ev.clientY > r.top + r.height / 2 ? 1 : 0);
}
function markDrop(idx) {
  const rows = sceneRows(); rows.forEach(e => e.classList.remove('drop-before', 'drop-after'));
  if (idx == null || !rows.length) return;
  if (idx >= rows.length) rows[rows.length - 1].classList.add('drop-after'); else rows[idx].classList.add('drop-before');
}
