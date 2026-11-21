# Handoff — RWX Blast Radius v3 (Fri Nov 20, 2026, ~10 PM CT)

Deadline: **Sun Nov 22, 10:00 AM CT**. Official rules: https://www.joinbuilders.org/buildathon/tracks/blast-radius

## State

- `main` (= v0.1, `a93f952`) untouched.
- **`v2-coverage-selector`** — `b751488` is on GitHub; `81b75b9` (handoff + 69 labels) is local only.
  Kept unchanged as the last known-good candidate.
- **`v3-import-instances`** (local, branched from `81b75b9`) — this commit:
  1. **Miss fixed.** Holdout `h11_021` (Join `arg_types` `"match_condition": False → True`) failed all 1,020
     `tests/dialects` tests at collection; v2 selected 208. Cause: `DuckDBGenerator` parses SQL templates
     in its class body, so a `Join` is built while `sqlglot.generators.duckdb` imports, and the index
     dropped class instantiations that happen during imports. `build_index.py` now records them
     (`cls_mods`, MRO-expanded, plus the few made before tracing starts, measured with a profiler);
     `selector.py` adds every importer of such a module for class-body edits of that class.
  2. **CPU ≈ halved** with byte-identical output: `_normalised` no longer deep-copies ASTs, and
     `_trace_uses` looks names up in a per-file table instead of re-walking every file per name.
  3. `trace_suite.sh`: `tail -1` with two files fails on GNU tail (script aborted before
     `build_index.py`); and a fresh checkout with no `.pyc` makes imports open `.py` files, which were
     traced as data reads and would broaden selections. Now precompiles first. A clean rebuild with the
     fixed script reproduces the shipped index exactly in every field, plus `cls_mods`.
  4. Holdout batch 2 labelled (26 more; 95 total) and its 40 patches committed.
  5. New unit test for the import-time-instance case (fails on v2, passes now).
- **Nothing pushed by me, no submission made.**

## Measured (local; not leaderboard)

| Check | v2 (`81b75b9`) | v3 (this commit) |
|---|---|---|
| Public sample, Docker + organizer `RUN_FLAGS` | 118.978 s, 0 misses | **118.978 s, 0 misses** (identical output) |
| Container CPU, 2.1 GHz Xeon, 3 runs | 4.0–4.7 s | **1.81–1.85 s** |
| Holdout, 95 graded (h7 ×56, h11 ×39) | 1,015.5 s, **1 miss** | **718.6 s, 0 misses** (oracle 298.0 s) |
| Commits whose selection changed (sample + 100 holdout) | — | 2, both only *added* tests (h11_021 fix; h7_031 +2 s) |
| Unit tests (`tests_local`) | 20 pass | 21 pass |
| Repo size | 2.7 MB | 3.0 MB |

The earlier "container CPU ≈ 0.6 s" was measured on a faster machine; the board's CPU is unknown, so
CPU is worth cutting. Label parity check: re-grading h11_001/h11_002 here matched the stored labels.

Most remaining holdout over-cost still comes from `test_execute_tpcds` (21.5 s); it stays (see v2 notes:
real failure in ~3 of 11 selections).

## How it works (one paragraph)

`index/` was built offline from the pinned sqlglot commit only (`tools/trace_suite.sh`). That build
records per-test coverage with import/collection contexts kept separate, plus fixture reads, class
instantiations and import requests. At runtime, `selector.py` diffs old and new ASTs per unit:
comment-only edits select nothing; changed statements select the tests that executed them;
import-time code selects every transitive importer; constants are narrowed through traced value uses
or expression-keyed dict entries; data files select their readers. Unknown or unparseable input
falls back to a broad selection. Details are in `README.md`.

## Next steps (in priority order)

1. **Push both branches** from PowerShell in `C:\rwx-blast-radius`:
   `git push -u origin v2-coverage-selector v3-import-instances`
2. **One practice submission** with the full SHA of `v3-import-instances` (`git rev-parse v3-import-instances`).
   Compare CPU and miss feedback with the table above. Fall back to `81b75b9` if v3 is somehow worse.
3. If the board shows misses: generate similar holdout mutations (`tools/make_mutants.py`), label them
   (`tools/ground_truth.py`), fix the rule involved, re-run sample + all holdout labels.
4. Possible cost cuts, each only with holdout evidence: string-keyed dict entries (`FUNCTIONS`,
   `SHOW_PARSERS`) narrowed by the expression classes they build; data-flow narrowing for
   class-scoped `setUpClass` fixture data. Remaining CPU is mostly `ast.parse`/parent links in `_tree`.
5. Freeze: never replace a graded green SHA with an untested change near the cutoff.

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
- Code that runs only once because of caching is credited only to the first test that ran it. It is still the
  main theoretical blind spot. The h11_021 miss was a close relative (work done once at import time), now
  covered for class instantiations; other kinds of once-only work are not.
- `GT_TIMEOUT` (default 900 s) raises ground_truth.py's per-patch limit for patches with huge failure output.
- CPU is measured inside the container with `getrusage`. The board's own CPU accounting may differ slightly.
- `index/source.json.gz` packages sqlglot's MIT source (license in `index/SQLGLOT_LICENSE`).
