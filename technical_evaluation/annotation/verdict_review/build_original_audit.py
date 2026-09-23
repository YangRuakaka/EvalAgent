"""Extend the original BLUE Simret annotation tool, preserving its CSS and DOM."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'annotation_tool/Simret/annotation_tool.html'


def main():
    html=SOURCE.read_text()
    data=json.loads((HERE/'simret/index.html').read_text().split('<script type="application/json" id="dataset">',1)[1].split('</script>',1)[0])
    data['base_tool_sha256']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    html=html.replace("const STORAGE_KEY = 'local_annotation_tool_progress_v1';", "const STORAGE_KEY = 'original-simret-audit-v1:'+AUDIT.id+(new URLSearchParams(location.search).has('test')?':qa':'');")
    payload='<script>const AUDIT='+json.dumps(data,ensure_ascii=False).replace('<','\\u003c')+';</script>'
    html=html.replace('  <script>\n    const STORAGE_KEY',payload+'\n  <script>\n    const STORAGE_KEY',1)
    old="""    window.addEventListener('beforeunload', () => {
      const payload = getProgressPayload();
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    });"""
    assert old in html
    html=html.replace(old,'    // Audit extension handles persistence without touching original tool storage.')
    extension=(HERE/'original-audit/extension.js').read_text()
    html=html.replace('</body>','<script>\n'+extension+'\n</script>\n</body>')
    (HERE/'original-audit/index.html').write_text(html)
    print('Built original-audit/index.html from '+str(SOURCE))


if __name__=='__main__':main()
