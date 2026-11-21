# RWX Execution Plan: Friday to Sunday

**Cutoff:** Sun Nov 22, 2026, **10:00 AM CST / 11:00 AM EST**. The hidden final is run on a chosen commit; the leaderboard now is **practice only**. It is currently Friday Nov 20. The team has two people on Friday, **teammate alone Saturday**, and Sunday morning as the final window.

## Workstream split

| Role | Owns | Does not own |
|---|---|---|
| Teammate — coverage/static index | Clone pinned SQLGlot, per-test coverage pilot, import/fixture index, container build feasibility | Main selector / submission without coordination |
| User + Claude — runtime selector and QA | Diff/hunk parser, cost/risk policy, scheduler, schema validators, local scoring, integration | Overwriting teammate index branch |
| Integration owner (one at a time) | Merge, clean Docker build, choose official commit, report metrics | Unreviewed edits to both worktrees |

Keep git branches independent. Share a *minimal interface contract* before splitting: `Index.lookup(changed_path, changed_spans) -> candidate IDs + confidence reason`, not the same file being edited by two agents.

## Tonight: establish evidence and a runnable next version

1. Save current `main` as a known-good commit; record SHA. Don't accidentally replace working v0.1.
2. Validate actual Docker with `make sample` and `make check`. This is more valuable than adding plugins.
3. Audit v0.1's top expensive changes and their selected tests/durations.
4. Implement robust diff parser and fixture index from *pinned source*.
5. Start coverage context feasibility test. If >10 minutes in clean image, switch to source-only precomputation.
6. Have Claude implement an independent synthetic mutation holdout harness.
7. Merge only validated components. Preserve ability to run v0.1 as rollback.

**Tonight exit criteria:** one valid Docker candidate, baseline score recorded, and the new features isolated behind switches/fallbacks. If container setup blocks us, explicitly document and prioritize fixing it.

## Saturday: teammate solo, focus on coverage and robustness

1. Run full pinned-source test/coverage capture or finish a compact static+fixture map.
2. Compare source-derived index size vs 20MB repo cap and 10-min build budget.
3. Verify missed failures against independently labeled synthetic patches.
4. Build candidate branches; compare CPU and sample cost with saved v0.1.
5. Clean Docker test. Keep logs and experiment summaries in the repo (not hidden labels).
6. If green, use one early official submission *only after the user authorizes it*, inspect CPU and miss feedback. Do not rely solely on simulated score.
7. Select strongest implementation **robust to unseen changes** for final improvement.

**Saturday exit criteria:** a clear best-known-green SHA and a tested submission, ideally a graded one.

## Sunday early morning: finalize

1. Recheck GitHub public visibility, remote URL, chosen commit hash, no secrets.
2. Compare high-risk final changes against latest green candidate; reject risky last-minute rewrites.
3. Full clean Docker run with exact restrictions and final-like number of commits if possible.
4. Submit or select the strongest valid immutable commit **well before** 10:00 AM CST.
5. Stop editing that submission commit. Keep the repo public and selected history available until results.

## Effective optimization order

**Zero-cost safety:** output contract, no leaks, reproducibility.  
**High gain:** exact fixtures → line/function coverage → reverse dependency reachability.  
**Medium gain:** cost-aware fallback and worker count.  
**Experimental:** AST-equivalence zero selection; LibCST; runtime targeted tests.  
**Last:** ML/ranking based on tiny sample, exotic MCP, full replatform in Rust.

## Decision checkpoints

- **Go/no-go coverage:** Does a complete, well-mapped per-test coverage index fit build/resource budget? If not, precompute from pinned source (allowed), or narrow coverage to target high-cost modules.
- **Go/no-go runtime tests:** Does local CPU-adjusted total improve *and* holdout misses decrease? Otherwise no.
- **Go/no-go official run:** Can the image be freshly rebuilt, run under official flags, emit valid JSONL, and avoid breaking unknown fixtures? Otherwise defer submission.
- **Freeze:** Never risk losing the best valid candidate near cutoff for a speculative optimization.
