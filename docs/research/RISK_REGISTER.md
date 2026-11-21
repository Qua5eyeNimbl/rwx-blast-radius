# RWX Risk Register — What Could Make a “Great” Solution Lose?

Review whenever a major design changes. Priority = severity × likelihood **qualitative, not statistical**.

| ID | Risk | Severity | Observable warning | Mitigation and required evidence |
|---|---|---|---|---|
| R01 | Hidden misses despite perfect public score | Critical | Sample zero misses; no independent failing holdout | Source-derived graphs; synthetic mutation-based ground truth; conservative fallback; no sample-answer memorization |
| R02 | Docker build fails or exceeds 10 minutes | Critical | Coverage/index takes too long or uses >8GB | Clean build with time limit; precompute allowed pinned-source index; minimal pinned dependencies |
| R03 | Runtime fails official sandbox | Critical | Writes to root, network access, `nobody` permissions, >3min | `make sample`, read-only/no-network/UID 65534 test; fail-fast output integrity |
| R04 | Invalid JSONL output | Critical | stdout logs, wrong keys/numbers/duplicate tests | Pure stdout JSON serializer; strict local schema validator; diagnostics stderr only |
| R05 | Answer leakage or rule violation | Critical | selector or image contains sampled patch/failure lookup | Remove all answer-derived index paths; audit image and reproducibility; keep `answers.json` evaluation-only |
| R06 | Missing changed symbols due to naive diff parsing | High | Renames/deletions/quotes mishandled | Hunk parser tests; both old and new paths; conservative unknown fallback |
| R07 | Dynamic coverage false negatives | High | Changed unseen branch gives empty/undersized set | Static import/caller/registration graph, fallback groups; inspect unusual dispatch |
| R08 | Frozen baseline index stale/wrong | High | Indexed source SHA not pinned, mismatched test IDs | Store base SHA + inventory hash; verify when loading and generating; deterministic build |
| R09 | Test labels mismatched due to environment | High | Different pytest version/SKIP_INTEGRATION | Organizer lock and digest; parent subtest-failure handling; compare collected IDs |
| R10 | Heavy runtime differential testing destroys score | High | CPU spikes; timeout/cross-patch contamination | Optional isolated prototype with hard budget; disable unless measured net win |
| R11 | Scheduling optimizer slower than savings | Medium | Exact solver CPU > makespan improvement | Compare CPU-adjusted total against LPT; budget search, fallback fast |
| R12 | Subagents overwrite teammate work | High | Mixed branch, dirty index, merge conflicts | Separate feature branches/worktrees; one integration owner; no destructive Git operations |
| R13 | Git repo private at submission / wrong URL | Critical | UI shows private; scorer cannot clone | Verify URL `https://github.com/Qua5eyeNimbl/rwx-blast-radius`; public read check before official attempt |
| R14 | Public repo contains tokens or personal files | Critical | `.env`, credentials, source archives staged | `git status`, `git diff --cached`, secret scans; scope GitHub tokens |
| R15 | Last-minute unverified optimization | Critical | Diff untested with minutes left | Freeze best known green SHA; preserve ability to select final commit |
| R16 | Overengineering addons wastes time | Medium | Installing many MCPs, obv irrelevant tools | Start with Docker + CLAUDE.md + Python diagnostics; optional tool 15min trial |
| R17 | Source docs misread as proof of performance | Medium | “Meta used ML” → assumed better here | Require local holdout gains; separate external research from RWX facts |
| R18 | Official scoring queue / hourly cap prevents feedback | High | Attempt delayed or cutoff close | Plan official run early; maintain best green candidate; stop submitting untested changes |
| R19 | `requirements.lock` changes silently | High | Different modules, regressions or import errors | Pin versions; isolated experiment environments; record image digest |
| R20 | Hidden change types not represented in sample | Critical | Selector hard-coded for only 30 examples | Cover changes to shared definitions, config, imports, tests, module-level code, fixtures and unknown files |

## Stop conditions

Never trade a valid, previously graded candidate for an unvalidated late change. Stop exploratory development when there is insufficient time to complete a clean Docker validation, commit, submit, and receive feedback. Competition closes Sunday **Nov 22, 2026 at 10:00 AM Central**; final rerun is on unseen commits and may take longer than the practice scoreboard. [S01], [S03]

## Final safety/security audit

- Public project contains only intentionally open-source material; all authored code MIT.
- No credentials, `~/.aws`, `.claude/settings.local.json`, browser cookies, personal config or private prompts pushed.
- Plugins and MCP servers not granted broad filesystem/repository write permissions merely for convenience.
- No unapproved external build endpoints, hidden networks, or code that evades the official runtime limitations.
