"""Build a self-contained, offline verdict-review page from fixed annotations."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TE = HERE.parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    reference = read(TE/'results/webharbor105_final_metrics.json')
    paths = {
        'Golden': Path(reference['new_human_file']),
        'Dan': TE/'experiments/march_binary_dan48/dan_criteria1_annotations.json',
        'Simret': Path('/Users/yukun/Downloads/Simret_criteria1_annotations (3).json'),
    }
    sources = {name: read(path) for name, path in paths.items()}
    root = TE/'annotation/webharbor_72_human'
    manifest = read(root/'assignment_manifest.json')
    cases = []
    for assigned in sorted(manifest['cases'], key=lambda c:c['case_id']):
        cid = assigned['case_id']
        candidates = [root/name/'raw_data'/f'{cid}.json' for name in ('Dan','Simret','Annalisa','Yukun')]
        raw_sources = [read(p) for p in candidates if p.exists()]
        assert raw_sources, cid
        raw = raw_sources[0]
        assert all(r['task']==raw['task'] and r['criteria1']==raw['criteria1'] and r['steps']==raw['steps'] for r in raw_sources), cid
        annotations = {}
        for name, document in sources.items():
            item = document['annotations'].get(cid)
            if item is not None:
                assert item['overall_assessment'] in ('pass','fail')
                annotations[name] = {
                    'verdict':item['overall_assessment'],
                    'reasoning':item.get('overall_reasoning') or '',
                    'step_labels':item.get('step_labels') or {},
                    'evidence':[{k:e.get(k) for k in ('step_id','field','text','verdict')} for e in item.get('evidences',[])],
                }
        assert 'Golden' in annotations
        differences = [f'{a}-{b}' for a,b in [('Dan','Golden'),('Simret','Golden'),('Dan','Simret')]]
        differences = [p for p in differences if all(x in annotations for x in p.split('-')) and annotations[p.split('-')[0]]['verdict'] != annotations[p.split('-')[1]]['verdict']]
        cases.append({'id':cid,'domain':cid.split('-')[0],'task':raw['task'],'criterion':raw['criteria1'],
                      'persona_value':raw.get('persona_value',''),'persona':raw.get('persona',''),
                      'assigned':assigned['assigned_annotators'],'annotations':annotations,
                      'differences':differences,'steps':raw['steps']})
    counts={p:sum(p in c['differences'] for c in cases) for p in ['Dan-Golden','Simret-Golden','Dan-Simret']}
    assert len(cases)==72 and counts=={'Dan-Golden':9,'Simret-Golden':27,'Dan-Simret':12}, counts
    dataset={'schema':'evalagent-verdict-review-dataset-v1','cases':cases,'pair_counts':counts,
             'sources':{name:{'file_name':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()} for name,path in paths.items()},
             'notes':['Golden 是 Yukun 完成仲裁后的最终参考标签，不是第三份独立原始标注。',
                      'Yukun 原始分配的 48 cases 与 golden 对应部分完全一致（用户已确认）。',
                      'Simret 文件内部 annotator_id 写为 Yukun；用户已确认该文件为 Simret 标注。',
                      '本页只包含具备 Dan / Simret 对照数据的 72-case 集合；旧 33 cases 不在本次复核范围。']}
    dataset['id']=hashlib.sha256(json.dumps(dataset,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
    payload=json.dumps(dataset,ensure_ascii=False).replace('<','\\u003c')
    template=(HERE/'template.html').read_text(encoding='utf-8')
    assert template.count('__DATA_JSON__')==1
    (HERE/'index.html').write_text(template.replace('__DATA_JSON__',payload),encoding='utf-8')
    print(json.dumps({'output':str(HERE/'index.html'),'cases':len(cases),'disagreements':sum(bool(c['differences']) for c in cases),'pairs':counts,'dataset_id':dataset['id']},ensure_ascii=False))


if __name__=='__main__':
    main()
