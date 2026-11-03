"""브루식 편집기 / 설정 화면 HTML (정적 문자열, 데이터는 JS가 API로 불러옴)."""
from __future__ import annotations

import html
import json

BASE_CSS = """
:root{--bg:#f3f4f7;--panel:#fff;--ink:#1c2230;--muted:#6b7385;--line:#e2e5eb;--acc:#5b5bf0;--acc-ink:#fff;--hl:#eef0ff;--warn:#d9822b;--bad:#d64545;--ok:#2f9e6a}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#121419;--panel:#1b1e25;--ink:#e7e9ef;--muted:#9aa1b2;--line:#2b303a;--hl:#262a45}}
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,"Hiragino Sans","Noto Sans JP","Malgun Gothic","Apple SD Gothic Neo",sans-serif}
button,.btn{font:inherit;font-size:13px;padding:6px 11px;border:1px solid var(--line);border-radius:8px;background:var(--panel);color:var(--ink);cursor:pointer;white-space:nowrap;text-decoration:none;display:inline-flex;align-items:center;gap:5px}
button:hover,.btn:hover{border-color:var(--acc)}button.primary{background:var(--acc);border-color:var(--acc);color:var(--acc-ink)}
button.ghost{border-color:transparent;background:transparent}button.danger{color:var(--bad)}
input,select,textarea{font:inherit;padding:7px 9px;border:1px solid var(--line);border-radius:8px;background:var(--panel);color:var(--ink);width:100%}
.muted{color:var(--muted);font-size:12px}
#toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:#222;color:#fff;padding:10px 16px;border-radius:10px;font-size:13px;display:none;z-index:50;max-width:80vw}
#joblog{position:fixed;right:16px;bottom:16px;width:min(520px,calc(100vw - 32px));max-height:40vh;overflow:auto;background:#0e1016;color:#cde5cd;font:12px/1.45 ui-monospace,monospace;padding:10px 12px;border-radius:10px;white-space:pre-wrap;display:none;z-index:40;box-shadow:0 8px 30px #0006}
#joblog .x{position:sticky;top:0;float:right;color:#fff;cursor:pointer}
"""

EDITOR_CSS = """
body{display:flex;flex-direction:column;overflow:hidden}
header{display:flex;align-items:center;gap:8px;padding:8px 14px;background:var(--panel);border-bottom:1px solid var(--line);flex-wrap:wrap}
header h1{font-size:15px;margin:0 8px 0 4px;max-width:40vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
header .sp{flex:1}
main{flex:1;display:grid;grid-template-columns:minmax(380px,46%) 1fr;min-height:0}
@media(max-width:900px){main{grid-template-columns:1fr;overflow:auto}body{overflow:auto}}
.left{padding:14px;display:flex;flex-direction:column;gap:10px;min-height:0}
.stage{position:relative;width:100%;aspect-ratio:16/9;background:#000;border-radius:10px;overflow:hidden;container-type:inline-size}
.stage.portrait{aspect-ratio:9/16;max-height:62vh;width:auto;margin:0 auto}
.stage video,.stage img.bg{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.stage .card{position:absolute;inset:0;display:grid;place-items:center;text-align:center;color:#cfd3dc;padding:24px;background:radial-gradient(circle at 30% 30%,#2b3150,#0f1118)}
.stage .card b{display:block;font-size:13px;color:#8f97b0;margin-bottom:6px;font-weight:500}
.stage .ch{position:absolute;bottom:0;height:46%;transition:opacity .2s,transform .2s;opacity:.6}
.stage .ch.on{opacity:1;transform:translateY(-2%)}
.stage .ch.pos-left{left:1.5%}.stage .ch.pos-right{right:1.5%}
.sub{position:absolute;left:20%;right:20%;bottom:4%;z-index:3;text-align:center;font-weight:700;font-size:3.3cqw;line-height:1.35;color:#fff;white-space:pre-line}
.sub span{white-space:pre;-webkit-box-decoration-break:clone;box-decoration-break:clone;border-radius:.15em}
.insp{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--panel)}
.insp .ihead{margin-bottom:6px}.insp .sec{font-weight:700;font-size:13px;margin:10px 0 6px}
.insp .g{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px 12px}
.insp label{display:flex;flex-direction:column;gap:3px;font-size:12px;color:var(--muted)}
.insp input[type=range]{padding:0}.insp input[type=color]{height:32px;padding:2px}
.insp label button.ghost{padding:0 4px;font-size:12px}
.insp .controls select{width:auto;max-width:220px}
.badge{display:inline-block;margin-left:6px;font-size:11px;color:var(--acc);border:1px solid var(--acc);border-radius:99px;padding:0 6px}
.stylep{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--panel);display:none}
.stylep.open{display:block}
.stylep .g{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px 12px;margin-bottom:8px}
.stylep label{display:flex;flex-direction:column;gap:3px;font-size:12px;color:var(--muted)}
.stylep label.ck{flex-direction:row;align-items:center;gap:6px;color:var(--ink)}
.stylep input[type=range]{padding:0}.stylep input[type=color]{height:32px;padding:2px}
.stylep input[type=checkbox]{width:auto}
.txt .brk{color:var(--acc);font-size:11px;user-select:none}
.controls{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.bar{flex:1;height:6px;background:var(--line);border-radius:6px;overflow:hidden;min-width:120px;cursor:pointer}
.bar i{display:block;height:100%;background:var(--acc);width:0}
.right{display:flex;flex-direction:column;min-height:0;border-left:1px solid var(--line);background:var(--panel)}
.listhead{padding:10px 14px;border-bottom:1px solid var(--line);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
#list{overflow:auto;flex:1;padding:6px 0 120px}
.chap{display:flex;align-items:center;gap:6px;padding:14px 14px 6px}
.chap input{font-weight:700;border-color:transparent;background:transparent;font-size:15px;padding:4px 6px}
.chap input:hover,.chap input:focus{border-color:var(--line)}
.chap .no{color:var(--acc);font-weight:700}
.scene{margin:6px 10px;border:1px solid var(--line);border-radius:10px;overflow:hidden}
.shead{display:flex;gap:8px;align-items:center;padding:7px;background:var(--bg);flex-wrap:wrap}
.thumb{width:88px;aspect-ratio:16/9;border-radius:6px;overflow:hidden;background:#000;flex:none;position:relative}
.thumb video,.thumb img{width:100%;height:100%;object-fit:cover}
.thumb .none{position:absolute;inset:0;display:grid;place-items:center;color:#aaa;font-size:11px;background:#262a35}
.shead input{flex:1;min-width:120px;padding:5px 8px;font-size:12px}
.shead label.btn input{display:none}
.line{display:grid;grid-template-columns:auto 1fr auto;gap:8px;align-items:start;padding:6px 10px;border-top:1px solid var(--line);cursor:pointer}
.line:hover{background:var(--hl)}
.line.cur{background:var(--hl);box-shadow:inset 3px 0 0 var(--acc)}
.spk{font-size:12px;font-weight:700;padding:2px 8px;border-radius:99px;border:1.5px solid currentColor;background:transparent;margin-top:2px}
.txt{outline:none;padding:3px 4px;border-radius:5px;min-height:1.5em;word-break:break-word;white-space:pre-wrap}
.txt:focus{background:var(--panel);box-shadow:0 0 0 2px var(--acc)}
.line .tools{display:flex;gap:2px;opacity:.5}.line:hover .tools{opacity:1}
.line .tools button{padding:2px 6px;font-size:12px}
.addline{margin:4px 10px 8px;font-size:12px;color:var(--muted)}
dialog{border:none;border-radius:14px;padding:0;width:min(980px,94vw);background:var(--panel);color:var(--ink);box-shadow:0 20px 60px #0008}
dialog::backdrop{background:#0008}
.dhead{display:flex;gap:8px;padding:12px;border-bottom:1px solid var(--line);align-items:center}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px;padding:12px;max-height:62vh;overflow:auto}
.item{border:1px solid var(--line);border-radius:8px;overflow:hidden;cursor:pointer;position:relative;background:#000}
.item:hover{outline:2px solid var(--acc)}
.item img,.item video{width:100%;aspect-ratio:16/9;object-fit:cover;display:block}
.item span{position:absolute;right:4px;bottom:4px;background:#000a;color:#fff;font-size:11px;padding:1px 5px;border-radius:4px}
.kbd{font-size:11px;color:var(--muted)}
"""

EDITOR_JS = r"""
const NAME = __NAME__;
const $ = s => document.querySelector(s);
const enc = encodeURIComponent;
let DOC = null, FLAT = [], cur = -1, playing = false, searchScene = null;
const audio = new Audio();
const nextAudio = new Audio();

function toast(msg, ms = 3500) { const t = $('#toast'); t.textContent = msg; t.style.display = 'block'; clearTimeout(t._h); t._h = setTimeout(() => t.style.display = 'none', ms); }
async function post(url, data) {
  const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
  let j = {}; try { j = await r.json(); } catch (e) {}
  if (!r.ok || j.ok === false) { toast(j.error || ('오류 ' + r.status)); throw new Error(j.error || r.status); }
  return j;
}
function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v; else if (k.startsWith('on')) e[k] = v; else if (k === 'text') e.textContent = v; else e.setAttribute(k, v);
  }
  for (const k of kids) if (k) e.append(k);
  return e;
}
const BRK = '⏎';
function toEdit(t) { return (t || '').split(BRK).join('\n'); }
function fromEdit(t) { return (t || '').replace(/\r/g, '').split('\n').map(x => x.trim()).filter(Boolean).join(BRK); }
// 자막 조각: Enter로 나눈 곳 + 너무 긴 곳은 자동으로 나눔(최대 2줄)
function pieces(text, size) {
  const mc = fitChars(size), lim = mc * 2, out = [];
  for (let part of text.split(BRK).map(x => x.trim()).filter(Boolean)) {
    while (part.length > lim) {
      const n = Math.ceil(part.length / lim), target = part.length / n; let cut = -1, best = 1e9;
      for (let i = 4; i <= lim && i < part.length - 3; i++) if ('、，,」』）'.includes(part[i - 1]) && Math.abs(i - target) < best) { best = Math.abs(i - target); cut = i; }
      if (cut < 0 || best > target * 0.4) cut = Math.min(lim, Math.round(target));
      out.push(part.slice(0, cut)); part = part.slice(cut);
    }
    if (part) out.push(part);
  }
  return out.map(p => wrap2(p, mc));
}
function wrap2(p, mc) {
  if (p.length <= mc) return p;
  const mid = p.length / 2; let cut = Math.ceil(mid), best = 1e9;
  for (let i = 1; i < p.length; i++) if ('、，,」』）'.includes(p[i - 1]) && i <= mc + 1 && p.length - i <= mc + 1 && Math.abs(i - mid) < best) { best = Math.abs(i - mid); cut = i; }
  return p.slice(0, cut) + '\n' + p.slice(cut);
}
function fitChars(size) {
  const st = DOC.subtitle || {}, W = DOC.width || 1920;
  const fit = Math.floor((W - 2 * (st.margin_lr ?? 80)) / ((size || st.size || 62) * 1.02));
  return Math.max(6, Math.min(st.max_chars || 24, fit));
}
function hexA(hex, a) { const h = (hex || '#000000').replace('#', ''); const n = parseInt(h, 16); return `rgba(${n >> 16 & 255},${n >> 8 & 255},${n & 255},${a})`; }
let curPieces = [], curPiece = -1, curSpk = '', curOpts = {};
function setSub(text, spk, opts) { curOpts = opts || {}; curPieces = text ? pieces(text, curOpts.size) : []; curSpk = spk; curPiece = -1; showPiece(0); }
function showPiece(i) {
  if (i === curPiece) return; curPiece = i;
  const st = DOC.subtitle || {}, W = DOC.width || 1920, sub = $('#sub');
  sub.innerHTML = ''; const t = curPieces[i]; if (!t) return;
  const span = el('span'); span.textContent = t; sub.append(span);
  const o = curOpts || {};
  span.style.color = o.color || (st.color_mode === 'fixed' ? st.color : colorOf(curSpk));
  if (o.size) span.style.fontSize = (o.size / W * 100) + 'cqw';
  if (o.bold !== undefined) span.style.fontWeight = o.bold ? '700' : '400';
  if (st.box) { span.style.background = hexA(st.box_color, (st.box_opacity ?? 60) / 100); span.style.padding = '.08em .35em'; span.style.textShadow = 'none'; }
  else {
    const r = (o.outline ?? st.outline ?? 5) / W * 100, sh = [];
    for (let k = 0; k < 16; k++) { const a = k / 16 * 2 * Math.PI; sh.push(`${(r * Math.cos(a)).toFixed(3)}cqw ${(r * Math.sin(a)).toFixed(3)}cqw 0 ${st.outline_color || '#000'}`); }
    if (st.shadow) sh.push(`${(r * .6).toFixed(3)}cqw ${(r * .6).toFixed(3)}cqw ${(r).toFixed(3)}cqw rgba(0,0,0,.6)`);
    span.style.textShadow = r > 0 ? sh.join(',') : 'none';
  }
}
function applySubStyle() {
  const st = DOC.subtitle || {}, W = DOC.width || 1920, H = DOC.height || 1080, sub = $('#sub');
  sub.style.fontFamily = `"${st.font}", "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Noto Sans JP", "Meiryo", sans-serif`;
  sub.style.fontSize = (st.size / W * 100) + 'cqw';
  sub.style.fontWeight = st.bold ? '700' : '400';
  sub.style.bottom = (st.margin_bottom / H * 100) + '%';
  sub.style.left = sub.style.right = (Math.min(st.margin_lr, W * 0.4) / W * 100) + '%';
  const keep = curPiece; if (curSpk !== undefined && FLAT[cur]) { const ln = FLAT[cur].sc.lines[FLAT[cur].li]; curOpts = ln.opts || {}; curPieces = pieces(ln.text, curOpts.size); }
  curPiece = -1; showPiece(Math.max(0, Math.min(keep, curPieces.length - 1)));
  const fn = $('#fitnote'); if (fn) { const f = fitChars(); fn.textContent = f < (st.max_chars || 24) ? `※ 이 크기·여백에서는 한 줄에 ${f}자까지 들어가서 ${f}자로 나눕니다` : ''; }
}
audio.ontimeupdate = () => {
  if (!curPieces.length || !audio.duration) return;
  const lens = curPieces.map(p => p.replace('\n', '').length), tot = lens.reduce((a, b) => a + b, 0) || 1;
  let acc = 0; const f = audio.currentTime / audio.duration * tot;
  for (let i = 0; i < lens.length; i++) { acc += lens[i]; if (f < acc) { showPiece(i); return; } }
  showPiece(lens.length - 1);
};

// ---------- 선택한 대사 패널 (목소리·자막을 이 줄만 바꾸기) ----------
let VOICES = null, inspTimer = null;
async function loadVoices() { try { const j = await (await fetch('/api/voices')).json(); VOICES = j.voices || []; if (!j.ok) VOICES.error = j.error; } catch (e) { VOICES = []; } }
function voiceName(id) { const v = (VOICES || []).find(v => v.id == id); return v ? `${v.name}（${v.style}）` : `ID ${id}`; }
function voiceSelect(value, withDefault, defLabel) {
  const sel = el('select');
  if (withDefault) sel.append(new Option(defLabel, ''));
  let last = '';
  for (const v of VOICES || []) {
    if (v.name !== last) { last = v.name; const og = el('optgroup', {label: v.name}); sel.append(og); }
    sel.lastChild.append(new Option(`${v.name}（${v.style}）`, v.id));
  }
  if (value !== undefined && value !== '' && ![...sel.options].some(o => o.value == value)) sel.append(new Option(`ID ${value}`, value));
  sel.value = value ?? '';
  return sel;
}
function inspSave(sc) { clearTimeout(inspTimer); inspTimer = setTimeout(() => saveScene(sc).then(() => { render(); select(cur, false); }), 450); }
function buildInspector() {
  const box = $('#insp'); if (!box || !FLAT[cur]) return;
  const {sc, li} = FLAT[cur], ln = sc.lines[li]; ln.opts = ln.opts || {}; const o = ln.opts;
  const st = DOC.subtitle || {}, vvDef = DOC.voicevox || {};
  box.innerHTML = '';
  const char = DOC.characters.find(c => c.name === ln.speaker);
  box.append(el('div', {class: 'ihead'}, el('b', {text: `선택한 대사 #${cur + 1}`}),
    el('span', {class: 'muted', text: ' 여기서 바꾼 목소리·자막은 이 대사에만 적용돼요'})));
  if (!VOICES) { box.append(el('p', {class: 'muted', text: '목소리 목록을 불러오는 중…'})); loadVoices().then(buildInspector); return; }

  // 🎙 목소리
  const vg = el('div', {class: 'g'});
  if (DOC.dialogue) {
    const spkSel = el('select'); for (const c of DOC.characters) spkSel.append(new Option(c.name, c.name)); spkSel.value = ln.speaker;
    spkSel.onchange = () => { ln.speaker = spkSel.value; inspSave(sc); };
    vg.append(el('label', {}, '화자', spkSel));
  }
  if (VOICES.error || !VOICES.length) vg.append(el('p', {class: 'muted', text: VOICES.error || 'VOICEVOX 목소리 목록이 없습니다'}));
  else {
    const def = char ? `${ln.speaker} 기본 — ${voiceName(char.speaker)}` : '기본 목소리';
    const vs = voiceSelect(o.v, true, def);
    vs.onchange = () => { if (vs.value === '') delete o.v; else o.v = +vs.value; inspSave(sc); };
    vg.append(el('label', {}, '이 대사 목소리', vs));
  }
  const slider = (label, key, min, max, step, defv, fmt = x => x) => {
    const val = o[key] ?? defv, out = el('span', {text: fmt(val) + (o[key] === undefined ? ' (기본)' : '')});
    const i = el('input', {type: 'range', min, max, step, value: val});
    i.oninput = () => { o[key] = +i.value; out.textContent = fmt(+i.value); };
    i.onchange = () => inspSave(sc);
    const reset = el('button', {class: 'ghost', text: '↺', title: '기본값', onclick: () => { delete o[key]; inspSave(sc); }});
    return el('label', {}, el('span', {}, label + ' ', out, reset), i);
  };
  vg.append(slider('속도', 'speed', 0.6, 2.0, 0.05, vvDef.speedScale ?? 1.0),
            slider('높이', 'pitch', -0.15, 0.15, 0.01, vvDef.pitchScale ?? 0),
            slider('억양', 'into', 0, 2, 0.05, vvDef.intonationScale ?? 1));
  box.append(el('div', {class: 'sec', text: '🎙 목소리'}), vg);
  const vrow = el('div', {class: 'controls'}, el('button', {class: 'primary', text: '▶ 이 대사 듣기', onclick: () => playOne(cur)}));
  if (char && VOICES.length) {
    const cs = voiceSelect(char.speaker, false);
    const apply = el('button', {text: '캐릭터 기본 목소리로 저장', onclick: async () => {
      await post('/api/char_voice', {name: char.name, speaker: +cs.value}); char.speaker = +cs.value; toast(`${char.name}의 기본 목소리를 바꿨어요 (모든 대사·영상에 적용)`); buildInspector(); }});
    vrow.append(el('span', {class: 'muted', text: `${char.name} 기본 목소리:`}), cs, apply);
  }
  box.append(vrow);

  // Aa 이 대사 자막
  const sg = el('div', {class: 'g'});
  const subSlider = (label, key, min, max, defv) => {
    const val = o[key] ?? defv, out = el('span', {text: val + (o[key] === undefined ? ' (기본)' : '')});
    const i = el('input', {type: 'range', min, max, step: 1, value: val});
    i.oninput = () => { o[key] = +i.value; out.textContent = i.value; setSub(ln.text, ln.speaker, o); };
    i.onchange = () => inspSave(sc);
    return el('label', {}, el('span', {}, label + ' ', out, el('button', {class: 'ghost', text: '↺', onclick: () => { delete o[key]; setSub(ln.text, ln.speaker, o); inspSave(sc); }})), i);
  };
  sg.append(subSlider('글자 크기', 'size', 28, 160, st.size || 62), subSlider('테두리', 'outline', 0, 16, st.outline ?? 5));
  const col = el('input', {type: 'color', value: o.color || (st.color_mode === 'fixed' ? st.color : (char ? char.color : '#ffffff'))});
  col.oninput = () => { o.color = col.value; setSub(ln.text, ln.speaker, o); };
  col.onchange = () => inspSave(sc);
  sg.append(el('label', {}, el('span', {}, '글자색 ', el('button', {class: 'ghost', text: '↺', onclick: () => { delete o.color; inspSave(sc); }})), col));
  const bold = el('select'); bold.append(new Option('기본', ''), new Option('굵게', '1'), new Option('보통', '0')); bold.value = o.bold === undefined ? '' : String(o.bold);
  bold.onchange = () => { if (bold.value === '') delete o.bold; else o.bold = +bold.value; setSub(ln.text, ln.speaker, o); inspSave(sc); };
  sg.append(el('label', {}, '굵기', bold));
  box.append(el('div', {class: 'sec', text: 'Aa 이 대사 자막 (강조용)'}), sg,
    el('div', {class: 'controls'},
      el('button', {text: '↺ 이 대사 설정 모두 지우기', onclick: () => { ln.opts = {}; inspSave(sc); }}),
      el('button', {text: 'Aa 전체 자막 스타일…', onclick: () => { if (!$('#stylep').classList.contains('open')) toggleStyle(); $('#stylep').scrollIntoView({behavior: 'smooth'}); }})));
}
async function playOne(fi) { onlyOne = true; await playFrom(fi); }
let onlyOne = false;

// ---------- 자막 스타일 패널 ----------
const FONTS = ['Hiragino Sans', 'Hiragino Maru Gothic ProN', 'Hiragino Mincho ProN', 'YuGothic', 'YuMincho', 'Osaka', 'Noto Sans JP', 'Meiryo', 'IPAGothic'];
function buildStylePanel() {
  const st = DOC.subtitle, p = $('#stylep'); p.innerHTML = '';
  const g = el('div', {class: 'g'});
  const fontSel = el('select'); for (const f of [...new Set([st.font, ...FONTS])]) fontSel.append(new Option(f, f)); fontSel.append(new Option('직접 입력…', '__custom'));
  fontSel.value = st.font;
  fontSel.onchange = () => { let v = fontSel.value; if (v === '__custom') { v = prompt('PC에 설치된 글꼴 이름', st.font) || st.font; if (![...fontSel.options].some(o => o.value === v)) fontSel.insertBefore(new Option(v, v), fontSel.lastChild); fontSel.value = v; } st.font = v; applySubStyle(); };
  g.append(el('label', {}, '글꼴', fontSel));
  const rng = (label, key, min, max, step = 1) => { const v = el('span', {text: st[key]}); const i = el('input', {type: 'range', min, max, step, value: st[key]});
    i.oninput = () => { st[key] = +i.value; v.textContent = i.value; applySubStyle(); }; return el('label', {}, el('span', {}, label + ' ', v), i); };
  const col = (label, key) => { const i = el('input', {type: 'color', value: st[key]}); i.oninput = () => { st[key] = i.value; applySubStyle(); }; return el('label', {}, label, i); };
  const ck = (label, key) => { const i = el('input', {type: 'checkbox'}); i.checked = !!st[key]; i.onchange = () => { st[key] = i.checked; applySubStyle(); buildStylePanel(); }; return el('label', {class: 'ck'}, i, label); };
  g.append(rng('크기', 'size', 28, 140), rng('한 줄 글자 수', 'max_chars', 8, 40), rng('아래 여백(위치)', 'margin_bottom', 0, Math.round((DOC.height || 1080) * 0.6), 5), rng('좌우 여백', 'margin_lr', 20, Math.round((DOC.width || 1920) * 0.35), 10));
  const mode = el('select'); mode.append(new Option('화자별 색', 'speaker'), new Option('한 가지 색', 'fixed')); mode.value = st.color_mode;
  mode.onchange = () => { st.color_mode = mode.value; applySubStyle(); buildStylePanel(); };
  g.append(el('label', {}, '글자색', mode));
  if (st.color_mode === 'fixed') g.append(col('글자색 선택', 'color'));
  p.append(g);
  const g2 = el('div', {class: 'g'});
  g2.append(ck('굵게', 'bold'), ck('배경 박스', 'box'));
  if (st.box) g2.append(col('박스 색', 'box_color'), rng('박스 불투명도(%)', 'box_opacity', 10, 100, 5));
  else g2.append(rng('테두리 두께', 'outline', 0, 16), col('테두리 색', 'outline_color'), ck('그림자', 'shadow'));
  p.append(g2);
  p.append(el('div', {class: 'controls'},
    el('button', {class: 'primary', text: '스타일 저장', onclick: async () => { const j = await post('/api/subtitle_style', st); DOC.subtitle = j.subtitle; toast('자막 스타일을 저장했습니다. 영상 내보내기에 적용됩니다'); }}),
    el('button', {text: '기본값으로', onclick: async () => { const j = await post('/api/subtitle_style', {reset: true}); DOC.subtitle = j.subtitle; buildStylePanel(); applySubStyle(); }}),
    el('span', {class: 'muted', text: '미리보기에 바로 반영 · 저장하면 모든 영상에 적용'})));
  p.append(el('div', {class: 'muted', id: 'fitnote', style: 'color:var(--warn);margin-top:6px'}));
  applySubStyle();
}
function toggleStyle() { const p = $('#stylep'); if (!p.classList.contains('open')) buildStylePanel(); p.classList.toggle('open'); }

function colorOf(spk) { const c = DOC.characters.find(c => c.name === spk); return c ? c.color : '#ffffff'; }
function voiceOpts(line) { const o = line.opts || {}, v = {}; for (const k of ['v', 'speed', 'pitch', 'into']) if (o[k] !== undefined) v[k] = o[k]; return v; }
function lineUrl(line) { return `/api/line_audio?name=${enc(NAME)}&speaker=${enc(line.speaker || '')}&text=${enc(line.text)}&opts=${enc(JSON.stringify(voiceOpts(line)))}`; }

async function load(keepCur = true) {
  const r = await fetch('/api/doc?name=' + enc(NAME));
  DOC = await r.json();
  $('#title').textContent = DOC.title;
  if (DOC.portrait) $('#stage').classList.add('portrait');
  buildChars();
  applySubStyle();
  render();
  if (keepCur && cur >= 0 && cur < FLAT.length) select(cur, false); else if (FLAT.length) select(0, false);
  $('#finalBtn').style.display = DOC.final ? '' : 'none';
}

function buildChars() {
  $('#stage').querySelectorAll('.ch').forEach(e => e.remove());
  for (const c of DOC.characters) if (c.image) $('#stage').insertBefore(el('img', {class: 'ch pos-' + c.position, src: c.image, 'data-n': c.name}), $('#sub'));
}

function render() {
  const list = $('#list'); list.innerHTML = ''; FLAT = [];
  DOC.chapters.forEach((ch, ci) => {
    list.append(el('div', {class: 'chap'}, el('span', {class: 'no', text: (ci + 1) + '.'}),
      el('input', {value: ch.heading, onchange: e => post('/api/heading', {project: NAME, section: ci, heading: e.target.value}).then(() => toast('챕터 이름 저장'))})));
    ch.scenes.forEach(sc => list.append(sceneBox(sc)));
  });
  $('#count').textContent = `${FLAT.length}줄 · 장면 ${DOC.chapters.reduce((a, c) => a + c.scenes.length, 0)}개`;
}

function thumbOf(sc) {
  const t = el('div', {class: 'thumb', title: '화면 소스'});
  if (sc.media && sc.media.type === 'video') { const v = el('video', {src: sc.media.url + '#t=0.5', muted: '', preload: 'metadata'}); v.muted = true; t.append(v); t.onmouseenter = () => v.play(); t.onmouseleave = () => v.pause(); }
  else if (sc.media) t.append(el('img', {src: sc.media.url}));
  else t.append(el('div', {class: 'none', text: '소스 없음'}));
  return t;
}

function sceneBox(sc) {
  const box = el('div', {class: 'scene'});
  const q = el('input', {value: sc.stock_query, placeholder: '화면 검색어 (영어)', title: '스톡 영상 검색어'});
  q.onchange = () => saveScene(sc, {stock_query: q.value});
  const file = el('input', {type: 'file', accept: 'video/*,image/*'});
  file.onchange = () => uploadMedia(sc, file);
  box.append(el('div', {class: 'shead'}, thumbOf(sc), q,
    el('button', {text: '🔍 영상 검색', onclick: () => openSearch(sc, q.value)}),
    el('button', {text: '↻ 자동', title: '다른 스톡 영상/이미지로 자동 교체', onclick: () => autoMedia(sc, !!sc.media)}),
    el('label', {class: 'btn', title: '내 파일 넣기'}, '📁 파일', file),
    el('button', {class: 'ghost', text: '＋장면', title: '아래에 장면 추가', onclick: () => post('/api/scene_add', {project: NAME, index: sc.index}).then(() => load())}),
    el('button', {class: 'ghost danger', text: '✕', title: '장면 삭제', onclick: () => confirm('이 장면을 삭제할까요?') && post('/api/scene_delete', {project: NAME, index: sc.index}).then(() => load(false))})));
  sc.lines.forEach((ln, li) => box.append(lineRow(sc, li)));
  box.append(el('button', {class: 'ghost addline', text: '＋ 대사 추가', onclick: () => addLine(sc, sc.lines.length - 1)}));
  return box;
}

function lineRow(sc, li) {
  const ln = sc.lines[li];
  const fi = FLAT.length; FLAT.push({sc, li});
  const spk = el('button', {class: 'spk', text: ln.speaker || '내레이션', title: '클릭: 화자 바꾸기'});
  spk.style.color = colorOf(ln.speaker);
  if (!DOC.dialogue) spk.style.display = 'none';
  spk.onclick = e => { e.stopPropagation(); const ns = DOC.characters.map(c => c.name); if (!ns.length) return;
    ln.speaker = ns[(ns.indexOf(ln.speaker) + 1) % ns.length]; spk.textContent = ln.speaker; spk.style.color = colorOf(ln.speaker); saveScene(sc); };
  const txt = el('div', {class: 'txt', contenteditable: 'plaintext-only', spellcheck: 'false'}); txt.textContent = toEdit(ln.text);
  if (txt.contentEditable !== 'plaintext-only') txt.contentEditable = 'true';
  txt.onfocus = () => select(fi, false);
  txt.onblur = () => { const v = fromEdit(txt.innerText); if (v !== ln.text) { ln.text = v; saveScene(sc); } if (cur === fi) setSub(ln.text, ln.speaker); };
  txt.oninput = () => { if (cur === fi) setSub(fromEdit(txt.innerText), ln.speaker); };
  txt.onkeydown = e => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && !e.isComposing) { e.preventDefault(); txt.blur(); addLine(sc, li); }
    else if (e.key === 'Enter' && !e.isComposing && txt.contentEditable === 'true') { e.preventDefault(); document.execCommand('insertLineBreak'); }
    else if (e.key === 'Backspace' && !txt.textContent && sc.lines.length > 1) { e.preventDefault(); sc.lines.splice(li, 1); saveScene(sc).then(() => { render(); focusLine(Math.max(0, fi - 1)); }); }
    else if (e.key === 'Escape') txt.blur();
  };
  const o = ln.opts || {}, badges = [];
  if (['v', 'speed', 'pitch', 'into'].some(k => o[k] !== undefined)) badges.push('🎙');
  if (['size', 'color', 'bold', 'outline'].some(k => o[k] !== undefined)) badges.push('Aa');
  const txtWrap = el('div', {}, txt, badges.length ? el('span', {class: 'badge', text: badges.join(' ') + ' 이 줄만 적용', title: '선택한 대사 패널에서 바꾼 설정'}) : null);
  const row = el('div', {class: 'line', 'data-f': fi}, spk, txtWrap,
    el('div', {class: 'tools'},
      el('button', {class: 'ghost', text: '▶', title: '여기서부터 재생', onclick: e => { e.stopPropagation(); playFrom(fi); }}),
      el('button', {class: 'ghost danger', text: '✕', title: '대사 삭제', onclick: e => { e.stopPropagation(); if (sc.lines.length < 2) return toast('장면의 마지막 대사는 장면 삭제(✕)로 지워 주세요'); sc.lines.splice(li, 1); saveScene(sc).then(render); }})));
  row.onclick = e => { if (e.target === row) select(fi); };
  return row;
}

function addLine(sc, afterLi) {
  const ns = DOC.characters.map(c => c.name);
  const prev = sc.lines[afterLi];
  const spk = ns.length ? ns[(ns.indexOf(prev ? prev.speaker : ns[0]) + 1) % ns.length] : '';
  sc.lines.splice(afterLi + 1, 0, {speaker: spk, text: ''});
  render();
  const fi = FLAT.findIndex(f => f.sc === sc && f.li === afterLi + 1);
  focusLine(fi);
}
function focusLine(fi) { const r = document.querySelector(`.line[data-f="${fi}"] .txt`); if (r) { r.focus(); r.scrollIntoView({block: 'nearest'}); } }

async function saveScene(sc, extra = {}) {
  if (extra.stock_query !== undefined) sc.stock_query = extra.stock_query;
  return post('/api/scene_lines', {project: NAME, index: sc.index, lines: sc.lines, stock_query: sc.stock_query});
}

// ---------- 플레이어 ----------
function showMedia(sc) {
  const stage = $('#stage');
  const key = sc.media ? sc.media.url : 'card:' + sc.index;
  if (stage.dataset.key === key) return;
  stage.dataset.key = key;
  stage.querySelectorAll('.bg,.card').forEach(e => e.remove());
  let node;
  if (sc.media && sc.media.type === 'video') { node = el('video', {class: 'bg', src: sc.media.url, loop: '', playsinline: ''}); node.muted = true; node.play().catch(() => {}); }
  else if (sc.media) node = el('img', {class: 'bg', src: sc.media.url});
  else node = el('div', {class: 'card'}, el('div', {}, el('b', {text: '화면 소스 미정 — 렌더링 때 자동 선택'}), document.createTextNode(sc.stock_query || sc.image_prompt || '')));
  stage.prepend(node);
}

function select(fi, scroll = true) {
  if (fi < 0 || fi >= FLAT.length) return;
  cur = fi;
  document.querySelectorAll('.line.cur').forEach(e => e.classList.remove('cur'));
  const row = document.querySelector(`.line[data-f="${fi}"]`);
  if (row) { row.classList.add('cur'); if (scroll) row.scrollIntoView({block: 'nearest', behavior: 'smooth'}); }
  const {sc, li} = FLAT[fi]; const ln = sc.lines[li];
  showMedia(sc);
  setSub(ln.text, ln.speaker, ln.opts);
  buildInspector();
  $('#stage').querySelectorAll('.ch').forEach(c => c.classList.toggle('on', c.dataset.n === ln.speaker));
  $('#pos').textContent = `${fi + 1} / ${FLAT.length}`;
  $('#bar i').style.width = (100 * (fi + 1) / FLAT.length) + '%';
}

async function playFrom(fi) {
  if (fi >= FLAT.length) { stop(); toast('끝까지 재생했습니다'); return; }
  select(fi); playing = true; $('#play').textContent = '⏸ 일시정지';
  const line = FLAT[fi].sc.lines[FLAT[fi].li];
  if (!line.text.trim()) return playFrom(fi + 1);
  $('#status').textContent = '음성 준비 중…';
  audio.src = lineUrl(line);
  try { await audio.play(); $('#status').textContent = ''; }
  catch (e) {
    if (!playing) return;
    const r = await fetch(lineUrl(line)); let msg = '음성을 만들 수 없습니다';
    try { msg = (await r.json()).error || msg; } catch (_) {}
    stop(); $('#status').textContent = ''; toast(msg, 7000); return;
  }
  // 다음 줄 미리 생성
  const nx = FLAT[fi + 1]; if (nx) { const l2 = nx.sc.lines[nx.li]; if (l2.text.trim()) nextAudio.src = lineUrl(l2); }
}
audio.onended = () => { if (onlyOne) { onlyOne = false; stop(); return; } if (playing) setTimeout(() => playing && playFrom(cur + 1), (DOC.gap || 0.2) * 1000); };
function stop() { playing = false; audio.pause(); $('#play').textContent = '▶ 재생'; }
function toggle() { onlyOne = false; playing ? stop() : playFrom(Math.max(0, cur)); }

// ---------- 소스 ----------
async function autoMedia(sc, replace) { toast('화면 소스를 찾는 중…'); await post('/api/auto_media', {project: NAME, index: sc.index, replace}); await load(); toast('교체했습니다'); }
async function uploadMedia(sc, input) {
  const fd = new FormData(); fd.append('project', NAME); fd.append('index', sc.index); fd.append('file', input.files[0]);
  toast('업로드 중…');
  const j = await (await fetch('/upload_media', {method: 'POST', body: fd})).json();
  if (!j.ok) return toast(j.error || '업로드 실패');
  await load(); toast('내 파일로 바꿨습니다');
}
function openSearch(sc, q) { searchScene = sc; $('#sq').value = q || sc.stock_query || ''; $('#dlg').showModal(); doSearch(); }
async function doSearch() {
  const g = $('#grid'); g.innerHTML = '<p class=muted style="padding:12px">검색 중…</p>';
  const j = await (await fetch(`/api/stock_search?q=${enc($('#sq').value)}&portrait=${DOC.portrait ? 1 : 0}&sources=${$('#ssrc').value}`)).json();
  g.innerHTML = '';
  if (j.missing_keys.length && !j.items.length && $('#ssrc').value.split(',').every(x => ['pexels', 'pixabay'].includes(x))) { g.append(el('p', {class: 'muted', style: 'padding:12px', text: '설정에서 Pexels 또는 Pixabay API 키를 입력하면 무료 스톡 영상을 검색할 수 있어요.'})); return; }
  if (!j.items.length) g.append(el('p', {class: 'muted', style: 'padding:12px', text: '결과가 없습니다. 영어로 짧게 검색해 보세요. ' + j.errors.join(' / ')}));
  for (const it of j.items) {
    const img = el('img', {src: it.thumb || '', loading: 'lazy'});
    const card = el('div', {class: 'item', title: `${it.source} · ${it.credit}`}, img, el('span', {text: `${it.source}${it.license ? ' · ' + it.license : ''}${it.duration ? ' · ' + it.duration + 's' : ''}`}));
    if (it.title) card.title = `${it.title}\n${it.credit} · ${it.license || ''}`;
    card.onmouseenter = () => { if (!card._v && it.preview) { card._v = el('video', {src: it.preview, autoplay: '', loop: ''}); card._v.muted = true; img.replaceWith(card._v); } };
    card.onclick = async e => { toast('다운로드 중…'); await post('/api/set_stock', {project: NAME, index: searchScene.index, item: it, mode: e.shiftKey ? 'add' : 'replace'}); $('#dlg').close(); await load(); toast(e.shiftKey ? '영상을 추가했습니다' : '영상을 바꿨습니다'); };
    g.append(card);
  }
}

// ---------- 작업 ----------
let poll = null;
function watch(id, onDone) {
  const box = $('#joblog'); box.style.display = 'block'; box.innerHTML = '<span class=x onclick="this.parentNode.style.display=\'none\'">✕</span>';
  const pre = el('div'); box.append(pre);
  clearInterval(poll);
  poll = setInterval(async () => {
    const j = await (await fetch('/job/' + id)).json();
    pre.textContent = j.log; box.scrollTop = box.scrollHeight;
    if (j.status !== 'running') { clearInterval(poll); if (j.status === 'done') { toast('완료!'); onDone && onDone(); } else toast('오류가 났습니다. 로그를 확인하세요', 6000); }
  }, 1200);
}
async function renderAll() { const j = await post('/api/build', {project: NAME}); watch(j.job, () => load()); }
function showFinal() { stop(); const s = $('#stage'); s.dataset.key = 'final'; s.querySelectorAll('.bg,.card').forEach(e => e.remove()); setSub('', ''); s.querySelectorAll('.ch').forEach(c => c.style.display = 'none');
  const v = el('video', {class: 'bg', src: DOC.final, controls: ''}); v.style.zIndex = 5; s.prepend(v); v.play(); }

document.addEventListener('keydown', e => {
  if (e.target.closest('input,textarea,[contenteditable]')) return;
  if (e.code === 'Space') { e.preventDefault(); toggle(); }
  else if (e.key === 'ArrowDown') { e.preventDefault(); select(cur + 1); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); select(cur - 1); }
});
$('#bar').onclick = e => { const r = e.currentTarget.getBoundingClientRect(); const fi = Math.floor((e.clientX - r.left) / r.width * FLAT.length); playing ? playFrom(fi) : select(fi); };
load();
"""


def editor_page(name: str) -> str:
    js = EDITOR_JS.replace("__NAME__", json.dumps(name))
    n = html.escape(name, quote=True)
    return f"""<!doctype html><html lang=ko><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>편집기 · ytgen</title><style>{BASE_CSS}{EDITOR_CSS}</style></head><body>
<header>
 <a class="btn ghost" href="/" title="프로젝트 목록">☰</a><h1 id=title>…</h1>
 <a class="btn" href="/p?name={n}">조사·주제·업로드</a>
 <span class=sp></span>
 <button id=finalBtn onclick="showFinal()" style="display:none">🎬 완성본 보기</button>
 <button class=primary onclick="renderAll()">⬇ 영상 내보내기</button>
 <button onclick="toggleStyle()">Aa 자막 스타일</button>
 <a class="btn" href="/settings">⚙ 설정</a>
</header>
<main>
 <section class=left>
  <div class=stage id=stage><div class=sub id=sub></div></div>
  <div class=controls>
   <button class=primary id=play onclick="toggle()">▶ 재생</button>
   <button onclick="select(cur-1)" title="이전 줄 (↑)">⏮</button><button onclick="select(cur+1)" title="다음 줄 (↓)">⏭</button>
   <div class=bar id=bar><i></i></div><span id=pos class=muted></span>
   <button onclick="toggleStyle()" title="자막 글꼴·크기·테두리·위치">Aa 자막 스타일</button>
  </div>
  <div class=insp id=insp></div>
  <div class=stylep id=stylep></div>
  <div class=muted id=status></div>
  <p class=kbd>스페이스: 재생/정지 · ↑↓: 줄 이동 · 대사에서 Enter: 자막 나누기(음성은 그대로) · ⌘+Enter: 아래에 새 대사 · 빈 대사에서 Backspace: 삭제 · 화자 이름 클릭: 화자 바꾸기 · 영상 검색에서 Shift+클릭: 장면에 영상 추가</p>
  <p class=kbd>미리보기는 렌더링 없이 바로 재생됩니다(자막 위치·크기는 실제 영상과 조금 다를 수 있어요). 최종 영상은 [영상 내보내기]로 만듭니다.</p>
 </section>
 <section class=right>
  <div class=listhead><b>대본</b><span class=muted id=count></span></div>
  <div id=list></div>
 </section>
</main>
<dialog id=dlg><div class=dhead><input id=sq placeholder="영어 검색어 (예: crow city)" onkeydown="if(event.key==='Enter')doSearch()">
<select id=ssrc style="width:auto" onchange="doSearch()">
 <option value="pexels,pixabay,wikimedia">전체 (스톡 + 위키미디어)</option>
 <option value="pexels,pixabay">고화질 스톡 (Pexels·Pixabay)</option>
 <option value="wikimedia">위키미디어 공용 (CC)</option>
 <option value="archive">인터넷 아카이브 (기록·역사 영상)</option>
 <option value="nasa">NASA (우주·과학)</option>
</select><button class=primary onclick="doSearch()">검색</button><button onclick="dlg.close()">닫기</button></div>
<p class=muted style="margin:8px 12px 0">클릭: 이 영상으로 교체 · Shift+클릭: 장면에 추가 · 모두 상업 이용 가능한 라이선스만 검색하며, CC 소재의 출처는 설명란에 자동으로 들어갑니다 · 긴 영상은 중간 20초만 잘라 옵니다</p><div class=grid id=grid></div></dialog>
<div id=toast></div><div id=joblog></div>
<script>{js}</script></body></html>"""


SETTINGS_JS = r"""
const $ = s => document.querySelector(s);
let S = null;
function toast(msg, ms = 3500) { const t = $('#toast'); t.textContent = msg; t.style.display = 'block'; clearTimeout(t._h); t._h = setTimeout(() => t.style.display = 'none', ms); }
async function post(url, data) { const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)}); const j = await r.json().catch(() => ({})); if (!r.ok || j.ok === false) { toast(j.error || '오류'); throw 0; } return j; }
function badge(ok, yes, no) { return `<span class="${ok ? 'good' : 'bad'}">${ok ? '● ' + yes : '● ' + no}</span>`; }
function esc(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c])); }

async function load() {
  S = await (await fetch('/api/settings')).json();
  const ff = S.ffmpeg, vv = S.voicevox;
  $('#ff').innerHTML = badge(ff.ok, '설치됨' + (ff.subtitles ? '' : ' (⚠ 자막 기능 없음)'), '없음') + `<div class=muted>${esc(ff.version || '')}</div>`;
  $('#ffbtn').style.display = ff.ok && ff.subtitles ? 'none' : '';
  $('#vv').innerHTML = badge(!!vv.version, '연결됨 v' + esc(vv.version), '연결 안 됨 — VOICEVOX 앱을 실행하세요');
  $('#vvpath').value = vv.path || '';
  for (const k of Object.keys(S.keys)) { const i = document.getElementById(k); i.value = ''; i.placeholder = S.keys[k] ? '저장됨 (바꾸려면 새로 입력)' : '미입력'; }
  $('#mode').value = S.tts.mode; if (![...$('#engine').options].some(o => o.value === S.tts.engine)) $('#engine').append(new Option(S.tts.engine, S.tts.engine)); $('#engine').value = S.tts.engine; $('#speed').value = S.tts.speed; $('#speedv').textContent = S.tts.speed;
  $('#font').value = S.subtitle.font; $('#burn').checked = S.subtitle.burn; $('#style').value = S.channel_style;
  $('#datadir').textContent = S.data_dir;
  const spOpts = id => vv.speakers.length ? vv.speakers.map(s => `<option value="${s.id}" ${s.id == id ? 'selected' : ''}>${esc(s.name)} (${esc(s.style)}) #${s.id}</option>`).join('') : `<option value="${id}">ID ${id} (VOICEVOX 연결 후 목록 표시)</option>`;
  $('#narr').innerHTML = spOpts(S.tts.voicevox_speaker);
  $('#chars').innerHTML = S.tts.characters.map((c, i) => `
   <div class=char>
    <div class=pic>${c.image ? `<img src="${c.image}?v=${Date.now()}">` : '<span class=muted>이미지 없음</span>'}</div>
    <div class=f>
     <label>이름 (대본의 「이름：」) <input data-k=name value="${esc(c.name)}"></label>
     <label>목소리 <span class=row style="flex-wrap:nowrap"><select data-k=speaker>${spOpts(c.speaker)}</select><button type=button onclick="listen(this)" title="미리 듣기" style="flex:none">▶ 듣기</button></span></label>
     <div class=row><label>자막 색 <input type=color data-k=color value="${c.color}"></label>
     <label>위치 <select data-k=position><option value=left ${c.position == 'left' ? 'selected' : ''}>왼쪽</option><option value=right ${c.position == 'right' ? 'selected' : ''}>오른쪽</option></select></label></div>
     <label>역할·말투 (대본 생성용) <input data-k=role value="${esc(c.role)}"></label>
     <label class=btn>스탠딩 이미지(PNG) 올리기<input type=file accept=".png,.webp" onchange="charImg(${i},this)" hidden></label>
    </div></div>`).join('');
}
const sample = new Audio();
async function listen(btn) {
  const sel = btn.parentNode.querySelector('select');
  if (!S.voicevox.version) return toast('VOICEVOX가 연결되어 있어야 들을 수 있어요');
  btn.disabled = true; btn.textContent = '…';
  sample.src = `/api/voice_sample?speaker=${sel.value}&speed=${$('#speed').value}&v=${Date.now()}`;
  try { await sample.play(); } catch (e) { toast('재생 실패: ' + e.message); }
  btn.disabled = false; btn.textContent = '▶ 듣기';
}
async function save() {
  const keys = {}; for (const k of Object.keys(S.keys)) keys[k] = document.getElementById(k).value;
  const chars = [...document.querySelectorAll('.char')].map(d => Object.fromEntries([...d.querySelectorAll('[data-k]')].map(i => [i.dataset.k, i.value])));
  await post('/api/settings', {keys, tts: {engine: $('#engine').value, mode: $('#mode').value, voicevox_speaker: $('#narr').value, speed: $('#speed').value, characters: chars},
    subtitle: {font: $('#font').value, burn: $('#burn').checked}, channel_style: $('#style').value, voicevox_path: $('#vvpath').value});
  toast('저장했습니다'); load();
}
async function charImg(i, input) { const fd = new FormData(); fd.append('index', i); fd.append('file', input.files[0]); const j = await (await fetch('/api/char_image', {method: 'POST', body: fd})).json(); if (!j.ok) return toast(j.error); toast('이미지를 저장했습니다'); load(); }
async function launchVV() { try { await post('/api/launch_voicevox', {}); toast('VOICEVOX를 실행했습니다. 잠시 후 연결을 확인합니다'); setTimeout(load, 6000); } catch (e) {} }
async function installFF() {
  const j = await post('/api/install_ffmpeg', {}); const box = $('#joblog'); box.style.display = 'block';
  const t = setInterval(async () => { const r = await (await fetch('/job/' + j.job)).json(); box.textContent = r.log; if (r.status !== 'running') { clearInterval(t); toast(r.status === 'done' ? 'ffmpeg 설치 완료' : '설치 실패 — 로그 확인'); load(); } }, 1000);
}
load();
"""

SETTINGS_CSS = """
main{max-width:980px;margin:0 auto;padding:18px 16px 80px}
h1{font-size:20px;margin:6px 0 14px}h2{font-size:15px;margin:0 0 10px}
section{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;margin:12px 0}
label{display:block;font-size:12px;color:var(--muted);margin:6px 0}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:end}.row>*{flex:1;min-width:160px}
.good{color:var(--ok);font-weight:700}.bad{color:var(--bad);font-weight:700}
.status{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:700px){.status{grid-template-columns:1fr}}
.status>div{border:1px solid var(--line);border-radius:10px;padding:12px}
.char{display:grid;grid-template-columns:120px 1fr;gap:12px;border:1px solid var(--line);border-radius:10px;padding:10px;margin:8px 0}
.pic{height:160px;display:grid;place-items:center;background:repeating-conic-gradient(#8881 0 25%,transparent 0 50%) 0/16px 16px;border-radius:8px;overflow:hidden}
.pic img{max-height:100%;max-width:100%}
input[type=color]{height:36px;padding:2px}
.save{position:sticky;bottom:12px;text-align:right}
a{color:var(--acc)}
"""


def settings_page() -> str:
    keys = [("YOUTUBE_API_KEY", "YouTube Data API (조사)", "https://console.cloud.google.com/apis/library/youtube.googleapis.com"),
            ("ANTHROPIC_API_KEY", "Anthropic (주제 제안·대본)", "https://console.anthropic.com/"),
            ("PEXELS_API_KEY", "Pexels (무료 스톡 영상)", "https://www.pexels.com/api/"),
            ("PIXABAY_API_KEY", "Pixabay (무료 스톡 영상)", "https://pixabay.com/api/docs/"),
            ("OPENAI_API_KEY", "OpenAI (선택: AI 이미지)", "https://platform.openai.com/api-keys")]
    key_html = "".join(f'<label>{label} · <a href="{url}" target=_blank>발급</a><input id={k} type=password autocomplete=off></label>'
                       for k, label, url in keys)
    return f"""<!doctype html><html lang=ko><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>설정 · ytgen</title><style>{BASE_CSS}{SETTINGS_CSS}</style></head><body><main>
<p><a href="/">← 프로젝트 목록</a></p><h1>설정</h1>
<section><h2>준비 상태</h2><div class=status>
 <div><b>ffmpeg (영상 처리)</b><div id=ff>확인 중…</div><button id=ffbtn class=primary onclick="installFF()" style="display:none;margin-top:8px">자동 설치</button></div>
 <div><b>VOICEVOX (음성)</b><div id=vv>확인 중…</div>
  <div class=row style="margin-top:8px"><button onclick="launchVV()">VOICEVOX 실행</button><a class=btn href="https://voicevox.hiroshiba.jp/" target=_blank>다운로드</a><button onclick="load()">다시 확인</button></div>
  <label>VOICEVOX 실행 파일 위치 (자동으로 못 찾을 때만) <input id=vvpath placeholder="예: C:\\Users\\me\\AppData\\Local\\Programs\\VOICEVOX\\VOICEVOX.exe"></label></div>
</div></section>
<section><h2>API 키</h2><p class=muted>입력한 키는 이 PC의 설정 폴더에만 저장됩니다.</p>{key_html}</section>
<section><h2>음성</h2><div class=row>
 <label>엔진 <select id=engine><option value=voicevox>VOICEVOX (무료·로컬)</option><option value=edge>Edge TTS (무료·인터넷)</option></select></label>
 <label>형식 <select id=mode><option value=dialogue>2인 대화 (掛け合い)</option><option value=narration>1인 내레이션</option></select></label>
 <label>1인 내레이션 목소리 <span class=row style="flex-wrap:nowrap"><select id=narr></select><button type=button onclick="listen(this)" style="flex:none">▶ 듣기</button></span></label>
 <label>말하기 속도 <span id=speedv></span><input id=speed type=range min=0.8 max=1.6 step=0.05 oninput="speedv.textContent=this.value"></label></div>
 <h2 style="margin-top:14px">캐릭터</h2><div id=chars></div>
 <p class=muted>VOICEVOX는 설명란에 「VOICEVOX:캐릭터명」 크레딧이 필요합니다 (자동 삽입). 스탠딩 이미지는 배포처 이용 규약을 확인하세요.</p></section>
<section><h2>자막·채널</h2><div class=row><label>자막 폰트 (PC에 설치된 일본어 폰트 이름) <input id=font placeholder="Meiryo / Hiragino Sans / Noto Sans CJK JP"></label>
 <label style="flex:0;min-width:200px"><input type=checkbox id=burn style="width:auto"> 영상에 자막 입히기</label></div>
 <label>채널 톤 (대본 생성용) <textarea id=style rows=3></textarea></label></section>
<p class=muted>설정 폴더: <span id=datadir></span></p>
<div class=save><button class=primary onclick="save()">저장</button></div>
</main><div id=toast></div><div id=joblog></div><script>{SETTINGS_JS}</script></body></html>"""
