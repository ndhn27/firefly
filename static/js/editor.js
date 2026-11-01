/* Khung chỉnh sửa cảnh bên phải: chữ, giọng, ảnh, tải ảnh lên.
   Các file trong static/js/ là script thường (không phải ES module), nạp lần lượt theo thứ tự trong index.html và dùng chung
   một phạm vi toàn cục (các test Playwright cũng gọi thẳng S, H, edit()…). Hàm chỉ được GỌI sau khi mọi file đã nạp xong. */
/* ------------------------------------------------------------ editor cảnh */
function field(label, el) { return [h('label', { class: 'f' }, label), el]; }
const ANIMS = [['zoom', 'Zoom vào'], ['zoom_out', 'Zoom ra'], ['pan', 'Lướt ngang'], ['none', 'Tĩnh']];
const MODES = [['card', 'Thẻ nổi'], ['fit', 'Vừa khung + nền mờ'], ['cover', 'Toàn màn hình']];
const LAYOUTS = [['stack', 'Chuẩn: chữ trên, ảnh giữa'], ['split', 'Chia đôi: chữ một bên, ảnh một bên']];
const SIDES = [['right', 'Ảnh bên phải'], ['left', 'Ảnh bên trái']];
const TRANS = [['fade', 'Chồng mờ'], ['dip', 'Mờ dần qua nền'], ['slide', 'Trượt'], ['none', 'Cắt thẳng']];
function sel(opts, val, on) {
  const s = h('select', { onchange: e => on(e.target.value) }, opts.map(([v, l]) => h('option', { value: v }, l)));
  s.value = val; return s;
}
function renderIssues() {  // chỉ vẽ lại khung cảnh báo (không đụng tới ô đang gõ), gọi lại sau mỗi lần lưu
  const box = $('#issuesBox'); if (!box) return;
  const mine = (S.issues || []).filter(x => x.scene === S.sel + 1 || x.scene == null);
  box.replaceChildren(...(mine.length ? [h('div', { class: 'issues' }, mine.map(x => h('div', {}, h('b', { class: x.level === 'error' ? 'err' : 'warn' }, '⚠ ' + x.msg), x.hint ? h('span', { class: 'hint' }, x.hint) : '')))] : []));
}
function renderEditor() {
  const box = $('#editor'); box.replaceChildren();
  const sc = cur();
  if (!sc) { box.append(h('p', { class: 'hint', style: 'padding-top:14px' }, 'Chọn hoặc thêm một cảnh để chỉnh sửa.')); return; }
  const e = S.tl.scenes[S.sel] || {};
  const cnt = h('span', { class: 'hint' });
  const upd = () => { cnt.textContent = sc.narration.length + ' ký tự · đọc khoảng ' + Math.round(sc.narration.length / 14.5) + 's'; };
  box.append(h('h3', { style: 'margin:12px 0 0' }, 'Cảnh ' + (S.sel + 1)));
  box.append(h('div', { id: 'issuesBox' }));
  renderIssues();
  box.append(...field('Tiêu đề lớn (hiện trên màn hình)', h('textarea', { rows: 2, value: sc.title, oninput: ev => { sc.title = ev.target.value; touch(); } })));
  box.append(...field('Dòng phụ (tuỳ chọn)', h('input', { type: 'text', value: sc.subtitle, oninput: ev => { sc.subtitle = ev.target.value; touch(); } })));
  box.append(h('label', { class: 'f' }, 'Lời đọc (cũng là phụ đề) ', cnt));
  box.append(h('textarea', { rows: 7, value: sc.narration, placeholder: 'Nội dung giọng đọc cho cảnh này…', oninput: ev => { sc.narration = ev.target.value; upd(); touch(); } }));
  upd();
  box.append(h('div', { class: 'row2' },
    h('label', { class: 'chk' }, h('input', { type: 'checkbox', checked: sc.voice, onchange: ev => { edit(() => { sc.voice = ev.target.checked; }); renderEditor(); } }), 'Có giọng đọc'),
    h('label', { class: 'chk' }, h('input', { type: 'checkbox', checked: sc.caption, onchange: ev => { edit(() => { sc.caption = ev.target.checked; }); } }), 'Hiện phụ đề')));
  if (sc.voice && sc.narration.trim()) {
    const st = h('div', { style: 'margin:4px 0 8px' });
    if (e.estimated) st.append(h('div', { class: 'warn hint' }, '⚠ Chưa tạo giọng – đang dùng thời lượng ước lượng.'));
    else if (sc.audio) st.append(h('div', { class: 'ok hint' }, '✓ Đã có giọng (' + sc.audio.dur.toFixed(1) + 's)'),
      isFallbackVoice(sc.audio) ? h('div', { class: 'warn hint' }, '⚠ Giọng dự phòng (' + ttsLabel(sc.audio.engine) + '), nghe khác giọng chính. Bấm “Tạo lại” khi giọng chính chạy lại.') : '',
      h('audio', { controls: true, style: 'width:100%;margin-top:4px', src: `/files/${S.pid}/audio/${sc.audio.file}` }));
    st.append(h('button', { class: 'sm', style: 'margin-top:6px', onclick: ev => genVoice(sc, ev.target) }, e.estimated ? '🔊 Tạo giọng cảnh này' : '🔊 Tạo lại'));
    box.append(st);
    box.append(...field('Dừng thêm cuối cảnh (giây)', h('input', { type: 'number', min: 0, max: 20, step: 0.1, value: sc.extra || 0, oninput: ev => { sc.extra = parseFloat(ev.target.value) || 0; touch(); } })));
  } else {
    box.append(...field('Thời lượng cảnh (giây)', h('input', { type: 'number', min: 1, max: 120, step: 0.5, value: sc.duration, oninput: ev => { sc.duration = parseFloat(ev.target.value) || 4; touch(); } })));
  }
  box.append(h('label', { class: 'f' }, 'Ảnh (hiện lần lượt, chia đều thời gian cảnh)'));
  sc.images.forEach((im, j) => box.append(h('div', { class: 'imgrow' },
    h('img', { src: `/files/${S.pid}/media/${im.file}`, loading: 'lazy' }),
    h('div', { class: 'c' }, sel(MODES, im.mode, v => edit(() => { im.mode = v; })), sel(ANIMS, im.anim, v => edit(() => { im.anim = v; }))),
    h('div', { style: 'display:flex;flex-direction:column;gap:2px' },
      h('button', { class: 'sm', onclick: () => { if (j > 0) { edit(() => { [sc.images[j - 1], sc.images[j]] = [sc.images[j], sc.images[j - 1]]; }); renderEditor(); } } }, '↑'),
      h('button', { class: 'sm', onclick: () => { edit(() => { sc.images.splice(j, 1); }); renderEditor(); } }, '✕')))));
  const fi = h('input', { type: 'file', accept: 'image/*', multiple: true, style: 'display:none', onchange: async ev => { await addImages([...ev.target.files]); ev.target.value = ''; } });
  box.append(fi, h('button', { class: 'sm', onclick: () => fi.click() }, '+ Thêm ảnh'), h('span', { class: 'hint' }, '  hoặc kéo thả / Ctrl+V dán ảnh chụp màn hình'));
  if (sc.images.length) {
    box.append(...field('Bố cục chữ và ảnh', sel(LAYOUTS, sc.layout || 'stack', v => { edit(() => { sc.layout = v; }); renderEditor(); })));
    if (sc.layout === 'split') box.append(sel(SIDES, sc.image_side || 'right', v => edit(() => { sc.image_side = v; })), h('div', { class: 'hint' }, 'Khung ngang/vuông: chữ và ảnh nằm hai cột. Khung dọc: ảnh ở trên, chữ ở dưới.'));
    box.append(h('div', { class: 'hint', style: 'margin-top:6px' }, '“Vừa khung + nền mờ”: giữ nguyên cả ảnh, nền là chính ảnh đó làm mờ – hợp với ảnh chụp màn hình lệch tỉ lệ. “Toàn màn hình” tự chuyển sang kiểu này khi phải cắt quá nhiều.'));
  }
  box.append(...field('Chuyển sang cảnh sau', sel(TRANS, sc.transition, v => edit(() => { sc.transition = v; }))));
}
async function upload(file) {
  const fd = new FormData(); fd.append('file', file, file.name || 'image.png');
  const r = await fetch(`/api/projects/${S.pid}/upload`, { method: 'POST', body: fd });
  let j = {}; try { j = await r.json(); } catch (e) {} if (!r.ok) throw apiError(j, r.status); return j.file;
}
async function addImages(files) {
  const sc = cur(); if (!sc) { toast('Hãy chọn một cảnh trước.', true); return; }
  const added = [];
  for (const f of files.filter(f => f.type.startsWith('image/'))) {
    try { added.push({ file: await upload(f), mode: 'card', anim: 'zoom' }); } catch (e) { toast(e, true); }
  }
  if (added.length) edit(() => { sc.images.push(...added); });  // cả lượt thêm ảnh = một bước hoàn tác
  renderEditor();
}
async function genVoice(sc, btn) {
  btn.disabled = true; btn.textContent = 'Đang tạo giọng…';
  try {
    await flush();
    const r = await api(`/api/projects/${S.pid}/tts`, 'POST', { scene: sc.id });
    sc.audio = r.audio; S.tl = r.tl; renderSceneList(); renderEditor(); updateScrub(); refreshPreview();
    if (r.notice) showNotice('Đã dùng giọng dự phòng', r.notice);
  } catch (e) { toast(e, true); renderEditor(); }
}
