# Handoff — RWX Blast Radius (Sat Nov 21, 2026, ~12:35 AM CT)

Start here in a new chat. Also read `CLAUDE.md` (project rules) and `README.md` (how the selector works).

- **Deadline: Sun Nov 22, 10:00 AM CT.** Submissions close then; the final is scored after.
- Track page (sign in there to submit): https://www.joinbuilders.org/buildathon/tracks/blast-radius
- Repo: https://github.com/Qua5eyeNimbl/rwx-blast-radius (public). Local: `C:\rwx-blast-radius`.
- Pushing: only the user's own PowerShell has GitHub credentials (`git push origin <branch>`);
  the cloud workspace and the device VM shell cannot push. Do not submit without the user's OK.

## Board status (Sat 1:31 AM CT)

| Receipt | Commit | Score | Simulated | CPU (3 runs) | Misses |
|---|---|---|---|---|---|
| **BB-2670E479** | `1c3bf4c` (v4, `v4-narrowing`) | **178.7 s — entered (best)** | 177.784 s | 0.92 / 0.89 / 1.07 | 0 |
| BB-7BA6EB0B | `3999bb3` (v3) | 180.3 s | 177.784 s | 2.48 / 2.49 / 2.52 | 0 |

Leaderboard (168 teams, Sat ~12:30 AM): 1st **146.3 s**, 2nd 149.7, 3rd 151.8, 5th 160.2, 10th 168.1.
We are ~18th–19th. The user wants 1st (asked for "aim for 70"; that is below any perfect-selection
floor: sample best possible is 94.351 s for 30 commits; the board has 40).

**Key lesson from v4's board run:** simulated time was *identical* to v3 (177.784 s). None of the
board's 40 commits hit any v4 rule; all of v4's gain was CPU (2.5 → 0.9 s). So:
- the board does not contain the sample commits (sample `4d63` alone would have saved ~6 s);
- the calibration "board ≈ sample × 40/30 × 1.12" predicted 168.5 s and was **wrong** — don't use it;
- the gap to 1st is ~31 s of *simulated* time. Our sample gap to perfect is only 18 s over 30
  commits, so the board likely has a few commits where we pay ~25 s for `test_execute_tpcds`
  (21.5 s) without it failing. Prime suspect, unverified.

The user asked to "cheat if needed"; that was declined (rules ban patch/edit-kind→failing-test
tables, entries are read, sample answers can't go in the image). Legitimate risk bets
(selecting nothing / dropping a test when failure looks unlikely) are allowed but are the
user's decision: the final is ~60 unseen commits, top 5 re-run 5×, one miss = +300 s.

## v4 (branch `v4-narrowing`) — submitted, 178.7 s (see Board status)

Built on v3. Local checks:

| Check | v3 (`3999bb3`, board 180.3 s) | v4 (`v4-narrowing` head) |
|---|---|---|
| Public sample, Docker + organizer `RUN_FLAGS` | 118.978 s, 0 misses | **112.359 s, 0 misses** |
| Container CPU on the sample (3 runs, same machine) | 1.5–2.1 s | **0.53–0.66 s** |
| Holdout, 96 graded | 744.9 s, 0 misses | **720.4 s, 0 misses** |
| Targeted holdout, 77 graded (`benchmarks/targeted/`) | 2,062 s, **2 misses** | **496 s, 0 misses** |
| Unit tests | 21 pass | 28 pass |

Docker output is byte-identical to a local run on sample, holdout and targeted sets.
The board result (178.7 s) shows these selection gains did not apply to the board's commits;
only the CPU gain did. They still matter for the final's unseen commits (and v4 fixes two v3 misses). v4 also closes two v3 misses (import-time breakage, see 5–6 below).

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

## Where things stood after v3 (history; v4 is now the entered score)

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
| `v4-narrowing` | `1c3bf4c`+ | **v4, scored 178.7 s, entered** (later commits on it are handoff edits only) |

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

**Superseded:** the prediction formula below failed for v4 (predicted 168.5 s, got 178.7 s; the
board's commits are not the sample's). Keep only the 40-vs-30 commit count.

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

1. **Find what the board's commits cost us.** We can't see them; reason from the sample (same
   organizer generator) and our own mutants. Prime target: commits that change broadly executed
   parser/generator/optimizer lines pull in `test_execute_tpcds` (21.5 s; ~25 s per commit).
   On the sample it was selected 3× and really failed 2× (`3utz`, `2jrq`), so never-select is not
   safe. Look for *provable* cases where a change can't reach it (paths its queries never take),
   validate on labelled mutants (`tools/ground_truth.py`), then offer the user a submission.
2. **Optional diagnostic submission (user's call):** a variant that never selects
   `test_execute_tpcds`. The board's change in simulated seconds and misses shows how many board
   commits pay for it and how often it really fails there. Legal (board feedback only), but it
   will show misses on the board; the best score stays entered. Practice commits ≠ final commits.
3. **Risk bets (user's call only):** e.g. select nothing for commits whose only selected tests
   execute a boundary-only change. Need ~1% failure odds to pay off at 2–6 s per commit; our 173
   labelled patches can't measure odds that small. If built, keep on its own branch, report
   savings and would-be misses on all labelled sets, and let the user choose.
4. **CPU:** board 0.9 s vs ~0.55 s local; remaining cost is `ast.parse` of patched files and JSON
   loading of `index.json.gz` (~0.08 s; a faster format is possible).
5. **Final entry:** the best score is entered automatically. Before the cutoff confirm the entered
   commit is the one wanted; never leave a commit with board misses as the chosen one.
   **Freeze well before Sun 10:00 AM CT.**

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

## v5 (Sat Nov 21 ~2:30 AM CT) — in-container verification + TPC replay (NOT submitted)

Track rules allow it: "running sqlglot's tests while you decide is allowed and charged here".
- `runner.py` (T1): forked child per commit, patched modules served from memory over the pinned
  tree in `/app/sq` (fetched at build by `build/fetch_sqlglot.py`, verified against
  `index/source.json.gz`), candidate tests run with unittest; only tests seen PASSING are dropped.
  Process pools run inline (pickle round trip); subprocess/process start or reading a patched
  file taints (sticky); RSS watchdog 1.5 GB; wall cap 100 s.
- `replay.py` (T2): TPC-DS/TPC-H executor tests. Replays parse/pickle/optimize/Plan + DuckDB
  transpile and compares structural digests with pinned ones (built in Docker, `PYTHONHASHSEED=0`
  is required: one TPC-DS plan depends on set order). Queries whose plan differs, or whose
  pinned phase-2 coverage (`index/replay_cov.json.gz`, `tools/build_replay_cov.py`) hits a changed
  line, are re-executed with the test's own code; early exit over budget. Only for
  function-body changes not executed at import.
- Parity (verify-all mode, every eligible commit): sample 13, holdout 56, targeted 56 commits,
  **0 violations** (no labelled-failing test ever reported passing).
- Production image, organizer flags, local: sample 103.165 s + 2.62 s CPU, 0 misses (v4: 112.359
  + 0.39); holdout 669.4 s, 0 misses, CPU 22; targeted 470.3 s, 0 misses, CPU 9.4.
- CPU calibration: board ≈ 2.4× this PC (v3 1.00 s here / 2.49 board; v4 0.387 / 0.92), so the
  realistic board gain is only ~4 s on sample-like commits. Policy constants in `selector.py`.

### Next (biggest remaining lever, half-built)
Import-time changes (DuckDB etc. parse SQL at import) make the selector add every transitive
user (1,100–1,600 tests incl. test_max_nodes 28.8 s): ~120 s of holdout waste in 5 commits.
Plan: in the child, import all sqlglot modules in sorted order with the patch: raises → select
core ∪ collectors ∪ requirers only; state digest equal → drop the import-time part; else keep.
`replay.import_states` exists but is NOT deterministic yet (dialect/typing modules differ run to
run even with seed 0 — find the id/order-dependent attribute) and is not wired in.

## v6 (Sat Nov 21 ~5 AM CT) — TPC replay for constant/binding changes and setup-only fixtures (NOT submitted)

Floor analysis (cost of the labelled failing set, optimally scheduled): sample 94.35 s vs v5 103.17 s,
so the sample is nearly exhausted (the rest is 4d63/5y72, where running the tests costs more CPU than
it saves). Holdout/targeted were 345 s / 274 s above floor; `test_execute_tpcds` (21.5 s) kept while
passing was the largest share (102 s / 62 s). v6 extends T2:
- class/module-level bindings and signature changes outside `sqlglot/executor/`: every reference of
  the bound names (selector `_trace_uses`, through pass-throughs) plays the role of the changed lines
  (must not run at import, must not be in the test's shared phase 2; queries whose phase 2 reaches them
  are re-executed); names ending `_sql` and dunders refused; references in the TPC tests' own files refuse.
- `replay.state_check`: in the child, import every sqlglot module (patched) and compare a per-attribute
  digest map (`flat_state`, 17k entries, pinned at build into /app/state_expected.json) with the
  pinned one; only entries bound to the changed names may differ (catches derived state, import
  raises). Order-insensitive for class-keyed dicts and class tuples (built from sets: per-process
  order); loggers by name/level; unittest imported first (`expressions.core.UNITTEST`).
- `tpc-h.sql` change → tpcds eligible, `tpc-ds.sql` → the TPC-H tests: setUpClass only loads it;
  the child checks the patched text loads (`replay.fixture_loads`). No T1 tests for data-file patches.
- Parity (verify-all): targeted 58, holdout 62 commits, 0 violations.
- Production (organizer flags, local): sample 103.165 s, CPU 2.55, 0 misses (unchanged);
  holdout 636.8 s (v5 669.4), CPU 28.5 (22.1), 0 misses; targeted 455.1 s (470.3), CPU 15.1 (9.4),
  0 misses. Net at board CPU rate ≈ −17 s holdout, −2.5 s targeted.
- Import-time "state equal ⇒ drop importers" lever measured: ~1 s on holdout, not pursued.

## Board results Sat 8:44–10:00 AM CT: v6 and the tpcds probe

| Receipt | Commit | Score | Simulated | CPU | Misses |
|---|---|---|---|---|---|
| BB-0A4A75A1 | `09759be` (v6) | 179.9 s | 175.776 s | 4.09 | 0 |
| BB-0E108FFD | `dff804c` (probe: v4 minus `test_execute_tpcds`) | 421.8 s | 420.971 s | 0.85 | 1 |

- v6 saved 2.0 s simulated on the board but cost +3.2 s CPU: net worse than v4 (178.7 s stays entered).
- Probe: `test_execute_tpcds` costs 177.784 − 420.971 + 300 × 1 = **56.8 s** on the board and really
  fails on exactly **1** board commit. So most of the gap to the leaders (126–131 s) is tpcds kept while
  passing, on commits v6's replay refused. Leaders: Aqua 126.1, 67 130.7, 1212 135.3 (Sat 10 AM).
- Second probe ready, not pushed: `6c45c26` on `probe-heavy4` = v4 minus qualify_columns,
  annotate_funcs, max_nodes, generator_memory (they fail on 4 sample commits, so expect misses; the
  same formula gives their board waste).

## v7 (Sat ~1 PM CT) — tpcds replay for import-time changes and mixed fixture/test edits (NOT submitted)

Why v6 refused labelled tpcds-passing commits: changed lines or bound names that also run at import
(dialect class bodies parse SQL templates through the parser), and any patch that also touched a file
outside `sqlglot/` (sample `986c`, `bvw2`, `rszg` mix code with optimizer fixtures). v7:
- a changed function line that runs at import, or a binding referenced at import, no longer refuses:
  the child's `state_check` runs (no names allowed for function lines) and must find every other module
  and class attribute equal to the pinned import state. Patches that break an import (duckdb in
  h7_029/h7_034/h11_021/t25_tmpl_000/t24_defarg_001) are still kept: their `:!` entry differs.
- `replay_ignorable`: other test modules and fixtures outside `tests/fixtures/optimizer/tpc-{h,ds}/`
  are ignored for the replay (passed to the child as data, so opening one taints).
- `Change.new_nodes` records statements added at class/module level; `_bound_names` reads them and
  import bindings (star imports refused). Read only by the replay, so selection is unchanged.
- Parity (verify-all): holdout 63, targeted 58, sample 13 commits, 0 violations. Seven synthetic
  commits of the new shapes (code+unrelated fixture, added module helper, added import; tools/ground_truth.py
  labels): every replay verdict matched the real tpcds outcome, 0 violations.
- Production image `rwx-v7` (organizer flags, local): sample 103.165 s, CPU 2.52, 0 misses;
  holdout 636.8 s, CPU 29.6, 0 misses; targeted 440.2 s (v6 455.1), CPU 19.5 (15.1), 0 misses.
- Board effect unknown until submitted: it depends on whether the board's tpcds commits have these shapes.
  Each tpcds replay costs ~3 s local CPU (~7 s board) and saves ~15–20 s when the test passes.
