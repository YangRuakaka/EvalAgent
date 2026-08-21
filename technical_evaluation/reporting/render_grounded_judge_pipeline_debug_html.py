from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
TECH_EVAL_DIR = SCRIPT_DIR.parent
DEFAULT_RESULTS_DIR = (
    TECH_EVAL_DIR
    / "results"
    / "grounded_judge_webharbor_v13_v14_tentative_15"
)


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EvalAgent · Judge Pipeline Debugger</title>
<style>
:root{
  --ink:#172033;--muted:#64748b;--line:#d9e0ea;--soft:#f5f7fa;
  --panel:#fff;--nav:#111827;--blue:#2563eb;--violet:#7c3aed;
  --green:#059669;--green-bg:#d1fae5;--red:#dc2626;--red-bg:#fee2e2;
  --amber:#b45309;--amber-bg:#fef3c7;--cyan:#0e7490;--cyan-bg:#cffafe;
}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{font:13px/1.45 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ink);background:#edf1f6;overflow:hidden}
button,select,input{font:inherit}
.app{height:100vh;display:flex;flex-direction:column}
.topbar{height:58px;background:var(--nav);color:#fff;display:flex;align-items:center;gap:16px;padding:0 18px}
.brand{font-weight:800;font-size:16px}.brand span{color:#93c5fd}
.title{color:#cbd5e1;border-left:1px solid #ffffff2b;padding-left:16px}
.back-link{color:#bfdbfe;text-decoration:none;border:1px solid #ffffff30;border-radius:4px;padding:5px 9px;font-size:11px;font-weight:700}
.back-link:hover{background:#ffffff14;color:#fff}
.picker{display:flex;align-items:center;gap:8px;margin-left:auto}
.picker label{font-size:11px;color:#94a3b8;text-transform:uppercase;font-weight:700;letter-spacing:.06em}
.picker select{min-width:260px;max-width:38vw;background:#1f2937;color:#fff;border:1px solid #ffffff30;border-radius:5px;padding:7px 28px 7px 9px}
.shell{display:grid;grid-template-columns:270px minmax(0,1fr);flex:1;min-height:0}
.stages{background:#fff;border-right:1px solid var(--line);display:flex;flex-direction:column;min-height:0}
.stages-head{padding:14px;border-bottom:1px solid var(--line)}
.stages-head b{display:block}.stages-head span{font-size:11px;color:var(--muted)}
.stage-list{overflow:auto;padding:8px}
.stage-btn{width:100%;border:1px solid transparent;background:transparent;border-radius:6px;padding:9px;text-align:left;cursor:pointer;margin-bottom:4px;color:var(--ink)}
.stage-btn:hover{background:var(--soft);border-color:var(--line)}
.stage-btn.active{background:#eff6ff;border-color:#93c5fd;color:#1e40af}
.stage-line{display:flex;align-items:center;gap:7px}
.stage-seq{width:21px;height:21px;border-radius:50%;display:grid;place-items:center;background:#e2e8f0;font-size:10px;font-weight:800}
.stage-btn.active .stage-seq{background:var(--blue);color:#fff}
.stage-name{font-weight:700;min-width:0;flex:1}
.stage-count{font-size:10px;padding:2px 6px;border-radius:999px;background:#e2e8f0;color:#475569}
.stage-key{margin-top:4px;font-size:10px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.main{display:flex;flex-direction:column;min-width:0;min-height:0;padding:10px;gap:9px}
.case-head{background:#fff;border:1px solid var(--line);padding:10px 12px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px}
.case-id{font-weight:800;font-size:15px}.criterion{color:var(--violet);font-weight:700;margin-left:7px}
.task{color:var(--muted);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.head-metrics{display:flex;align-items:center;gap:7px}
.metric{padding:4px 8px;border:1px solid var(--line);border-radius:999px;font-size:11px;color:#475569;background:var(--soft)}
.verdict{font-weight:800}.verdict.pass{color:#065f46;background:var(--green-bg);border-color:#6ee7b7}.verdict.fail{color:#7f1d1d;background:var(--red-bg);border-color:#fca5a5}
.stage-summary{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center;background:#fff;border:1px solid var(--line);padding:9px 12px}
.stage-summary h2{font-size:14px;margin:0}.stage-summary p{margin:2px 0 0;color:var(--muted);font-size:11px}
.summary-counts{display:flex;gap:7px}.summary-count{font-size:11px;padding:3px 7px;border-radius:4px;background:var(--soft);border:1px solid var(--line)}
.workspace{display:grid;grid-template-columns:minmax(420px,1.3fr) minmax(390px,1fr);gap:9px;flex:1;min-height:0}
.panel{background:#fff;border:1px solid var(--line);display:flex;flex-direction:column;min-width:0;min-height:0}
.panel-head{height:43px;display:flex;align-items:center;padding:0 11px;border-bottom:1px solid var(--line)}
.panel-head h3{margin:0;font-size:13px}.panel-note{margin-left:auto;color:var(--muted);font-size:10px}
.trajectory{overflow:auto;padding:9px}
.step{border:1px solid var(--line);border-radius:6px;margin-bottom:8px;background:#fff;scroll-margin-top:8px}
.step[open]{border-color:#93c5fd}
.step summary{cursor:pointer;padding:8px 10px;display:flex;align-items:center;gap:8px;list-style:none}
.step summary::-webkit-details-marker{display:none}
.step-num{font-weight:800}.step-hit{font-size:10px;padding:2px 6px;border-radius:999px;background:var(--cyan-bg);color:#155e75}.step-empty{font-size:10px;color:var(--muted)}
.fields{padding:0 9px 9px;display:grid;grid-template-columns:1fr 1fr;gap:7px}
.field{min-width:0}.field.wide{grid-column:1/-1}
.field-label{font-size:10px;color:var(--muted);font-weight:800;text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px}
.field-value{border:1px solid #e5e9f0;background:#fafbfc;border-radius:4px;padding:7px;white-space:pre-wrap;word-break:break-word;max-height:220px;overflow:auto;font-size:11px;line-height:1.5}
.field-value.hit{border-color:#60a5fa;box-shadow:inset 3px 0 0 #60a5fa}
mark.ev{padding:1px 2px;border-radius:2px;background:var(--amber-bg);outline:1px solid #f59e0b;color:inherit;box-decoration-break:clone;-webkit-box-decoration-break:clone}
mark.ev.support{background:var(--green-bg);outline-color:#34d399}
mark.ev.oppose{background:var(--red-bg);outline-color:#f87171}
.debug-tabs{display:flex;gap:3px;border-bottom:1px solid var(--line);padding:7px 8px 0}
.tab{border:1px solid transparent;border-bottom:0;background:transparent;padding:7px 10px;border-radius:5px 5px 0 0;cursor:pointer;color:var(--muted)}
.tab.active{background:#fff;border-color:var(--line);color:var(--ink);font-weight:700;transform:translateY(1px)}
.tab-body{flex:1;min-height:0;overflow:auto;padding:9px}
.candidate{border-bottom:1px solid var(--line);padding:8px 3px}
.candidate:last-child{border-bottom:0}
.candidate-top{display:flex;align-items:center;gap:6px;margin-bottom:4px}
.badge{font-size:10px;padding:2px 6px;border-radius:999px;background:#e2e8f0;color:#475569}
.badge.support{background:var(--green-bg);color:#065f46}.badge.oppose{background:var(--red-bg);color:#7f1d1d}.badge.context{background:var(--amber-bg);color:#92400e}
.candidate-text{font-weight:650;white-space:pre-wrap;word-break:break-word}
.candidate-reason{font-size:11px;color:var(--muted);margin-top:4px}
.jump{margin-left:auto;border:0;background:transparent;color:var(--blue);cursor:pointer;font-size:11px}
pre{margin:0;background:#0f172a;color:#dbeafe;border-radius:5px;padding:10px;white-space:pre-wrap;word-break:break-word;font:11px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.matrix-wrap{overflow:auto}
.matrix{border-collapse:collapse;font-size:10px;width:max-content;min-width:100%}
.matrix th,.matrix td{border-bottom:1px solid var(--line);padding:5px 6px;text-align:center;max-width:220px}
.matrix th{position:sticky;top:0;background:#fff;z-index:1;color:var(--muted)}
.matrix th:first-child,.matrix td:first-child{text-align:left;position:sticky;left:0;background:#fff;z-index:2}
.matrix-dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#cbd5e1}.matrix-dot.on{background:var(--blue)}
.matrix-label{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:220px}
.empty{color:var(--muted);padding:18px;text-align:center}
@media(max-width:1050px){body{overflow:auto}.app{height:auto;min-height:100vh}.shell{grid-template-columns:1fr}.stages{max-height:260px;border-right:0;border-bottom:1px solid var(--line)}.workspace{grid-template-columns:1fr}.panel{min-height:600px}.picker select{min-width:180px}.task{white-space:normal}}
</style>
</head>
<body>
<div class="app">
  <header class="topbar">
    <div class="brand"><span>Eval</span>Agent</div>
    <div class="title">Judge Pipeline Debugger</div>
    <a class="back-link" href="index.html">Final evidence view</a>
    <div class="picker"><label for="caseSelect">Case</label><select id="caseSelect"></select></div>
  </header>
  <div class="shell">
    <aside class="stages">
      <div class="stages-head"><b>Pipeline stages</b><span id="stageMeta"></span></div>
      <div class="stage-list" id="stageList"></div>
    </aside>
    <main class="main">
      <section class="case-head" id="caseHead"></section>
      <section class="stage-summary" id="stageSummary"></section>
      <div class="workspace">
        <section class="panel">
          <div class="panel-head"><h3>Agent trajectory at this stage</h3><span class="panel-note">Exact spans highlighted from current candidates</span></div>
          <div class="trajectory" id="trajectory"></div>
        </section>
        <section class="panel">
          <div class="debug-tabs">
            <button class="tab active" data-tab="candidates">Candidates</button>
            <button class="tab" data-tab="raw">Raw stage output</button>
            <button class="tab" data-tab="lifecycle">Lifecycle matrix</button>
          </div>
          <div class="tab-body" id="debugBody"></div>
        </section>
      </div>
    </main>
  </div>
</div>
<script>
const DEBUG=__DEBUG_DATA__;
const RESULTS=__RESULT_DATA__;
const resultById=new Map((RESULTS.cases||[]).map(c=>[c.case_id,c]));
const cases=DEBUG.cases||[];
const FIELDS=[
  ["Thinking Process","thinking_process"],
  ["Evaluation","evaluation_previous_goal"],
  ["Memory","memory"],
  ["Next Goal","next_goal"],
  ["Action","action"]
];
const STAGE_HELP={
  input:"Formal criterion/task supplied to the blind judge.",
  contract:"Criterion converted into observable pass/fail requirements.",
  initial_extraction:"High-recall extraction over the complete trajectory.",
  post_scan_merge:"Initial extraction and all chunk scans after grounding, semantic normalization, and wrapper pruning.",
  repair_extraction:"Second pass that searches for important evidence missed earlier.",
  post_repair_merge:"All grounded candidates after the repair pass.",
  relevance_audit_1:"First LLM relevance blacklist; rejected IDs and reasons are visible in raw output.",
  targeted_coverage:"Targeted search for requirements marked missing by the first audit.",
  post_targeted_merge:"Candidate pool after targeted coverage is grounded and merged.",
  relevance_audit_2:"Final relevance audit before deterministic enrichment.",
  semantic_enrichment:"Concessive-sentence merge plus deterministic recall from the final Action.",
  internal_candidate_pool:"Complete evidence pool sent to final adjudication.",
  adjudication:"Raw blinded verdict, polarity groups, and selected evidence IDs.",
  polarity_reconciliation:"Candidates after adjudicator support/context/opposition directions are applied.",
  guardrails:"Binary verdict after deterministic consistency checks.",
  public_projection:"Criterion-specific subset chosen for user-facing highlights.",
  public_alignment:"Public evidence labels aligned with the binary overall verdict.",
  result:"Schema-compatible result returned to EvalAgent."
};
let caseIndex=0,stageIndex=0,activeTab="candidates";
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const currentCase=()=>cases[caseIndex]||{};
const currentResult=()=>resultById.get(currentCase().case_id)||{};
const currentStage=()=>currentCase().stages?.[stageIndex]||{};
const verdict=()=>String(currentResult().judge?.verdict||"UNKNOWN").toUpperCase();
const candidateKey=c=>c.candidate_key||`${c.step_index}|${c.source_field}|${String(c.highlighted_text||"").toLowerCase().replace(/\s+/g," ").trim()}`;
const stageHelp=s=>{
  if(String(s.stage||"").startsWith("step_scan_")){
    const a=s.metadata?.step_start,b=s.metadata?.step_end;
    return `Independent high-recall scan of agent steps ${a}-${b}.`;
  }
  return STAGE_HELP[s.stage]||"Intermediate judge pipeline state.";
};
const actionNarratives=value=>{
  const found=[];
  const visit=node=>{
    if(node===null||node===undefined)return;
    if(typeof node==="string"){
      const t=node.trim();
      if(t.startsWith("{")||t.startsWith("[")){try{visit(JSON.parse(t));return}catch(_e){}}
      found.push(node);return;
    }
    if(Array.isArray(node)){node.forEach(visit);return}
    if(typeof node==="object"){
      Object.entries(node).forEach(([key,child])=>{
        if((key==="text"||key==="content")&&typeof child==="string"&&child.trim())found.push(child);
        else visit(child);
      });
    }
  };
  visit(value);return [...new Set(found)];
};
const fieldText=(step,key)=>key==="action"
  ? actionNarratives(step?.[key]).join("\n\n")
  : (typeof step?.[key]==="string"?step[key]:JSON.stringify(step?.[key]??"",null,2));
function highlighted(raw,candidates,source){
  const text=String(raw??"");
  const spans=[];
  candidates.filter(c=>String(c.source_field)===source).forEach((c,order)=>{
    const phrase=String(c.highlighted_text||"");if(!phrase)return;
    let at=0,pos;
    while((pos=text.indexOf(phrase,at))!==-1){
      spans.push({start:pos,end:pos+phrase.length,c,order});
      at=pos+Math.max(1,phrase.length);
    }
  });
  if(!spans.length)return esc(text);
  const bounds=[...new Set([0,text.length,...spans.flatMap(s=>[s.start,s.end])])].sort((a,b)=>a-b);
  let html="";
  for(let i=0;i<bounds.length-1;i++){
    const a=bounds[i],b=bounds[i+1];
    const layers=spans.filter(s=>s.start<=a&&s.end>=b).sort((x,y)=>x.order-y.order);
    let part=esc(text.slice(a,b));
    layers.slice().reverse().forEach(s=>{part=`<mark class="ev ${esc(s.c.polarity)}">${part}</mark>`});
    html+=part;
  }
  return html;
}
function renderCasePicker(){
  const select=document.querySelector("#caseSelect");
  select.innerHTML=cases.map((c,i)=>{
    const r=resultById.get(c.case_id)||{};
    return `<option value="${i}">${esc(c.case_id)} · ${esc(r.judge?.verdict||"")}</option>`;
  }).join("");
  select.value=caseIndex;
  select.onchange=()=>{caseIndex=Number(select.value);stageIndex=0;render()};
}
function renderStageList(){
  const c=currentCase(),stages=c.stages||[];
  document.querySelector("#stageMeta").textContent=`${stages.length} recorded states · ${c.judge_version||""}`;
  document.querySelector("#stageList").innerHTML=stages.map((s,i)=>`
    <button class="stage-btn ${i===stageIndex?"active":""}" data-stage="${i}">
      <div class="stage-line"><span class="stage-seq">${i+1}</span><span class="stage-name">${esc(s.label)}</span><span class="stage-count">${s.candidate_count||0}</span></div>
      <div class="stage-key">${esc(s.stage)}</div>
    </button>`).join("");
  document.querySelectorAll("[data-stage]").forEach(b=>b.onclick=()=>{stageIndex=Number(b.dataset.stage);render()});
}
function renderHead(){
  const c=currentCase(),r=currentResult(),v=verdict(),s=currentStage();
  document.querySelector("#caseHead").innerHTML=`
    <div><div><span class="case-id">${esc(c.case_id)}</span><span class="criterion">${esc(c.criterion?.title)}</span></div><div class="task">${esc(c.task)}</div></div>
    <div class="head-metrics"><span class="metric verdict ${v.toLowerCase()}">${esc(v)}</span><span class="metric">${r.steps?.length||0} agent steps</span><span class="metric">${c.stages?.length||0} pipeline states</span></div>`;
  const rawCount=Array.isArray(s.raw_output?.evidence)?s.raw_output.evidence.length:null;
  document.querySelector("#stageSummary").innerHTML=`
    <div><h2>${stageIndex+1}. ${esc(s.label||"")}</h2><p>${esc(stageHelp(s))}</p></div>
    <div class="summary-counts"><span class="summary-count">${s.candidate_count||0} grounded candidates</span>${rawCount===null?"":`<span class="summary-count">${rawCount} raw spans</span>`}</div>`;
}
function renderTrajectory(){
  const r=currentResult(),s=currentStage(),candidates=s.candidates||[];
  const steps=r.steps||[];
  document.querySelector("#trajectory").innerHTML=steps.map((step,idx)=>{
    const stepCandidates=candidates.filter(c=>Number(c.step_index)===idx);
    const fields=FIELDS.map(([label,key])=>{
      const value=fieldText(step,key);
      const hits=stepCandidates.filter(c=>String(c.source_field)===label);
      return `<div class="field ${key==="thinking_process"||key==="action"?"wide":""}">
        <div class="field-label">${esc(label)}${hits.length?` · ${hits.length}`:""}</div>
        <div class="field-value ${hits.length?"hit":""}">${value?highlighted(value,hits,label):'<span class="step-empty">Empty</span>'}</div>
      </div>`;
    }).join("");
    return `<details class="step" id="step-${idx}" ${stepCandidates.length?"open":""}>
      <summary><span class="step-num">Step ${idx}</span>${stepCandidates.length?`<span class="step-hit">${stepCandidates.length} candidates</span>`:'<span class="step-empty">no candidates at this stage</span>'}</summary>
      <div class="fields">${fields}</div>
    </details>`;
  }).join("");
}
function candidateHtml(c,i){
  return `<article class="candidate">
    <div class="candidate-top"><span class="badge ${esc(c.polarity)}">${esc(c.polarity)}</span><span class="badge">${esc(c.criterion_element)}</span><span class="badge">step ${esc(c.step_index)} · ${esc(c.source_field)}</span><button class="jump" data-jump="${esc(c.step_index)}">show in trace</button></div>
    <div class="candidate-text">${esc(c.highlighted_text)}</div>
    <div class="candidate-reason">${esc(c.reasoning||"No reasoning supplied.")}</div>
  </article>`;
}
function renderCandidates(){
  const items=currentStage().candidates||[];
  return items.length?items.map(candidateHtml).join(""):'<div class="empty">This stage does not expose grounded candidates.</div>';
}
function renderRaw(){
  return `<pre>${esc(JSON.stringify(currentStage().raw_output,null,2))}</pre>`;
}
function lifecycleRows(){
  const stages=currentCase().stages||[];
  const byKey=new Map();
  stages.forEach((s,si)=>(s.candidates||[]).forEach(c=>{
    const key=candidateKey(c);
    if(!byKey.has(key))byKey.set(key,{candidate:c,present:new Set()});
    byKey.get(key).present.add(si);
  }));
  const rows=[...byKey.values()].sort((a,b)=>Number(a.candidate.step_index)-Number(b.candidate.step_index));
  if(!rows.length)return '<div class="empty">No candidate lifecycle is available.</div>';
  const head=stages.map((s,i)=>`<th title="${esc(s.label)}">${i+1}</th>`).join("");
  const body=rows.map(row=>{
    const c=row.candidate;
    const dots=stages.map((_,i)=>`<td><span class="matrix-dot ${row.present.has(i)?"on":""}"></span></td>`).join("");
    return `<tr><td><div class="matrix-label">S${esc(c.step_index)} ${esc(c.source_field)} · ${esc(c.highlighted_text)}</div></td>${dots}</tr>`;
  }).join("");
  return `<div class="matrix-wrap"><table class="matrix"><thead><tr><th>Candidate</th>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}
function renderDebugBody(){
  let html=activeTab==="raw"?renderRaw():activeTab==="lifecycle"?lifecycleRows():renderCandidates();
  document.querySelector("#debugBody").innerHTML=html;
  document.querySelectorAll("[data-jump]").forEach(b=>b.onclick=()=>{
    const target=document.querySelector(`#step-${b.dataset.jump}`);
    if(target){target.open=true;target.scrollIntoView({behavior:"smooth",block:"start"})}
  });
}
function renderTabs(){
  document.querySelectorAll("[data-tab]").forEach(b=>{
    b.classList.toggle("active",b.dataset.tab===activeTab);
    b.onclick=()=>{activeTab=b.dataset.tab;renderTabs();renderDebugBody()};
  });
}
function render(){
  renderCasePicker();renderStageList();renderHead();renderTrajectory();renderTabs();renderDebugBody();
}
render();
</script>
</body>
</html>
"""


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def render(results_dir: Path) -> Path:
    debug_path = results_dir / "pipeline_debug.json"
    result_path = results_dir / "visualization_data.json"
    if not debug_path.is_file():
        raise FileNotFoundError(
            f"Missing {debug_path}; rerun the judge with --debug-trace"
        )
    if not result_path.is_file():
        raise FileNotFoundError(f"Missing {result_path}")
    debug = _load_json(debug_path)
    results = _load_json(result_path)
    debug_json = json.dumps(debug, ensure_ascii=False).replace("</", "<\\/")
    result_json = json.dumps(results, ensure_ascii=False).replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__DEBUG_DATA__", debug_json).replace(
        "__RESULT_DATA__",
        result_json,
    )
    output = results_dir / "pipeline_debug.html"
    output.write_text(html, encoding="utf-8")
    return output


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render every grounded-judge pipeline stage for debugging."
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
    )
    return parser.parse_args()


def main() -> int:
    output = render(_parse_args().results_dir.resolve())
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
