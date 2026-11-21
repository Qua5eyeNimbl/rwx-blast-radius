# RWX Blast Radius — Project Instructions for Claude Code

**Workspace:** `C:\rwx-blast-radius` (Windows), GitHub `Qua5eyeNimbl/rwx-blast-radius`.  
**Deadline:** Sunday, November 22, 2026, 10:00 AM Central.  
**Objective:** win the legitimate hidden evaluation by selecting the smallest defensible test sets, minimizing misses, CPU, and worker costs.

## Read in this order

1. This project's **original** `README.md`, `SCORING.md`, `Makefile`, `Dockerfile`, `score.py`, `selector.py`, sample test catalog.
2. `docs/research/DESIGN.md` — current architecture and score formula.
3. `docs/research/EXPERIMENTS.md` — required evidence and submission checks.
4. `docs/research/RISK_REGISTER.md` — critical failure modes.
5. `docs/research/TOOLING.md`, `REFERENCES.md`, `SOURCES.md` as needed.

If the research pack is in a different folder, locate it without overwriting the current project's README. This file is intended to go at **repository root**, while the pack's other `.md` files live under `docs/research/`.

## Ground truths

- Pinned SQLGlot SHA `eb11aec4be8cb2122afe713a4816662c3f0fb2fa`.
- Local public sample: 30 commits, 1,620 numbered tests, 494.300s simulated, 0 misses on current v0.1 (verified by the user in PowerShell); actual Docker and hidden scores remain unverified.
- Per commit: `max(worker loads) + 2 seconds per nonempty worker`; each missed failing commit adds 300s; charged runtime CPU adds to total.
- **A single nonempty worker costs >=2s.** A literal 1-second score is not possible if any commit needs test execution. Aim for the theoretical minimum without gaming the scorer.
- Only **pinned-source-derived** coverage/import/fixture maps are legal. Sample answers belong in evaluation tooling, never in the container. Never memorize patch→failure answers or mappings from edit kind→failure labels.

## Coding practice

- Measure, don't assume. Show CPU-adjusted local benchmarks and independent holdout evidence, not sample wins alone.
- Before editing: `git status`, current branch/remote, inspect teammate changes, preserve best-known-good candidate; use feature branches/worktrees.
- Work autonomously on safe reversible changes; no unapproved official submit, repository visibility change, untrusted downloads, credential use, or destructive Git commands.
- Implement functionality, execute tests, diagnose, repeat. No premature “complete” claims.
- Use Python's stdlib and the organizer lock by default; introduce packages only after a measured experiment. Preserve official Docker digest and test-label parity.
- Never emit logs on stdout in judge image. Output exactly one JSON `{commit,workers}` per input patch, no duplicated tests, <=8 workers, valid numbers only.
- Docker build <=10 minutes; runtime offline, read-only, `nobody`, 2 CPUs, 4GB, <=3min practice/4.5min final, 64MB tmpfs, repository <20MB.
- Document uncertainties, failed attempts, exact commands, test outputs, and source SHA. Use stderr for diagnostics.
- Keep MIT licensing and avoid storing secrets/public-sample answer-derived indexes in published build artifacts.

## Review rule

Do not replace the last verified candidate with a potentially lower-scoring one without reproducible Docker tests and independent holdout regression results. A valid lower-ranked candidate is better than a rejected final.
