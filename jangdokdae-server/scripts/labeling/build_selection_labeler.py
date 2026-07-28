# -*- coding: utf-8 -*-
# ruff: noqa: E501  # HTML 템플릿 문자열 포함
"""선택 골드셋 라벨링 UI 빌더 — 후보 풀 스냅샷을 임베드한 단일 HTML 생성.

evaluation/learning/snapshots/selection-pool-*.json 전체를 읽어 라벨링 페이지를
만든다. 결과 HTML을 Claude Artifact 등으로 사용자에게 전달해 라벨을 수집한다.

사용(서버 디렉터리에서):
    uv run python scripts/labeling/build_selection_labeler.py
    → selection-labeler.html
"""
import json
from pathlib import Path

SNAPSHOT_DIR = Path("evaluation/learning/snapshots")
DATA = [
    {
        "date": snap["learning_date"],
        "candidates": [
            {
                "id": c["issue_id"],
                "title": c["title"],
                "hook": c["hook"],
                "scope": c["scope"],
                "sectors": c["sector_names"],
                "run_date": c["run_date"],
            }
            for c in snap["candidates"]
        ],
    }
    for snap in (
        json.loads(p.read_text())
        for p in sorted(SNAPSHOT_DIR.glob("selection-pool-*.json"))
    )
]

HTML = """<title>오늘의 세 가지 — 선택 골드셋 라벨링</title>
<style>
:root{
  --ink:#111214; --ground:#FFFFFF; --muted:#6E7076; --hair:#E4E4E7;
  --accent:#2E47FF; --accent-soft:rgba(46,71,255,.05); --accent-line:rgba(46,71,255,.35);
  --chip:#F4F4F6;
}
@media (prefers-color-scheme: dark){:root{
  --ink:#E8E8EA; --ground:#0E0F12; --muted:#8B8D93; --hair:#26272C;
  --accent:#5B72FF; --accent-soft:rgba(91,114,255,.09); --accent-line:rgba(91,114,255,.45);
  --chip:#1A1B20;
}}
:root[data-theme="dark"]{
  --ink:#E8E8EA; --ground:#0E0F12; --muted:#8B8D93; --hair:#26272C;
  --accent:#5B72FF; --accent-soft:rgba(91,114,255,.09); --accent-line:rgba(91,114,255,.45);
  --chip:#1A1B20;
}
:root[data-theme="light"]{
  --ink:#111214; --ground:#FFFFFF; --muted:#6E7076; --hair:#E4E4E7;
  --accent:#2E47FF; --accent-soft:rgba(46,71,255,.05); --accent-line:rgba(46,71,255,.35);
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
.top h1{font-size:15px; font-weight:700; margin:0; letter-spacing:-.01em}
.top .spacer{flex:1}
.progress{font-variant-numeric:tabular-nums; font-size:13px; color:var(--muted)}
.progress b{color:var(--accent); font-weight:700}
button.export{
  border:1px solid var(--ink); background:var(--ink); color:var(--ground);
  font:inherit; font-size:13px; font-weight:600; padding:7px 14px; border-radius:6px; cursor:pointer;
}
button.export:focus-visible,.rolebtn:focus-visible,.fold:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
.intro{padding:28px 0 8px; border-bottom:1px solid var(--hair)}
.intro p{margin:8px 0; font-size:14px; color:var(--muted); max-width:62ch}
.intro p b{color:var(--ink)}
.legend{display:flex; gap:18px; margin-top:14px; font-size:13px}
.legend span{display:flex; align-items:center; gap:6px; color:var(--muted)}
.dot{width:8px;height:8px;border-radius:50%}
.dot.r1{background:var(--accent)}
.dot.r2{background:transparent;border:2px solid var(--accent)}
.dot.r3{background:transparent;border:2px dashed var(--accent)}
section.day{padding-top:36px}
.dayhead{display:flex; align-items:baseline; gap:14px; border-bottom:2px solid var(--ink); padding-bottom:10px}
.daynum{font-size:34px; font-weight:800; letter-spacing:-.03em; font-variant-numeric:tabular-nums}
.daymeta{font-size:13px; color:var(--muted)}
.daydone{margin-left:auto; font-size:13px; font-weight:700; color:var(--accent); visibility:hidden}
section.day.done .daydone{visibility:visible}
.grouplabel{font-size:12px; font-weight:700; color:var(--muted); margin:18px 0 2px; letter-spacing:.02em}
.cand{display:flex; gap:14px; padding:13px 10px 13px 12px; border-bottom:1px solid var(--hair); margin:0 -10px 0 -12px}
.cand.selected{background:var(--accent-soft)}
.cand .body{flex:1; min-width:0}
.cand h3{margin:0 0 3px; font-size:14.5px; font-weight:600; letter-spacing:-.01em; text-wrap:balance}
.cand .hook{margin:0; font-size:13px; color:var(--muted); display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden}
.tags{display:flex; flex-wrap:wrap; gap:6px; margin-top:7px}
.tag{font-size:11.5px; padding:2px 8px; border-radius:99px; background:var(--chip); color:var(--muted)}
.tag.scope-market{border:1px solid var(--hair); background:transparent}
.roles{display:flex; flex-direction:column; gap:5px; justify-content:center}
.rolebtn{
  font:inherit; font-size:12px; font-weight:600; padding:3px 10px; border-radius:6px;
  border:1px solid var(--hair); background:transparent; color:var(--muted); cursor:pointer; white-space:nowrap;
}
.rolebtn:hover{border-color:var(--accent-line); color:var(--ink)}
.rolebtn.active{border-color:var(--accent); background:var(--accent); color:#fff}
.rolebtn.active.r2{background:transparent; color:var(--accent)}
.rolebtn.active.r3{background:transparent; color:var(--accent); border-style:dashed}
.fold{
  width:100%; text-align:left; font:inherit; font-size:13px; font-weight:600; color:var(--muted);
  background:none; border:none; border-bottom:1px solid var(--hair); padding:13px 0; cursor:pointer;
}
.fold::before{content:"▸ "; color:var(--accent)}
.fold.open::before{content:"▾ "}
.carry{display:none}
.carry.open{display:block}
.note{width:100%; margin-top:14px; font:inherit; font-size:13px; color:var(--ink);
  background:var(--chip); border:1px solid var(--hair); border-radius:8px; padding:9px 12px}
.note::placeholder{color:var(--muted)}
.toast{
  position:fixed; left:50%; bottom:28px; transform:translateX(-50%) translateY(80px);
  background:var(--ink); color:var(--ground); font-size:13px; font-weight:600;
  padding:10px 18px; border-radius:8px; transition:transform .25s; z-index:20;
}
.toast.show{transform:translateX(-50%) translateY(0)}
.overlay{
  position:fixed; inset:0; background:rgba(0,0,0,.45); z-index:30;
  display:none; align-items:center; justify-content:center; padding:20px;
}
.overlay.show{display:flex}
.panel{
  background:var(--ground); color:var(--ink); border:1px solid var(--hair);
  border-radius:12px; width:min(640px,100%); max-height:80vh;
  display:flex; flex-direction:column; padding:18px; gap:12px;
}
.panel h2{margin:0; font-size:15px; font-weight:700}
.panel p{margin:0; font-size:13px; color:var(--muted)}
.panel textarea{
  flex:1; min-height:260px; font:12px/1.5 ui-monospace,Menlo,monospace;
  color:var(--ink); background:var(--chip); border:1px solid var(--hair);
  border-radius:8px; padding:10px; resize:vertical; white-space:pre;
}
.panel .row{display:flex; gap:10px; justify-content:flex-end}
.panel .row button{
  font:inherit; font-size:13px; font-weight:600; padding:7px 14px;
  border-radius:6px; cursor:pointer; border:1px solid var(--hair);
  background:transparent; color:var(--ink);
}
.panel .row button.primary{background:var(--ink); color:var(--ground); border-color:var(--ink)}
@media (prefers-reduced-motion: reduce){.toast{transition:none}}
@media (max-width:560px){.cand{flex-direction:column; gap:8px}.roles{flex-direction:row}}
</style>
<div class="wrap">
<header class="top">
  <h1>오늘의 세 가지 · 라벨링</h1>
  <div class="spacer"></div>
  <div class="progress"><b id="doneCount">0</b>/12일 완료</div>
  <button class="export" id="exportBtn">결과 JSON 복사</button>
</header>
<div class="intro">
  <p><b>관심사 없는 주식 초보자</b>에게 그날 꼭 필요한 세 가지를 고르는 기준을 만드는 작업입니다.
  각 날짜에서 후보를 훑고 세 역할에 하나씩 배정해 주세요. 표시 순서는 무작위이며 알고리즘의 선택은 보이지 않습니다.</p>
  <p>진행 상태는 브라우저에 저장되므로 나눠서 작업해도 됩니다. 뒤 날짜일수록 앞에서 본 후보가 다시 나와 점점 빨라집니다.
  전부 하지 않아도 됩니다 — <b>5일 이상</b>이면 기준선 평가가 가능합니다.</p>
  <div class="legend">
    <span><i class="dot r1"></i>핵심 — 오늘 가장 먼저 이해할 이슈</span>
    <span><i class="dot r2"></i>맥락 — 시장 전체의 큰 흐름</span>
    <span><i class="dot r3"></i>발견 — 시야를 넓히는 다른 영역</span>
  </div>
</div>
<main id="days"></main>
</div>
<div class="toast" id="toast"></div>
<div class="overlay" id="overlay">
  <div class="panel">
    <h2>라벨 결과 JSON</h2>
    <p>아래 내용이 자동 선택되어 있습니다. <b>Cmd+C</b>(또는 Ctrl+C)로 복사해 Claude에게 붙여넣어 주세요.</p>
    <textarea id="exportText" readonly></textarea>
    <div class="row">
      <button type="button" id="copyAgain" class="primary">다시 복사 시도</button>
      <button type="button" id="closeOverlay">닫기</button>
    </div>
  </div>
</div>
<script>
const DATA = __DATA__;
const ROLES = [["focus","핵심","r1"],["context","맥락","r2"],["discovery","발견","r3"]];
const KEY = "jangdokdae-selection-labels-v1";
let state = {};
try { state = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { state = {}; }

function shuffleKey(id){ let x = (id * 2654435761) % 4294967296; x ^= x >>> 16; return x; }
function dayState(date){ if(!state[date]) state[date] = {selections:{}, note:""}; return state[date]; }
function save(){ localStorage.setItem(KEY, JSON.stringify(state)); }

const main = document.getElementById("days");
DATA.forEach(day => {
  const sec = document.createElement("section");
  sec.className = "day"; sec.dataset.date = day.date;
  const fresh = day.candidates.filter(c => c.run_date === day.date).sort((a,b)=>shuffleKey(a.id)-shuffleKey(b.id));
  const carry = day.candidates.filter(c => c.run_date !== day.date).sort((a,b)=>shuffleKey(a.id)-shuffleKey(b.id));
  const [y,m,d] = day.date.split("-");
  sec.innerHTML = `
    <div class="dayhead">
      <span class="daynum">${m}.${d}</span>
      <span class="daymeta">후보 ${day.candidates.length}개 · 당일 ${fresh.length} · 이월 ${carry.length}</span>
      <span class="daydone">3/3 ✓</span>
    </div>
    <div class="grouplabel">당일 후보</div>
    <div class="freshlist"></div>
    ${carry.length ? `<button class="fold" type="button">이월 후보 ${carry.length}개 보기</button><div class="carry"></div>` : ""}
    <input class="note" placeholder="이 날 선택 이유·메모 (선택)" value="">
  `;
  const renderCand = (c) => {
    const el = document.createElement("div");
    el.className = "cand"; el.dataset.id = c.id;
    const scopeCls = c.scope === "시장 전체" ? "tag scope-market" : "tag";
    el.innerHTML = `
      <div class="body">
        <h3>${c.title}</h3>
        <p class="hook">${c.hook || ""}</p>
        <div class="tags">
          <span class="${scopeCls}">${c.scope}</span>
          ${c.sectors.map(s=>`<span class="tag">${s}</span>`).join("")}
          ${c.run_date !== day.date ? `<span class="tag">${c.run_date.slice(5)}</span>` : ""}
        </div>
      </div>
      <div class="roles">
        ${ROLES.map(([k,label,cls])=>`<button class="rolebtn ${cls}" type="button" data-role="${k}">${label}</button>`).join("")}
      </div>`;
    el.querySelectorAll(".rolebtn").forEach(btn => {
      btn.addEventListener("click", () => {
        const ds = dayState(day.date), role = btn.dataset.role;
        if (ds.selections[role] === c.id) delete ds.selections[role];
        else ds.selections[role] = c.id;
        save(); paint(sec, day);
      });
    });
    return el;
  };
  const freshList = sec.querySelector(".freshlist");
  fresh.forEach(c => freshList.appendChild(renderCand(c)));
  const carryBox = sec.querySelector(".carry");
  if (carryBox) {
    carry.forEach(c => carryBox.appendChild(renderCand(c)));
    const fold = sec.querySelector(".fold");
    fold.addEventListener("click", () => {
      fold.classList.toggle("open"); carryBox.classList.toggle("open");
    });
  }
  const note = sec.querySelector(".note");
  note.value = dayState(day.date).note || "";
  note.addEventListener("input", () => { dayState(day.date).note = note.value; save(); });
  main.appendChild(sec);
  paint(sec, day);
});

function paint(sec, day){
  const ds = dayState(day.date);
  const byId = {};
  Object.entries(ds.selections).forEach(([role,id]) => { byId[id] = role; });
  sec.querySelectorAll(".cand").forEach(el => {
    const id = Number(el.dataset.id), role = byId[id];
    el.classList.toggle("selected", Boolean(role));
    el.querySelectorAll(".rolebtn").forEach(btn => {
      btn.classList.toggle("active", role === btn.dataset.role);
    });
  });
  const complete = Object.keys(ds.selections).length === 3;
  sec.classList.toggle("done", complete);
  const doneDays = DATA.filter(d => Object.keys(dayState(d.date).selections).length === 3).length;
  document.getElementById("doneCount").textContent = doneDays;
}

function buildExportText(){
  const days = DATA.map(d => {
    const ds = dayState(d.date);
    const selections = Object.entries(ds.selections).map(([role, issue_id]) => ({role, issue_id}));
    return {learning_date: d.date, selections, note: ds.note || ""};
  }).filter(d => d.selections.length > 0);
  return {count: days.length, text: JSON.stringify(
    {schema: "selection-labels-v1", labeled_at: new Date().toISOString(), days}, null, 1)};
}
function showExportPanel(text){
  const area = document.getElementById("exportText");
  area.value = text;
  document.getElementById("overlay").classList.add("show");
  area.focus(); area.select();
}
async function tryCopy(text){
  try { await navigator.clipboard.writeText(text); return true; }
  catch (e) { return false; }
}
document.getElementById("exportBtn").addEventListener("click", async () => {
  const {count, text} = buildExportText();
  if (await tryCopy(text)) toast(`${count}일치 라벨 복사됨 — Claude에게 붙여넣기`);
  showExportPanel(text);
});
document.getElementById("copyAgain").addEventListener("click", async () => {
  const area = document.getElementById("exportText");
  area.focus(); area.select();
  if (await tryCopy(area.value)) { toast("복사됨"); return; }
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
out = Path("selection-labeler.html")
out.write_text(html, encoding="utf-8")
print(out, out.stat().st_size)
