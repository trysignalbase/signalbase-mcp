"""Screen recorded recruiting results, preserving the snapshot and every row.

Produces evidence per prompt, never claims a fresh DB query or model evaluation.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import runpy
import sys

parser=argparse.ArgumentParser()
parser.add_argument('--evidence-dir', required=True)
parser.add_argument('--output', required=True)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
runpy.run_path(str(root/'tests/conftest.py'))
entry=sys.modules['entry']
reports=[]
for path in sorted(Path(args.evidence_dir).glob('*.json')):
    record=json.loads(path.read_text('utf8'))
    rows=record.get('response',{}).get('data',[])
    if not isinstance(rows,list):
        continue
    tool_args={'role':'software engineer'} if path.stem.startswith('l02') else {}
    flags=[]
    for row in rows:
        if isinstance(row,dict):
            for flag in entry._wf_screen_row(row,tool_args):
                flags.append({'company':row.get('companyName'),'posting_id':row.get('id'),'url':row.get('jobUrl'),**flag})
    reports.append({'case':path.stem,'snapshot_timestamp':record.get('timestamp'),'rows':len(rows),'flag_counts':dict(Counter(flag['code'] for flag in flags)),'review_flags':flags})
result={'scope':'read-only replay of prior recorded rows; flags require evidence review and are not labeled ground truth','cases':reports}
Path(args.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
for report in reports:
    print(json.dumps({k:v for k,v in report.items() if k!='review_flags'}))
