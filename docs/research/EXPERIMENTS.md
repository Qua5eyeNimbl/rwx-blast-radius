# RWX Experimental Protocol and Acceptance Tests

**This document defines what counts as evidence.** “Works”, “zero misses”, “beats the leader”, and “low CPU” are distinct claims. The aim is to prevent false confidence and avoid burning the hourly official submission.

## 1. Established baseline

User-supplied Windows PowerShell output confirmed:

```text
Ran 5 tests in 0.084s
OK
Selection complete
Simulated: 494.300 s
Misses: 0 (0.000 s of the simulated time)
CPU: not measured here
```

These are **public-sample**, **non-Docker** results. The same output cannot establish hidden performance, official total CPU, or Linux parity. The organizer's original starter had ~1,210.470s on the same sample in previous local analysis; it is not the official 1,614.1s baseline, which used a different context and includes official evaluation details.

## 2. First commands to run on Windows

In `C:\rwx-blast-radius`:

```powershell
Get-Location
git status --short
git branch --show-current
git remote -v
python --version
python -m unittest discover -s tests_local -v
$env:RWX_DATA = (Resolve-Path .\sample).Path
# Use cmd redirection to avoid Windows PowerShell 5.1 UTF-16 output:
cmd /c "python selector.py > output.jsonl"
python score.py sample sample/answers.json output.jsonl
```

Do not rely on plain `python selector.py > output.jsonl` in Windows PowerShell 5.1 because its output encoding can be UTF-16; this may be rejected as invalid UTF-8.

For Docker Desktop with WSL2 Ubuntu integration, in Ubuntu:

```bash
cd /mnt/c/rwx-blast-radius
make sample
make check
```

`make sample` uses the organizers' Docker flags; it verifies real Linux/amd64 build, `nobody`, no network, read-only root, tmpfs, memory and CPU caps. If WSL path I/O is painfully slow, clone the project into the WSL ext4 filesystem in a *separate worktree* first, retaining the same commit; don't overwrite the Windows copy.

If Docker is absent or stopped, **report exactly that**, avoid claiming final submission validation, and continue unit/integration tests with the same source on Python until Docker becomes available.

## 3. Benchmark record template

Store results outside the judge image, e.g. `benchmarks/runs/YYYYMMDD-HHMM-<sha>.json`. Do not leak sample answers into container.

```json
{
  "utc": "YYYY-MM-DDTHH:MM:SSZ",
  "git_sha": "40_hex_sha",
  "environment": "windows-python | wsl-docker-linux-amd64",
  "testset": "public-sample | synthetic-holdout-v1",
  "policy_name": "coverage-static-hybrid-v1",
  "simulated_seconds": null,
  "cpu_seconds": null,
  "wall_seconds": null,
  "missed_commits": null,
  "selected_test_count_total": null,
  "active_worker_count_total": null,
  "build_wall_seconds": null,
  "index_bytes": null,
  "docker_exit_code": null,
  "notes": "Measured facts only"
}
```

### Per-commit diagnostics

For the public sample, compute *after selection*:

| commit | changed paths | selected tests | total selected duration | workers | makespan | overhead | missed? | fallback reason |
|---|---|---:|---:|---:|---:|---:|---|---|

Surface the most expensive 5 changes, slowest selected test IDs, and any misses. During development, avoid embedding the public answer labels or commit-specific corrections into the selector.

## 4. Evaluation splits and anti-overfitting

1. **Public 30 commits:** smoke test, scorer validity, regression diagnostics. Sample answers may be used only by an isolated evaluation harness after it has received the selector output.
2. **Unlabeled synthetic patches from pinned SQLGlot:** generated from project source and fixture structures, *not copied/derived from sample answers*. Assert interface and policy behavior; labels unknown unless independently executed.
3. **Executable holdout changes with independent ground truth:** construct deterministic semantic mutations from the pinned source (for example changing a parser branch predicate) and run the complete pinned suite against separately applied changes, in a clean environment, to obtain exact failing parent test IDs. Compare against predictions. Keep this local or as synthetic-fixture definitions; **never package precomputed patch-answer maps or train against public sample answers**.
4. **Cross-dialect/unknown cases:** rename module, modify export/import, add subclass method, change decorator, module-level constant, dynamic registration, `.sql` resource, and malformed patch. Error cases should not cause invalid JSONL output.
5. **Final hidden test:** not available locally. Only competition provides a genuine hidden evaluation. Never infer hidden outcomes from local metrics.

**Boundary:** don't accidentally use the v0.1 sample patches themselves as labeled training items. The contest forbids baked-in patch or edit-kind answers; legitimate source-derived coverage, imports and fixtures are okay. The most defensible evaluation protocol logs provenance for all data.

## 5. Contract-specific unit tests

- All commits, sorted, exactly once; non-ASCII commit names/patch text handled safely.
- `workers=[]` allowed; empty inner lists removed for counting.
- Every worker element is an integer test number; no `true`, strings, floats, repeated numbers, or unknown numbers.
- Maximum eight nonempty workers; 9+ rejected.
- Stdout exactly JSONL with no progress line, BOM, extra trailing spaces/signatures, or `NaN`/`Infinity`.
- Test lengths from `seconds` rounded to integer ms to match scorer.
- `print(..., file=sys.stderr)` for diagnostics; no spurious lib/pytest stdout.
- Input globs and path parsing tolerate names with spaces, renames, deleted/new files, `\ No newline at end of file`, CRLF lines and `/dev/null`.
- Missing `tests.json`, invalid patch, unreadable indexes -> explicit safe behavior; do not output a partial set of commits.
- No runtime network calls or writes outside `/tmp`; precomputed index readable by `nobody`.
- Output stays under 2 MB for final-like 45-commit batches.

## 6. Source/coverage correctness probes

Test each using a simple pinned-source fixture with a controlled expected set:

- Simple changed implementation line in an importable function.
- Changed branch not covered by base test execution; does static fallback catch it?
- Change to pure comment, docstring used as data, SQL comment in fixture, SQL syntax string; don't collapse all to zero.
- Changed module global constant; indirect import-time users should be counted.
- Changed base class method, overridden method, mixin, dynamically registered dialect.
- Function renamed, decorator changed, imported symbol re-exported.
- Changed `tests/fixtures/...` resource consumed by one exact parent test.
- Changed shared `test` utility, `conftest.py`, or fixture loader.
- Added code that affects a previously unexecuted path.
- `unittest.subTest`: failing subtest should imply failing numbered parent.
- Integration tests included with `SKIP_INTEGRATION=0`.

A coverage edge absent from the index must not by itself prove that a test is unrelated. Record a fallback reason.

## 7. Coverage build feasibility experiment

**Goal:** decide in at most one development session whether a full per-test context map is practical under the 10-minute clean build.

Against the pinned checkout with organizer lock (plus the exact approved `pytest-cov` package version in the build environment):

```bash
export SKIP_INTEGRATION=0
python -m pytest tests --cov=sqlglot --cov-context=test \
  --cov-branch --cov-report= -q
```

This is a **proposed experiment**, not a guaranteed valid command for that checkout. Confirm pytest-cov version and whether `--cov-branch` is accepted with the installed tool; if not, adjust according to its official help. Benchmark full suite runtime, count contexts and bytes, map generated node IDs exactly onto `tests.json`, note skipped and import-time contexts. Export via CoverageData public API. Compare exporting at module and function granularity; evaluate index compression and query speed.

**Stop criterion:** if full clean image + map build won't finish in 10 minutes, switch to offline precomputation from the pinned source and commit a compact source-derived index, or use partial targeted coverage plus static graph. Don't keep rebuilding a fat image for each iteration.

## 8. Worker optimizer experiment

For every selected set, compare:

1. LPT over `k=1..8` (baseline).
2. LPT with pairwise exchange/local search.
3. Bounded exact branch-and-bound for small `n` only.

Use actual integer ms from `tests.json` and measure decision CPU; keep the lowest **total (simulated + CPU)**, not the lowest makespan alone. Never infer that more workers improve score: 2s overhead per worker changes the optimum.

## 9. Runtime targeted-test experiment (optional)

Set a strict CPU+wall budget by commit. Apply patch to **isolated** scratch state; use `pytest -q` with explicitly selected node IDs, `SKIP_INTEGRATION=0`, and organizer dependencies. On failure, collect parent test number by exact node ID and output only confirmed failures **plus** safe risk fallbacks if tests were incomplete or errored for environmental reasons.

Problems to deliberately test: patch rejection, inability to import test module, timeout/kill, subprocess stdout contamination, cross-patch state, Python startup overhead, root read-only filesystem, 64MB tmpfs. If any cannot be solved within the time budget, drop this approach. It is higher priority to get a valid offline selector than to gamble on a complicated runtime harness.

## 10. Submission gate (all mandatory)

- [ ] Git status checked; no conflicting teammate modifications.
- [ ] Source matches exact selected SHA, branch, dependency locks.
- [ ] All unit tests pass.
- [ ] Public scorer produces a valid score; misses recorded.
- [ ] Independent held-out patches tested and provenance documented.
- [ ] Clean Docker build passes in 10-minute limit on linux/amd64.
- [ ] Container runtime passes under official Docker flags and 3-minute practice limit.
- [ ] Run as `nobody`, read-only, no runtime network, all indexed files readable.
- [ ] No sample `answers.json` or derived patch-answer lookup tables inside image.
- [ ] No credentials, API keys or `.env` in public repo.
- [ ] Final project size <20MB, Dockerfile in repo root, MIT License present.
- [ ] Real Git commit created; selected immutable SHA recorded.
- [ ] User explicitly approves spending official hourly attempt.
- [ ] After submitted run, inspect official feedback; do not treat sample score as leaderboard score.

## 11. Questions the next experiment must answer

1. Can per-test coverage fully build under 10 min, or must we precompute offline?
2. What fraction of the largest v0.1 cost comes from broad parser/expression fallbacks vs fixtures vs worker layout?
3. Does static transitive propagation rescue the known difficult source mutation cases?
4. What fraction of predictions lacks direct evidence, and is that cost acceptable?
5. Are we seeing real improvements on independently generated failing mutations, or only public-sample cuts?
6. What is the measured official-style **charged CPU** added by each refinement?

A model may only assert a high-quality improvement after these are measured.
