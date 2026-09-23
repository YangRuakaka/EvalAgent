"""Two evidence-union trials, holding all case-level verdicts fixed.

Duplicate identity: case + resolved integer step_id + normalized source field
+ exact quoted text. Do not merge different excerpts or collapse by location.
"""
import copy
import json
from collections import Counter
from pathlib import Path

import analyze_dan_golden_sensitivity as shared
import compute_append_only_golden_evidence as append


OUT=shared.TE/'results/evidence_union_trial'


def key(cid,item):
    step=shared.metrics._parse_int(item.get('step_id'))
    field=shared.metrics._normalize_source_field_for_matching(item.get('field'))
    assert step is not None and field is not None, (cid,item)
    assert shared.metrics._normalize_label(item.get('verdict')) is not None, (cid,item)
    return (cid,step,field,str(item.get('text') or ''))


def main():
    reference=shared.read(shared.REPORT)
    golden_path=Path(reference['new_human_file'])
    manifest_path=shared.TE/'annotation/webharbor_72_human/assignment_manifest.json'
    manifest=shared.read(manifest_path)
    assignments={who:{c['case_id'] for c in manifest['cases'] if who in c['assigned_annotators']}
                 for who in ['Yukun','Dan','Simret']}
    assert all(len(ids)==48 for ids in assignments.values())
    original=shared.read(golden_path)
    dan=shared.read(shared.DAN)
    simret=shared.read(append.SIMRET)
    assert set(dan['annotations'])==assignments['Dan']
    assert set(simret['annotations'])==assignments['Simret']
    assert set(original['annotations'])==set().union(*assignments.values())
    source_paths=[golden_path,shared.DAN,append.SIMRET,manifest_path,Path(reference['old_human_file']),Path(shared.metrics.__file__),shared.REPORT]
    hashes=[shared.fingerprint(p) for p in source_paths]
    new_dirs=dict(shared.pooled.SYSTEMS)
    new_dirs['baseline_gpt5']=Path(reference['baseline_gpt_new_results_dir'])
    old_sources=shared.read(Path(reference['baseline_gpt_old_metrics_overlay']))['sources']
    old_dirs={name:Path(old_sources[k]) for name,k in
              [('agentic_gpt5','gpt_dir'),('baseline_gpt5','baseline_gpt_dir'),
               ('agentic_deepseek','deepseek_dir'),('baseline_deepseek','baseline_deepseek_dir')]}
    old_human=shared.metrics._load_human_cases(Path(reference['old_human_file']))
    old_scores={name:append.score(old_dirs[name],name,old_human) for name in shared.NAMES}
    original_human=shared.metrics._load_human_cases(golden_path)
    initial={name:append.score(new_dirs[name],name,original_human) for name in shared.NAMES}
    modes={}
    OUT.mkdir(parents=True,exist_ok=True)
    for mode,yukun_ids in [('all_golden72_union',set(original['annotations'])),
                           ('assigned_yukun48_union',assignments['Yukun'])]:
        result=copy.deepcopy(original)
        for item in result['annotations'].values():
            item['evidences']=[]
        seen={}
        counts=Counter()
        contributions=Counter()
        provenance=[]
        for who,document,ids in [('Yukun',original,yukun_ids),('Dan',dan,assignments['Dan']),('Simret',simret,assignments['Simret'])]:
            for cid in sorted(ids):
                for item in document['annotations'][cid].get('evidences',[]):
                    counts[who]+=1
                    identity=key(cid,item)
                    source={'annotator':who,'source_evidence_id':item.get('id'),'verdict':item.get('verdict')}
                    if identity in seen:
                        provenance[seen[identity]]['sources'].append(source)
                    else:
                        seen[identity]=len(provenance)
                        provenance.append({'case_id':cid,'step_id':identity[1],'normalized_field':identity[2],
                                           'text':identity[3],'sources':[source]})
                        result['annotations'][cid]['evidences'].append(copy.deepcopy(item))
                        contributions[who]+=1
        unique=sum(len(v['evidences']) for v in result['annotations'].values())
        assert unique==len(seen)
        for cid,old in original['annotations'].items():
            assert {k:v for k,v in result['annotations'][cid].items() if k!='evidences'}=={k:v for k,v in old.items() if k!='evidences'}
        actual_keys={key(cid,e) for cid,v in result['annotations'].items() for e in v['evidences']}
        assert actual_keys==set(seen)
        conflicts=[p for p in provenance if len({s['verdict'] for s in p['sources']})>1]
        output_path=OUT/f'{mode}.json'
        output_path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        human=shared.metrics._load_human_cases(output_path)
        systems={}
        for name in shared.NAMES:
            s=append.score(new_dirs[name],name,human)
            assert s['H']==unique and s['M']==initial[name]['M']
            if mode=='all_golden72_union':
                assert s['OR_numerator']>=initial[name]['OR_numerator']
            systems[name]={'union72':s,'union105_current_code':append.pooled(old_scores[name],s)}
        modes[mode]={'output_file':str(output_path),'included_yukun_case_ids':sorted(yukun_ids),
                     'input_counts':dict(counts),'input_total':sum(counts.values()),
                     'unique_evidence72':unique,'removed_duplicate_entries':sum(counts.values())-unique,
                     'unique_evidence105_with_old33_unchanged':unique+sum(len(c['evidence']) for c in old_human.values()),
                     'cases_with_evidence':sum(bool(c['evidence']) for c in human.values()),
                     'first_occurrence_contributions_not_exclusive_ownership':dict(contributions),
                     'duplicate_items_with_conflicting_evidence_verdicts':len(conflicts),
                     'provenance':provenance,'systems':systems}
    assert hashes==[shared.fingerprint(p) for p in source_paths]
    report={'source_files':hashes,
            'deduplication':'Exact quoted text, same case, integer step_id and normalized source field. No whitespace/case/text normalization; overlapping but non-identical quotations remain separate.',
            'duplicate_verdicts':'Evidence identity ignores its pass/fail label. First occurrence is retained; all original labels are preserved in sidecar provenance. These metrics do not require evidence verdict agreement. No adjudication is inferred.',
            'matching':'Existing grounded same-case/step/field many-to-many metric, including valid-model-verdict check for HR; not one-to-one matching.',
            'source_interpretation':'User identified golden as Yukun-authored. The assigned48 mode restricts that final export to the 48 Yukun cases in the assignment manifest; it does not recover a separate pre-adjudication export.',
            'old33_scope':'No old33 Dan/Simret evidence was added or deduplicated; the original 444 evidence items are kept. Combined105 metrics inherit known historical reproduction differences.',
            'original72':initial,'modes':modes,'validation':'All input evidence identities are represented exactly once per mode; all case-level verdicts and source files remain unchanged.'}
    (OUT/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# Deduplicated evidence union trials','',report['deduplication'],'',report['source_interpretation'],'',
           '| Scheme | Yukun items | Dan items | Simret items | Before dedup | Duplicates removed | Final72 | Final105 |',
           '|---|---:|---:|---:|---:|---:|---:|---:|']
    for mode,r in modes.items():
        c=r['input_counts']
        lines.append(f"| {mode} | {c['Yukun']} | {c['Dan']} | {c['Simret']} | {r['input_total']} | {r['removed_duplicate_entries']} | {r['unique_evidence72']} | {r['unique_evidence105_with_old33_unchanged']} |")
    for mode,r in modes.items():
        lines+=['',f'## {mode}','',f"Cases with evidence: {r['cases_with_evidence']}/72. Duplicate identities with conflicting evidence verdicts: {r['duplicate_items_with_conflicting_evidence_verdicts']}.",'',
                '| System | 72-case HR | 72-case OR | 105-case HR (current code) | 105-case OR (current code) |','|---|---:|---:|---:|---:|']
        for name,s in r['systems'].items():
            a,b=s['union72'],s['union105_current_code']
            lines.append(f"| {shared.NAMES[name]} | {a['HR_numerator']}/{a['H']} ({a['HR']:.2%}) | {a['OR_numerator']}/{a['M']} ({a['OR']:.2%}) | {b['HR_numerator']}/{b['H']} ({b['HR']:.2%}) | {b['OR_numerator']}/{b['M']} ({b['OR']:.2%}) |")
    lines+=['','## Qualifications','',report['old33_scope'],'',report['duplicate_verdicts'],'',report['validation'],'',
            'The assigned48 scheme follows the two-annotator assignment. Final verdicts are still the existing golden verdicts; evidence union does not change or replace verdict adjudication.']
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines))


if __name__=='__main__':
    main()
