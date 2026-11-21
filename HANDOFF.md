# Handoff — RWX Blast Radius v2 (Fri Nov 20, 2026, ~8 PM CT)

Deadline: **Sun Nov 22, 10:00 AM CT**. Official rules: https://www.joinbuilders.org/buildathon/tracks/blast-radius

## State

- Branch **`v2-coverage-selector`** (local, `C:\rwx-blast-radius`). `main` (= v0.1, `a93f952`) untouched.
- Commit 1: `b751488bb29abecf2a9c2dcb800cca480d172479` — v2 selector + index + tools + docs.
- Commit 2 (this handoff): evaluator fix (counts collection-error ground truth), 69 holdout labels, this file.
- **Not pushed yet.** From PowerShell: `git push -u origin v2-coverage-selector`.
- **No official submission made.** The repo is public (verified by anonymous clone).

## Measured (local; not leaderboard)

| Check | Result |
|---|---|
| Public sample, Docker + organizer `RUN_FLAGS` | **118.978 s simulated, 0 misses**, container CPU ≈ 0.6 s (3 runs) |
| v0.1 on same sample | 494.300 s |
| Perfect-knowledge floor on sample | 94.351 s |
| Independent holdout (own mutations, labels from full pinned suite) | **69 graded, 0 misses** (batch 1: 56 → 404.2 s vs 137.2 s oracle; batch 2: 13 → 105.3 s vs 49.8 s) |
| Unit tests (`tests_local`) | 20 pass |
| Scheduler | equals lower bound on every sample/holdout commit |
| Repo size | 2.7 MB |

Most remaining holdout over-cost comes from `test_execute_tpcds` (21.5 s). When selected it actually
failed in about 3 of 11 cases, so it stays: dropping it is a losing bet against a 300 s miss.

## How v2 works (one paragraph)

`index/` was built offline from the pinned sqlglot commit only (`tools/trace_suite.sh`). That build
records per-test coverage with import/collection contexts kept separate, plus fixture reads, class
instantiations and import requests. At runtime, `selector.py` diffs old and new ASTs per unit:
comment-only edits select nothing; changed statements select the tests that executed them;
import-time code selects every transitive importer; constants are narrowed through traced value uses
or expression-keyed dict entries; data files select their readers. Unknown or unparseable input
falls back to a broad selection. Details are in `README.md`.

## Next steps (in priority order)

1. **Push the branch**, then run `make sample` / `make check` on your machine (WSL + Docker) as a parity check.
2. **One practice submission** with the full SHA of the branch head. That is the only way to see
   the board's commits. Compare its CPU and miss feedback against the local numbers.
3. If the board shows misses: get the commit types from the feedback, generate similar holdout
   mutations (`tools/make_mutants.py`), label them (`tools/ground_truth.py`), and fix the rule involved.
4. Finish holdout batch 2 (27 unlabeled patches): `python tools/make_mutants.py <sqlglot> <dir>/commits 40 11`
   regenerates them deterministically; already-labelled names are skipped automatically.
5. Possible cost cuts, each only with holdout evidence: string-keyed dict entries (`FUNCTIONS`,
   `SHOW_PARSERS`) narrowed by the expression classes they build; data-flow narrowing for
   class-scoped `setUpClass` fixture data (currently every test in the class is credited).
6. Freeze: never replace a graded green SHA with an untested change near the cutoff.

## Reproduce

```bash
# rebuild index (≈5 min, needs network once): clones pinned sqlglot, runs suite under tracing
tools/trace_suite.sh /tmp/indexbuild
# sample
RWX_DATA=$PWD/sample python selector.py > out.jsonl && python score.py sample sample/answers.json out.jsonl
python tools/evaluate.py sample sample/answers.json out.jsonl          # per-commit cost table
# holdout (needs a dir with tests.json + commits/)
mkdir -p /tmp/h && cp sample/tests.json /tmp/h && cp -r benchmarks/holdout/commits /tmp/h/
RWX_DATA=/tmp/h python selector.py > h.jsonl && python tools/eval_holdout.py /tmp/h h.jsonl benchmarks/holdout/labels.json
# ground truth for new patches (≈80–150 s each, serial, pinned Python 3.13 + requirements.lock)
GT_WORKERS=1 python tools/ground_truth.py <sqlglot-checkout> sample/tests.json labels.json patches/*.patch
```

## Known caveats

- On the sample, harness labels matched the organizer labels in 4 of 5 checks. The 5th (`3utz`) differed by 4
  Teradata tests, which the selector includes anyway. This looks environment/order sensitive.
- Code that runs only once because of caching is credited only to the first test that ran it. No holdout miss has
  come from this so far, but it is the main theoretical blind spot.
- CPU is measured inside the container with `getrusage`. The board's own CPU accounting may differ slightly.
- `index/source.json.gz` packages sqlglot's MIT source (license in `index/SQLGLOT_LICENSE`).
