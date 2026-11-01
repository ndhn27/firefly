/* Việc chạy nền: tạo giọng, xem thử, xuất video; lỗi, nhật ký, kiểm tra máy.
   Các file trong static/js/ là script thường (không phải ES module), nạp lần lượt theo thứ tự trong index.html và dùng chung
   một phạm vi toàn cục (các test Playwright cũng gọi thẳng S, H, edit()…). Hàm chỉ được GỌI sau khi mọi file đã nạp xong. */
/* ------------------------------------------------------------ job (tạo giọng / xem thử / xuất) */
async function runJob(startUrl, body, title) {
  await flush();
  let jid;
  try { jid = (await api(startUrl, 'POST', body)).job; } catch (e) { toast(e, true); return null; }
  const bar = h('i'), stage = h('div', {}), msg = h('div', { class: 'hint' });
  openModal(h('h3', {}, title), stage, h('div', { class: 'bar' }, bar), msg, h('div', { style: 'text-align:right;margin-top:10px' }, h('button', { onclick: () => api(`/api/jobs/${jid}/cancel`, 'POST', {}) }, 'Huỷ')));
  for (;;) {
    await new Promise(r => setTimeout(r, 600));
    let j; try { j = await api(`/api/jobs/${jid}`); } catch (e) { closeModal(); toast(e, true); return null; }
    bar.style.width = Math.round(j.progress * 100) + '%'; stage.textContent = j.stage || 'Đang chuẩn bị…'; msg.textContent = j.message || '';
    if (j.state === 'running') continue;
    closeModal();
    if (j.state === 'error') { if (j.hint || j.code === 'unexpected') showError(j, title); else toast(j.error || 'Có lỗi xảy ra', true); return null; }
    if (j.state === 'cancelled') { toast('Đã huỷ.'); return null; }
    return j;
  }
}
function showError(e, title) {
  openModal(h('h3', {}, title ? `${title}: không thành công` : 'Có lỗi'),
    h('p', {}, e.error || e.message), e.hint ? h('p', { class: 'hint' }, e.hint) : '',
    e.ref ? h('p', { class: 'hint' }, `Mã tra nhật ký: ${e.ref}`) : '',
    h('div', { style: 'margin-top:12px;display:flex;gap:8px;justify-content:flex-end' }, h('button', { onclick: openLogs }, '📄 Xem nhật ký'), h('button', { class: 'pri', onclick: closeModal }, 'Đóng')));
}
async function openLogs() {
  openModal(h('h3', {}, 'Nhật ký'), h('p', { class: 'hint' }, 'Đang đọc…'));
  let r; try { r = await api('/api/logs?lines=300'); } catch (e) { closeModal(); toast(e, true); return; }
  const pre = h('pre', { class: 'log' }, r.lines.length ? r.lines.join('\n') : '(nhật ký đang trống)');
  openModal(h('h3', {}, 'Nhật ký'), h('p', { class: 'hint' }, `${r.path} – 300 dòng cuối. Gửi file này khi cần hỗ trợ.`), pre,
    h('div', { style: 'margin-top:12px;display:flex;gap:8px;justify-content:flex-end' }, h('a', { href: '/api/logs/download', download: 'firefly.log' }, h('button', {}, '⬇ Tải file nhật ký')), h('button', { class: 'pri', onclick: closeModal }, 'Đóng')));
  pre.scrollTop = pre.scrollHeight;
}
async function openDoctor() {
  openModal(h('h3', {}, 'Kiểm tra máy'), h('p', { class: 'hint' }, 'Đang kiểm tra… (dò GPU có thể mất vài giây)'));
  let r; try { r = await api('/api/doctor'); } catch (e) { closeModal(); toast(e, true); return; }
  const mark = { ok: '✓', warn: '!', error: '✗' };
  openModal(h('h3', {}, r.ok ? 'Máy đủ điều kiện chạy' : 'Còn lỗi cần sửa'),
    h('div', { style: 'font-size:13px;line-height:1.6;max-height:50vh;overflow:auto' }, r.items.map(i =>
      h('div', { class: i.level === 'ok' ? 'ok' : i.level === 'warn' ? 'warn' : 'err' }, `${mark[i.level]} ${i.name}: ${i.detail}`))),
    h('div', { style: 'margin-top:12px;display:flex;gap:8px;justify-content:flex-end' }, h('button', { onclick: openLogs }, '📄 Nhật ký'), h('button', { class: 'pri', onclick: closeModal }, 'Đóng')));
}
async function reloadAudio() {
  const r = await api(`/api/projects/${S.pid}`); const m = {}; r.project.scenes.forEach(s => m[s.id] = s.audio);
  S.proj.scenes.forEach(s => s.audio = m[s.id] || null); S.tl = r.tl; renderSceneList(); renderEditor(); updateScrub(); refreshPreview();
}
function showNotice(title, text) {  // thông báo dài, không phải lỗi (VD: có cảnh đã đọc bằng giọng dự phòng)
  openModal(h('h3', {}, '⚠ ' + title), h('p', {}, text), h('div', { style: 'text-align:right;margin-top:12px' }, h('button', { class: 'pri', onclick: closeModal }, 'Đã hiểu')));
}
async function doVoices(redoFallback) {
  const j = await runJob(`/api/projects/${S.pid}/tts_all`, { redo_fallback: !!redoFallback }, redoFallback ? 'Tạo lại giọng dự phòng bằng giọng chính' : 'Tạo giọng đọc');
  if (!j) return;
  await reloadAudio();
  if (j.notice) showNotice('Đã dùng giọng dự phòng', j.notice); else toast(redoFallback ? 'Đã tạo lại bằng giọng chính.' : 'Đã tạo xong giọng đọc.');
}
async function doPreview() {
  if (!S.proj.scenes.length) return toast('Chưa có cảnh nào.', true);
  const j = await runJob(`/api/projects/${S.pid}/render`, { mode: 'preview' }, 'Dựng bản xem thử (nhỏ, nhanh)');
  if (j) { await reloadAudio(); showVideo(j.file); if (j.notice) toast({ message: '⚠ ' + j.notice, ms: 10000 }); }
}
const fmtDur = s => s >= 3600 ? `${Math.floor(s / 3600)} giờ ${Math.round(s % 3600 / 60)} phút` : s >= 90 ? `${Math.round(s / 60)} phút` : `${s} giây`;
async function confirmExport() {  // dựng thử vài khung để ước lượng thời gian + dung lượng, rồi hỏi lại trước khi xuất
  const e = await runJob(`/api/projects/${S.pid}/estimate`, {}, 'Ước lượng thời gian xuất');
  if (!e) return false;
  const i = e.info, TIER = { draft: 'Nháp', standard: 'Chuẩn', high: 'Cao' };
  const errs = (i.issues || []).filter(x => x.level === 'error'), warns = (i.issues || []).filter(x => x.level !== 'error');
  return new Promise(res => {
    const ok = () => { closeModal(); res(true); }, no = () => { closeModal(); res(false); };
    openModal(h('h3', {}, 'Xuất video?'),
      h('p', {}, `${i.W}×${i.H} · ${i.fps}fps · ${i.total}s · mức ${TIER[i.tier] || i.tier} · bộ mã hoá ${i.encoder}`),
      h('p', {}, h('b', {}, `Dự kiến mất khoảng ${fmtDur(i.seconds)}, file khoảng ${i.mb} MB`), h('span', { class: 'hint' }, ' (ước tính, có thể lệch ±30%)')),
      h('p', { class: 'hint' }, `Dựng 1 khung mất ${i.render_ms} ms, chạy ${i.workers} tiến trình song song trên máy ${i.cpus} luồng.`),
      i.voices_missing ? h('p', { class: 'warn hint' }, `⚠ ${i.voices_missing} cảnh chưa có giọng: thời lượng đang ước lượng, sẽ tạo giọng ngay khi xuất nên con số có thể đổi.`) : '',
      ...i.warnings.map(w => h('p', { class: 'warn hint' }, '⚠ ' + w)),
      ...warns.map(x => h('p', { class: 'warn hint' }, '⚠ ' + x.msg + (x.hint ? ' ' + x.hint : ''))),
      ...errs.map(x => h('p', { class: 'err' }, '✗ ' + x.msg + (x.hint ? ' ' + x.hint : ''))),
      h('div', { style: 'text-align:right;margin-top:12px;display:flex;gap:8px;justify-content:flex-end' }, h('button', { onclick: no }, errs.length ? 'Đóng' : 'Để sau'), errs.length ? '' : h('button', { class: 'pri', onclick: ok }, '⬇ Xuất')));
  });
}
async function doExport() {
  if (!S.proj.scenes.length) return toast('Chưa có cảnh nào.', true);
  if (!(await confirmExport())) return;
  const j = await runJob(`/api/projects/${S.pid}/render`, { mode: 'final' }, 'Đang xuất video');
  if (!j) return;
  await reloadAudio();
  const i = j.info || {};
  openModal(h('h3', {}, '✓ Xuất xong'), h('p', {}, `${i.W}×${i.H} · ${i.fps}fps · mất ${i.seconds}s · bộ mã hoá ${i.encoder}` + (i.loudness && i.loudness.after != null ? ` · âm lượng ${i.loudness.after} LUFS` : '') + (i.resumed ? ` · dùng lại ${i.resumed} đoạn đã dựng từ lần trước` : '')),
    h('p', { class: 'hint' }, 'File nằm trong thư mục projects/' + S.pid + '/out/ của tool.'),
    j.notice ? h('p', { class: 'warn hint' }, '⚠ ' + j.notice) : '',
    h('video', { src: j.file, controls: true, style: 'width:100%;max-height:50vh;background:#000;border-radius:8px' }),
    h('div', { style: 'text-align:right;margin-top:12px;display:flex;gap:8px;justify-content:flex-end' }, h('button', { onclick: closeModal }, 'Đóng'), h('a', { href: j.file + '?dl=1', download: '' }, h('button', { class: 'pri' }, '⬇ Tải về'))));
}
