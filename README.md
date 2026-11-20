# RWX Blast Radius — Team Starter (v0.1)

Working submission candidate for the November 20–22, 2026 Builders Buildathon RWX track. This package is derived from the organizer-supplied `blast-radius-sample.tar.gz` and retains its scoring harness and sample input. The selector is a new, dependency-free, patch-aware implementation.

## Verified local sample result

- **494.300 simulated seconds** (30 public sample commits)
- **0 missed failing commits**, per the sample answers used exclusively by `score.py`
- Original organizer starter: **1,210.470 simulated seconds** on the same sample
- These figures **exclude Docker/container CPU time**, and **do not predict** the hidden leaderboard score.
- Docker itself was **not available** in the environment where this package was built, so the actual container build and Linux read-only sandbox run remain to be tested by the team.

The algorithm does **not** read `answers.json`. Selection is based on changed paths and test IDs; the scorer reads answers **after** the selector exits. Never add patch/answers lookup tables: the challenge explicitly prohibits that.

## Team setup — Windows 11

1. Create a **public** GitHub repository owned by your buildathon team, e.g. `rwx-blast-radius`.
2. Extract this ZIP into the repository root (the **Dockerfile must be in the top-level directory**).
3. Install [Git for Windows](https://git-scm.com/downloads/win), Python 3.9+, and Docker Desktop (with WSL 2 backend) for full Docker testing.
4. Open a PowerShell terminal in the project directory. Test without Docker first:

```powershell
$env:RWX_DATA = (Resolve-Path .\sample).Path
python selector.py > output.jsonl
python score.py sample sample/answers.json output.jsonl
python -m unittest discover -s tests_local -v
```

5. For the **competition-equivalent container test**, open the project under WSL Ubuntu with Docker Desktop integration and execute:

```bash
make sample
make check
```

6. Publish the code (replace the URL with your team's own repository):

```bash
git init
git add .
git commit -m "Add initial RWX patch-aware selector"
git branch -M main
git remote add origin https://github.com/YOUR-TEAM/rwx-blast-radius.git
git push -u origin main
```

7. Submit the **public GitHub repository URL** via the RWX form (optionally supply a 40-character commit SHA). At the final cutoff, ensure the correct final commit is selected. A practice score is not a prize-winning final score.

## Files

- `selector.py` — program executed in the judge's sandbox; one JSON line per commit on **stdout**, no other stdout.
- `Dockerfile` — standard pinned Python image from organizer kit; copies selector only.
- `sample/` — public practice patches, test timings, and practice ground truth (not included in image).
- `score.py`, `SCORING.md` — unmodified organizer scorer and rules.
- `tests_local/` — small Python unit tests; not part of container image.
- `Makefile` — organizer's Docker-based local test commands.

## Next improvements that matter

The current v0.1 is a conservative **file-level** predictor. It selects broad suites for shared modules and does not inspect statement-level runtime dependencies. This is why some code changes still run hundreds of unnecessary tests.

**Highest-value next step:** during the Docker **build**, clone the allowed *pinned* SQLGlot revision `eb11aec4be8cb2122afe713a4816662c3f0fb2fa` and construct per-test coverage maps. Build-time work is not scored for CPU, though the build has a strict 10-minute/8 GB limit. The runtime selector should map patch hunks to affected functions and use the index for targeted selection, while retaining conservative fallbacks for monkeypatching, dynamic imports, and poorly covered code.

Then:

- Better handle diffs that touch shared parser and expression code.
- Build a fixture-file-to-test map by inspecting the pinned SQLGlot test code rather than relying only on filename heuristics.
- Prioritize reducing **misses** (300 seconds each), not just reducing the number of selected tests.
- Benchmark changed implementations on sample, but avoid memorizing individual sample patch IDs or their known failures.
- Validate with actual `make sample` inside Docker before submitting.

## Work split

**Developer A**: pinned SQLGlot coverage/AST index + test-reference graph during Docker build.

**Developer B**: selector improvements + scheduling optimizer + local scoring and safeguards.

Agree on `selector.py`'s `Selector.for_patch(patch_text) -> set[int]` interface and have one integrator merge and test changes. Keep each change in a feature branch and do not overwrite a teammate's work.

## Rules to remember

- Code/image must not use a hardcoded sample patch/answer map, including maps by edit kind to failures.
- The image may download dependencies during build only from permitted registries and pinned SQLGlot source.
- Runtime network is disabled, filesystem is read-only, `/tmp` is 64 MB, and the container runs as `nobody`.
- The build may use 4 CPUs, 8 GB RAM, and 10 minutes; runtime uses 2 CPUs, 4 GB RAM, and about 3 minutes for practice.
- One line of JSON for **every** commit, with valid test numbers, no duplicates, at most 8 workers.
- Keep public repository under 20 MB; don't commit credentials, private challenge data, or large generated indexes.
- Read `SCORING.md` and the organizer's official rules before final submission.

MIT License. See `LICENSE`.
