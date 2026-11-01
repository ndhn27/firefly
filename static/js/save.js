/* Tự lưu dự án lên server (touch/flush).
   Các file trong static/js/ là script thường (không phải ES module), nạp lần lượt theo thứ tự trong index.html và dùng chung
   một phạm vi toàn cục (các test Playwright cũng gọi thẳng S, H, edit()…). Hàm chỉ được GỌI sau khi mọi file đã nạp xong. */
/* ------------------------------------------------------------ lưu & xem trước */
function touch() {
  S.dirty = true; showStill(); clearTimeout(S.timer); S.timer = setTimeout(flush, 350); renderSceneList();
  clearTimeout(H.timer); H.timer = setTimeout(commit, HIST_PAUSE); histUI();
}
function flush() {
  clearTimeout(S.timer);
  if (S.saving) { S.again = true; return S.savePromise; }
  if (!S.dirty || !S.pid) return Promise.resolve();
  S.dirty = false; S.saving = true;
  S.savePromise = (async () => {
    try {
      const r = await api(`/api/projects/${S.pid}`, 'PUT', S.proj); S.tl = r.tl; S.issues = r.issues || [];
      if (r.audio) S.proj.scenes.forEach(s => { if (s.id in r.audio) s.audio = r.audio[s.id]; });  // server có thể tìm lại giọng cũ khớp nội dung
    } catch (e) { toast(e, true); }
    S.saving = false;
    if (S.dirty || S.again) { S.again = false; await flush(); return; }
    renderSceneList(); renderIssues(); updateScrub(); refreshPreview();
  })();
  return S.savePromise;
}
