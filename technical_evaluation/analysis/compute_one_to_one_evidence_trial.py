"""Trial: maximum one-to-one evidence matching within case/step/field.

This changes the matching convention; it is NOT an algebraic correction to the
published metrics. Current files/helpers do not fully reproduce cached evidence
counts. Report both the trial and that discrepancy, without altering gold labels.
"""
from collections import Counter
from pathlib import Path
import json

import analyze_dan_golden_sensitivity as shared


def main():
    reference = shared.read(shared.REPORT)
    human_paths = {part: Path(reference[key]) for part,key in
                   [('old','old_human_file'),('new','new_human_file')]}
    humans = {part:shared.metrics._load_human_cases(p) for part,p in human_paths.items()}
    sources = shared.read(Path(reference['baseline_gpt_old_metrics_overlay']))['sources']
    old_dirs = {name:Path(sources[key]) for name,key in
                [('agentic_gpt5','gpt_dir'),('baseline_gpt5','baseline_gpt_dir'),
                 ('agentic_deepseek','deepseek_dir'),('baseline_deepseek','baseline_deepseek_dir')]}
    new_dirs = dict(shared.pooled.SYSTEMS)
    new_dirs['baseline_gpt5'] = Path(reference['baseline_gpt_new_results_dir'])
    results = {}
    for name in shared.NAMES:
        total = Counter()
        splits = {}
        fingerprints = []
        for part,folder in [('old',old_dirs[name]),('new',new_dirs[name])]:
            human = humans[part]
            hc = Counter()
            for cid,case in human.items():
                for item in case['evidence']:
                    sid=shared.metrics._parse_int(item.get('step_id'))
                    verdict=shared.metrics._normalize_label(item.get('verdict'))
                    field=shared.metrics._normalize_source_field_for_matching(item.get('field'))
                    if sid is not None and verdict is not None:
                        hc[(cid,sid,field)]+=1
            grounded,valid = Counter(),Counter()
            model_total = 0
            _,records,hashes = shared.load_predictions(folder)
            fingerprints.extend(hashes)
            assert set(records)==set(human)
            for cid,record in records.items():
                result=shared.metrics._extract_criteria1_result(record) or {}
                for phase in result.get('involved_steps',[]):
                    for item in phase.get('highlighted_evidence',[]):
                        text=str(item.get('highlighted_text') or '').strip()
                        if not text:
                            continue
                        model_total+=1
                        if not shared.metrics._evidence_text_is_grounded_in_record(record,text,item.get('step_index'),item.get('source_field')):
                            continue
                        ids=shared.metrics._resolve_step_id_candidates_from_record(record,item.get('step_index'))
                        assert len(ids)==1
                        key=(cid,ids[0],shared.metrics._normalize_source_field_for_matching(item.get('source_field')))
                        grounded[key]+=1
                        if shared.metrics._normalize_label(item.get('verdict')) is not None:
                            valid[key]+=1
            counts=Counter(H=sum(hc.values()),M=model_total,G=sum(grounded.values()),
                           current_HR_num=sum(n for k,n in hc.items() if k in valid),
                           current_OR_num=sum(n for k,n in grounded.items() if k in hc),
                           K=sum(min(hc[k],grounded[k]) for k in hc.keys()&grounded.keys()))
            splits[part]=dict(counts)
            total+=counts
        cached=reference['combined_105']['systems'][name]
        published={key:cached[field] for key,field in
                   [('H','hit_denominator'),('M','overlap_denominator'),('G','grounding_numerator'),
                    ('current_HR_num','hit_numerator'),('current_OR_num','overlap_numerator')]}
        results[name]={'counts':dict(total),'HR':total['K']/total['H'],'OR':total['K']/total['M'],
                       'splits':splits,'cached_original_counts':published,
                       'reproduction_differences':{k:{'current':total[k],'cached':v} for k,v in published.items() if total[k]!=v},
                       'source_files':fingerprints}
    output=shared.TE/'results/one_to_one_evidence_trial'
    report={'status':'PROVISIONAL: new matching convention; cached evidence metrics not fully reproduced',
            'definition':'K=sum over case/step/normalized-field groups of min(human count, grounded model count). HR=K/H; OR=K/M. No item is used twice; no human-model textual or verdict equality is required.',
            'meaning_of_intersection':'Matched pairs after one-to-one alignment; not literal equality of quoted strings.',
            'grounding':'Current helper: full stripped model quote is a literal substring of the cited raw step and normalized field.',
            'denominators':'H: eligible human items. M: all nonempty model quotations, including ungrounded ones.',
            'inputs':[shared.fingerprint(p) for p in [shared.REPORT,*human_paths.values(),Path(shared.metrics.__file__)]],
            'systems':results}
    output.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# One-to-one evidence trial','',report['status'],'',report['definition'],'',
           '| System | K | H | M | HR | OR |','|---|---:|---:|---:|---:|---:|']
    for name,r in results.items():
        c=r['counts']
        lines.append(f"| {shared.NAMES[name]} | {c['K']} | {c['H']} | {c['M']} | {r['HR']:.2%} | {r['OR']:.2%} |")
    lines+=['','These results are a trial under a new operational definition. They are not ready to replace the paper table until source versions and original evidence-count discrepancies are resolved.','',
            '## Reproduction discrepancies','']
    for name,r in results.items():
        lines.append(f"- {shared.NAMES[name]}: "+json.dumps(r['reproduction_differences']))
    output.with_suffix('.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines))


if __name__=='__main__':
    main()
