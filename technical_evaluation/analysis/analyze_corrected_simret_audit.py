"""Descriptive agreement and sensitivity with user-supplied audit export.

The file is explicitly a revised audit export, not assumed independent labels.
"""
import copy
import json
from pathlib import Path
from collections import Counter
import numpy as np
import analyze_dan_golden_sensitivity as s
from test_dan_reference_sensitivity import counts, infer, holm
from compute_evidence_agreement_sensitivity import identity, published_score

INPUT=Path('/Users/yukun/Downloads/Simret_audit.json')
OUT=s.TE/'results/corrected_simret_audit_sensitivity'


def kappa_pairs(rows):
    n=len(rows); agree=sum(a==b for a,b in rows)
    totals=Counter(x for pair in rows for x in pair)
    pe=sum((totals[v]/(2*n))**2 for v in ('pass','fail'))
    pcohen=sum(sum(a==v for a,b in rows)*sum(b==v for a,b in rows) for v in ('pass','fail'))/n**2
    return {'cases':n,'agreements':agree,'disagreements':n-agree,'observed':agree/n,
            'pooled_label_counts':dict(totals),'fleiss_kappa':(agree/n-pe)/(1-pe),
            'cohen_kappa':(agree/n-pcohen)/(1-pcohen)}


def main():
    ref=s.read(s.REPORT); gp=Path(ref['new_human_file'])
    manifest_path=s.TE/'annotation/webharbor_72_human/assignment_manifest.json'
    source_paths=[INPUT,gp,s.DAN,manifest_path,s.REPORT]
    hashes=[s.fingerprint(p) for p in source_paths]
    source=s.read(INPUT)
    gold=s.metrics._load_human_cases(gp); dan=s.metrics._load_human_cases(s.DAN); sim=s.metrics._load_human_cases(INPUT)
    who={'Yukun':gold,'Dan':dan,'Simret':sim}
    assignments={c['case_id']:c['assigned_annotators'] for c in s.read(manifest_path)['cases']}
    assert len(gold)==72 and len(sim)==len(dan)==48
    for name in ('Dan','Simret'):
        assert set(who[name])=={cid for cid,a in assignments.items() if name in a}
    assert all(c['overall_assessment'] in ('pass','fail') for h in who.values() for c in h.values())
    rows=[]; discrepant=[]; any_vs_gold=[]
    for cid,names in assignments.items():
        a,b=[who[n][cid]['overall_assessment'] for n in names];rows.append((a,b))
        if a!=b:discrepant.append(cid)
        if a!=gold[cid]['overall_assessment'] or b!=gold[cid]['overall_assessment']:any_vs_gold.append(cid)
    agreement=kappa_pairs(rows);agreement.pop('cohen_kappa')
    pairwise={}
    for a,b in [('Dan','Yukun'),('Simret','Yukun'),('Dan','Simret')]:
        ids=sorted(cid for cid,names in assignments.items() if a in names and b in names)
        pairwise[a+'-'+b]={'ids':ids,**kappa_pairs([(who[a][cid]['overall_assessment'],who[b][cid]['overall_assessment']) for cid in ids])}
    comparisons={name:kappa_pairs([(h[cid]['overall_assessment'],gold[cid]['overall_assessment']) for cid in h]) for name,h in [('Dan-Golden48',dan),('Simret-Golden48',sim)]}
    dirs=dict(s.pooled.SYSTEMS);dirs['baseline_gpt5']=Path(ref['baseline_gpt_new_results_dir'])
    outputs={n:s.load_predictions(dirs[n]) for n in s.NAMES}
    for n,o in outputs.items():assert set(o[0])==set(gold)
    report={'sources':hashes,'provenance':{'meta':source.get('meta'),'audit_note':source.get('audit',{}).get('note'),
             'reviews':len(source.get('audit',{}).get('reviews',{})),'history':len(source.get('audit',{}).get('history',[]))},
            'agreement72_descriptive':agreement,'original_assignment_pairs':pairwise,'versus_final_reference':comparisons,
            'assigned_pair_disagreement_ids':discrepant,'any_assigned_vs_golden_disagreement_ids':any_vs_gold,
            'evidence':{},'verdict':{},'model_sources':{n:o[2] for n,o in outputs.items()}}
    references={'golden72':gold,'supplied_simret48':sim}
    for strict in (False,True):
        human=copy.deepcopy(gold)
        for cid,c in human.items():
            indexes=[{identity(e,strict) for e in who[name][cid]['evidence']} for name in assignments[cid]]
            c['evidence']=[e for e in c['evidence'] if all(identity(e,strict) in idx for idx in indexes)]
        references['joint_location_label72' if strict else 'joint_location72']=human
    OUT.mkdir(parents=True,exist_ok=True)
    for title,human in references.items():
        ids=sorted(human)
        arrays={n:np.array([counts(outputs[n][1][cid],human[cid]) for cid in ids],dtype=np.int64) for n in s.NAMES}
        totals={n:dict(zip(['HR_numerator','H','OR_numerator','M'],map(int,a.sum(axis=0)))) for n,a in arrays.items()}
        for t in totals.values():t.update(HR=t['HR_numerator']/t['H'],OR=t['OR_numerator']/t['M'])
        if title=='golden72':
            assert all(totals[n]==published_score(ref['new_72']['systems'][n]) for n in s.NAMES)
        tests=[]
        for family in ('gpt5','deepseek'):
            for metric,ni,di in [('HR',0,1),('OR',2,3)]:
                tests.append(dict(model=family,metric=metric,**infer(arrays['agentic_'+family],arrays['baseline_'+family],ni,di)))
        holm(tests)
        result={'case_count':len(ids),'human_evidence':sum(len(c['evidence']) for c in human.values()),'cases_with_evidence':sum(bool(c['evidence']) for c in human.values()),'totals':totals,'tests':tests}
        if len(ids)==72:
            result['conditional105']={}
            for n,t in totals.items():
                pub=published_score(ref['combined_105']['systems'][n]);base=published_score(ref['new_72']['systems'][n])
                p={k:pub[k]-base[k]+t[k] for k in ('H','M','HR_numerator','OR_numerator')}
                p.update(HR=p['HR_numerator']/p['H'],OR=p['OR_numerator']/p['M']);result['conditional105'][n]=p
        report['evidence'][title]=result
    cohorts={'golden72':gold,'assigned_pair_agreement_only':{cid:c for cid,c in gold.items() if cid not in discrepant},
             'all_assigned_and_golden_agree':{cid:c for cid,c in gold.items() if cid not in any_vs_gold},'supplied_simret48':sim}
    for title,h in cohorts.items():
        labels={cid:c['overall_assessment'] for cid,c in h.items()}
        evaluated=s.score(h,labels,{n:o[0] for n,o in outputs.items()})
        tests=[dict(model=f,p=t['mcnemar_exact_two_sided_p_unadjusted']) for f,t in evaluated['paired_tests'].items()];holm(tests)
        evaluated['holm_tests']=tests;report['verdict'][title]=evaluated
    report['limitations']=['Uploaded file is Simret_revised with 48 review records and 385 history entries, not established independent pre-adjudication annotation. Agreement is descriptive post-revision unless provenance is clarified.',
      'Yukun48 is represented by matching final-golden entries per user confirmation, not recovered from a separate original export.',
      'No verified original dual annotations for old33 were supplied; no Fleiss kappa105 calculated.',
      'Reference selection filters remove non-joint evidence locations, not necessarily explicit negative judgments; all model evidence stays in OR denominator.',
      'Evidence tests: 100000 paired case-level randomizations, two-sided, Holm across four comparisons within each scenario; paired case-bootstrap unadjusted95% CIs. Post hoc analysis; assumes case exchangeability, does not model shared-task clustering.',
      '105 scores condition on published old33 contributions; inferential tests use raw72 or48 only.',
      'Reference-construction sensitivity is not an overlap-threshold analysis and does not itself eliminate lead-annotator bias.']
    assert hashes==[s.fingerprint(p) for p in source_paths]
    (OUT/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    lines=['# Supplied Simret audit: descriptive agreement and sensitivity','',json.dumps(report['provenance'],ensure_ascii=False),'',
           '## Fleiss72',json.dumps(agreement), '', '## Original assignment pair agreement']
    for name,r in pairwise.items():lines.append(name+': '+json.dumps({k:v for k,v in r.items() if k!='ids'}))
    lines+=['','## Versus final golden',json.dumps(comparisons),'','Assigned-pair disagreements: '+', '.join(discrepant),'Any assigned vs golden disagreement: '+', '.join(any_vs_gold)]
    for title,r in report['evidence'].items():
        lines+=['','## Evidence '+title,f"Human evidence {r['human_evidence']}; nonempty cases {r['cases_with_evidence']}/{r['case_count']}",'','| Model | Metric | Agentic | Baseline | Difference pp [95% CI] | p raw | p Holm |','|---|---|---:|---:|---:|---:|---:|']
        for t in r['tests']:
            lo,hi=t['paired_case_bootstrap_95ci_pp'];lines.append(f"| {t['model']} | {t['metric']} | {t['agentic_n']}/{t['agentic_d']} ({t['agentic']:.2%}) | {t['baseline_n']}/{t['baseline_d']} ({t['baseline']:.2%}) | {t['difference_pp']:.2f} [{lo:.2f}, {hi:.2f}] | {t['p']:.6f} | {t['p_holm']:.6f} |")
        if 'conditional105' in r:
            lines+=['','Conditional105 (old33 unchanged):']+[f"- {n}: HR {t['HR_numerator']}/{t['H']} ({t['HR']:.2%}); OR {t['OR_numerator']}/{t['M']} ({t['OR']:.2%})" for n,t in r['conditional105'].items()]
    for title,r in report['verdict'].items():
        lines+=['','## Verdict '+title]+[f"- {n}: {t['correct']}/{t['n']} ({t['accuracy']:.2%})" for n,t in r['systems'].items()]+[json.dumps(r['holm_tests'])]
    lines+=['','## Limitations']+['- '+x for x in report['limitations']]
    (OUT/'report.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines))


if __name__=='__main__':main()
