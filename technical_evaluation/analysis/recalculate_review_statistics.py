"""Read-only input audit and paired inference for the review (2026-09-08).

Run with Python containing numpy/pandas. Outputs are isolated from published reports.
Use current location-matching implementation; never alter labels to fit paper totals.
"""
from pathlib import Path
import csv
import hashlib
import importlib.util
import json
import math
import sys
import subprocess
import types

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import compare_criteria1_agreement as metrics
import compute_golden72_metrics as pooled

OUT = ROOT / 'technical_evaluation/results/review_statistics_20260908'
SEED, DRAWS = 20260908, 20000


def read(p):
    return json.loads(Path(p).read_text())


def holm(ps):
    order = np.argsort(ps)
    result = np.zeros(len(ps))
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1., float(ps[index]) * (len(ps) - rank)))
        result[index] = running
    return result.tolist()


def ci(values):
    return np.quantile(values, [.025, .975]).tolist()


def count_record(record, human, metrics=metrics):
    evidence = human['evidence']
    steps = {metrics._parse_int(e.get('step_id')) for e in evidence}
    fields = {(metrics._parse_int(e.get('step_id')), metrics._normalize_source_field_for_matching(e.get('field'))) for e in evidence}
    _, index, skipped, total, overlap = metrics._build_model_evidence_verdict_index(record, True, steps, fields)
    valid = [e for e in evidence if metrics._parse_int(e.get('step_id')) is not None and metrics._normalize_label(e.get('verdict')) is not None]
    hit = sum((metrics._parse_int(e.get('step_id')), metrics._normalize_source_field_for_matching(e.get('field'))) in index for e in valid)
    result = metrics._extract_criteria1_result(record) or {}
    label = str(result.get('overall_assessment') or 'missing').strip().lower()
    return [int(label == human['overall_assessment']), total-skipped, total, hit, len(valid), overlap], label


def technical(historical_old=False):
    old_metrics = metrics
    if historical_old:
        code = subprocess.check_output(['git','show','733de8e:technical_evaluation/compare_criteria1_agreement.py'],cwd=ROOT,text=True)
        old_metrics = types.ModuleType('historical_733de8e')
        exec(compile(code, 'git:733de8e:technical_evaluation/compare_criteria1_agreement.py', 'exec'),old_metrics.__dict__)
    ref = read(ROOT/'technical_evaluation/results/webharbor105_final_metrics.json')
    human_old = metrics._load_human_cases(Path(ref['old_human_file']))
    human_new = metrics._load_human_cases(Path(ref['new_human_file']))
    adj = ref['binary_adjudication']
    human_old[adj['case_id']]['overall_assessment'] = adj['final_human_verdict']
    human = human_old | human_new
    old_sources = read(ref['baseline_gpt_old_metrics_overlay'])['sources']
    old_dirs = dict(zip(pooled.SYSTEMS, [Path(old_sources[x]) for x in ('gpt_dir','baseline_gpt_dir','deepseek_dir','baseline_deepseek_dir')]))
    new_dirs = dict(pooled.SYSTEMS)
    new_dirs['baseline_gpt5'] = Path(ref['baseline_gpt_new_results_dir'])
    ids = sorted(human_old) + sorted(human_new)
    assert len(ids) == len(set(ids)) == 105
    arrays, rows, fingerprints = {}, [], []
    for name in new_dirs:
        records = {}
        for folder, expected in ((old_dirs[name],human_old), (new_dirs[name],human_new)):
            local = {}
            for path in sorted(folder.glob('*__evaluated.json')):
                raw = path.read_bytes()
                record = json.loads(raw)
                cid = record['data_id']
                assert cid not in local, (folder,cid)
                local[cid] = record
                fingerprints.append({'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()})
            assert set(local) == set(expected), (name,folder)
            records.update(local)
        vals = []
        for cid in ids:
            counts, label = count_record(records[cid], human[cid], old_metrics if cid in human_old else metrics)
            vals.append(counts)
            rows.append(dict(system=name,case_id=cid,stratum='controlled33' if cid in human_old else 'webharbor72',gold=human[cid]['overall_assessment'],prediction=label,**dict(zip(('correct','grounded','model_items','human_hits','human_items','model_matches'),counts))))
        arrays[name] = np.array(vals,dtype=float)
    rng = np.random.default_rng(SEED)
    # Preserve 33/72 stratum sizes and pair identities across all methods.
    idx = np.concatenate([rng.integers(0,33,(DRAWS,33)),rng.integers(33,105,(DRAWS,72))],axis=1)
    pairs = {'Grounding':(1,2),'HR':(3,4),'OR':(5,2),'OR_grounded':(5,1)}
    report = {'historical_old33_definition':historical_old,'seed':SEED,'draws':DRAWS,'unit':'case; stratified 33/72 paired percentile bootstrap; item-weighted ratios of pooled counts','caveat':'Cases treated independent within stratum. Shared task prompts may induce additional dependence; CIs are conditional on the current case sample/design. Current implementation outputs must reproduce published totals before interpreting as paper-table CIs.','systems':{},'paired_verdict':{},'paired_evidence':{},'sources':fingerprints}
    boots = {}
    for name, arr in arrays.items():
        sums = arr.sum(0)
        draws = arr[idx].sum(1)
        published = ref['combined_105']['systems'][name]
        expected = [published[k] for k in ('correct_final_verdict_count','grounding_numerator','grounding_denominator','hit_numerator','hit_denominator','overlap_numerator')]
        vals = {}
        boots[name] = {}
        for metric,(n,d) in pairs.items():
            bs = draws[:,n]/draws[:,d]
            boots[name][metric] = bs
            vals[metric] = {'value':sums[n]/sums[d],'ci95':ci(bs)}
        report['systems'][name] = {'raw_counts':sums.astype(int).tolist(),'published_counts':expected,'reproduces_paper':sums.astype(int).tolist()==expected,'metrics':vals}
    for fam in ('gpt5','deepseek'):
        a,b = arrays['agentic_'+fam], arrays['baseline_'+fam]
        ao = int(((a[:,0]==1)&(b[:,0]==0)).sum())
        bo = int(((a[:,0]==0)&(b[:,0]==1)).sum())
        report['paired_verdict'][fam] = {'agentic_only_correct':ao,'baseline_only_correct':bo,'agentic_correct':int(a[:,0].sum()),'baseline_correct':int(b[:,0].sum()),'p_exact':pooled._exact_mcnemar_p(ao,bo),'difference_ci95':ci((a[:,0]-b[:,0])[idx].mean(1))}
        # Within-case condition swaps test exchangeability of method outputs.
        swap = rng.integers(0,2,(DRAWS,len(ids)))
        da = a.sum(0) + swap @ (b-a)
        db = b.sum(0) + swap @ (a-b)
        report['paired_evidence'][fam] = {}
        for metric,(n,d) in pairs.items():
            observed = a[:,n].sum()/a[:,d].sum()-b[:,n].sum()/b[:,d].sum()
            null = da[:,n]/da[:,d]-db[:,n]/db[:,d]
            p = (1+int((np.abs(null)>=abs(observed)-1e-12).sum()))/(DRAWS+1)
            report['paired_evidence'][fam][metric] = {'difference':observed,'ci95':ci(boots['agentic_'+fam][metric]-boots['baseline_'+fam][metric]),'paired_swap_p':p}
        adjusted = holm([report['paired_evidence'][fam][m]['paired_swap_p'] for m in ('Grounding','HR','OR')])
        for m,p in zip(('Grounding','HR','OR'),adjusted):
            report['paired_evidence'][fam][m]['holm_within_three_metrics'] = p
    for fam,p in zip(('gpt5','deepseek'),holm([r['p_exact'] for r in report['paired_verdict'].values()])):
        report['paired_verdict'][fam]['holm_two_models'] = p
    return report, rows


def survey():
    spec = importlib.util.spec_from_file_location('survey_analysis', ROOT/'user_study_analysis/analysis.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ab = ['nasa_workload_5d','mental_demand','evidence_findability','step_pinpointing','actionable_recommendations','divergence_understanding','comparison_efficiency']
    ac = ['nasa_workload_5d','evidence_findability','step_pinpointing','less_manual_log_search','reasoning_panel_helpful']
    results = {}
    for source,path,condition,measures in [('dag',mod.DAG_PATH,'Condition B',ab),('evidence',mod.EVIDENCE_PATH,'Condition C',ac)]:
        df = mod.load_survey(path, source)
        six = ['mental_demand','physical_demand','temporal_demand','frustration','effort','performance']
        assert df[six].notna().all().all()
        assert not df.duplicated(['user_id','condition']).any()
        output = []
        for metric in measures:
            pvt = df.pivot(index='user_id',columns='condition',values=metric).dropna(subset=['Condition A',condition])
            assert len(pvt)==9
            a,b = pvt['Condition A'],pvt[condition]
            # Avoid creating spurious unequal ranks from floating-point sixths.
            delta = np.round((a-b).to_numpy(),10)
            output.append({'metric':metric,'n':len(a),'A':float(a.mean()),'other':float(b.mean()),'dz':float(delta.mean()/delta.std(ddof=1)) if delta.std(ddof=1)>0 else None,'p_exact':mod.exact_signed_rank_pvalue(delta),'participant_ids':pvt.index.tolist(),'paired_differences':delta.tolist()})
            if metric == 'nasa_workload_5d':
                output[-1]['A_using_0_to_10_scale'] = float(a.mean()-1/6)
                output[-1]['other_using_0_to_10_scale'] = float(b.mean()-1/6)
        for row,p in zip(output,holm([r['p_exact'] for r in output])):
            row['holm_within_table'] = p
        results[source] = output
    all_rows = results['dag']+results['evidence']
    for row,p in zip(all_rows,holm([r['p_exact'] for r in all_rows])):
        row['holm_all_12_reported_tests'] = p
    return {'method':'Exact two-sided sign enumeration over average ranks of nonzero paired differences; zeros omitted and ties assigned average ranks. Holm families: each reported table (7/5), plus sensitivity over 12 reported tests. These families are retrospective, not preregistered.','scale':'Current code uses 11-performance (assumes 1–10). If actual scale is 0–10, 10-performance lowers every six-item workload average by 1/6; paired differences, dz, and paired p-values are unchanged for complete six-item records.','tables':results}


def main():
    assert holm([.03125,.00390625,.0078125,.0078125,.03125]) == [.0625,.01953125,.03125,.03125,.0625]
    assert pooled._exact_mcnemar_p(12,3) == .03515625
    technical_report,rows = technical()
    historical_report,historical_rows = technical(historical_old=True)
    report = {'technical':technical_report,'historical_replication':historical_report,'user_study':survey()}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'statistics.json').write_text(json.dumps(report,indent=2)+'\n')
    with (OUT/'case_counts.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    with (OUT/'historical_case_counts.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(historical_rows[0])); w.writeheader(); w.writerows(historical_rows)
    lines = ['# Review statistics, 2026-09-08', '',
             'Inputs are read-only. This report is separate from the paper and published metrics.', '',
             '## Provenance and reproduction', '',
             'The published table pools old33 scored with commit 733de8e and new72 scored with the current strict index resolver. The old resolver accepts k, k-1, and matching step IDs (falling back to all steps if unresolved); the current resolver accepts only zero-based k. Thus the published table is not uniformly strict same-step matching.', '',
             'Historical-rule reproduction matches all counts for Agentic GPT-5, Baseline GPT-5, and Agentic DeepSeek. Baseline DeepSeek does not reproduce: current saved old33 outputs plus new72 give 78 correct, 228/366 grounding, 240/967 HR, and 167/366 OR under the historical-old33 definition. Published values are 80 correct, 232/367, 257/967, and 175/367. Do not attach these raw-output CIs or p-values to the unreproduced published baseline row.', '',
             'The existing baseline GPT-5 overlay contains a documented manual verdict override for HOT-01-B. All calculations preserve this stored value and the published human binary adjudication; these results describe the saved benchmark, not an untouched API-only baseline.', '',
             '## Paired verdict tests', '',
             '| Model | Correct A/B | A-only/B-only | Exact p | Holm, two models |', '|---|---:|---:|---:|---:|']
    for fam,r in technical_report['paired_verdict'].items():
        lines.append(f"| {fam} | {r['agentic_correct']}/{r['baseline_correct']} | {r['agentic_only_correct']}/{r['baseline_only_correct']} | {r['p_exact']:.6f} | {r['holm_two_models']:.6f} |")
    for title,r in [('Historical-old33 reproduction',historical_report),('Uniform current implementation',technical_report)]:
        lines += ['', '## '+title, '', r['unit']+f'; {DRAWS:,} draws, seed {SEED}.', '', r['caveat'], '', '| System | Grounding [95% CI] | HR [95% CI] | OR [95% CI] | Grounded-only OR [95% CI] |', '|---|---:|---:|---:|---:|']
        for name,s in r['systems'].items():
            cells = [f"{v['value']*100:.2f} [{v['ci95'][0]*100:.2f}, {v['ci95'][1]*100:.2f}]" for v in s['metrics'].values()]
            lines.append('| '+name+' | '+' | '.join(cells)+' |')
        lines += ['', '| Model | Metric | A-B (pp) [95% CI] | Paired swap p | Holm, three primary metrics |', '|---|---|---:|---:|---:|']
        for fam,mm in r['paired_evidence'].items():
            for metric,v in mm.items():
                lines.append(f"| {fam} | {metric} | {100*v['difference']:.2f} [{100*v['ci95'][0]:.2f}, {100*v['ci95'][1]:.2f}] | {v['paired_swap_p']:.6f} | {v.get('holm_within_three_metrics','exploratory')} |")
    lines += ['', '## User-study ablations', '', report['user_study']['method'], '',
              'Rounding exact sixth-unit workload differences before ranking fixes a floating-point tie artifact: A/B workload p is .890625, rather than the previously reported .921875. This does not change the conclusion.', '', report['user_study']['scale']]
    for name,table in report['user_study']['tables'].items():
        lines += ['', '### '+name, '', '| Measure | Mean A | Mean other | Exact p | Holm within table | Holm across 12 ablation tests |', '|---|---:|---:|---:|---:|---:|']
        for r in table:
            lines.append(f"| {r['metric']} | {r['A']:.4f} | {r['other']:.4f} | {r['p_exact']:.6f} | {r['holm_within_table']:.6f} | {r['holm_all_12_reported_tests']:.6f} |")
        workload = table[0]
        lines += ['', f"Using 0–10 reversal, workload means become {workload['A_using_0_to_10_scale']:.4f} vs {workload['other_using_0_to_10_scale']:.4f}; paired differences and tests are unchanged."]
    (OUT/'report.md').write_text('\n'.join(lines)+'\n')
    for name,r in report.items():
        print(name, json.dumps({k:v for k,v in r.items() if k not in ('sources','paired_evidence')},indent=2))


if __name__=='__main__':
    main()
