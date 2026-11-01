/* Tiện ích dùng chung: chọn phần tử $, dựng DOM h(), gọi API, báo lỗi, toast, định dạng, trạng thái S; cửa sổ (modal).
   Các file trong static/js/ là script thường (không phải ES module), nạp lần lượt theo thứ tự trong index.html và dùng chung
   một phạm vi toàn cục (các test Playwright cũng gọi thẳng S, H, edit()…). Hàm chỉ được GỌI sau khi mọi file đã nạp xong. */
const $ = (s, r = document) => r.querySelector(s);
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const c of kids.flat(9)) { if (c == null || c === false) continue; e.append(c.nodeType ? c : document.createTextNode(String(c))); }
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'style') e.style.cssText = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'value' || k === 'checked' || k === 'disabled' || k === 'hidden') e[k] = v;
    else e.setAttribute(k, v === true ? '' : v);
  }
  return e;
}
function apiError(j, status) {  // lỗi từ server: {error, hint, code, ref} (tiếng Việt, đã được errors.py giải thích)
  const e = new Error(j.error || ('Lỗi ' + status)); e.hint = j.hint || ''; e.ref = j.ref || ''; e.code = j.code || ''; return e;
}
async function api(path, method = 'GET', body) {
  let r;
  try { r = await fetch(path, { method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined }); }
  catch (e) { const x = new Error('Không nối được tới tool (có thể đã bị tắt).'); x.hint = 'Mở lại tool rồi tải lại trang (F5). Dự án đã lưu vẫn còn nguyên.'; x.code = 'offline'; throw x; }
  let j = {}; try { j = await r.json(); } catch (e) {}
  if (!r.ok) throw apiError(j, r.status);
  return j;
}
let reported = 0;  // lỗi JavaScript trong trang cũng được ghi vào nhật ký của tool (tối đa 20 lần mỗi lần mở trang)
function reportError(msg, src, stack) {
  if (reported++ >= 20) return;
  try { fetch('/api/client-log', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ msg: String(msg), src: String(src || ''), stack: String(stack || '') }) }).catch(() => {}); } catch (e) {}
}
window.__ffvReport = reportError;
window.addEventListener('error', ev => reportError(ev.message, `${ev.filename}:${ev.lineno}`, ev.error && ev.error.stack));
window.addEventListener('unhandledrejection', ev => reportError('Promise bị từ chối: ' + ((ev.reason && ev.reason.message) || ev.reason), '', ev.reason && ev.reason.stack));
let toastT;
function toast(m, err) {  // m: chuỗi, hoặc Error/{error|message, hint, ref, code} từ server (kèm cách xử lý)
  const o = (m && typeof m === 'object') ? m : { message: m };
  const t = $('#toast'); t.textContent = (o.message || o.error || '') + (o.hint ? '\n' + o.hint : '') + (o.code === 'unexpected' && o.ref ? `\n(mã lỗi ${o.ref} – xem nhật ký)` : '');
  t.className = err ? 'err' : ''; t.style.display = 'block'; clearTimeout(toastT); toastT = setTimeout(() => t.style.display = 'none', o.ms || (err ? (o.hint ? 12000 : 6000) : 2600));
}
const fmt = s => { s = Math.max(0, s || 0); return Math.floor(s / 60) + ':' + String(Math.floor(s % 60)).padStart(2, '0'); };
function frameSize(a, s) { const [x, y] = a.split(':').map(Number); return x >= y ? [Math.round(s * x / y / 2) * 2, s] : [s, Math.round(s * y / x / 2) * 2]; }
const hex = c => '#' + c.map(v => Math.max(0, Math.min(255, v | 0)).toString(16).padStart(2, '0')).join('');
const rgb = x => [1, 3, 5].map(i => parseInt(x.slice(i, i + 2), 16));
const rid = () => 's' + Math.random().toString(36).slice(2, 8);
const newScene = (o = {}) => Object.assign({ id: rid(), title: '', subtitle: '', narration: '', voice: true, caption: true, duration: 4, extra: 0, transition: 'fade', images: [], audio: null }, o);

const S = { pid: null, proj: null, tl: { total: 0, scenes: [] }, sel: 0, t: 0, themes: {}, voices: [], safe: null, showSafe: false, tts: [], dirty: false, saving: false, again: false, savePromise: null, timer: null, issues: [] };
const cur = () => S.proj && S.proj.scenes[S.sel];
// Giọng đọc: S.tts = tình trạng các nhà cung cấp từ /api/tts/status (phần tử đầu là giọng chính, còn lại là giọng dự phòng).
const ttsLabel = n => ((S.tts.find(e => e.name === n) || {}).label) || n;
const isFallbackVoice = a => !!(a && a.engine && a.engine !== 'fake' && S.tts.length && a.engine !== S.tts[0].name);

/* ------------------------------------------------------------ cửa sổ (modal) */
function openModal(...kids) { const m = $('#modal'); m.replaceChildren(...kids.flat(9)); $('#modalBg').classList.add('on'); }
function closeModal() { $('#modalBg').classList.remove('on'); commit(); }
