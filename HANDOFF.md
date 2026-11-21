# Handoff — RWX Blast Radius (Fri Nov 20, 2026, ~10:30 PM CT)

Start here in a new chat. Also read `CLAUDE.md` (project rules) and `README.md` (how the selector works).

- **Deadline: Sun Nov 22, 10:00 AM CT.** Submissions close then; the final is scored after.
- Track page (sign in there to submit): https://www.joinbuilders.org/buildathon/tracks/blast-radius
- Repo: https://github.com/Qua5eyeNimbl/rwx-blast-radius (public). Local: `C:\rwx-blast-radius`.

## Where things stand

**Submitted and scored: 180.3 s, 0 missed commits.** Receipt `BB-7BA6EB0B`, commit
`3999bb36c86f363f7db123a335ab390e901b060b` (`v3-import-instances`), submitted Fri ~10:24 PM CT.
Three runs: 177.784 s simulated each, CPU 2.48 / 2.49 / 2.52 s, 0 misses each. It is entered in
the final as the team's best score.

Board context when we submitted (130 teams): leaders were about 152–157 s; 180.3 s placed about
13th. The gap to the top (~25 s) matches our gap to the best possible score on the sample.

### Branches (all pushed to GitHub)

| Branch | Head | What it is |
|---|---|---|
| `main` (default) | `a93f952` | v0.1. **An empty Commit box on the submit form scores this.** |
| `v2-coverage-selector` | `81b75b9` | v2 coverage selector; known-good fallback |
| `v3-import-instances` | `3999bb3` | **v3, the scored submission** (this file's later edits sit on top) |

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

1. **Cost cuts, only with evidence.** Any change must keep: sample 0 misses, all 96 holdout labels
   0 misses, unit tests passing, Docker run valid. Compare totals with `tools/eval_holdout.py`.
   Where v3 pays beyond the best possible on the sample (24.6 s total):
   - `4d63`: 12.69 s, 358 tests selected, none fail — the single biggest target.
   - `2qn5`, `5y72`, `gbav`, `fryt`, `ktz3`: ~2.1–2.5 s each, nothing fails (any non-empty
     selection costs at least 2 s).
   - Smaller: `535z` +0.25, `bj7g` +0.23.
   Do not tune rules to these sample commits specifically (that is fitting to answers). Find the
   general rule that over-selects, then confirm on the holdout. Ideas from before: narrow string-keyed
   dict entries (`FUNCTIONS`, `SHOW_PARSERS`) by the expression classes they build; data-flow
   narrowing for class-scoped `setUpClass` fixture data.
   `test_execute_tpcds` (21.5 s) drives most holdout over-cost but really fails in ~3 of 11
   selections: keep it (dropping it is a losing bet against a 300 s miss).
2. **Remaining CPU** (~1.8 s here, ~2.5 s on the board) is mostly `ast.parse` and parent links in `_tree`.
3. **Only resubmit a commit that beats v3 locally and has 0 holdout misses.** Then compare the board's
   misses/CPU. If a new submission shows misses, the final still uses the best score unless you pick
   another, but don't leave a worse commit as the chosen one.
4. **Freeze well before Sun 10:00 AM CT.** Never swap a graded, working commit for an untested change
   near the cutoff.

## Environment notes (for whoever continues)

- The Claude cloud workspace had Python 3.13, uv, and Docker (start the daemon with `dockerd &`).
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
