"""Case-paired inference on Dan48; original model outputs and labels unchanged."""
import copy
import json
from pathlib import Path
import numpy as np
import analyze_dan_golden_sensitivity as s
from compute_evidence_agreement_sensitivity import identity

B = 100000
SEED = 20260907


def counts(record, human):
    evidence = human['evidence']
    locs = {identity(e) for e in evidence}
    _, idx, _, m, overlap = s.metrics._build_model_evidence_verdict_index(
        record, True, {x[0] for x in locs}, locs)
    valid = [e for e in evidence if s.metrics._parse_int(e.get('step_id')) is not None
             and s.metrics._normalize_label(e.get('verdict')) is not None]
    return [sum(identity(e) in idx for e in valid), len(valid), overlap, m]


def holm(tests, pkey='p'):
    ordered = sorted(tests, key=lambda x:x[pkey])
    prev = 0
    for i, t in enumerate(ordered):
        prev = max(prev, min(1., (len(ordered)-i)*t[pkey]))
        t['p_holm'] = prev


def infer(a, b, numerator, denominator):
    an, ad, bn, bd = a[:,numerator], a[:,denominator], b[:,numerator], b[:,denominator]
    observed = an.sum()/ad.sum()-bn.sum()/bd.sum()
    rng = np.random.default_rng(SEED)
    extreme = 0
    cis = []
    for start in range(0, B, 2000):
        size = min(2000, B-start)
        swap = rng.integers(0, 2, size=(size,len(a)))
        # Exchange entire case-level outputs, including OR denominators.
        xn = an.sum()+swap@(bn-an); xd = ad.sum()+swap@(bd-ad)
        yn = bn.sum()+swap@(an-bn); yd = bd.sum()+swap@(ad-bd)
        null = xn/xd-yn/yd
        extreme += int(np.sum(np.abs(null)>=abs(observed)-1e-12))
        ids = rng.integers(0, len(a), size=(size,len(a)))
        delta = an[ids].sum(axis=1)/ad[ids].sum(axis=1)-bn[ids].sum(axis=1)/bd[ids].sum(axis=1)
        cis.extend(delta.tolist())
    return {'agentic_n':int(an.sum()), 'agentic_d':int(ad.sum()),
            'baseline_n':int(bn.sum()), 'baseline_d':int(bd.sum()),
            'agentic':float(an.sum()/ad.sum()), 'baseline':float(bn.sum()/bd.sum()),
            'difference_pp':float(100*observed),
            'paired_case_bootstrap_95ci_pp':(100*np.quantile(cis,[.025,.975])).tolist(),
            'p':(extreme+1)/(B+1)}


def main():
    ref = s.read(s.REPORT)
    gp = Path(ref['new_human_file'])
    gold = s.metrics._load_human_cases(gp)
    dan = s.metrics._load_human_cases(s.DAN)
    ids = sorted(dan)
    assert len(ids)==48
    dirs = dict(s.pooled.SYSTEMS)
    dirs['baseline_gpt5'] = Path(ref['baseline_gpt_new_results_dir'])
    outputs = {n:s.load_predictions(dirs[n]) for n in s.NAMES}
    hashes = [s.fingerprint(p) for p in (gp,s.DAN,s.REPORT)]
    cohorts = {'golden_on_Dan48':{cid:gold[cid] for cid in ids}, 'Dan_reference48':dan}
    for strict in (False,True):
        h = copy.deepcopy(cohorts['golden_on_Dan48'])
        for cid, c in h.items():
            locs = {identity(e,strict) for e in dan[cid]['evidence']}
            c['evidence'] = [e for e in c['evidence'] if identity(e,strict) in locs]
        cohorts['golden_Dan_shared_'+('location_label' if strict else 'location')] = h
    result = {'seed':SEED, 'resamples':B, 'case_ids':ids, 'sources':hashes,
              'model_sources':{n:o[2] for n,o in outputs.items()},
              'method':'Micro HR/OR differences; two-sided paired case-level randomization (swap complete model outputs within case), plus paired case-bootstrap percentile 95% CIs. Holm correction across four evidence comparisons within each reference scenario. Final verdict: exact two-sided McNemar, Holm across two model families per scenario. CIs unadjusted. Analyses post hoc.',
              'cohorts':{}}
    lines = ['# Dan48 reference sensitivity and paired inference','',result['method'],'']
    for title, human in cohorts.items():
        arrays = {n:np.array([counts(outputs[n][1][cid],human[cid]) for cid in ids],dtype=np.int64) for n in s.NAMES}
        assert all(a[:,1].sum()==sum(len(c['evidence']) for c in human.values()) for a in arrays.values())
        tests=[]; verdict=[]
        for fam in ('gpt5','deepseek'):
            a,b=arrays['agentic_'+fam],arrays['baseline_'+fam]
            for metric,ni,di in [('HR',0,1),('OR',2,3)]:
                tests.append(dict(model=fam,metric=metric,**infer(a,b,ni,di)))
            ac=np.array([outputs['agentic_'+fam][0][cid]==human[cid]['overall_assessment'] for cid in ids])
            bc=np.array([outputs['baseline_'+fam][0][cid]==human[cid]['overall_assessment'] for cid in ids])
            ao=int(np.sum(ac & ~bc)); bo=int(np.sum(bc & ~ac))
            verdict.append({'model':fam,'agentic_correct':int(ac.sum()),'baseline_correct':int(bc.sum()),'n':48,'agentic_only':ao,'baseline_only':bo,'p':s.exact_p(ao,bo)})
        holm(tests); holm(verdict)
        result['cohorts'][title]={'evidence_count':int(next(iter(arrays.values()))[:,1].sum()),'evidence_tests':tests,'verdict_tests':verdict,'per_case_counts':{n:a.tolist() for n,a in arrays.items()}}
        lines += ['## '+title,'',f"Human evidence items: {result['cohorts'][title]['evidence_count']}",'','| Model | Metric | Agentic | Baseline | Difference pp [95% CI] | p raw | p Holm |','|---|---|---:|---:|---:|---:|---:|']
        for t in tests:
            lo,hi=t['paired_case_bootstrap_95ci_pp']
            lines.append(f"| {t['model']} | {t['metric']} | {t['agentic_n']}/{t['agentic_d']} ({t['agentic']:.2%}) | {t['baseline_n']}/{t['baseline_d']} ({t['baseline']:.2%}) | {t['difference_pp']:+.2f} [{lo:.2f}, {hi:.2f}] | {t['p']:.6f} | {t['p_holm']:.6f} |")
        for t in verdict:
            lines.append(f"\nVerdict {t['model']}: Agentic {t['agentic_correct']}/48 vs Baseline {t['baseline_correct']}/48; discordant {t['agentic_only']}/{t['baseline_only']}; p={t['p']:.6f}, Holm p={t['p_holm']:.6f}.")
    assert hashes==[s.fingerprint(p) for p in (gp,s.DAN,s.REPORT)]
    lines += ['','These tests do not establish adjudicator correctness or eliminate adjudication bias. Dan48 is a selected subset. No Simret data is used. Location versus location+label filters test reference construction, not a numeric substring-overlap threshold. No inferential tests are provided for mixed historical105 aggregates.']
    out=s.TE/'results/dan_reference_significance'; out.mkdir(exist_ok=True,parents=True)
    (out/'metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))


if __name__=='__main__':
    main()
