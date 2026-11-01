/* Khởi động và gắn sự kiện. PHẢI nạp cuối cùng.
   Các file trong static/js/ là script thường (không phải ES module), nạp lần lượt theo thứ tự trong index.html và dùng chung
   một phạm vi toàn cục (các test Playwright cũng gọi thẳng S, H, edit()…). Hàm chỉ được GỌI sau khi mọi file đã nạp xong. */
/* ------------------------------------------------------------ khởi động */
async function refreshProjectList(selectId) {
  const list = await api('/api/projects'); const sl = $('#projSel'); sl.replaceChildren();
  list.forEach(p => sl.append(h('option', { value: p.id }, p.name + ' (' + p.aspect + ')')));
  sl.append(h('option', { value: '__new' }, '＋ Dự án mới…'));
  if (selectId) sl.value = selectId;
  return list;
}
async function loadProject(pid) {
  const r = await api('/api/projects/' + pid);
  S.pid = pid; S.proj = r.project; S.tl = r.tl; S.issues = r.issues || []; S.sel = 0; S.t = 0; S.dirty = false; histReset();
  try { localStorage.setItem('ffv_last', pid); } catch (e) {}
  $('#projSel').value = pid; showStill(); fit(); renderSceneList(); renderEditor(); updateScrub();
  if (S.proj.scenes.length) selectScene(0); else refreshPreview();
}
async function boot() {
  try { S.themes = await api('/api/themes'); } catch (e) {}
  api('/api/voices').then(v => S.voices = v).catch(() => {});
  api('/api/tts/status').then(r => { S.tts = r.engines || []; renderSceneList(); }).catch(() => {});
  try { S.showSafe = localStorage.getItem('ffv_safe') === '1'; } catch (e) {}
  api('/api/safe').then(z => { S.safe = z; drawSafe(); }).catch(() => {});
  const list = await refreshProjectList();
  let last = null; try { last = localStorage.getItem('ffv_last'); } catch (e) {}
  const pick = list.find(p => p.id === last) || list[0];
  if (pick) { await loadProject(pick.id); $('#projSel').value = pick.id; } else openNewProject();
}
$('#projSel').onchange = async ev => { const v = ev.target.value; if (v === '__new') { ev.target.value = S.pid || ''; openNewProject(); return; } await flush(); loadProject(v); };
$('#btnSettings').onclick = () => S.proj && openSettings();
$('#btnAdd').onclick = () => S.proj && addScenes([newScene()], S.proj.scenes.length ? S.sel + 1 : 0);
$('#btnPaste').onclick = () => S.proj && openPaste();
$('#btnAI').onclick = () => S.proj && openAI();
$('#btnVoices').onclick = () => S.proj && doVoices();
$('#btnPreview').onclick = () => S.proj && doPreview();
$('#btnExport').onclick = () => S.proj && doExport();
$('#btnStill').onclick = () => { showStill(); refreshPreview(); };
$('#scrub').oninput = ev => {
  S.t = parseFloat(ev.target.value); $('#timeLbl').textContent = fmt(S.t) + ' / ' + fmt(S.tl.total);
  const i = S.tl.scenes.findIndex((s, k) => S.t >= s.start && (k === S.tl.scenes.length - 1 || S.t < S.tl.scenes[k + 1].start));
  if (i >= 0 && i !== S.sel) { commit(); S.sel = i; if (H.base) H.base.sel = selId(); renderSceneList(); renderEditor(); updateScrub(); }
  showStill(); refreshPreview();
};
$('#modalBg').onmousedown = ev => { if (ev.target.id === 'modalBg' && S.pid && !$('#modal').querySelector('.bar')) closeModal(); };
window.addEventListener('resize', fit);
document.addEventListener('paste', async ev => { const f = [...(ev.clipboardData && ev.clipboardData.files || [])].filter(x => x.type.startsWith('image/')); if (f.length && S.proj) { ev.preventDefault(); await addImages(f); } });
const ed = $('#editor');
ed.addEventListener('dragover', ev => { if (dragFrom == null) ev.preventDefault(); });  // kéo cảnh ngang qua đây thì không báo "thả được"
ed.addEventListener('drop', async ev => { ev.preventDefault(); const f = [...ev.dataTransfer.files]; if (f.length) await addImages(f); });
$('#btnSafe').onclick = toggleSafe;
$('#btnUndo').onclick = undo;
$('#btnRedo').onclick = redo;
document.addEventListener('keydown', ev => {
  if (!(ev.ctrlKey || ev.metaKey) || ev.altKey || (ev.key || '').toLowerCase() !== 'z' && (ev.key || '').toLowerCase() !== 'y') return;
  // đang gõ trong ô chữ/số: để trình duyệt hoàn tác chữ của chính ô đó (việc đó cũng được ghi vào lịch sử như một lần sửa)
  if (ev.target.matches && ev.target.matches('textarea,[contenteditable],input:not([type=range]):not([type=checkbox]):not([type=color]):not([type=file]):not([type=button])')) return;
  ev.preventDefault();
  if ((ev.key || '').toLowerCase() === 'y' || ev.shiftKey) redo(); else undo();
});
const scenesBox = $('#scenes');
scenesBox.addEventListener('dragover', ev => { if (dragFrom == null) return; ev.preventDefault(); ev.dataTransfer.dropEffect = 'move'; markDrop(dropIndex(ev)); });
scenesBox.addEventListener('dragleave', ev => {
  const b = scenesBox.getBoundingClientRect();
  if (ev.clientX < b.left || ev.clientX >= b.right || ev.clientY < b.top || ev.clientY >= b.bottom) markDrop(null);
});
scenesBox.addEventListener('drop', ev => {
  if (dragFrom == null) return; ev.preventDefault();
  const from = dragFrom, idx = dropIndex(ev); dragFrom = null; markDrop(null);
  if (idx != null) reorderScene(from, idx > from ? idx - 1 : idx);
});
// thả file ra ngoài khung chỉnh sửa thì không làm gì (thay vì trình duyệt mở file và mất trang)
for (const t of ['dragover', 'drop']) window.addEventListener(t, ev => {
  if (!ev.dataTransfer || ![...ev.dataTransfer.types].includes('Files')) return;
  ev.preventDefault(); if (t === 'dragover' && !ev.target.closest('#editor')) ev.dataTransfer.dropEffect = 'none';
});
boot().catch(e => { reportError('Lỗi khi khởi động: ' + (e && e.message || e), 'boot', e && e.stack); toast(e, true); });  // ghi cả vào nhật ký: trước đây chỉ hiện toast nên rất khó truy
