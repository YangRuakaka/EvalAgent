"""Append Dan and Simret evidence to a COPY of golden72, without deduplication.

All existing golden evidence and verdicts remain unchanged. Counts use the
existing many-to-many step/field metric, not the one-to-one trial definition.
"""
import copy
import json
from pathlib import Path

import analyze_dan_golden_sensitivity as shared


SIMRET = Path('/Users/yukun/Downloads/Simret_criteria1_annotations (3).json')
OUT = shared.TE / 'results/evidence_append_trial'


def score(folder, name, human):
    result = shared.metrics._compute_model_human_step_label_hit_rates(
        results_dir=folder, model_name=name, human_cases=human,
        require_grounded_evidence=True)
    return {'H':result['evidence_items_compared'], 'M':result['model_evidence_items_total'],
            'HR_numerator':result['evidence_hits'], 'OR_numerator':result['model_evidence_items_also_human_and_grounded'],
            'HR':result['evidence_human_label_hit_rate'], 'OR':result['model_evidence_also_human_and_grounded_rate']}


def pooled(old, new):
    result={k:old[k]+new[k] for k in ('H','M','HR_numerator','OR_numerator')}
    result.update(HR=result['HR_numerator']/result['H'], OR=result['OR_numerator']/result['M'])
    return result


def main():
    reference=shared.read(shared.REPORT)
    golden_path=Path(reference['new_human_file'])
    original=shared.read(golden_path)
    added_sources={'Dan':shared.read(shared.DAN), 'Simret':shared.read(SIMRET)}
    input_paths=[golden_path,shared.DAN,SIMRET,Path(reference['old_human_file']),shared.REPORT,Path(shared.metrics.__file__)]
    before_hashes=[shared.fingerprint(p) for p in input_paths]
    extended=copy.deepcopy(original)
    counts={'golden_original':sum(len(c.get('evidences',[])) for c in original['annotations'].values())}
    provenance=[]
    for who,source in added_sources.items():
        assigned_path=shared.TE/f'annotation/webharbor_72_human/{who}/assigned_case_ids.txt'
        assert set(source['annotations'])==set(assigned_path.read_text().split())
        assert set(source['annotations'])<=set(original['annotations'])
        counts[who]=0
        for cid,annotation in source['annotations'].items():
            items=annotation.get('evidences',[])
            assert isinstance(items,list)
            target=extended['annotations'][cid].setdefault('evidences',[])
            start=len(target)
            target.extend(copy.deepcopy(items))
            counts[who]+=len(items)
            provenance.append({'case_id':cid,'source':who,'start_index_inclusive':start,'end_index_exclusive':len(target)})
    counts['extended72']=sum(len(c.get('evidences',[])) for c in extended['annotations'].values())
    assert counts['extended72']==counts['golden_original']+counts['Dan']+counts['Simret']
    assert set(extended['annotations'])==set(original['annotations'])
    for cid,initial in original['annotations'].items():
        current=extended['annotations'][cid]
        assert current['evidences'][:len(initial.get('evidences',[]))]==initial.get('evidences',[])
        assert {k:v for k,v in current.items() if k!='evidences'}=={k:v for k,v in initial.items() if k!='evidences'}
    for entry in provenance:
        actual=extended['annotations'][entry['case_id']]['evidences'][entry['start_index_inclusive']:entry['end_index_exclusive']]
        assert actual==added_sources[entry['source']]['annotations'][entry['case_id']].get('evidences',[])

    OUT.mkdir(parents=True,exist_ok=True)
    extended_path=OUT/'golden72_plus_dan_simret_evidence.json'
    extended_path.write_text(json.dumps(extended,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    base=shared.metrics._load_human_cases(golden_path)
    augmented=shared.metrics._load_human_cases(extended_path)
    old=shared.metrics._load_human_cases(Path(reference['old_human_file']))
    old_counts=sum(len(c['evidence']) for c in old.values())
    counts.update(old33=old_counts,extended105=old_counts+counts['extended72'])
    source_dirs=shared.read(Path(reference['baseline_gpt_old_metrics_overlay']))['sources']
    old_dirs={name:Path(source_dirs[key]) for name,key in
              [('agentic_gpt5','gpt_dir'),('baseline_gpt5','baseline_gpt_dir'),
               ('agentic_deepseek','deepseek_dir'),('baseline_deepseek','baseline_deepseek_dir')]}
    new_dirs=dict(shared.pooled.SYSTEMS)
    new_dirs['baseline_gpt5']=Path(reference['baseline_gpt_new_results_dir'])
    systems={}
    for name in shared.NAMES:
        initial=score(new_dirs[name],name,base)
        added=score(new_dirs[name],name,augmented)
        old_score=score(old_dirs[name],name,old)
        published=reference['new_72']['systems'][name]
        assert initial['HR_numerator']==published['hit_numerator']
        assert initial['OR_numerator']==published['overlap_numerator']
        assert initial['H']==counts['golden_original'] and added['H']==counts['extended72']
        assert added['M']==initial['M'] and added['OR_numerator']>=initial['OR_numerator']
        systems[name]={'original72':initial,'appended72':added,'unchanged_old33_current_code':old_score,
                       'original105_current_code':pooled(old_score,initial),
                       'appended105_current_code':pooled(old_score,added)}
    assert before_hashes==[shared.fingerprint(p) for p in input_paths]
    report={'status':'Append-only sensitivity trial, not a replacement for the adjudicated reference',
            'method':'Existing many-to-many matching, same case/step/normalized field and grounded model quotations; HR additionally requires valid model evidence verdict. No agreement between evidence verdicts is required.',
            'append_policy':'Retain every original entry and append all Dan and Simret entries, including duplicates and conflicting evidence verdicts; no deduplication or adjudication. All golden case-level verdicts and other fields are preserved.',
            'simret_identity':'User confirmed that the Simret-named file is Simret-authored despite its Yukun metadata field.',
            'counts':counts,'source_files':before_hashes,'append_provenance':provenance,'systems':systems,
            'validation':{'source_files_unchanged':True,'golden_verdicts_unchanged':True,
                          'original_evidence_preserved_as_prefix':True,'all_appended_items_retained_exactly':True,
                          'all_four_original72_results_reproduced':True},
            'limitations':['Combined105 uses current old33 files and helpers; previously identified differences from cached old33/105 results remain unresolved.',
                           'Adding human evidence expands eligible model match locations, so OR cannot decrease with fixed model outputs. HR can rise or fall because both its numerator and denominator grow.',
                           'Duplicates remain separate human items and therefore increase their locations\' weight in HR. This is concatenation of evidence lists, not a deduplicated union.',
                           'Neither the source golden file nor the manuscript was changed.']}
    (OUT/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# Append-only Dan + Simret evidence trial','',report['append_policy'],'',
           f"Human evidence: original golden72 {counts['golden_original']} + Dan {counts['Dan']} + Simret {counts['Simret']} = {counts['extended72']}. With unchanged old33 ({old_counts}), total = {counts['extended105']}.",'',
           '## 72 cases: original versus appended','','| System | Original HR | Appended HR | Original OR | Appended OR |','|---|---:|---:|---:|---:|']
    for name,r in systems.items():
        b,a=r['original72'],r['appended72']
        lines.append(f"| {shared.NAMES[name]} | {b['HR_numerator']}/{b['H']} ({b['HR']:.2%}) | {a['HR_numerator']}/{a['H']} ({a['HR']:.2%}) | {b['OR_numerator']}/{b['M']} ({b['OR']:.2%}) | {a['OR_numerator']}/{a['M']} ({a['OR']:.2%}) |")
    lines+=['','## 105 cases using current old33 data and code','','Historical reproduction discrepancies remain unresolved.','',
            '| System | Original HR | Appended HR | Original OR | Appended OR |','|---|---:|---:|---:|---:|']
    for name,r in systems.items():
        b,a=r['original105_current_code'],r['appended105_current_code']
        lines.append(f"| {shared.NAMES[name]} | {b['HR_numerator']}/{b['H']} ({b['HR']:.2%}) | {a['HR_numerator']}/{a['H']} ({a['HR']:.2%}) | {b['OR_numerator']}/{b['M']} ({b['OR']:.2%}) | {a['OR_numerator']}/{a['M']} ({a['OR']:.2%}) |")
    lines+=['','## Interpretation','']+[f'- {s}' for s in report['limitations']]
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines))
    print('Output:',OUT)


if __name__=='__main__':
    main()
