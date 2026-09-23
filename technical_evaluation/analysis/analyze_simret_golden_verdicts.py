"""Verdict-only comparison of the Simret-named export and fixed golden labels."""

import json
from collections import Counter
from pathlib import Path

import analyze_dan_golden_sensitivity as shared


SIMRET = Path('/Users/yukun/Downloads/Simret_criteria1_annotations (3).json')
OUTPUT = shared.TE / 'results/simret_golden_verdict_sensitivity'


def verdicts(document):
    values = {str(cid): str(item.get('overall_assessment', '')).strip().lower()
              for cid, item in document['annotations'].items()}
    assert all(v in ('pass', 'fail') for v in values.values()), Counter(values.values())
    return values


def main():
    reference = shared.read(shared.REPORT)
    golden_path = Path(reference['new_human_file'])
    source = shared.read(SIMRET)
    labels = verdicts(shared.read(golden_path))
    simret = verdicts(source)
    assignment_path = shared.TE / 'annotation/webharbor_72_human/Simret/assigned_case_ids.txt'
    assigned = set(assignment_path.read_text().split())
    assert set(simret) == assigned and len(assigned) == 48
    assert set(simret) <= set(labels) and len(labels) == 72
    dirs = dict(shared.pooled.SYSTEMS)
    dirs['baseline_gpt5'] = Path(reference['baseline_gpt_new_results_dir'])
    predictions, prediction_sources = {}, {}
    for name in shared.NAMES:
        pred, _, hashes = shared.load_predictions(dirs[name])
        assert set(pred) == set(labels)
        assert sum(pred[i] == labels[i] for i in labels) == reference['new_72']['systems'][name]['correct_final_verdict_count']
        predictions[name] = pred
        prediction_sources[name] = hashes
    different = sorted(i for i in simret if simret[i] != labels[i])
    agree = sorted(set(simret) - set(different))
    observed = len(agree)/len(simret)
    expected = sum(sum(simret[i] == v for i in simret)*sum(labels[i] == v for i in simret)
                   for v in ('pass','fail')) / len(simret)**2
    pairs = Counter((simret[i],labels[i]) for i in simret)
    cohorts = {
        'shared48_vs_golden': shared.score(simret,labels,predictions),
        'agreement_only_vs_golden': shared.score(agree,labels,predictions),
        'disagreements_only_vs_golden': shared.score(different,labels,predictions),
        'shared48_vs_simret': shared.score(simret,simret,predictions),
        'webharbor72_excluding_simret_golden_disagreements': shared.score(set(labels)-set(different),labels,predictions),
    }
    report = {
        'scope':'Verdicts only; Simret-named export versus user-identified Yukun final golden reference.',
        'source_files':[shared.fingerprint(p) for p in (SIMRET,golden_path,assignment_path,shared.REPORT)],
        'identity_caveat': "The filename identifies Simret and all 48 IDs exactly match Simret's assignment, but meta.annotator_id says Yukun. Attribution is based on filename and assignment and remains subject to provenance confirmation.",
        'source_meta':source.get('meta'), 'assignment_exact_match':True,
        'prediction_files':prediction_sources, 'published_new72_counts_reproduced':True,
        'shared_n':len(simret),'agreement_n':len(agree),'disagreement_n':len(different),
        'agreement_rate':observed,'cohens_kappa_vs_final_reference':(observed-expected)/(1-expected),
        'pair_counts_simret_then_golden':{f'{a}/{b}':n for (a,b),n in pairs.items()},
        'cohorts':cohorts,
        'disagreements':[{'case_id':i,'simret_verdict':simret[i],'golden_verdict':labels[i],
                           'model_verdicts':{name:predictions[name][i] for name in shared.NAMES}} for i in different],
        'limitations':['Final golden is not an independent pre-adjudication Yukun export.',
                       'No evidence metrics or evidence selections were analyzed or changed.',
                       'Unknown/missing predictions count as incorrect; labels and model outputs were held fixed.',
                       'Exact McNemar tests are two-sided and unadjusted; these are exploratory subset comparisons.'],
    }
    OUTPUT.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# Simret–golden verdict-only comparison','',report['identity_caveat'],'',
           f"Shared n = {len(simret)}; agreement n = {len(agree)} ({observed:.2%}); disagreement n = {len(different)} ({1-observed:.2%}); descriptive Cohen's kappa versus final golden = {(observed-expected)/(1-expected):.3f}.",'',
           'The 72-case model accuracy totals were reproduced for all four systems. Final golden is not an independent pre-adjudication annotation.','',
           '## Accuracy','', '| Subset | n | Agentic GPT-5 | Baseline GPT-5 | Agentic DeepSeek | Baseline DeepSeek |',
           '|---|---:|---:|---:|---:|---:|']
    for key,c in cohorts.items():
        cells=[f"{c['systems'][s]['correct']}/{c['n']} ({c['systems'][s]['accuracy']:.2%})" for s in shared.NAMES]
        lines.append(f"| {key} | {c['n']} | "+' | '.join(cells)+' |')
    lines+=['','## Paired tests','','Two-sided exact McNemar p-values, unadjusted.','',
            '| Subset | Model | Agentic-only correct | Baseline-only correct | p |','|---|---|---:|---:|---:|']
    for key,c in cohorts.items():
        for family,p in c['paired_tests'].items():
            lines.append(f"| {key} | {family} | {p['agentic_only_correct']} | {p['baseline_only_correct']} | {p['mcnemar_exact_two_sided_p_unadjusted']:.6f} |")
    lines+=['','## Verdict disagreements','','| Case | Simret | Golden | Agentic GPT-5 | Baseline GPT-5 | Agentic DeepSeek | Baseline DeepSeek |',
            '|---|---|---|---|---|---|---|']
    for d in report['disagreements']:
        lines.append(f"| {d['case_id']} | {d['simret_verdict']} | {d['golden_verdict']} | "+' | '.join(d['model_verdicts'][s] for s in shared.NAMES)+' |')
    lines+=['','## Limitations','']+[f'- {v}' for v in report['limitations']]
    lines+=['','## Sources','']+[f"- `{v['path']}`; SHA-256 `{v['sha256']}`" for v in report['source_files']]
    OUTPUT.with_suffix('.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('prediction_files','source_files')},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
