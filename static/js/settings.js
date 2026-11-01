/* Cài đặt dự án, dọn file không dùng, hộp thoại dự án mới.
   Các file trong static/js/ là script thường (không phải ES module), nạp lần lượt theo thứ tự trong index.html và dùng chung
   một phạm vi toàn cục (các test Playwright cũng gọi thẳng S, H, edit()…). Hàm chỉ được GỌI sau khi mọi file đã nạp xong. */
function settingsBody(P, edit, onChange) {
  const out = [];
  const chg = now => { onChange && onChange(now); };  // chg(1) = lựa chọn rời (một bước hoàn tác), chg() = đang kéo/gõ (gộp bước)
  const aspBox = h('div', { class: 'asp' });
  const sizeLbl = h('div', { class: 'hint', style: 'margin-top:6px' });
  const qBox = h('div', { class: 'seg' }), fBox = h('div', { class: 'seg' });
  const draw = () => {
    aspBox.replaceChildren(...[['9:16', 'Dọc 9:16', 'Reels · Shorts · TikTok'], ['16:9', 'Ngang 16:9', 'YouTube · FB video'], ['1:1', 'Vuông 1:1', 'Bài đăng feed'], ['4:5', 'Dọc 4:5', 'Feed dọc']].map(([a, n, d]) => {
      const [x, y] = a.split(':').map(Number), k = 38 / Math.max(x, y);
      return h('button', { class: P.aspect === a ? 'on' : '', onclick: () => { P.aspect = a; draw(); chg(1); } },
        h('div', { class: 'bx', style: `width:${x * k}px;height:${y * k}px` }), h('b', {}, n), h('span', { class: 'hint', style: 'font-size:11px' }, d));
    }));
    qBox.replaceChildren(...[[720, '720p'], [1080, '1080p'], [1440, '2K (1440p)']].map(([q, l]) => h('button', { class: P.quality === q ? 'on' : '', onclick: () => { P.quality = q; draw(); chg(1); } }, l)));
    fBox.replaceChildren(...[24, 30, 60].map(f => h('button', { class: P.fps === f ? 'on' : '', onclick: () => { P.fps = f; draw(); chg(1); } }, f + ' fps')));
    const [w, hh] = frameSize(P.aspect, P.quality); sizeLbl.textContent = `Video xuất ra: ${w}×${hh} · ${P.fps}fps`;
  };
  out.push(h('h4', {}, '1 · Khung hình'), aspBox, h('h4', {}, '2 · Chất lượng'), qBox, h('div', { style: 'height:6px' }), fBox, sizeLbl);
  const th = P.theme;
  const sli = (k, label, min, max, step) => { const v = h('span', { class: 'hint' }, th[k]); return [h('label', { class: 'f' }, label + ' ', v), h('input', { type: 'range', min, max, step, value: th[k], oninput: ev => { th[k] = parseFloat(ev.target.value); v.textContent = th[k]; chg(); } })]; };
  const col = (k, label) => h('div', {}, h('label', { class: 'f' }, label), h('input', { type: 'color', value: hex(th[k]), oninput: ev => { th[k] = rgb(ev.target.value); chg(); } }));
  const colsBox = h('div', { class: 'row2' });
  const sliBox = h('div');
  const drawTheme = () => {
    sliBox.replaceChildren(...sli('count', 'Số đốm sáng', 10, 200, 5), ...sli('size', 'Kích thước', 0.5, 2, 0.1), ...sli('speed', 'Tốc độ bay', 0, 3, 0.1), ...sli('glow', 'Độ sáng', 0.3, 2, 0.1), ...sli('rays', 'Tia sáng', 0, 1.5, 0.1),
      h('label', { class: 'chk' }, h('input', { type: 'checkbox', checked: (th.bokeh || 0) > 0.5, onchange: ev => { th.bokeh = ev.target.checked ? 1 : 0; chg(1); } }), 'Đốm mờ to kiểu bokeh (thay cho đom đóm nhỏ)'));
    colsBox.replaceChildren(col('bg_top', 'Nền – trên'), col('bg_bottom', 'Nền – dưới'), col('c1', 'Ánh sáng 1'), col('c2', 'Ánh sáng 2'));
  };
  drawTheme();
  const ts = h('select', { onchange: ev => { const t = S.themes[ev.target.value]; Object.keys(th).forEach(k => delete th[k]); Object.assign(th, JSON.parse(JSON.stringify(t))); drawTheme(); chg(1); } },
    Object.entries(S.themes).map(([k, t]) => h('option', { value: k }, t.label)));
  ts.value = th.preset;
  out.push(h('h4', {}, '3 · Nền động'), ts, sliBox, h('div', { style: 'height:8px' }), colsBox);
  const vlist = S.voices.length ? S.voices : [{ name: 'vi-VN-HoaiMyNeural', gender: 'Nữ', locale: 'vi-VN' }];
  const groups = {}; vlist.forEach(v => (groups[v.locale] = groups[v.locale] || []).push(v));
  const vs = h('select', { onchange: ev => { P.voice.name = ev.target.value; chg(1); } },
    Object.entries(groups).map(([loc, arr]) => h('optgroup', { label: loc }, arr.map(v => h('option', { value: v.name }, v.name.replace(/Neural$/, '') + ' · ' + v.gender)))));
  vs.value = P.voice.name;
  const rv = h('span', { class: 'hint' }, P.voice.rate + '%'), pv = h('span', { class: 'hint' }, P.voice.pitch + 'Hz');
  out.push(h('h4', {}, '4 · Giọng đọc (chính: Microsoft Edge TTS – miễn phí)'), vs,
    h('label', { class: 'f' }, 'Tốc độ ', rv), h('input', { type: 'range', min: -40, max: 60, step: 5, value: P.voice.rate, oninput: ev => { P.voice.rate = +ev.target.value; rv.textContent = P.voice.rate + '%'; chg(); } }),
    h('label', { class: 'f' }, 'Cao độ ', pv), h('input', { type: 'range', min: -30, max: 30, step: 2, value: P.voice.pitch, oninput: ev => { P.voice.pitch = +ev.target.value; pv.textContent = P.voice.pitch + 'Hz'; chg(); } }));
  if (edit) {
    // Giọng dự phòng: Edge TTS là endpoint không chính thức nên có thể ngừng bất cứ lúc nào (xem README, mục Giọng dự phòng)
    const fbBox = h('div', { class: 'hint', style: 'margin-top:6px;line-height:1.6' }, 'Đang kiểm tra giọng dự phòng…');
    const nFb = P.scenes.filter(s => isFallbackVoice(s.audio)).length;
    out.push(
      h('label', { class: 'chk', style: 'margin-top:10px' }, h('input', { type: 'checkbox', checked: P.voice.fallback !== false, onchange: ev => { P.voice.fallback = ev.target.checked; chg(1); } }), 'Tự chuyển sang giọng dự phòng khi giọng chính lỗi'),
      fbBox,
      nFb ? h('div', { style: 'margin-top:6px' }, h('div', { class: 'warn hint' }, `⚠ ${nFb} cảnh đang dùng giọng dự phòng.`),
        h('button', { class: 'sm', style: 'margin-top:4px', onclick: () => { closeModal(); doVoices(true); } }, '🔊 Tạo lại các cảnh đó bằng giọng chính')) : '');
    api('/api/tts/status?voice=' + encodeURIComponent(P.voice.name)).then(r => {
      S.tts = r.engines;
      fbBox.replaceChildren(...r.engines.map(e => h('div', { class: e.ok ? 'ok' : 'warn' },
        `${e.ok ? '✓' : '!'} ${e.primary ? 'Giọng chính' : 'Dự phòng'} · ${e.label}${e.online ? '' : ' (chạy trên máy)'}: ${e.detail}`)),
        h('div', {}, 'Giọng dự phòng không có mốc từng từ (phụ đề đổi cụm theo chỗ ngắt hơi) và không chỉnh được cao độ. Google gTTS gửi lời đọc tới Google; Piper chạy hoàn toàn trên máy.'));
    }).catch(() => { fbBox.textContent = ''; });
    out.push(h('label', { class: 'f' }, 'Từ điển phát âm – mỗi dòng “từ=cách đọc” (chỉ ảnh hưởng giọng, phụ đề vẫn giữ nguyên)'),
      h('textarea', { rows: 3, placeholder: 'GitHub=Ghít hấp\nmalware=man-ue', value: P.pron || '', oninput: ev => { P.pron = ev.target.value; chg(); } }));
    out.push(h('label', { class: 'chk', style: 'margin-top:8px' }, h('input', { type: 'checkbox', checked: P.normalize_text !== false, onchange: ev => { P.normalize_text = ev.target.checked; chg(1); } }), 'Chuẩn hoá số, %, ngày, đơn vị khi đọc (đổi mục này thì phải tạo lại giọng)'),
      h('label', { class: 'chk' }, h('input', { type: 'checkbox', checked: !!P.caption_hl, onchange: ev => { P.caption_hl = ev.target.checked; chg(1); } }), 'Phụ đề: tô sáng từ đang đọc'));
    const bn = h('span', { class: 'hint' }, P.bgm.file ? 'Đã chọn nhạc nền' : 'Chưa có nhạc nền');
    const bf = h('input', { type: 'file', accept: 'audio/*', style: 'display:none', onchange: async ev => { const f = ev.target.files[0]; if (!f) return; try { P.bgm.file = await upload(f); bn.textContent = 'Đã chọn: ' + f.name; chg(1); } catch (e) { toast(e, true); } } });
    P.logo = P.logo || { file: null, pos: 'tr', size: 0.14, opacity: 0.9 };
    const ln = h('span', { class: 'hint' }, P.logo.file ? 'Đã chọn logo' : 'Chưa có logo');
    const lf = h('input', { type: 'file', accept: 'image/*', style: 'display:none', onchange: async ev => { const f = ev.target.files[0]; if (!f) return; try { P.logo.file = await upload(f); ln.textContent = 'Đã chọn: ' + f.name; chg(1); } catch (e) { toast(e, true); } } });
    out.push(h('h4', {}, '5 · Nhạc nền (tự nhỏ lại khi có giọng)'), bf,
      h('div', { style: 'display:flex;gap:8px;align-items:center' }, h('button', { class: 'sm', onclick: () => bf.click() }, 'Chọn file nhạc…'), h('button', { class: 'sm', onclick: () => { P.bgm.file = null; bn.textContent = 'Chưa có nhạc nền'; chg(1); } }, 'Bỏ'), bn),
      h('label', { class: 'f' }, 'Âm lượng nhạc'), h('input', { type: 'range', min: 0, max: 0.5, step: 0.01, value: P.bgm.volume, oninput: ev => { P.bgm.volume = +ev.target.value; chg(); } }),
      h('label', { class: 'f' }, 'Âm lượng cuối của video'), sel([['lufs:-14', 'Chuẩn hoá -14 LUFS (mức YouTube/Facebook)'], ['lufs:-16', 'Chuẩn hoá -16 LUFS (êm hơn)'], ['off', 'Tắt – chỉ chặn đỉnh']], P.audio_norm && P.audio_norm.mode === 'off' ? 'off' : 'lufs:' + ((P.audio_norm && P.audio_norm.target) || -14), v => { P.audio_norm = v === 'off' ? { mode: 'off', target: -14 } : { mode: 'lufs', target: +v.split(':')[1] }; chg(1); }),
      h('h4', {}, '6 · Logo / watermark'), lf,
      h('div', { style: 'display:flex;gap:8px;align-items:center' }, h('button', { class: 'sm', onclick: () => lf.click() }, 'Chọn ảnh logo (PNG nền trong suốt)…'), h('button', { class: 'sm', onclick: () => { P.logo.file = null; ln.textContent = 'Chưa có logo'; chg(1); } }, 'Bỏ'), ln),
      h('label', { class: 'f' }, 'Vị trí'), sel([['tr', 'Góc trên phải'], ['tl', 'Góc trên trái'], ['br', 'Góc dưới phải'], ['bl', 'Góc dưới trái']], P.logo.pos, v => { P.logo.pos = v; chg(1); }),
      h('div', { class: 'hint' }, 'Khung 9:16 nên đặt logo ở trên: phía dưới bị giao diện Reels/Shorts/TikTok che.'),
      h('label', { class: 'f' }, 'Kích thước'), h('input', { type: 'range', min: 0.04, max: 0.4, step: 0.01, value: P.logo.size, oninput: ev => { P.logo.size = +ev.target.value; chg(); } }),
      h('label', { class: 'f' }, 'Độ đậm'), h('input', { type: 'range', min: 0.1, max: 1, step: 0.05, value: P.logo.opacity, oninput: ev => { P.logo.opacity = +ev.target.value; chg(); } }),
      h('h4', {}, '7 · Xuất video'),
      h('label', { class: 'f' }, 'Mức chất lượng khi xuất'), sel([['draft', 'Nháp – nhanh, file nhỏ'], ['standard', 'Chuẩn'], ['high', 'Cao – chậm hơn, file lớn hơn']], P.export_tier || 'standard', v => { P.export_tier = v; chg(1); }),
      h('label', { class: 'f' }, 'Bộ mã hoá'), sel([['auto', 'Tự động (thử NVIDIA → Intel → AMD, không có thì CPU)'], ['cpu', 'Luôn dùng CPU (x264)'], ['nvenc', 'NVIDIA NVENC'], ['qsv', 'Intel QSV'], ['amf', 'AMD AMF']], P.encoder || 'auto', v => { P.encoder = v; chg(1); }),
      h('div', { style: 'margin-top:10px' }, h('button', { class: 'sm', onclick: openDoctor }, '🩺 Kiểm tra máy (FFmpeg, GPU, font, mạng)')),
      h('h4', {}, '8 · Dọn dẹp'),
      h('div', { class: 'hint' }, 'Ảnh, nhạc, logo và giọng đã bỏ khỏi dự án vẫn nằm trong thư mục dự án cho tới khi bạn dọn.'),
      h('div', { style: 'margin-top:6px' }, h('button', { class: 'sm', onclick: openCleanup }, '🧹 Dọn file không dùng…')));
  }
  draw();
  return out;
}
function openSettings() {
  openModal(h('h3', {}, 'Cài đặt dự án'), settingsBody(S.proj, true, now => { touch(); if (now) commit(); fit(); }),
    h('div', { style: 'margin-top:16px;text-align:right' }, h('button', { class: 'pri', onclick: () => { closeModal(); flush().then(() => { fit(); refreshPreview(); }); } }, 'Xong')));
}
const mbs = b => b >= 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB';
async function openCleanup() {
  await flush();
  let r; try { r = await api(`/api/projects/${S.pid}/unused`); } catch (e) { toast(e, true); return; }
  const note = r.recent ? h('p', { class: 'hint' }, `${r.recent} file vừa tạo (dưới 1 phút) được giữ lại, dọn lại sau nhé.`) : '';
  if (!r.items.length) {
    openModal(h('h3', {}, '🧹 Dọn file không dùng'), h('p', {}, 'Không có file thừa: mọi ảnh, nhạc, logo và giọng trong thư mục dự án đều đang được dùng.'), note,
      h('div', { style: 'text-align:right;margin-top:12px' }, h('button', { class: 'pri', onclick: closeModal }, 'Đóng')));
    return;
  }
  const shown = r.items.filter(i => !i.name.endsWith('.json')), list = shown.length ? shown : r.items;  // .json = file mô tả đi kèm file giọng
  const nm = list.filter(i => i.kind === 'media').length, na = list.filter(i => i.kind === 'audio').length;
  const go = async () => {
    try {
      const d = await api(`/api/projects/${S.pid}/cleanup`, 'POST', { files: r.items.map(i => i.kind + '/' + i.name) });
      histReset(); closeModal();
      toast(`Đã dọn ${list.length} file, giải phóng ${mbs(d.bytes)}.` + (d.failed ? ` ${d.failed} file không xoá được.` : ''), !!d.failed);
    } catch (e) { toast(e, true); }
  };
  openModal(h('h3', {}, '🧹 Dọn file không dùng'),
    h('p', {}, `Tìm thấy ${list.length} file không còn được dự án dùng, tổng ${mbs(r.bytes)}: ${[nm && nm + ' ảnh/nhạc/logo', na && na + ' file giọng'].filter(Boolean).join(', ')}.`),
    h('div', { style: 'max-height:34vh;overflow:auto;font-size:12px;border:1px solid var(--line);border-radius:8px;padding:6px 10px;background:var(--panel2)' },
      list.map(i => h('div', { style: 'display:flex;justify-content:space-between;gap:12px' }, h('span', {}, i.kind + '/' + i.name), h('span', { class: 'hint' }, mbs(i.size))))),
    note,
    h('p', { class: 'hint' }, 'Xoá hẳn, không có thùng rác. Sau khi dọn, lịch sử hoàn tác (Ctrl+Z) bị xoá vì các bước cũ có thể cần những file này. Video đã xuất trong out/ không bị đụng tới.'),
    h('div', { style: 'text-align:right;margin-top:12px;display:flex;gap:8px;justify-content:flex-end' }, h('button', { onclick: openSettings }, 'Huỷ'), h('button', { class: 'pri', onclick: go }, `Xoá ${list.length} file`)));
}
function openNewProject() {
  const P = { name: '', aspect: '9:16', quality: 1080, fps: 30, theme: JSON.parse(JSON.stringify(S.themes['dom-dom-vang'] || {})), voice: { name: 'vi-VN-HoaiMyNeural', rate: 0, pitch: 0 } };
  const nm = h('input', { type: 'text', placeholder: 'VD: GitHub là gì?' });
  openModal(h('h3', {}, 'Dự án video mới'), h('p', { class: 'hint', style: 'margin:0' }, 'Chọn khung hình trước – có thể đổi lại sau trong Cài đặt.'),
    h('label', { class: 'f' }, 'Tên dự án'), nm, settingsBody(P, false, null),
    h('div', { style: 'margin-top:16px;display:flex;gap:8px;justify-content:flex-end' },
      S.pid ? h('button', { onclick: closeModal }, 'Huỷ') : '',
      h('button', { class: 'pri', onclick: async () => { P.name = nm.value.trim() || 'Video mới'; try { const r = await api('/api/projects', 'POST', P); closeModal(); await refreshProjectList(r.id); await loadProject(r.id); } catch (e) { toast(e, true); } } }, 'Tạo dự án')));
  nm.focus();
}
