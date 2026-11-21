# RWX Blast Radius — Evidence-Based Research & Claude Build Pack

**Compiled November 20, 2026.** Built for a two-person team competing in the RWX Blast Radius track with a Sunday, November 22, 2026 **10:00 AM Central** cutoff.

## Start here

1. Read `DESIGN.md` for the proposed architecture, proven scoring facts and experimentally unproven hypotheses.
2. Read `EXPERIMENTS.md` for sample, holdout, Docker, performance, and submission validation gates.
3. Read `TOOLING.md` before installing any Claude extension, language server, or MCP integration.
4. Read `REFERENCES.md` for findings translated into design choices and `SOURCES.md` for direct links, evidence grades, and transcript citations.
5. Open `CLAUDE_MASTER_PROMPT.md` for the complete autonomous implementation handoff.
6. Use `ACTION_PLAN.md` and `RISK_REGISTER.md` to divide work and protect the best verified submission under the deadline.

### Pack contents

| File | Purpose |
| --- | --- |
| `DESIGN.md` | Scoring mathematics; proposed hybrid coverage/static/fixture/patch analysis; source-only indexes; scheduling; tradeoffs |
| `REFERENCES.md` | Technical synthesis, reasons to adopt or reject approaches, YouTube transcript takeaways |
| `SOURCES.md` | Annotated primary and independent sources with URLs, evidence levels and caveats |
| `EXPERIMENTS.md` | Reproducible sample/Docker tests, holdout validation, reporting schema and submission gate |
| `TOOLING.md` | Evaluated Claude add-ons, trusted mature tools, experiments, security and smoke tests |
| `ACTION_PLAN.md` | Work split and practical Friday/Saturday/Sunday schedule |
| `RISK_REGISTER.md` | Technical, competition, data integrity, tooling and scheduling risks |
| `CLAUDE_MASTER_PROMPT.md` | Full executable instruction set for Claude Code on your local machine |
| `CLAUDE.md` | Suggested short root-level project instructions for Claude Code; **review/merge**, never overwrite existing file |

## Install without damaging the existing project

Your actual project is `C:\rwx-blast-radius`, with GitHub remote `https://github.com/Qua5eyeNimbl/rwx-blast-radius` (the username contains the digit **5**).

1. Download/extract this research pack into a separate temporary folder.
2. In `C:\rwx-blast-radius`, create `docs\research\`.
3. Copy the pack's `.md` files **except `CLAUDE.md` and `README.md`** into `docs\research\`. You may optionally copy this `README.md` as `docs\research\PACK_README.md`.
4. Review any existing `C:\rwx-blast-radius\CLAUDE.md` before copying or merging the supplied `CLAUDE.md` at repository root. Do not overwrite other contributors' instructions.
5. Launch Claude Code **from the project directory** with local terminal access and the strongest available Opus/High reasoning option; paste `CLAUDE_MASTER_PROMPT.md` beginning at `START OF PROMPT`.
6. Let Claude audit Git status and the actual project before modifying anything. Work in a separate branch. Require a real Docker run and repeatable holdout testing before submitting.

Do **not** overwrite your existing root `README.md`, `SCORING.md`, `selector.py`, `Dockerfile`, `score.py`, or any sample data with these research documents.

## Verified facts vs proposed improvements

- On the **public 30-commit sample**, user's v0.1 selector output **494.300 simulated seconds and 0 missed commits**, and 5 unit tests passed. This is not a hidden leaderboard result. Real Docker validation remains outstanding.
- The official scoring cost includes **2 seconds per nonempty worker per commit**, maximum worker test duration, **300 seconds per missed failing commit**, and charged container CPU time. One second total is mathematically impossible if the strategy selects any test, but it remains a useful aspirational direction toward the minimum legitimate total score.
- Analysis of the supplied sample answers permits a *diagnostic oracle* scoring 94.351 simulated seconds with the existing scheduler, **not a real deployable selector**. Those answers cannot be placed into the submitted predictor or used to memorize edits.
- The most promising proposed architecture combines **per-test line coverage + static reverse-dependency reasoning + source-derived fixture mapping + risk-aware selection + worker scheduling**. **It has not yet been implemented or benchmarked end to end** on the user's PC.
- Research includes two YouTube talks analyzed using their actual **vidIQ-provided transcripts**, not visual frame inspection or reproduction of their live demos. Vendor-reported success rates are not independent validation for RWX.
- Official Claude Pyright language-server integration, Git and Docker are defensible tools to *trial*. None of the new integrations were installed or validated against this user's Windows environment in this research session. Obsidian is useful if your team wants a Markdown knowledge base, but is not a direct way to improve score; avoid installing unverified Obsidian MCP integrations solely for this contest.

## Competition submission safety

Do not submit without an approved valid Git SHA, clean public repository under the competition size limit, verified Docker build and runtime, independent holdout regression checks, correct stdout JSONL, and review that no answer labels or credentials are packaged. Competition rules may change: the [official track page](https://www.joinbuilders.org/buildathon/tracks/blast-radius) takes priority over this document.
