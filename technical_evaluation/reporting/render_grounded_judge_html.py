from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
TECH_EVAL_DIR = SCRIPT_DIR.parent
ROOT = TECH_EVAL_DIR.parent
DEFAULT_RESULTS_DIR = TECH_EVAL_DIR / "results" / "grounded_judge_webharbor_v13"


def _relativize_screenshots(payload: dict[str, Any], output_dir: Path) -> None:
    for case in payload.get("cases", []):
        converted: list[str] = []
        for raw in case.get("screenshots", []):
            source = Path(str(raw))
            if not source.is_absolute():
                source = ROOT / source
            converted.append(os.path.relpath(source, output_dir).replace("\\", "/"))
        case["screenshots"] = converted


# This intentionally mirrors EvalAgent's ReasoningPanel rather than presenting
# evidence as a detached report. Judge citations are projected back onto their
# original trajectory fields and steps.
HTML_TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EvalAgent · Agentic Judge Results</title>
<style>
:root{
  --slate-950:#0f172a;--slate-800:#1e293b;--slate-700:#334155;
  --slate-600:#475569;--slate-500:#64748b;--slate-400:#94a3b8;
  --slate-300:#cbd5e1;--slate-200:#e2e8f0;--slate-100:#f1f5f9;
  --slate-50:#f8fafc;--blue:#3b82f6;--criterion:#8b5cf6;
  --pass:#10b981;--pass-bg:#d1fae5;--pass-text:#065f46;
  --partial:#f59e0b;--partial-bg:#fef3c7;--partial-text:#92400e;
  --fail:#ef4444;--fail-bg:#fee2e2;--fail-text:#7f1d1d;
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:#eef2f7;color:var(--slate-800);font:13px/1.45 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;overflow:hidden}
button,select{font:inherit}
.app{height:100vh;display:flex;flex-direction:column}
.appbar{height:54px;display:flex;align-items:center;gap:18px;padding:0 18px;background:var(--slate-950);color:#fff;box-shadow:0 1px 5px #0f172a44;z-index:5}
.brand{font-weight:750;font-size:16px;letter-spacing:-.01em}.brand span{color:#93c5fd}
.appbar-divider{height:24px;width:1px;background:#ffffff26}
.debug-link{color:#bfdbfe;text-decoration:none;border:1px solid #ffffff38;border-radius:4px;padding:5px 9px;font-size:11px;font-weight:700}
.debug-link:hover{background:#ffffff14;color:#fff}
.case-picker{display:flex;align-items:center;gap:8px;min-width:0}
.case-picker label{font-size:11px;color:#cbd5e1;text-transform:uppercase;letter-spacing:.06em;font-weight:700}
.case-picker select{width:min(420px,42vw);padding:6px 30px 6px 10px;border:1px solid #ffffff38;border-radius:4px;background:#1e293b;color:#fff;outline:none}
.app-summary{margin-left:auto;display:flex;gap:8px}
.summary-chip{padding:4px 9px;border-radius:999px;background:#ffffff14;color:#dbeafe;font-size:11px}
.layout{display:grid;grid-template-columns:270px minmax(0,1fr);flex:1;min-height:0}
.sidebar{background:#fff;border-right:1px solid var(--slate-300);display:flex;flex-direction:column;min-height:0}
.sidebar-head{padding:14px 14px 10px;border-bottom:1px solid var(--slate-200)}
.sidebar-title{font-weight:700;color:var(--slate-950);font-size:13px}
.sidebar-subtitle{font-size:11px;color:var(--slate-500);margin-top:3px}
.case-list{padding:8px;overflow:auto}
.case-btn{width:100%;border:1px solid transparent;background:transparent;padding:10px;border-radius:6px;text-align:left;cursor:pointer;margin-bottom:4px;color:var(--slate-700)}
.case-btn:hover{background:var(--slate-50);border-color:var(--slate-200)}
.case-btn.active{background:#eff6ff;border-color:#bfdbfe;color:#1e40af}
.case-line{display:flex;align-items:center;gap:8px}.case-id{font-weight:700;flex:1}.status-dot{width:9px;height:9px;border-radius:50%}.status-dot.pass{background:var(--pass)}.status-dot.partial{background:var(--partial)}.status-dot.fail{background:var(--fail)}
.case-meta{font-size:10px;color:var(--slate-500);margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.main{display:flex;flex-direction:column;min-width:0;min-height:0;padding:12px}
.condition-bar{display:flex;align-items:center;gap:12px;background:#fff;border:1px solid var(--slate-300);border-bottom:0;padding:9px 12px}
.condition-title{font-weight:700;color:var(--slate-950)}.condition-task{color:var(--slate-600);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}
.overall-badge{padding:4px 10px;border:1px solid;border-radius:999px;font-weight:800;font-size:11px;letter-spacing:.04em}
.overall-badge.pass{background:var(--pass-bg);color:var(--pass-text);border-color:var(--pass)}
.overall-badge.partial{background:var(--partial-bg);color:var(--partial-text);border-color:var(--partial)}
.overall-badge.fail{background:var(--fail-bg);color:var(--fail-text);border-color:var(--fail)}
.detail-btn{border:1px solid var(--slate-300);background:#fff;border-radius:4px;padding:5px 9px;cursor:pointer;color:var(--slate-600)}
.detail-btn:hover{background:var(--slate-50);color:var(--slate-950)}
.reasoning-panel{display:flex;flex-direction:column;flex:1;min-width:0;min-height:0;background:#fff;border:1px solid var(--slate-300)}
.panel-head{height:44px;display:flex;align-items:center;padding:0 14px;border-bottom:1px solid var(--slate-200);background:#fff}
.panel-head h2{font-size:14px;margin:0;color:var(--slate-950)}
.agent-label{margin-left:auto;color:var(--slate-500);font-size:11px;text-transform:uppercase;font-weight:700;letter-spacing:.05em}
.agent-value{margin-left:7px;padding:5px 8px;border:1px solid var(--slate-200);border-radius:4px;color:var(--slate-700);max-width:430px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.panel-body{display:flex;flex-direction:column;gap:13px;padding:13px;flex:1;min-height:0}
.reasoning-content{display:grid;grid-template-columns:minmax(0,4fr) minmax(210px,1fr);gap:12px;flex:1;min-height:0}
.step-workspace{display:flex;flex-direction:column;min-width:0;min-height:0}
.step-header{display:flex;align-items:center;padding:0 2px 8px;border-bottom:1px solid var(--slate-200)}
.step-header h3{margin:0;font-size:14px}.step-evidence-count{margin-left:8px;color:var(--slate-500);font-size:11px}
.shot-btn{margin-left:auto;border:0;background:var(--blue);color:#fff;border-radius:4px;padding:5px 9px;cursor:pointer;font-size:11px}
.fields{display:grid;grid-template-columns:minmax(0,2fr) minmax(190px,1fr);gap:12px;flex:1;min-height:0;padding-top:9px}
.field-col{display:flex;flex-direction:column;gap:9px;min-width:0;min-height:0}.field-col.details{overflow:auto;padding-right:2px}
.field-block{display:flex;flex-direction:column;gap:5px;min-height:0}.field-block.thinking{flex:1}
.field-label{font-size:11px;font-weight:700;color:var(--slate-500);text-transform:uppercase;letter-spacing:.05em}
.field-text{background:#fff;border:1px solid #e4e8ee;border-radius:6px;padding:9px;font-size:12px;line-height:1.55;color:var(--slate-700);white-space:pre-wrap;overflow:auto;min-height:72px;word-break:break-word}
.field-block.thinking .field-text{flex:1}.field-text.has-evidence{border:2px solid #60a5fa88;box-shadow:inset 0 0 0 1px #93c5fd55}
.action-text{font-family:Monaco,Menlo,Consolas,monospace;font-size:11px;background:var(--slate-50)}
mark.evidence{padding:1px 2px;border-radius:2px;border:2px solid var(--criterion);cursor:help;box-decoration-break:clone;-webkit-box-decoration-break:clone}
mark.evidence.pass{background:var(--pass-bg);color:inherit}mark.evidence.partial{background:var(--partial-bg);color:inherit}mark.evidence.fail{background:var(--fail-bg);color:inherit}
.criteria-pane{display:flex;flex-direction:column;min-height:0;background:var(--slate-50);border:1px solid #e4e8ee;border-radius:6px;padding:11px}
.criteria-pane-title{font-weight:700;color:var(--slate-950);margin-bottom:8px}
.criterion-card{border:1px solid var(--criterion);border-left:4px solid var(--criterion);border-radius:4px;padding:10px;background:var(--pass-bg);cursor:pointer}
.criterion-card.partial{background:var(--partial-bg)}
.criterion-card.fail{background:var(--fail-bg)}
.criterion-head{display:flex;align-items:center;gap:8px}.criterion-name{font-weight:700;min-width:0;flex:1}.confidence-ring{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;font-size:12px;font-weight:900;background:#fff;border:3px solid var(--pass);color:var(--pass-text)}.criterion-card.partial .confidence-ring{border-color:var(--partial);color:var(--partial-text)}.criterion-card.fail .confidence-ring{border-color:var(--fail);color:var(--fail-text)}
.criterion-desc{font-size:11px;color:var(--slate-600);margin-top:7px}.criterion-step-reason{font-size:11px;color:var(--slate-700);margin-top:9px;padding-top:8px;border-top:1px solid #00000012}
.no-step-evidence{color:var(--slate-500);font-size:12px;padding:15px 5px}
.timeline{flex:0 0 auto;border-top:1px solid var(--slate-200);padding-top:18px;min-height:100px}
.timeline-track{position:relative;display:flex;justify-content:space-between;gap:7px;align-items:flex-start;padding:12px 0 0}
.timeline-line{position:absolute;left:3%;right:3%;top:35px;border-top:2px dashed #d1d5db;z-index:0}
.timeline-item{position:relative;z-index:1;flex:1;display:flex;flex-direction:column;align-items:center;min-width:38px}
.timeline-eval{position:absolute;top:-18px;width:20px;height:20px;border-radius:50%;display:grid;place-items:center;color:#fff;font-size:12px;font-weight:900;border:3px solid var(--criterion);box-shadow:0 1px 3px #0f172a44}
.timeline-eval.pass{background:var(--pass)}.timeline-eval.partial{background:var(--partial)}.timeline-eval.fail{background:var(--fail)}
.timeline-node{width:100%;max-width:64px;height:45px;padding:2px;border:0;border-radius:4px;background:#fff;cursor:pointer}
.timeline-node img{width:100%;height:100%;object-fit:cover;border:2px solid var(--slate-300);border-radius:4px;display:block}
.timeline-node.placeholder{border:2px solid var(--slate-300);background:var(--slate-100);color:var(--slate-500);font-size:10px}
.timeline-item.active .timeline-node{transform:translateY(-6px)}.timeline-item.active .timeline-node img,.timeline-item.active .timeline-node.placeholder{border-color:var(--blue);box-shadow:0 0 0 2px #fff,0 0 0 4px var(--blue)}
.timeline-step{font-size:10px;color:var(--slate-500);margin-top:5px}.timeline-counter{text-align:center;color:var(--slate-500);font-size:10px;text-transform:uppercase;letter-spacing:.05em;margin-top:5px;font-weight:700}
.tooltip{position:fixed;z-index:50;width:min(340px,calc(100vw - 24px));background:#fff;border:1px solid var(--slate-200);border-radius:8px;padding:11px;box-shadow:0 14px 30px #0f172a2e;pointer-events:none;display:none}
.tooltip.show{display:block}.tooltip-top{display:flex;align-items:center;gap:7px;margin-bottom:6px}.tooltip-verdict{font-weight:800;font-size:10px;text-transform:uppercase;padding:2px 6px;border-radius:4px}.tooltip-verdict.pass{background:var(--pass-bg);color:var(--pass-text)}.tooltip-verdict.partial{background:var(--partial-bg);color:var(--partial-text)}.tooltip-verdict.fail{background:var(--fail-bg);color:var(--fail-text)}.tooltip-source{font-size:10px;color:var(--slate-500)}.tooltip-reason{color:var(--slate-700);font-size:12px}
.modal-backdrop{position:fixed;inset:0;background:#0f172a99;display:none;align-items:center;justify-content:center;z-index:40;padding:20px}.modal-backdrop.open{display:flex}
.modal{background:#fff;width:min(760px,96vw);max-height:90vh;border-radius:8px;box-shadow:0 20px 50px #0005;display:flex;flex-direction:column;overflow:hidden}
.modal.shot{width:min(1200px,96vw)}.modal-head{display:flex;align-items:center;padding:14px 16px;border-bottom:1px solid var(--slate-200)}.modal-head h2{font-size:16px;margin:0}.modal-close{margin-left:auto;border:0;background:transparent;font-size:23px;cursor:pointer;color:var(--slate-500)}
.modal-body{padding:16px;overflow:auto}.assessment{display:flex;align-items:center;gap:10px}.assessment h3{margin:0;font-size:15px}.assessment-badge{margin-left:auto;padding:5px 10px;border-radius:999px;color:#fff;font-weight:800;font-size:11px}.assessment-badge.pass{background:var(--pass)}.assessment-badge.partial{background:var(--partial)}.assessment-badge.fail{background:var(--fail)}
.overall-reason{margin:13px 0;color:var(--slate-700);white-space:pre-wrap}.meta-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:14px}.meta-box{background:var(--slate-50);border:1px solid var(--slate-200);border-radius:5px;padding:9px}.meta-box b{display:block;font-size:10px;text-transform:uppercase;color:var(--slate-500);margin-bottom:3px}.criterion-assertion{padding:11px;background:#f5f3ff;border-left:4px solid var(--criterion);margin-top:14px;color:var(--slate-700)}
.modal-image{display:block;max-width:100%;max-height:78vh;margin:auto}
@media(max-width:900px){body{overflow:auto}.app{height:auto;min-height:100vh}.layout{grid-template-columns:1fr}.sidebar{max-height:220px;border-right:0;border-bottom:1px solid var(--slate-300)}.main{min-height:900px}.reasoning-content{grid-template-columns:1fr}.criteria-pane{min-height:160px}.fields{grid-template-columns:1fr}.app-summary{display:none}.case-picker select{width:44vw}}
</style>
</head>
<body>
<div class="app">
  <header class="appbar">
    <div class="brand"><span>Eval</span>Agent</div>
    <div class="appbar-divider"></div>
    __DEBUG_LINK__
    <div class="case-picker"><label for="caseSelect">Condition</label><select id="caseSelect"></select></div>
    <div class="app-summary" id="summary"></div>
  </header>
  <div class="layout">
    <aside class="sidebar">
      <div class="sidebar-head"><div class="sidebar-title">Agentic Judge Results</div><div class="sidebar-subtitle" id="judgeMeta"></div></div>
      <div class="case-list" id="caseList"></div>
    </aside>
    <main class="main">
      <div class="condition-bar" id="conditionBar"></div>
      <section class="reasoning-panel">
        <div class="panel-head"><h2>Reasoning</h2><span class="agent-label">Agent</span><span class="agent-value" id="agentValue"></span></div>
        <div class="panel-body">
          <div class="reasoning-content">
            <section class="step-workspace" id="stepWorkspace"></section>
            <aside class="criteria-pane" id="criteriaPane"></aside>
          </div>
          <section class="timeline" id="timeline"></section>
        </div>
      </section>
    </main>
  </div>
</div>
<div class="tooltip" id="tooltip"></div>
<div class="modal-backdrop" id="detailBackdrop"><section class="modal"><header class="modal-head"><h2>Condition Details</h2><button class="modal-close" data-close="detailBackdrop">×</button></header><div class="modal-body" id="detailModal"></div></section></div>
<div class="modal-backdrop" id="shotBackdrop"><section class="modal shot"><header class="modal-head"><h2 id="shotTitle">Step Screenshot</h2><button class="modal-close" data-close="shotBackdrop">×</button></header><div class="modal-body"><img class="modal-image" id="shotImage" alt="Step screenshot"></div></section></div>
<script>
const DATA=__DATA__;
const cases=DATA.cases||[];
const FIELD_MAP={
  "Thinking Process":"thinking_process",
  "Evaluation":"evaluation_previous_goal",
  "Memory":"memory",
  "Next Goal":"next_goal",
  "Action":"action"
};
let caseIndex=0,stepIndex=0;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const normalizeVerdict=v=>{
  const value=String(v||'').toUpperCase();
  return value==='PASS'||value==='PARTIAL'||value==='FAIL'?value:'FAIL';
};
const verdict=c=>normalizeVerdict(c?.judge?.verdict);
const cls=v=>normalizeVerdict(v).toLowerCase();
const icon=v=>normalizeVerdict(v)==='PASS'?'✓':normalizeVerdict(v)==='PARTIAL'?'~':'✕';
const verdictLabel=v=>normalizeVerdict(v);
const current=()=>cases[caseIndex];
const actionNarratives=value=>{
  const found=[];
  const visit=node=>{
    if(node===null||node===undefined)return;
    if(typeof node==='string'){
      const trimmed=node.trim();
      if(trimmed.startsWith('{')||trimmed.startsWith('[')){
        try{visit(JSON.parse(trimmed));return}catch(_err){}
      }
      return;
    }
    if(Array.isArray(node)){node.forEach(visit);return}
    if(typeof node==='object'){
      Object.entries(node).forEach(([key,child])=>{
        if((key==='text'||key==='content')&&typeof child==='string'&&child.trim()){
          found.push(child);
        }else{
          visit(child);
        }
      });
    }
  };
  visit(value);
  return [...new Set(found)];
};
const sourceValue=(step,field)=>{
  const value=step?.[FIELD_MAP[field]];
  if(field==='Action'){
    const narratives=actionNarratives(value);
    if(narratives.length)return narratives.join('\n\n');
  }
  return typeof value==='string'?value:JSON.stringify(value??'',null,2);
};
const stepEvidence=(c,idx)=>(c.judge?.evidence||[]).filter(e=>Number(e.step_index)===idx);
const rawStepVerdict=(c,idx)=>{
  const values=new Set(stepEvidence(c,idx).map(e=>String(e.verdict||'').toUpperCase()));
  if(values.has('PARTIAL')||(values.has('PASS')&&values.has('FAIL')))return 'PARTIAL';
  if(values.has('PASS'))return 'PASS';
  return values.size?'FAIL':null;
};
const inferredStepVerdicts=c=>{
  const result={};
  (c.steps||[]).forEach((_,idx)=>{const value=rawStepVerdict(c,idx);if(value)result[idx]=value});
  return result;
};
const stepVerdict=(c,idx)=>{
  const declared=c.judge?.step_verdicts?.[String(idx)];
  return declared?normalizeVerdict(declared):(inferredStepVerdicts(c)[idx]||null);
};

function highlightText(raw,evidence,field){
  const text=String(raw??'');
  const matches=[];
  evidence.filter(e=>String(e.source_field).toLowerCase()===field.toLowerCase()).forEach((e,order)=>{
    const phrase=String(e.highlighted_text||'');
    if(!phrase)return;
    let from=0,pos;
    while((pos=text.indexOf(phrase,from))!==-1){
      matches.push({start:pos,end:pos+phrase.length,e,order});from=pos+Math.max(1,phrase.length);
    }
  });
  if(!matches.length)return esc(text);
  const boundaries=[...new Set([0,text.length,...matches.flatMap(m=>[m.start,m.end])])].sort((a,b)=>a-b);
  let html='';
  for(let i=0;i<boundaries.length-1;i++){
    const a=boundaries[i],b=boundaries[i+1],layers=matches.filter(m=>m.start<=a&&m.end>=b).sort((x,y)=>x.order-y.order);
    let segment=esc(text.slice(a,b));
    layers.slice().reverse().forEach(m=>{
      const encoded=encodeURIComponent(JSON.stringify({verdict:m.e.verdict,source:m.e.source_field,reasoning:m.e.reasoning}));
      segment=`<mark class="evidence ${cls(m.e.verdict)}" data-tip="${encoded}">${segment}</mark>`;
    });
    html+=segment;
  }
  return html;
}

function renderSidebar(){
  const pass=cases.filter(c=>verdict(c)==='PASS').length;
  const partial=cases.filter(c=>verdict(c)==='PARTIAL').length;
  const fail=cases.filter(c=>verdict(c)==='FAIL').length;
  document.querySelector('#summary').innerHTML=`<span class="summary-chip">${cases.length} cases</span><span class="summary-chip">${pass} pass · ${partial} partial · ${fail} fail</span>`;
  document.querySelector('#judgeMeta').textContent=`${DATA.judge_version} · ${DATA.judge_model}`;
  const options=cases.map((c,i)=>`<option value="${i}">${esc(c.case_id)} · ${verdict(c)} · ${esc(c.agent?.persona_value)}</option>`).join('');
  const select=document.querySelector('#caseSelect');select.innerHTML=options;select.value=caseIndex;
  document.querySelector('#caseList').innerHTML=cases.map((c,i)=>`<button class="case-btn ${i===caseIndex?'active':''}" data-case="${i}"><div class="case-line"><span class="case-id">${esc(c.case_id)}</span><span class="status-dot ${cls(verdict(c))}"></span></div><div class="case-meta">${esc(c.agent?.persona_value)} · ${esc(c.agent?.model)}</div></button>`).join('');
  document.querySelectorAll('[data-case]').forEach(b=>b.onclick=()=>selectCase(Number(b.dataset.case)));
}

function renderCondition(){
  const c=current(),v=verdict(c);
  document.querySelector('#conditionBar').innerHTML=`<span class="condition-title">${esc(c.case_id)}</span><span class="condition-task" title="${esc(c.task)}">${esc(c.task)}</span><span class="overall-badge ${cls(v)}">${v} · ${Math.round(Number(c.judge?.confidence||0)*100)}%</span><button class="detail-btn" id="openDetail">Condition details</button>`;
  document.querySelector('#agentValue').textContent=`${c.agent?.persona_value||''} - ${c.agent?.model||''} - Run 1`;
  document.querySelector('#openDetail').onclick=openDetail;
}

function fieldBlock(c,step,label,extra=''){
  const ev=stepEvidence(c,stepIndex),raw=sourceValue(step,label),has=ev.some(e=>String(e.source_field).toLowerCase()===label.toLowerCase());
  return `<div class="field-block ${extra}"><div class="field-label">${label}</div><div class="field-text ${has?'has-evidence':''} ${label==='Action'?'action-text':''}">${highlightText(raw,ev,label)||'<span style="color:#94a3b8;font-style:italic">No data</span>'}</div></div>`;
}

function renderStep(){
  const c=current(),step=c.steps?.[stepIndex]||{},ev=stepEvidence(c,stepIndex),shot=c.screenshots?.[stepIndex];
  document.querySelector('#stepWorkspace').innerHTML=`
    <header class="step-header"><h3>Step ${stepIndex}</h3><span class="step-evidence-count">${ev.length?`${ev.length} highlighted evidence span${ev.length>1?'s':''}`:'No judge evidence on this step'}</span>${shot?'<button class="shot-btn" id="openShot">View Screenshot</button>':''}</header>
    <div class="fields">
      <div class="field-col">${fieldBlock(c,step,'Thinking Process','thinking')}</div>
      <div class="field-col details">
        ${fieldBlock(c,step,'Evaluation')}
        ${fieldBlock(c,step,'Memory')}
        ${fieldBlock(c,step,'Next Goal')}
        ${fieldBlock(c,step,'Action')}
      </div>
    </div>`;
  if(shot)document.querySelector('#openShot').onclick=()=>openShot(stepIndex);
  bindEvidenceTooltips();
}

function renderCriteria(){
  const c=current(),ev=stepEvidence(c,stepIndex),v=stepVerdict(c,stepIndex);
  const reasons=[...new Set(ev.map(e=>e.reasoning).filter(Boolean))];
  document.querySelector('#criteriaPane').innerHTML=`<div class="criteria-pane-title">Criteria (${v?1:0})</div>${v?`
    <article class="criterion-card ${cls(v)}" id="criterionCard">
      <div class="criterion-head"><span class="criterion-name">${esc(c.criterion?.title||'Criterion')}</span><span class="confidence-ring" title="${esc(verdictLabel(v))} · ${Math.round(Number(c.judge?.confidence||0)*100)}%">${icon(v)}</span></div>
      <div class="criterion-desc">${esc(c.criterion?.assertion)}</div>
      <div class="criterion-step-reason">${reasons.map(esc).join('<br><br>')}</div>
    </article>`:`<div class="no-step-evidence">This step was not selected by the agentic judge as criterion-relevant.</div>`}`;
  const card=document.querySelector('#criterionCard');if(card)card.onclick=openDetail;
}

function renderTimeline(){
  const c=current(),steps=c.steps||[];
  document.querySelector('#timeline').innerHTML=`<div class="timeline-track"><div class="timeline-line"></div>${steps.map((s,i)=>{
    const ev=stepEvidence(c,i),v=stepVerdict(c,i),shot=c.screenshots?.[i];
    return `<div class="timeline-item ${i===stepIndex?'active':''}">${v?`<span class="timeline-eval ${cls(v)}" title="${esc(c.criterion?.title)} · ${esc(verdictLabel(v))}">${icon(v)}</span>`:''}<button class="timeline-node ${shot?'':'placeholder'}" data-step="${i}">${shot?`<img src="${esc(shot)}" alt="Step ${i} thumbnail">`:`Step ${i}`}</button><span class="timeline-step">Step ${i}</span></div>`;
  }).join('')}</div><div class="timeline-counter">Step ${stepIndex+1} of ${steps.length}</div>`;
  document.querySelectorAll('[data-step]').forEach(b=>b.onclick=()=>selectStep(Number(b.dataset.step)));
}

function renderAll(){
  renderSidebar();renderCondition();renderStep();renderCriteria();renderTimeline();
}
function selectCase(i){caseIndex=i;stepIndex=0;renderAll()}
function selectStep(i){stepIndex=i;renderStep();renderCriteria();renderTimeline()}

function openDetail(){
  const c=current(),v=verdict(c);
  document.querySelector('#detailModal').innerHTML=`
    <div class="assessment"><span style="width:10px;height:34px;background:var(--criterion);border-radius:4px"></span><h3>${esc(c.criterion?.title||'Criterion')}</h3><span class="assessment-badge ${cls(v)}">${v}</span></div>
    <div class="criterion-assertion">${esc(c.criterion?.assertion)}</div>
    <p class="overall-reason">${esc(c.judge?.reasoning)}</p>
    <div class="meta-grid">
      <div class="meta-box"><b>Confidence</b>${Math.round(Number(c.judge?.confidence||0)*100)}%</div>
      <div class="meta-box"><b>Relevant steps</b>${esc((c.judge?.relevant_steps||[]).join(', '))}</div>
      <div class="meta-box"><b>Evidence spans</b>${c.judge?.evidence?.length||0}</div>
      <div class="meta-box"><b>Model</b>${esc(c.judge?.model)}</div>
      <div class="meta-box"><b>Agent success</b>${c.agent?.summary?.is_successful?'Yes':'No'}</div>
      <div class="meta-box"><b>Steps</b>${c.steps?.length||0}</div>
    </div>`;
  document.querySelector('#detailBackdrop').classList.add('open');
}
function openShot(i){
  const c=current();document.querySelector('#shotTitle').textContent=`${c.case_id} · Step ${i} Screenshot`;document.querySelector('#shotImage').src=c.screenshots?.[i]||'';document.querySelector('#shotBackdrop').classList.add('open');
}

function bindEvidenceTooltips(){
  const tip=document.querySelector('#tooltip');
  document.querySelectorAll('[data-tip]').forEach(el=>{
    el.onmouseenter=e=>{
      const d=JSON.parse(decodeURIComponent(el.dataset.tip));tip.innerHTML=`<div class="tooltip-top"><span class="tooltip-verdict ${cls(d.verdict)}">${esc(d.verdict)}</span><span class="tooltip-source">${esc(d.source)}</span></div><div class="tooltip-reason">${esc(d.reasoning)}</div>`;tip.classList.add('show');moveTip(e);
    };
    el.onmousemove=moveTip;el.onmouseleave=()=>tip.classList.remove('show');
  });
}
function moveTip(e){
  const tip=document.querySelector('#tooltip'),pad=14,w=tip.offsetWidth||340,h=tip.offsetHeight||100;
  tip.style.left=`${Math.min(window.innerWidth-w-pad,e.clientX+14)}px`;tip.style.top=`${Math.max(pad,e.clientY-h-14)}px`;
}
document.querySelector('#caseSelect').onchange=e=>selectCase(Number(e.target.value));
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>document.querySelector('#'+b.dataset.close).classList.remove('open'));
document.querySelectorAll('.modal-backdrop').forEach(b=>b.onclick=e=>{if(e.target===b)b.classList.remove('open')});
document.onkeydown=e=>{if(e.key==='Escape')document.querySelectorAll('.modal-backdrop').forEach(b=>b.classList.remove('open'));if(e.key==='ArrowRight')selectStep(Math.min((current().steps?.length||1)-1,stepIndex+1));if(e.key==='ArrowLeft')selectStep(Math.max(0,stepIndex-1))};
renderAll();
</script>
</body></html>'''


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render agentic-judge output with EvalAgent-style evidence projection."
    )
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    results_dir = args.results_dir.resolve()
    payload = json.loads(
        (results_dir / "visualization_data.json").read_text(encoding="utf-8")
    )
    _relativize_screenshots(payload, results_dir)
    embedded = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    debug_link = (
        '<a class="debug-link" href="pipeline_debug.html">Pipeline debug</a>'
        if (results_dir / "pipeline_debug.html").is_file()
        else ""
    )
    html = (
        HTML_TEMPLATE.replace("__DATA__", embedded)
        .replace("__DEBUG_LINK__", debug_link)
    )
    output_path = args.output.resolve() if args.output else results_dir / "index.html"
    output_path.write_text(html, encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
