"""Repeatable evidence precision regression, not an end-to-end recruiter benchmark.

Run from the Worker root. Baseline source is loaded in memory from Git; no worktree
is changed, no credentials are read and no network request is made.
"""
import argparse
import json
from pathlib import Path
import runpy
import subprocess
import sys
import types

parser = argparse.ArgumentParser()
parser.add_argument('--baseline', default='1a25f91143e23c92a4f52be086f7430322ca1bb0')
parser.add_argument('--output')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
runpy.run_path(str(root / 'tests/conftest.py'))
current = sys.modules['entry']
baseline = types.ModuleType('baseline_entry')
source = subprocess.check_output(['git','show',args.baseline+':src/entry.py'], cwd=root).decode('utf8')
exec(compile(source, '<baseline-entry>', 'exec'), baseline.__dict__)
cases = json.loads((root/'tests/fixtures/evidence-claims.json').read_text('utf8'))
results = {}
for label,module in [('baseline',baseline),('current',current)]:
    matrix = {'true_positive':0,'false_positive':0,'true_negative':0,'false_negative':0}
    details = []
    for case in cases:
        evidence = module._wf_source_claims({'descriptionText':case['text'],'jobUrl':'https://example.org/job/1'}, [case['requirement']], case.get('args',{}))
        positive = case['requirement'] in evidence
        key = ('true_' if positive == case['expected'] else 'false_') + ('positive' if positive else 'negative')
        matrix[key] += 1
        details.append({'requirement':case['requirement'],'text':case['text'],'expected':case['expected'],'actual':positive})
    tp,fp,fn = matrix['true_positive'],matrix['false_positive'],matrix['false_negative']
    results[label] = {**matrix,'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,'cases':details}
output = {'scope':'24 labeled English source-claim regression cases; no market-wide recall claim','baseline_sha':args.baseline,'current_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'worktree_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip()),'results':results}
if args.output:
    Path(args.output).write_text(json.dumps(output,indent=2)+'\n',encoding='utf8')
print(json.dumps({label:{k:v for k,v in result.items() if k!='cases'} for label,result in results.items()},indent=2))
if results['current']['false_positive'] or results['current']['false_negative']:
    sys.exit(1)
