# Handoff — RWX Blast Radius (Sat Nov 21, 2026, ~12:15 AM CT)

Start here in a new chat. Also read `CLAUDE.md` (project rules) and `README.md` (how the selector works).

- **Deadline: Sun Nov 22, 10:00 AM CT.** Submissions close then; the final is scored after.
- Track page (sign in there to submit): https://www.joinbuilders.org/buildathon/tracks/blast-radius
- Repo: https://github.com/Qua5eyeNimbl/rwx-blast-radius (public). Local: `C:\rwx-blast-radius`.

## v4 (branch `v4-narrowing`) — ready, NOT submitted

Built on v3 in a later session. **Not submitted; the user decides.** All checks pass:

| Check | v3 (`3999bb3`, board 180.3 s) | v4 (`v4-narrowing` head) |
|---|---|---|
| Public sample, Docker + organizer `RUN_FLAGS` | 118.978 s, 0 misses | **112.359 s, 0 misses** |
| Container CPU on the sample (3 runs, same machine) | 1.5–2.1 s | **0.53–0.66 s** |
| Holdout, 96 graded | 744.9 s, 0 misses | **720.4 s, 0 misses** |
| Targeted holdout, 77 graded (`benchmarks/targeted/`) | 2,062 s, **2 misses** | **496 s, 0 misses** |
| Unit tests | 21 pass | 28 pass |

Docker output is byte-identical to a local run on sample, holdout and targeted sets.
Projected practice-board score with the calibration below (`sample_sim × 40/30 × 1.12 + CPU × 1.35`):
112.359 × 1.493 + 0.55 × 1.35 ≈ **168.5 s** (v3: 180.3 s). One data point; re-fit after a submission. v4 also closes two v3 misses (import-time breakage, see 5–6 below).

### What v4 changed (all general rules, evidence in `benchmarks/targeted/`)

1. **Dict value edits ignore key-only uses.** When only values of a dict literal change,
   `k in D`, `len(D)`, truth tests are not uses. Sample `4d63` (358 → 11 tests).
2. **Literal class attribute removed/added** → traced like a value change (removed: every
   reference counts, pass-throughs too, since any read can raise). Holdout `h11_026` 1,153 → 16.
3. **Insert/delete next to a touched line** no longer swallows the neighbour: unequal
   replace ranges are re-matched by AST (`_refined`).
4. **Docstring edits** (non-empty → non-empty) select nothing: `__doc__` is only tested for
   emptiness in sqlglot and doctests are not in the collected suite (`load_tests` isn't run by pytest).
5. **Constants read through the class name** (`TimeUnit.VAR_LIKE`) are no longer intersected
   with users of the class (that intersection was wrong in v3 too; found by a labelled miss).
6. **Import-time breakage fails whole test files at collection.** The index never recorded
   collection-time imports of sqlglot modules; v4 adds a static import graph of the pinned
   source and selects every test of each file whose collection imports the broken module
   (`Index.collectors`, used by `requirers`). Fixes v3 misses `t24_defarg_001`, `t25_tmpl_000`.
7. **SQL text parsed at import** (`maybe_parse("...")`, `parse_one`, `DataType.build`, ...):
   a literal change there can break the import → requirers.
8. **Default-argument changes** → only tests that ran the function *and* a call that omits the
   parameter (all references must be direct calls; dunder/decorated functions excluded).
9. **CPU**: use traces, call sites and the collection import graph are precomputed into
   `index/trace_cache.json.gz` (`tools/build_trace_cache.py`, ~30 s). It stores a hash of the
   tracing code; on mismatch the selector traces live (same answers, slower). Unit test
   `test_trace_cache_is_fresh` fails if you edit tracing code without rebuilding.
   Also: one-pass AST indexing, cheaper scheduler search, no full dumps of class ASTs. Output identical.

**If you change selector.py tracing code, run `python tools/build_trace_cache.py`.**

## Where things stood after v3 (still the submitted score)

**Submitted and scored: 180.3 s, 0 missed commits.** Receipt `BB-7BA6EB0B`, commit
`3999bb36c86f363f7db123a335ab390e901b060b` (`v3-import-instances`), submitted Fri ~10:24 PM CT.
Three runs: 177.784 s simulated each, CPU 2.48 / 2.49 / 2.52 s, 0 misses each. It is entered in
the final as the team's best score.

Board context when we submitted (130 teams): leaders were about 152–157 s; 180.3 s placed about
13th. The gap to the top (~25 s) matches our gap to the best possible score on the sample.

### Branches

| Branch | Head | What it is |
|---|---|---|
| `main` (default) | `a93f952` | v0.1. **An empty Commit box on the submit form scores this.** |
| `v2-coverage-selector` | `81b75b9` | v2 coverage selector; known-good fallback |
| `v3-import-instances` | `3999bb3` | **v3, the scored submission** (this file's later edits sit on top) |
| `v4-narrowing` | see `git log` | **v4 candidate, not submitted, not pushed yet** (branched from v3 + handoff) |

### Numbers (local)

| Check | v2 (`81b75b9`) | v3 (`3999bb3`) |
|---|---|---|
| Public sample, Docker + organizer `RUN_FLAGS` | 118.978 s, 0 misses | **118.978 s, 0 misses** (identical output) |
| Best possible on sample (knows the failures) | 94.351 s | 94.351 s |
| Container CPU, 2.1 GHz Xeon, 3 runs | 4.0–4.7 s | **1.81–1.85 s** (board measured ~2.5 s) |
| Own holdout, 96 graded changes | 1,041.8 s, **1 miss** | **744.9 s, 0 misses** (best possible 324.4 s) |
| Unit tests (`tests_local`) | 20 pass | 21 pass |
| Repo size | 2.7 MB | 3.0 MB (limit 20 MB) |

v0.1 scored 494.3 s on the sample.

## Local number vs board number (why 119 s became 180 s)

The practice board scores **40 commits; the sample has 30.** Proof: the starter (run every test, 3 workers)
costs the same on every commit, 40.349 s (LPT over 3 workers; sample total 1,210.470 s = 30 × 40.349).
The board's starter baseline is 1,614.1 s = 40.0 × 40.349. So compare **per commit**, not totals:

| | Sample (30) | Board (40) |
|---|---|---|
| v3 simulated total | 118.978 s | 177.784 s |
| v3 per commit | 3.97 s | 4.44 s (1.12× the sample) |
| Leaders per commit | — | ~3.8–3.9 s (151.8–157 s) |
| Best possible per commit | 3.15 s | unknown |

Of the 59 s difference, ~40 s is just 10 more commits; the remaining ~19 s is the board's commits being
~12% more expensive each (one extra `test_execute_tpcds`-style commit is ~25 s). CPU: board 2.5 s vs
1.8 s here (≈1.35×).

Rough board prediction for a new version, from one data point (re-fit after each submission):
`board ≈ sample_simulated × 40/30 × 1.12 + local_CPU × 1.35`. For v3: 158.6 × 1.12 + 2.5 ≈ 180.

The final has ~1.5× the practice commits (~60), so totals there will be ~1.5× larger for everyone;
only rank matters.

## What v3 changed (vs v2)

1. **Fixed a real miss.** Holdout `h11_021` changes Join's `arg_types` (`"match_condition": False → True`).
   `DuckDBGenerator` parses SQL templates in its class body, so a `Join` is built while
   `sqlglot.generators.duckdb` imports. Making the arg required breaks that import, and every test in
   `tests/dialects` (1,020) fails at collection. v2 picked 208. The index had dropped class
   instantiations that happen during imports. `tools/build_index.py` now records them as `cls_mods`
   (MRO-expanded; the few made before tracing starts are measured with a profiler), and
   `selector.py` adds every importer of such a module for class-body edits of that class
   (`import_instancers`, `_nested_instancers`, `_expr_class_instancers`).
2. **CPU halved, output byte-identical.** `_normalised` swaps Compare ops in place instead of
   deep-copying ASTs (checked equal on all 56,329 statements of the pinned source); `_trace_uses`
   looks names up in a per-file table (`_named_nodes`) instead of re-walking files per name.
3. **Index build fixes** (`tools/trace_suite.sh`): `tail -1` with two files aborts on GNU tail before
   `build_index.py` ran; and a checkout with no `.pyc` makes imports open `.py` files, which were traced
   as data reads and would broaden selections. Now precompiles first. A clean rebuild with the fixed
   script reproduces the shipped index exactly in every field, plus `cls_mods`. The shipped
   `index.json.gz` is the old index with only `cls_mods` grafted in.
4. `tools/ground_truth.py`: `GT_TIMEOUT` env (default 900 s).
5. Holdout batch 2 fully labelled and its 40 patches committed (`benchmarks/holdout/`).
6. New unit test for the import-time instance case (fails on v2, passes on v3).

Selection changed on only 2 of 126 commits (sample + 96 graded holdout), both by adding tests.

## How the selector works (one paragraph)

`index/` was built offline from the pinned sqlglot commit only (`tools/trace_suite.sh`). That build
records per-test coverage with import/collection contexts kept separate, plus fixture reads, class
instantiations (in tests and during imports) and import requests. At runtime, `selector.py` diffs old
and new ASTs per unit: comment-only edits select nothing; changed statements select the tests that
executed them; import-time code selects every transitive importer; constants are narrowed through
traced value uses or expression-keyed dict entries; class-body edits also select importers of modules
that instantiate the class at import; data files select their readers. Unknown or unparseable input
falls back to a broad selection. Details in `README.md`.

## Rules that matter (from the track page)

- Submit: public repo URL + **40-char commit SHA**. Empty commit = newest commit on `main` (v0.1).
- **One submission per hour** to start. The page shows when the next one frees up.
- Feedback per run: simulated seconds, CPU seconds, number of missed commits. Never which commits.
- A failed build/crash/timeout is rejected with a reason and never changes the best score.
- Score = busiest worker's test seconds + 2 s per worker + 300 s per missed commit + CPU; middle of 3 runs.
- Runs: no network, 2 cores, 4 GB, read-only, user nobody, 3 min per batch (4.5 min in the final).
- **Final:** at the cutoff, the chosen commit (best unless you pick another) runs on unseen commits,
  about 1.5x as many, **including kinds of change not in practice**. Top 5+ are re-run 5 times on an
  idle machine. Scores within 1 s of the best count as tied and rank by submission time, earliest first.
- No lookup tables from patch or edit kind to failing tests; maps built from the pinned commit are fine.
  Top entries are read. Keep the repo public with every submitted commit in it until results.

## Next steps

1. **Decide whether to submit v4** (`v4-narrowing` head SHA). It beats v3 on every local check.
   One submission per hour; compare the board's misses/CPU after. If it shows misses, pick v3 back.
2. Remaining over-cost is mostly inherent to line coverage: a broadly executed line pulls in
   `test_execute_tpcds` (21.5 s). Ideas tried and dropped this session: narrowing `setUpClass`
   fixture data (TestExecutor's tpch/tpcds paths share `subtestHelper`, so static analysis
   keeps tpcds anyway). The four "1,020 dialect tests fail" holdout cases look cheap in the
   oracle only because pytest stops after a collection error; do not chase them.
3. CPU left (~0.5 s on the sample) is mostly `ast.parse` of the patched files and JSON load.
4. **Freeze well before Sun 10:00 AM CT.** Never swap a graded, working commit for an untested change
   near the cutoff.

## Environment notes (for whoever continues)

- The Claude cloud workspace had Python 3.13, uv, and Docker (start the daemon with `dockerd &`).
  Two serial `ground_truth.py` runs in parallel on its 2 cores label ~1 patch/75 s overall.
  The pinned sqlglot + venv were set up there with `uv venv -p 3.13` and `requirements.lock`.
- The shell on the Windows PC (Claude's device VM) has Python 3.10 and no Docker; use it only for git.
  Writes into `.git` from remote tools are blocked; git needs delete permission in the folder for its
  lock files. Bring changes over with `git format-patch` + `git am`.
- Labelling standard: serial full suite (`GT_WORKERS=1`). A 2-worker run of `h11_009` failed
  `test_generator_memory` that the serial run did not: order-dependent, don't label with `-n`.
- Label parity: re-grading `h11_001`/`h11_002` in a fresh environment matched the stored labels.

## Reproduce

```bash
# rebuild index (≈5 min, needs network once): clones pinned sqlglot, runs suite under tracing
tools/trace_suite.sh /tmp/indexbuild
# sample
RWX_DATA=$PWD/sample python selector.py > out.jsonl && python score.py sample sample/answers.json out.jsonl
python tools/evaluate.py sample sample/answers.json out.jsonl          # per-commit cost table
# holdout (all 100 patches; 96 labelled)
mkdir -p /tmp/h && cp sample/tests.json /tmp/h && cp -r benchmarks/holdout/commits /tmp/h/
RWX_DATA=/tmp/h python selector.py > h.jsonl && python tools/eval_holdout.py /tmp/h h.jsonl benchmarks/holdout/labels.json
# targeted holdout (v4 rules): see benchmarks/targeted/README.md; generator: tools/target_mutants.py
# new holdout patches + labels (≈80–150 s each, serial, Python 3.13 + requirements.lock)
python tools/make_mutants.py <sqlglot-checkout> <dir> <count> <seed>
GT_WORKERS=1 GT_TIMEOUT=900 python tools/ground_truth.py <sqlglot-checkout> sample/tests.json labels.json <dir>/*.patch
# unit tests
python -m unittest discover -s tests_local
# Docker with organizer flags
make sample
```

## Known caveats

- On the sample, harness labels matched the organizer labels in 4 of 5 checks. The 5th (`3utz`) differed by 4
  Teradata tests, which the selector includes anyway. Looks environment/order sensitive.
- Code that runs only once because of caching is credited only to the first test that ran it. Still the main
  blind spot. The h11_021 miss was a close relative (work done once at import time), now covered for class
  instantiations; other kinds of once-only work are not.
- Holdout: 4 of the 60 batch-1 patches have no usable label (as before).
- CPU is measured inside the container with `getrusage`; the board measured ~2.5 s vs ~1.8 s locally.
- `index/source.json.gz` packages sqlglot's MIT source (license in `index/SQLGLOT_LICENSE`).
