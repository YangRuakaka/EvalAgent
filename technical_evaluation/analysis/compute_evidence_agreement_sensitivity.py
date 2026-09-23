"""Remove unsupported golden evidence, retaining every case and model output.

This is a sensitivity analysis, not a replacement or reliability estimate.
Yukun's assigned48 selections are represented by golden per user confirmation.
"""
import copy
import json
from pathlib import Path

import analyze_dan_golden_sensitivity as shared
import compute_append_only_golden_evidence as scoring

OUT = shared.TE / 'results/evidence_agreement_sensitivity'


def identity(e, strict=False):
    value = (shared.metrics._parse_int(e.get('step_id')),
             shared.metrics._normalize_source_field_for_matching(e.get('field')))
    assert None not in value, e
    return value + ((shared.metrics._normalize_label(e.get('verdict')), ) if strict else ())


def published_score(s):
    return dict(H=s['hit_denominator'], M=s['overlap_denominator'],
                HR_numerator=s['hit_numerator'], OR_numerator=s['overlap_numerator'],
                HR=s['hit_rate'], OR=s['overlap_rate'])


def main():
    ref = shared.read(shared.REPORT)
    golden_path = Path(ref['new_human_file'])
    manifest_path = shared.TE / 'annotation/webharbor_72_human/assignment_manifest.json'
    paths = [golden_path, shared.DAN, scoring.SIMRET, manifest_path, shared.REPORT]
    before = [shared.fingerprint(p) for p in paths]
    gold = shared.read(golden_path)
    docs = {'Yukun': gold, 'Dan': shared.read(shared.DAN), 'Simret': shared.read(scoring.SIMRET)}
    assigned = {c['case_id']: c['assigned_annotators'] for c in shared.read(manifest_path)['cases']}
    original = shared.metrics._load_human_cases(golden_path)
    dirs = dict(shared.pooled.SYSTEMS)
    dirs['baseline_gpt5'] = Path(ref['baseline_gpt_new_results_dir'])
    initial = {n: scoring.score(dirs[n], n, original) for n in shared.NAMES}
    for n, s in initial.items():
        assert s == published_score(ref['new_72']['systems'][n]), (n, s)
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'sources': before, 'original72': initial, 'modes': {},
              'scope': 'Filter golden72 evidence by the original two-annotator assignment. Keep all 72 cases, model evidence, and final verdicts fixed. Old33 remains unchanged.',
              'caveats': ['Yukun assigned48 uses final golden entries as a proxy for original selections, as confirmed by the user; no independent pre-adjudication export was recovered.',
                          'Unselected evidence means lack of joint selection, not an explicit negative judgment. Step-only labels do not establish source-field selection.',
                          '105-case totals preserve published old33 contributions by subtracting reproduced original72 and adding filtered72; they are conditional aggregates, not a fresh reproduction of historical33.',
                          'Existing golden item multiplicity is retained. Matching is same case/step/normalized field, not exact quotation. OR denominator still includes all model evidence, even in cases with no retained human evidence.']}
    for mode, strict in [('joint_location_selection', False), ('joint_location_and_label', True)]:
        filtered = copy.deepcopy(gold)
        audit = []
        for cid, ann in filtered['annotations'].items():
            reviewers = assigned[cid]
            assert len(reviewers) == 2
            indexes = {who: {identity(e, strict) for e in docs[who]['annotations'][cid].get('evidences', [])} for who in reviewers}
            keep = []
            for i, e in enumerate(ann.get('evidences', [])):
                unsupported = [who for who in reviewers if identity(e, strict) not in indexes[who]]
                audit.append({'case_id': cid, 'golden_index': i, 'evidence': e, 'retained': not unsupported, 'not_selected_by': unsupported})
                if not unsupported:
                    keep.append(e)
            ann['evidences'] = keep
            assert ann['overall_assessment'] == gold['annotations'][cid]['overall_assessment']
        output = OUT / (mode + '.json')
        output.write_text(json.dumps(filtered, ensure_ascii=False, indent=2) + '\n')
        human = shared.metrics._load_human_cases(output)
        systems = {}
        for n in shared.NAMES:
            s = scoring.score(dirs[n], n, human)
            assert s['M'] == initial[n]['M'] and s['H'] <= initial[n]['H']
            assert s['OR_numerator'] <= initial[n]['OR_numerator']
            pub = published_score(ref['combined_105']['systems'][n])
            combined = {k: pub[k] - initial[n][k] + s[k] for k in ('H', 'M', 'HR_numerator', 'OR_numerator')}
            combined.update(HR=combined['HR_numerator']/combined['H'], OR=combined['OR_numerator']/combined['M'])
            systems[n] = {'filtered72': s, 'conditional105': combined, 'original105_published': pub}
        retained = sum(len(c['evidence']) for c in human.values())
        report['modes'][mode] = {'retained72': retained, 'removed72': 523-retained,
                               'cases_with_retained_evidence': sum(bool(c['evidence']) for c in human.values()),
                               'empty_cases': [cid for cid,c in human.items() if not c['evidence']],
                               'systems': systems, 'audit': audit}
    assert before == [shared.fingerprint(p) for p in paths]
    (OUT/'metrics.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    lines = ['# Evidence agreement sensitivity', '', report['scope'], '']
    for mode, r in report['modes'].items():
        lines += ['## ' + mode, '', f"Retained {r['retained72']}/523 golden72 items; removed {r['removed72']}; cases with retained evidence {r['cases_with_retained_evidence']}/72.", '']
        for scope in ['filtered72', 'conditional105']:
            lines += ['### '+scope, '', '| System | Original HR | Filtered HR | Original OR | Filtered OR |', '|---|---:|---:|---:|---:|']
            for n, v in r['systems'].items():
                old = initial[n] if scope == 'filtered72' else v['original105_published']
                new = v[scope]
                lines.append(f"| {shared.NAMES[n]} | {old['HR_numerator']}/{old['H']} ({old['HR']:.2%}) | {new['HR_numerator']}/{new['H']} ({new['HR']:.2%}) | {old['OR_numerator']}/{old['M']} ({old['OR']:.2%}) | {new['OR_numerator']}/{new['M']} ({new['OR']:.2%}) |")
            lines += ['']
    lines += ['## Qualifications', ''] + ['- '+x for x in report['caveats']]
    (OUT/'report.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
