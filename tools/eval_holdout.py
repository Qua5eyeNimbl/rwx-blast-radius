"""Score selector output against independently generated ground truth.
  python tools/eval_holdout.py DATA_DIR OUTPUT_JSONL GT_JSON...
Only ground-truth entries whose test run completed normally (exit0/exit1) count."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from selector import schedule
data, output, *gts = sys.argv[1:]
tests = {t['number']: t for t in json.load(open(f'{data}/tests.json'))['tests']}
gt = {}
for g in gts:
    if os.path.exists(g):
        gt.update({k: v for k, v in json.load(open(g)).items() if v['status'].split('+')[0] in ('exit0', 'exit1', 'exit2') and not v.get('unknown')})
def cost(ws):
    ws = [w for w in ws if w]
    return 0 if not ws else (max(sum(round(tests[n]['seconds']*1000) for n in w) for w in ws) + 2000*len(ws))/1000
tot = orc = 0; misses = []
for line in open(output):
    o = json.loads(line); c = o['commit']
    if c not in gt: continue
    sel = {n for w in o['workers'] for n in w}; f = set(gt[c]['failing'])
    miss = not f <= sel; k = cost(o['workers']); oc = cost(schedule(f, tests))
    tot += k + 300*miss; orc += oc
    print(f'{c:28s} cost={k:6.2f} sel={len(sel):4d} fail={len(f):3d} oracle={oc:6.2f} {"MISS "+str(sorted(f-sel)[:6]) if miss else ""}')
    if miss: misses.append(c)
print(f'n={sum(1 for _ in open(output)) and len([1 for l in open(output) if json.loads(l)["commit"] in gt])} total={tot:.2f} oracle={orc:.2f} misses={len(misses)} {misses}')
