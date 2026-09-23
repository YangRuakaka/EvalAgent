"""Build a local Simret reannotation workspace; never modify input annotations."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TE = HERE.parents[1]


def main():
    base = (HERE/'index.html').read_text()
    payload = base.split('<script id="dataset" type="application/json">',1)[1].split('</script>',1)[0]
    data = json.loads(payload)
    ref = json.loads((TE/'results/webharbor105_final_metrics.json').read_text())
    paths = {'Golden':Path(ref['new_human_file']),
             'Dan':TE/'experiments/march_binary_dan48/dan_criteria1_annotations.json',
             'Simret':Path('/Users/yukun/Downloads/Simret_criteria1_annotations (3).json')}
    docs = {k:json.loads(p.read_text()) for k,p in paths.items()}
    for k,p in paths.items():
        assert hashlib.sha256(p.read_bytes()).hexdigest()==data['sources'][k]['sha256'], 'Rebuild base page first'
    for c in data['cases']:
        c['originals']={k:d['annotations'][c['id']] for k,d in docs.items() if c['id'] in d['annotations']}
    data['simret_document']=docs['Simret']
    assert len(docs['Simret']['annotations'])==48
    data['id']=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()[:20]
    output=HERE/'simret'; output.mkdir(exist_ok=True)
    html=(output/'template.html').read_text().replace('__DATA_JSON__',json.dumps(data,ensure_ascii=False).replace('<','\\u003c'))
    (output/'index.html').write_text(html)
    print(json.dumps({'output':str(output/'index.html'),'editable_cases':48,'reference_cases':72,'dataset_id':data['id']}))


if __name__=='__main__':
    main()
