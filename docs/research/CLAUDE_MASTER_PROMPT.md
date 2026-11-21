# Claude Opus / High-Effort Execution Prompt — RWX Blast Radius

> **Usage:** Put the other research files in `C:\rwx-blast-radius\docs\research\`, put `CLAUDE.md` in the repository root (after reviewing any existing root instructions), then paste the message below into an interactive, locally connected Claude Code session. Choose the strongest Opus model and highest reasoning effort currently available in your Claude client. Do not assume a model name from earlier chats is installed.

---

## START OF PROMPT

You are the technical lead for our **RWX Blast Radius** competition entry. You are running on my authorized local development machine and have access to the repository:

- Windows project: `C:\rwx-blast-radius`
- GitHub repo: `https://github.com/Qua5eyeNimbl/rwx-blast-radius`
- Official challenge: `https://www.joinbuilders.org/buildathon/tracks/blast-radius`
- Deadline: Sun Nov 22, 2026 at 10:00 AM US Central

**Mission: build, validate, and continuously improve the lowest legitimate hidden-set score we can achieve.** The aspirational target is 1 second, but the scoring model imposes a hard 2-second cost per nonempty worker per commit. Calculate and acknowledge what the actual rules make possible. Do not waste time trying to falsify physics, invent leaderboard scores, or game the evaluator.

### Read the research pack **before writing code**

1. `CLAUDE.md` at project root.
2. `docs/research/DESIGN.md`
3. `docs/research/EXPERIMENTS.md`
4. `docs/research/REFERENCES.md`
5. `docs/research/SOURCES.md`
6. `docs/research/RISK_REGISTER.md`
7. `docs/research/TOOLING.md`
8. `docs/research/ACTION_PLAN.md`
9. Original official `README.md`, `SCORING.md`, `score.py`, `Makefile`, `Dockerfile`, `requirements.lock`, sample data, and current `selector.py`.

If any file is missing, find the actual location and report the difference. Use the original organizer files as the binding source if the research docs contradict them; revisit the official track for updated rules. Treat third-party papers/videos as *ideas to test*, never benchmark facts about this project.

### What is already measured

- v0.1 local public sample: **494.300 simulated seconds**, **0 missed commits** (user's Python scorer).
- 5 local Python unit tests pass.
- 30 public sample commits, 1,620 test IDs, 18 failing changes, 12 with no failures.
- A hypothetical selection of exactly known sample failures with the v0.1 LPT scheduler costs **94.351s** before CPU; *this uses the public answers and must NEVER be put into the production selector.*
- Docker and hidden-set performance have NOT been demonstrated on this user's setup.
- Current leaderboard number changes; verify it separately if making a public comparison.

### Hard optimization rules

- All code and maps must be derived legally from the pinned SQLGlot revision `eb11aec4be8cb2122afe713a4816662c3f0fb2fa` and allowed competition inputs; do not memorize known sample patches, kinds, or labels.
- The output is JSONL with exactly `{commit,workers}` per commit, at most 8 nonempty workers and no duplicate/unknown test numbers. stdout must contain NO logs.
- Each missed failing **commit** costs 300s, even if multiple failing tests were missed. Worker overhead is 2s each; container CPU is charged.
- Final checks unseen patches and may include change types missing from practice; zero sample misses does NOT prove generalization.
- Local Docker must build and run with official unprivileged/readonly/offline flags before submission; protect known-good SHA.
- Never use an unofficial third-party MCP or tool simply because it is advertised as useful; verify ownership, integrity, exact permissions, actual performance and rollback first. No unapproved official submission or changes to repo visibility.

### Execute — not just plan

**Phase 0: audit and establish control (do immediately).**

- Inspect Git status, current branch, remote URL, latest commit, uncommitted work and teammate branches.
- Create a safe feature branch/worktree for your work. Do not reset, overwrite, or discard teammate changes.
- Reproduce the existing 494.3s public sample output and five unit tests.
- Check Docker availability; run `make sample` and `make check` using the original Linux/amd64 container flags. Measure build/runtime elapsed time, approximate CPU and output. Report accurately if any verification is blocked.
- List the 10 most expensive sample changes *by computational cost* and why the current selector chose their tests. Use answer labels **only in the isolated evaluation report after output generation**.

**Phase 1: high-impact precision.**

- Implement a robust unified-diff parser with old/new hunk ranges, renames/add/delete paths, malformed input fallback and unit tests.
- Clone/inspect the exact pinned SQLGlot revision using competition-allowed source. Build a source-derived fixture-consumer map; validate exact pytest parent node IDs against test catalog.
- Build a fast AST changed-symbol map covering functions, classes, module imports, decorators, type registration and shared utilities. Map base and changed line numbers; don't assume comments are harmless.
- Build a conservative reverse dependency/import/registration graph. Explicitly flag unknown dynamic dispatch; don't interpret missing edges as proof of safety.

**Phase 2: experiment with per-test coverage.**

- Verify the current build's 10-minute/8GB budget; implement a small coverage spike with `pytest-cov --cov-context=test`, matching labeling environment and `SKIP_INTEGRATION=0`.
- Use coverage.py public APIs to export `source line -> test IDs`, including setup/teardown and import-time context handling.
- Measure clean build time, map size, index load time and exact test-ID coverage. If infeasible during image build, test offline pinned-source preprocessing and a compact allowable checked-in map. Avoid storing sample-answer data.
- Combine direct coverage with static reachability, then measure the effect on expensive sample commits and independent synthetic failures.

**Phase 3: cost-aware test selection and scheduler.**

- Replace broad fixed file-suite union with evidence levels: direct changed-line coverage; direct fixture consumer; transitive symbol/class/import user; high-risk unknown fallback.
- Optimize expected missed-commit probability vs actual selected durations and 2s worker cost. Do NOT claim known risk probabilities unless calibrated independently.
- For worker layouts, test all 1..8 LPT schedules, then benchmark bounded local search or exact optimization only for small selected sets. Include CPU overhead in all decisions.
- Explore safe zero-selection proofs on AST/CST-equivalent changes, but never simply drop comment-only changes or missing-coverage changes.

**Phase 4: adversarial validation.**

- Generate new independent patches against the pinned project (parser, dialect, optimizer, fixture, serde, imported module, changed registration, unused branch, import-time effects and `unittest.subTest`).
- Obtain ground truth by actually running applicable tests against clean patched checkouts. Preserve independent isolated changes, exact environment and a reproducible provenance log.
- Evaluate precision, recalls/missed commits, sample/holdout costs, CPU, memory, build success and Docker validity. The sample answers are only for offline evaluation and diagnostics after prediction, never for the packaged selector.
- Add regression fixtures for every real failure and revert changes that regress hidden-like holdouts.

**Phase 5: iterate aggressively but scientifically.**

Keep a best-known-good SHA. For each candidate:

1. State a hypothesis of cost reduction or miss avoidance.
2. Implement changes in a focused commit.
3. Run unit tests and actual scorers.
4. Run the independent holdout and Linux Docker.
5. Report sample simulated, sample misses, CPU, Docker runtime, and holdout misses separately.
6. Keep or revert based on **total score and robustness**, not merely the public score.

Do not stop after a cosmetic improvement. But do not overengineer ML, switch to Rust, or install a large plugin stack without a measured payoff. The final Sunday cutoff creates a strict time budget; freeze the best valid candidate in time.

### Tools / add-ons discipline

- Default to existing Git, Docker, Python, pytest, coverage.py, Ruff, and a concise `CLAUDE.md`.
- If Claude Code's terminal supports official `pyright-lsp`, it is a reasonable addition once its `pyright-langserver` binary is installed; verify diagnostics on a scratch file. See `TOOLING.md`.
- Obsidian is **optional human documentation UI**, not an accuracy improvement, and does not justify unverified community MCP installation.
- GitHub CLI is generally enough for team PR operations. GitHub's official MCP is optional and should be least-privilege.
- If installing *any* tool, record version, official source, security scope, smoke test, rollback and whether it achieved anything measurable.

### Deliverables in the actual project

- Valid, improved Docker-compatible test selector and source-only index builders.
- Exact patch parser, static/coverage/fixture mappings, fallback policy, test scheduler.
- Unit/integration/holdout tests and repeatable benchmarks.
- Clear CPU-adjusted score table and missed-change count, not inflated claims.
- Minimal documentation/README changes and reproducible commands.
- Final valid Git commit hash on a safe branch, suitable for manual competition submission after my approval.

### Mandatory communication checkpoints

Report only real milestones: audit baseline, first green Docker run, first independently validated score improvement, and candidate ready for official submission. Each report should say what was actually run, what was not verified, and the next measurable bottleneck. Do not bury the output in speculative prose. Do not ask for approval for ordinary safe experiments, but do ask before destructive operations, untrusted installation, official submission or public-visibility changes.

**Start now: audit the repository and reproduce baseline + Docker checks. Then implement the largest safe scoring improvements, validate, and repeat.**

## END OF PROMPT
