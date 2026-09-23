"""Pairwise evidence-location agreement on the actual 72-case assignment."""
import json
import statistics
from pathlib import Path
from collections import Counter
import analyze_dan_golden_sensitivity as s


def summarize(rows):
    valid=[r for r in rows if r['jaccard'] is not None]
    values=[r['jaccard'] for r in valid]
    union=sum(r['union'] for r in rows)
    return {'cases':len(rows),'evaluable_cases':len(valid),
            'both_empty':len(rows)-len(valid),'one_empty':sum(r['one_empty'] for r in rows),
            'mean_jaccard':statistics.mean(values) if values else None,
            'sd_jaccard':statistics.stdev(values) if len(values)>1 else None,
            'median_jaccard':statistics.median(values) if values else None,
            'micro_jaccard':sum(r['intersection'] for r in rows)/union if union else None,
            'nonempty_exact_matches':sum(v==1 for v in values),
            'nonempty_zero_overlap':sum(v==0 for v in values)}


def main():
    ref=s.read(s.REPORT)
    paths={'Yukun':Path(ref['new_human_file']),'Dan':s.DAN,'Simret':Path('/Users/yukun/Downloads/Simret_audit.json')}
    manifest=s.TE/'annotation/webharbor_72_human/assignment_manifest.json'
    hashes=[s.fingerprint(p) for p in [*paths.values(),manifest]]
    docs={name:s.read(p)['annotations'] for name,p in paths.items()}
    assignments=s.read(manifest)['cases']
    assert len(assignments)==72
    who_counts=Counter(n for c in assignments for n in c['assigned_annotators'])
    assert who_counts=={'Yukun':48,'Dan':48,'Simret':48}
    rows=[]; source_counts=Counter(); location_counts=Counter()
    for c in sorted(assignments,key=lambda c:c['case_id']):
        cid=c['case_id']; names=sorted(c['assigned_annotators']); assert len(names)==2
        locations={}
        for n in names:
            items=docs[n][cid].get('evidences',[]); loc=set()
            for e in items:
                step=s.metrics._parse_int(e.get('step_id'))
                field=s.metrics._normalize_source_field_for_matching(e.get('field'))
                assert step is not None and field is not None,(cid,n,e)
                loc.add((step,field))
            locations[n]=loc;source_counts[n]+=len(items);location_counts[n]+=len(loc)
        a,b=[locations[n] for n in names]; intersection=len(a&b);union=len(a|b)
        rows.append({'case_id':cid,'annotators':names,'pair':'–'.join(names),
                     'locations':{n:sorted(loc) for n,loc in locations.items()},
                     'intersection':intersection,'union':union,'jaccard':intersection/union if union else None,
                     'one_empty':bool(a)!=bool(b)})
    grouped={pair:summarize([r for r in rows if r['pair']==pair]) for pair in sorted({r['pair'] for r in rows})}
    report={'definition':'For each case, deduplicate each assigned annotator\'s selections by raw step_id and normalized source field; Jaccard is intersection/union. Ignore quoted-text identity and evidence verdict. Macro average gives equal weight to cases. Both-empty cases excluded and counted separately; one-empty cases score zero. No use of unselected raw fields as true negatives.',
            'sources':hashes,'source_interpretation':'Uses user-designated Simret_audit.json; its export retains audit/revised metadata. Yukun uses only original assigned48 golden records, confirmed identical by user. No all-three-per-case or annotator-vs-golden comparisons are used.',
            'assignment_counts':dict(who_counts),'raw_evidence_counts':dict(source_counts),
            'deduplicated_location_counts':dict(location_counts),'overall':summarize(rows),'pairs':grouped,'cases':rows}
    assert hashes==[s.fingerprint(p) for p in [*paths.values(),manifest]]
    out=s.TE/'results/human_evidence_jaccard72';out.mkdir(exist_ok=True,parents=True)
    (out/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    lines=['# Human evidence location agreement (72 cases)','',report['definition'],'',report['source_interpretation'],'',
           '| Pair | Cases | Mean Jaccard | SD | Median | Micro Jaccard | Exact nonempty matches | Zero overlap | Both empty |',
           '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for name,r in [*grouped.items(),('Overall',report['overall'])]:
        lines.append(f"| {name} | {r['cases']} | {r['mean_jaccard']:.2%} | {r['sd_jaccard']:.4f} | {r['median_jaccard']:.2%} | {r['micro_jaccard']:.2%} | {r['nonempty_exact_matches']} | {r['nonempty_zero_overlap']} | {r['both_empty']} |")
    lines+=['','Raw evidence counts: '+json.dumps(dict(source_counts)),'Location counts: '+json.dumps(dict(location_counts)),
            '', 'This measures shared selection locations, not semantic equivalence, quote identity, label agreement, or freedom from adjudicator bias.']
    (out/'report.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines))


if __name__=='__main__':main()
