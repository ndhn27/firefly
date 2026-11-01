/* Tạo kịch bản: bằng AI (Ollama) và dán tay.
   Các file trong static/js/ là script thường (không phải ES module), nạp lần lượt theo thứ tự trong index.html và dùng chung
   một phạm vi toàn cục (các test Playwright cũng gọi thẳng S, H, edit()…). Hàm chỉ được GỌI sau khi mọi file đã nạp xong. */
const AI_LAST = { topic: '', dur: 60, tone: 'explain', notes: '' };  // giữ lại để lỗi/huỷ rồi mở lại không mất chủ đề đã gõ
async function openAI() {
  const lang = ((S.proj.voice && S.proj.voice.name) || 'vi').split('-')[0].toLowerCase();
  const opt = (arr, cur) => arr.map(([v, l]) => h('option', { value: v }, l));
  const topic = h('textarea', { rows: 6, value: AI_LAST.topic, placeholder: 'VD: GitHub là gì và vì sao lập trình viên dùng nó?\n\nHoặc dán cả một bài viết / ghi chú vào đây, AI sẽ rút thành kịch bản.' });
  const dur = h('select', {}, opt([[30, '30 giây'], [60, '1 phút'], [90, '1 phút 30'], [120, '2 phút'], [180, '3 phút']])); dur.value = AI_LAST.dur;
  const tone = h('select', {}, opt([['explain', 'Giải thích dễ hiểu'], ['story', 'Kể chuyện'], ['news', 'Ngắn gọn như bản tin'], ['fun', 'Vui, hóm hỉnh']])); tone.value = AI_LAST.tone;
  const notes = h('input', { type: 'text', value: AI_LAST.notes, placeholder: 'VD: dành cho học sinh cấp 3, đừng dùng thuật ngữ' });
  const url = h('input', { type: 'text' }), model = h('select', { onchange: () => smallHint() }), stat = h('div', { class: 'hint', style: 'margin-top:6px' }), small = h('div', { class: 'warn hint', style: 'margin-top:6px' });
  const go = h('button', { class: 'pri', disabled: true }, 'Viết kịch bản');
  async function refresh(probe) {
    stat.style.color = ''; stat.textContent = 'Đang tìm Ollama…'; go.disabled = true;
    let r; try { r = await api('/api/ai/status' + (probe ? '?url=' + encodeURIComponent(url.value) : '')); } catch (e) { stat.textContent = e.message; stat.style.color = '#ff8a8a'; return; }
    url.value = r.url;
    MODELS = r.models;
    model.replaceChildren(...r.models.map(m => h('option', { value: m.name }, m.name + (m.params || m.size ? ' (' + [m.params, m.size ? (m.size / 1e9).toFixed(1) + ' GB' : ''].filter(Boolean).join(', ') + ')' : ''))));
    if (r.model) model.value = r.model;
    const bad = r.error || (!r.models.length && 'Ollama chạy rồi nhưng chưa có mô hình nào. Chạy trong cửa sổ lệnh, ví dụ: ollama pull qwen2.5:7b');
    stat.textContent = bad || ''; stat.style.color = bad ? '#ff8a8a' : '';
    go.disabled = !!bad;
    smallHint();
  }
  let MODELS = [];
  function smallHint() {  // mô hình dưới ~3,5 tỉ tham số hay viết tiếng Việt kém hoặc lẫn ngôn ngữ khác: báo trước khi người dùng chờ
    const m = MODELS.find(x => x.name === model.value);
    small.textContent = m && m.small ? `⚠ Mô hình nhỏ (${m.params}): thường viết tiếng Việt kém hoặc lẫn ngôn ngữ khác. Nếu máy chạy nổi, chọn mô hình từ khoảng 7B trở lên.` : '';
  }
  go.onclick = async () => {
    const t = topic.value.trim();
    if (t.length < 3) { toast('Hãy nhập chủ đề trước.', true); topic.focus(); return; }
    Object.assign(AI_LAST, { topic: topic.value, dur: +dur.value, tone: tone.value, notes: notes.value });
    try { await api('/api/ai/config', 'PUT', { url: url.value, model: model.value }); } catch (e) { toast(e, true); return; }
    closeModal();
    const j = await runJob('/api/ai/script', { topic: t, duration: +dur.value, tone: tone.value, notes: notes.value, lang }, 'AI viết kịch bản');
    if (!j || !j.script) { openAI(); return; }  // lỗi hoặc huỷ: mở lại hộp thoại, chủ đề vẫn còn
    const sc = j.script;
    openPaste(j.text, `AI (${sc.model}) đã viết ${sc.scenes.length} cảnh, đọc khoảng ${fmt(sc.est_seconds)}` + (sc.attempts > 1 ? ` (sau ${sc.attempts} lần thử)` : '') + '. Xem lại và sửa trước khi tạo cảnh.' + (sc.topic_cut ? ' Lưu ý: tư liệu dài quá nên AI chỉ đọc 8000 ký tự đầu.' : ''), sc.warnings);
  };
  openModal(h('h3', {}, 'Tạo kịch bản bằng AI'),
    h('p', { class: 'hint', style: 'margin:0' }, 'Dùng Ollama chạy ngay trên máy bạn (cài từ ollama.com và tải một mô hình). AI chỉ viết bản nháp; bạn xem lại và sửa trong ô “Dán kịch bản” trước khi tạo cảnh.'),
    h('label', { class: 'f' }, 'Chủ đề hoặc tư liệu'), topic,
    h('div', { style: 'display:grid;grid-template-columns:1fr 1fr;gap:10px' }, h('div', {}, h('label', { class: 'f' }, 'Độ dài video'), dur), h('div', {}, h('label', { class: 'f' }, 'Giọng điệu'), tone)),
    h('label', { class: 'f' }, 'Yêu cầu thêm (tuỳ chọn)'), notes,
    h('label', { class: 'f' }, 'Địa chỉ Ollama'), h('div', { style: 'display:flex;gap:6px' }, url, h('button', { class: 'sm', onclick: () => refresh(true) }, 'Làm mới')),
    h('label', { class: 'f' }, 'Mô hình'), model, small, stat,
    h('div', { style: 'text-align:right;margin-top:14px;display:flex;gap:8px;justify-content:flex-end' }, h('button', { onclick: closeModal }, 'Huỷ'), go));
  topic.focus();
  refresh(false);
}
function openPaste(prefill = '', note = '', warnings = []) {
  const ta = h('textarea', { rows: 14, value: prefill, placeholder: '# GitHub là gì?\nGitHub là nơi lập trình viên lưu và chia sẻ code…\n\n# Repository\nMỗi dự án nằm trong một repository…\n\n(mỗi đoạn cách nhau một dòng trống = 1 cảnh; dòng bắt đầu bằng # là tiêu đề của cảnh)' });
  const rep = h('input', { type: 'checkbox' });
  openModal(h('h3', {}, 'Dán kịch bản'), h('p', { class: 'hint', style: 'margin:0' }, 'Mỗi đoạn cách nhau một dòng trống thành 1 cảnh. Dòng bắt đầu bằng # là tiêu đề hiện trên màn hình, phần còn lại là lời đọc.'), note ? h('p', { style: 'margin:8px 0;color:var(--acc)' }, note) : '',
    warnings.length ? h('div', { class: 'warn hint', id: 'aiWarn', style: 'margin:0 0 8px;line-height:1.55' }, h('b', {}, '⚠ Nên xem lại trước khi tạo cảnh:'), ...warnings.map(w => h('div', {}, '• ' + w.msg))) : '', ta,
    h('label', { class: 'chk' }, rep, 'Thay thế toàn bộ các cảnh hiện có'),
    h('div', { style: 'text-align:right;display:flex;gap:8px;justify-content:flex-end' }, h('button', { onclick: closeModal }, 'Huỷ'), h('button', { class: 'pri', onclick: () => {
      const scenes = ta.value.split(/\n\s*\n/).map(b => b.trim()).filter(Boolean).map(b => {
        const lines = b.split('\n').map(l => l.trim()).filter(Boolean); let title = '';
        if (lines[0].startsWith('#')) title = lines.shift().replace(/^#+\s*/, '');
        return newScene({ title, narration: lines.join(' ') });
      });
      if (!scenes.length) return closeModal();
      closeModal(); addScenes(scenes, S.proj.scenes.length, rep.checked);
    } }, 'Tạo cảnh')));
  ta.focus();
}
