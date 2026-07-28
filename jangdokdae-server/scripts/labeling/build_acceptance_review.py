# -*- coding: utf-8 -*-
# ruff: noqa: E501  # HTML 템플릿 문자열 포함
"""v3 선택 수용률 검토 UI 빌더."""
import json
import sys
from pathlib import Path

# 사용: uv run python scripts/labeling/build_acceptance_review.py <v3_picks.json>
# picks JSON은 evaluation.learning.run_selection의 replay_day_v2(model="v3")로
# 날짜별 선택을 뽑아 [{date, items:[{role, issue_id, title, hook, scope, sectors,
# judge_reason}]}] 형태로 만든다.
DATA = json.loads(Path(sys.argv[1]).read_text())

HTML = """<title>오늘의 세 가지 — v3 선택 수용률 검토</title>
<style>
:root{
  --ink:#111214; --ground:#FFFFFF; --muted:#6E7076; --hair:#E4E4E7;
  --accent:#2E47FF; --accent-soft:rgba(46,71,255,.05);
  --ok:#0B7A3E; --ok-soft:rgba(11,122,62,.08);
  --no:#B42318; --no-soft:rgba(180,35,24,.08);
  --chip:#F4F4F6;
}
@media (prefers-color-scheme: dark){:root{
  --ink:#E8E8EA; --ground:#0E0F12; --muted:#8B8D93; --hair:#26272C;
  --accent:#5B72FF; --accent-soft:rgba(91,114,255,.09);
  --ok:#3FBF77; --ok-soft:rgba(63,191,119,.12);
  --no:#F0716A; --no-soft:rgba(240,113,106,.12);
  --chip:#1A1B20;
}}
:root[data-theme="dark"]{
  --ink:#E8E8EA; --ground:#0E0F12; --muted:#8B8D93; --hair:#26272C;
  --accent:#5B72FF; --accent-soft:rgba(91,114,255,.09);
  --ok:#3FBF77; --ok-soft:rgba(63,191,119,.12);
  --no:#F0716A; --no-soft:rgba(240,113,106,.12);
  --chip:#1A1B20;
}
:root[data-theme="light"]{
  --ink:#111214; --ground:#FFFFFF; --muted:#6E7076; --hair:#E4E4E7;
  --accent:#2E47FF; --accent-soft:rgba(46,71,255,.05);
  --ok:#0B7A3E; --ok-soft:rgba(11,122,62,.08);
  --no:#B42318; --no-soft:rgba(180,35,24,.08);
  --chip:#F4F4F6;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:"Pretendard","Pretendard Variable",-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
  line-height:1.55; -webkit-font-smoothing:antialiased;
}
.wrap{max-width:720px; margin:0 auto; padding:0 20px 96px}
header.top{
  position:sticky; top:0; z-index:10; background:var(--ground);
  border-bottom:1px solid var(--hair); margin:0 -20px; padding:14px 20px;
  display:flex; align-items:center; gap:14px;
}
.top h1{font-size:15px; font-weight:700; margin:0}
.top .spacer{flex:1}
.progress{font-variant-numeric:tabular-nums; font-size:13px; color:var(--muted)}
.progress b{color:var(--accent); font-weight:700}
button.export{
  border:1px solid var(--ink); background:var(--ink); color:var(--ground);
  font:inherit; font-size:13px; font-weight:600; padding:7px 14px; border-radius:6px; cursor:pointer;
}
button:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
.intro{padding:24px 0 8px; border-bottom:1px solid var(--hair)}
.intro p{margin:8px 0; font-size:14px; color:var(--muted); max-width:62ch}
.intro p b{color:var(--ink)}
section.day{padding-top:32px}
.dayhead{display:flex; align-items:baseline; gap:14px; border-bottom:2px solid var(--ink); padding-bottom:8px}
.daynum{font-size:28px; font-weight:800; letter-spacing:-.03em; font-variant-numeric:tabular-nums}
.item{padding:14px 0; border-bottom:1px solid var(--hair); display:flex; gap:14px}
.item .body{flex:1; min-width:0}
.rolechip{
  display:inline-block; font-size:11px; font-weight:700; color:var(--accent);
  border:1px solid var(--accent); border-radius:99px; padding:1px 9px; margin-bottom:6px;
}
.item h3{margin:0 0 3px; font-size:14.5px; font-weight:600; text-wrap:balance}
.item .hook{margin:0; font-size:13px; color:var(--muted)}
.item .why{margin:6px 0 0; font-size:12px; color:var(--muted)}
.item .why b{color:var(--ink); font-weight:600}
.tags{display:flex; flex-wrap:wrap; gap:6px; margin-top:7px}
.tag{font-size:11.5px; padding:2px 8px; border-radius:99px; background:var(--chip); color:var(--muted)}
.verdict{display:flex; flex-direction:column; gap:6px; justify-content:center}
.vbtn{
  font:inherit; font-size:12.5px; font-weight:600; padding:5px 12px; border-radius:6px;
  border:1px solid var(--hair); background:transparent; color:var(--muted); cursor:pointer; white-space:nowrap;
}
.vbtn.ok.active{border-color:var(--ok); background:var(--ok-soft); color:var(--ok)}
.vbtn.no.active{border-color:var(--no); background:var(--no-soft); color:var(--no)}
.item.v-ok{background:var(--ok-soft); margin:0 -10px; padding-left:10px; padding-right:10px}
.item.v-no{background:var(--no-soft); margin:0 -10px; padding-left:10px; padding-right:10px}
.note{width:100%; margin-top:12px; font:inherit; font-size:13px; color:var(--ink);
  background:var(--chip); border:1px solid var(--hair); border-radius:8px; padding:8px 12px}
.note::placeholder{color:var(--muted)}
.toast{
  position:fixed; left:50%; bottom:28px; transform:translateX(-50%) translateY(80px);
  background:var(--ink); color:var(--ground); font-size:13px; font-weight:600;
  padding:10px 18px; border-radius:8px; transition:transform .25s; z-index:20;
}
.toast.show{transform:translateX(-50%) translateY(0)}
@media (prefers-reduced-motion: reduce){.toast{transition:none}}
.overlay{position:fixed; inset:0; background:rgba(0,0,0,.45); z-index:30;
  display:none; align-items:center; justify-content:center; padding:20px}
.overlay.show{display:flex}
.panel{background:var(--ground); color:var(--ink); border:1px solid var(--hair);
  border-radius:12px; width:min(640px,100%); max-height:80vh;
  display:flex; flex-direction:column; padding:18px; gap:12px}
.panel h2{margin:0; font-size:15px; font-weight:700}
.panel p{margin:0; font-size:13px; color:var(--muted)}
.panel textarea{flex:1; min-height:240px; font:12px/1.5 ui-monospace,Menlo,monospace;
  color:var(--ink); background:var(--chip); border:1px solid var(--hair);
  border-radius:8px; padding:10px; resize:vertical; white-space:pre}
.panel .row{display:flex; gap:10px; justify-content:flex-end}
.panel .row button{font:inherit; font-size:13px; font-weight:600; padding:7px 14px;
  border-radius:6px; cursor:pointer; border:1px solid var(--hair); background:transparent; color:var(--ink)}
.panel .row button.primary{background:var(--ink); color:var(--ground); border-color:var(--ink)}
@media (max-width:560px){.item{flex-direction:column; gap:8px}.verdict{flex-direction:row}}
</style>
<div class="wrap">
<header class="top">
  <h1>v3 선택 수용률 검토</h1>
  <div class="spacer"></div>
  <div class="progress"><b id="doneCount">0</b>/33 판정</div>
  <button class="export" id="exportBtn">결과 JSON 내보내기</button>
</header>
<div class="intro">
  <p>점수 모델 v3가 11일치 각 날짜에 고른 세 가지입니다. 정답과 같을 필요는 없고,
  <b>"그날 서비스에 나갔어도 괜찮았는가"</b>만 판단해 주세요. 항목마다 허용/불허를 누르고,
  불허라면 이유를 짧게 남겨주시면 다음 보정에 그대로 쓰입니다.</p>
</div>
<main id="days"></main>
</div>
<div class="toast" id="toast"></div>
<div class="overlay" id="overlay">
  <div class="panel">
    <h2>검토 결과 JSON</h2>
    <p>아래 내용이 자동 선택되어 있습니다. Cmd+C(또는 Ctrl+C)로 복사해 Claude에게 붙여넣어 주세요.</p>
    <textarea id="exportText" readonly></textarea>
    <div class="row">
      <button type="button" id="copyAgain" class="primary">다시 복사 시도</button>
      <button type="button" id="closeOverlay">닫기</button>
    </div>
  </div>
</div>
<script>
const DATA = __DATA__;
const ROLE_LABEL = {focus:"핵심", context:"맥락", discovery:"발견"};
const KEY = "jangdokdae-v3-acceptance-v1";
let state = {};
try { state = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { state = {}; }
function itemState(date, id){
  const k = date + ":" + id;
  if (!state[k]) state[k] = {verdict: null, note: ""};
  return state[k];
}
function save(){ localStorage.setItem(KEY, JSON.stringify(state)); }

const main = document.getElementById("days");
DATA.forEach(day => {
  const sec = document.createElement("section");
  sec.className = "day";
  const [y,m,d] = day.date.split("-");
  sec.innerHTML = `<div class="dayhead"><span class="daynum">${m}.${d}</span></div>`;
  day.items.forEach(item => {
    const el = document.createElement("div");
    el.className = "item";
    el.innerHTML = `
      <div class="body">
        <span class="rolechip">${ROLE_LABEL[item.role]}</span>
        <h3>${item.title}</h3>
        <p class="hook">${item.hook || ""}</p>
        <p class="why"><b>선정 근거(LLM)</b> — ${item.judge_reason || "-"}</p>
        <div class="tags">
          <span class="tag">${item.scope}</span>
          ${item.sectors.map(s=>`<span class="tag">${s}</span>`).join("")}
        </div>
        <input class="note" placeholder="불허 이유 (선택)" style="display:none">
      </div>
      <div class="verdict">
        <button class="vbtn ok" type="button">허용</button>
        <button class="vbtn no" type="button">불허</button>
      </div>`;
    const st = itemState(day.date, item.issue_id);
    const okBtn = el.querySelector(".vbtn.ok"), noBtn = el.querySelector(".vbtn.no");
    const note = el.querySelector(".note");
    note.value = st.note || "";
    note.addEventListener("input", () => { st.note = note.value; save(); });
    function paint(){
      okBtn.classList.toggle("active", st.verdict === "ok");
      noBtn.classList.toggle("active", st.verdict === "no");
      el.classList.toggle("v-ok", st.verdict === "ok");
      el.classList.toggle("v-no", st.verdict === "no");
      note.style.display = st.verdict === "no" ? "" : "none";
      const done = Object.values(state).filter(s => s.verdict).length;
      document.getElementById("doneCount").textContent = done;
    }
    okBtn.addEventListener("click", () => { st.verdict = st.verdict === "ok" ? null : "ok"; save(); paint(); });
    noBtn.addEventListener("click", () => { st.verdict = st.verdict === "no" ? null : "no"; save(); paint(); });
    paint();
    sec.appendChild(el);
  });
  main.appendChild(sec);
});

function buildExport(){
  const days = DATA.map(day => ({
    learning_date: day.date,
    verdicts: day.items.map(item => {
      const st = itemState(day.date, item.issue_id);
      return {role: item.role, issue_id: item.issue_id, verdict: st.verdict, note: st.note || ""};
    }),
  }));
  return JSON.stringify({schema: "selection-acceptance-v1",
    reviewed_at: new Date().toISOString(), days}, null, 1);
}
document.getElementById("exportBtn").addEventListener("click", async () => {
  const text = buildExport();
  try { await navigator.clipboard.writeText(text); toast("복사됨 — Claude에게 붙여넣기"); } catch (e) {}
  const area = document.getElementById("exportText");
  area.value = text;
  document.getElementById("overlay").classList.add("show");
  area.focus(); area.select();
});
document.getElementById("copyAgain").addEventListener("click", async () => {
  const area = document.getElementById("exportText");
  area.focus(); area.select();
  try { await navigator.clipboard.writeText(area.value); toast("복사됨"); return; } catch (e) {}
  const ok = document.execCommand && document.execCommand("copy");
  toast(ok ? "복사됨" : "자동 복사가 막혀 있어요 — 선택된 상태에서 Cmd+C를 눌러주세요");
});
document.getElementById("closeOverlay").addEventListener("click", () => {
  document.getElementById("overlay").classList.remove("show");
});
function toast(msg){
  const t = document.getElementById("toast");
  t.textContent = msg; t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2600);
}
</script>
"""

html = HTML.replace("__DATA__", json.dumps(DATA, ensure_ascii=False))
out = Path("v3-acceptance-review.html")
out.write_text(html, encoding="utf-8")
print(out, out.stat().st_size)
