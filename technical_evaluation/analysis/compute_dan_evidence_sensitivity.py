"""Dan versus fixed golden evidence; no Simret input. Preserve source files."""
import copy
import json
from pathlib import Path
import analyze_dan_golden_sensitivity as shared
import compute_append_only_golden_evidence as scoring
from compute_evidence_agreement_sensitivity import identity, published_score


def main():
    ref = shared.read(shared.REPORT)
    gp = Path(ref['new_human_file'])
    paths = [gp, shared.DAN, shared.REPORT]
    hashes = [shared.fingerprint(p) for p in paths]
    gold, dan = shared.read(gp), shared.read(shared.DAN)['annotations']
    assert len(dan) == 48
    original = shared.metrics._load_human_cases(gp)
    dirs = dict(shared.pooled.SYSTEMS)
    dirs['baseline_gpt5'] = Path(ref['baseline_gpt_new_results_dir'])
    initial = {n: scoring.score(dirs[n], n, original) for n in shared.NAMES}
    assert all(initial[n] == published_score(ref['new_72']['systems'][n]) for n in shared.NAMES)
    out = shared.TE/'results/dan_evidence_sensitivity'
    out.mkdir(parents=True, exist_ok=True)
    report = {'sources': hashes, 'scope': 'Dan versus final golden on 48 shared cases. No Simret input; other24 and old33 unchanged. No case or final verdict is removed.', 'modes': {}}
    lines = ['# Dan-only evidence sensitivity', '', report['scope'], '']
    for strict in (False, True):
        mode = 'location_and_label' if strict else 'location_only'
        filtered = copy.deepcopy(gold)
        audit = []
        for cid, ann in filtered['annotations'].items():
            if cid not in dan:
                continue
            selected = {identity(e, strict) for e in dan[cid].get('evidences', [])}
            kept = []
            for i, e in enumerate(ann['evidences']):
                retain = identity(e, strict) in selected
                audit.append({'case_id': cid, 'index': i, 'retained': retain, 'evidence': e})
                if retain:
                    kept.append(e)
            ann['evidences'] = kept
        for cid, ann in filtered['annotations'].items():
            assert {k:v for k,v in ann.items() if k!='evidences'} == {k:v for k,v in gold['annotations'][cid].items() if k!='evidences'}
            if cid not in dan:
                assert ann == gold['annotations'][cid]
        path = out/(mode+'.json')
        path.write_text(json.dumps(filtered, ensure_ascii=False, indent=2)+'\n')
        human = shared.metrics._load_human_cases(path)
        result = {'compared_golden_items': len(audit), 'removed': sum(not x['retained'] for x in audit), 'retained_compared': sum(x['retained'] for x in audit), 'audit': audit, 'systems': {}}
        for n in shared.NAMES:
            score = scoring.score(dirs[n], n, human)
            assert score['M'] == initial[n]['M'] and score['OR_numerator'] <= initial[n]['OR_numerator']
            pub = published_score(ref['combined_105']['systems'][n])
            combined = {k:pub[k]-initial[n][k]+score[k] for k in ('H','M','HR_numerator','OR_numerator')}
            combined.update(HR=combined['HR_numerator']/combined['H'], OR=combined['OR_numerator']/combined['M'])
            result['systems'][n] = {'original72': initial[n], 'filtered72': score, 'published105': pub, 'conditional105': combined}
        report['modes'][mode] = result
        lines += ['## '+mode, '', f"Compared {len(audit)} golden evidence items in Dan48; removed {result['removed']}; retained {result['retained_compared']}.", '']
        for scope in ('filtered72', 'conditional105'):
            lines += ['### '+scope, '', '| System | Original HR | Filtered HR | Original OR | Filtered OR |', '|---|---:|---:|---:|---:|']
            for n, s in result['systems'].items():
                a=s['original72' if scope=='filtered72' else 'published105']; b=s[scope]
                lines.append(f"| {shared.NAMES[n]} | {a['HR']:.2%} | {b['HR_numerator']}/{b['H']} ({b['HR']:.2%}) | {a['OR']:.2%} | {b['OR_numerator']}/{b['M']} ({b['OR']:.2%}) |")
            lines += ['']
    report['limitations'] = ['Pairwise comparison to adjudicated golden, not an independent consensus benchmark.', 'No joint selection is not necessarily an explicit disagreement.', '105 aggregates preserve published old33 contributions; historical raw-output reproduction differences remain unresolved.', 'This targeted analysis does not establish that Simret annotations are invalid or justify excluding them from the primary study.']
    assert hashes == [shared.fingerprint(p) for p in paths]
    lines += ['## Limitations', '']+['- '+x for x in report['limitations']]
    (out/'metrics.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
