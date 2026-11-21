"""Local evaluation harness (never shipped in the image).  Reads the selector's
output AFTER it ran and compares it with sample answers; prints per-commit cost."""
import json, sys
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
from selector import schedule
data, answers, output = sys.argv[1:4]
tests = {t['number']: t for t in json.load(open(f'{data}/tests.json'))['tests']}
ans = json.load(open(answers))['commits']
def cost(ws):
    ws = [w for w in ws if w]
    return 0 if not ws else (max(sum(round(tests[n]['seconds']*1000) for n in w) for w in ws) + 2000*len(ws))/1000
rows = []
for line in open(output):
    o = json.loads(line); c = o['commit']; sel = {n for w in o['workers'] for n in w}
    f = set(ans[c]['failing']); miss = not f <= sel
    oracle = cost(schedule(f, tests))
    rows.append((cost(o['workers']) + 300*miss, c, ans[c]['kind'], len(sel), len(f), miss, oracle))
rows.sort(reverse=True)
for r in rows: print(f'{r[1]} {r[2]:8s} cost={r[0]:7.2f} sel={r[3]:4d} fail={r[4]:3d} {"MISS" if r[5] else ""} oracle={r[6]:.2f}')
print('total', round(sum(r[0] for r in rows), 3), 'oracle', round(sum(r[6] for r in rows), 3), 'misses', sum(r[5] for r in rows))
