# Annotated Technical References: What to Use, What to Question

This document is the **engineering translation** of the primary sources indexed in [`SOURCES.md`](SOURCES.md), not a list of promising-sounding tools. The key question for each is: *What does it teach us to build, and what would disprove its usefulness on RWX?*

## 1. Dynamic coverage: the highest-value first experiment

**Sources:** [S04], [S05], [S07], [S26].  
**Maturity:** mature maintained infrastructure; **not yet measured on pinned SQLGlot**.  
**Implementation:** `pytest --cov=sqlglot --cov-context=test`, then `CoverageData.contexts_by_lineno()`.

### Why this matters

The v0.1 selector makes decisions from file path groupings and test file names. One changed line in a common module often triggers essentially every test. The per-test coverage contexts let us know *which individual tests actually executed each line in the pinned source*. Querying changed hunks directly can cut a broad suite to a small set.

### Important caution

Coverage only records executed paths. It does not reveal what a changed branch *would* do under new behavior; nor does it necessarily capture setup/import effects or dynamic execution in another process. This is the core reason to combine coverage with reverse dependencies and broad fallbacks for uncertain changes. Avoid declaring “no tests” because a line lacks coverage.

### Experiment that earns adoption

1. Reproduce the exact test IDs (`tests.json`) and label environment.
2. Run one `pytest-cov` context collection pass using the pinned source.
3. Check elapsed build time, memory, file format, size, and mapping coverage.
4. Modify the *local* selector to select direct context tests while conservatively including dynamic/static consumers.
5. Compare full-run costs and misses against sample and synthetic holdout.
6. Only keep it if the gains survive actual Docker CPU and 10-minute build constraints.

## 2. Static reverse graph: insurance for unknown changes

**Sources:** [S11], [S12], [S24].  
**Maturity:** general approach is established; **specific SQLGlot graph must be inspected**.

Google's 2026 research on core-library regression selection combines a hybrid call graph and cheap structural graph features; its reported fixed budget captures only a fraction of failing commits, illustrating that ranking under a strict budget does not ensure zero misses. The take-home lesson is **use the graph to improve both recall and ranking, not to claim formal certainty**.

### Practical graph

```
changed hunk -> enclosing function/class/module
    -> direct test coverage
    -> static importer / caller / subclass / registry
    -> fixture / test helper reverse consumers
    -> risk-ranked selected tests
```

Never blindly apply the newest SQLGlot architecture to the pinned commit. The repository changes over time. Clone the exact SHA and inspect registration mechanisms, decorator usage, fixtures, module initialization, and import paths.

## 3. Testmon: a viable comparator, not magic

**Sources:** [S23].  
**Maturity:** established open-source pytest plugin.  
**Unverified on this project:** compatibility with pinned pytest/subtests, SQL fixtures, build budget, cross-dialect dynamic behavior.

`pytest-testmon` tracks changes to executed Python code and selects affected tests. Its approach is close enough to RWX that it is worth testing in a **separate experimental branch**. But the competition's input is *patches against a fixed base*, not an ordinary developer working tree; output is numbered test IDs and optimized worker assignments, not just the set pytest chooses to run. Testmon's internal state/model must be translated carefully; a plain installation cannot satisfy the contest output contract.

**Decision rule:** run it as a benchmark comparator under the exact pinned revision and test environment. Keep only components with documented correctness and score advantage; otherwise use coverage.py direct.

## 4. Meta predictive selection: what carries over and what doesn't

**Sources:** [S09], [S13].  
**Maturity:** documented production deployment at a huge company; **not directly reproducible in this contest**.

Meta describes using long-term code/test execution histories to predict which tests catch regressions. The TestCon talk transcript (13:15–17:15) explains how reverse-dependency selection still overselects on central libraries and how historical learning reduces work further.

**Transferable:** dependency fanout, cost-vs-recall tradeoffs, telemetry quality, flakiness, optimizing changed-code relevance rather than naive “run everything.”

**Not transferable:** trained failure models from years of production data; absolute accuracy/efficiency rates; special infrastructure available only inside Meta. With only 30 public labels we should avoid training a brittle lookup disguised as ML.

## 5. Gradle predictive selection: strong counterargument to coverage-only plans

**Source:** [S10], video transcript reviewed.  
**Maturity:** real vendor system, vendor-provided claims, *not independent RWX benchmark*.

Relevant moments:

- 03:06–04:00 — selection learned from code-change and test history.
- 12:35–14:45 — “shadow mode” validation with actual outcomes, missed-failure tracking, and interpretable selection decisions.
- 15:05–16:50 — why dynamic dispatch/reflection and integration boundaries degrade pure static/dynamic analysis.
- 17:10–20:25 — continuously updating predictions and use of an XGBoost ensemble.

**Use now:** build transparent coverage vs static evidence labels, run a holdout harness before submission, avoid uncertain “proven safe” claims. **Do not use now:** training a large predictive ensemble on the 30 public answers; this risks overfitting and violating the challenge integrity rule.

## 6. Google transition-based test selection: don't trust obvious heuristics

**Source:** [S12].

The 2019 Google study found that several reasonable history-based heuristics underperformed expectations, particularly with realistic developer/test behavior and flaky tests. This is direct motivation for *evaluation methodology*, not another algorithm to paste in.

**Use:** log per-change reasons and expensive tests; evaluate by holdout and counterexamples; prohibit silent optimistic zero selections when dependency data is missing.

## 7. LibCST vs Python stdlib AST

**Source:** [S08].

`ast` is fast, available without dependencies, captures enclosing definition lines with `end_lineno`, and handles most executable-code hunks. However, comments and formatting vanish from its representation; deleted-line cases still need preimage mapping.

LibCST preserves exact source layout and can associate positions/qualified names. This is useful when parsing patch hunks that touch decorators, comments, generated SQL strings, and multi-line syntax. It might be too expensive for runtime if parsed repeatedly. **Proposed tradeoff:** AST index during build plus a small CST experiment for ambiguous cases; measure before adopting.

## 8. Worker scheduling under RWX economics

**Source:** scoring rules [S01] and [S02], not a vendor product.

The objective is **not** shortest per-worker time and **not** always eight workers. Every new nonempty worker adds 2s. For 1–8 workers compute LPT schedules and choose minimum `(max load + 2*k)`. For small selections with expensive jobs, bounded branch-and-bound may improve makespan. CPU search cost is charged, and the advantage may be measured in milliseconds.

**Cheap win:** optimize which tests are selected before writing a sophisticated scheduler. One missed commit costs more than hundreds of LPT micro-optimizations.

## 9. A potentially overlooked opportunity: run real targeted tests in runtime

**Source:** organizer permission [S01].

The rules allow running SQLGlot tests while selecting. An actual failing result can provide stronger evidence than static prediction. But it costs CPU and wall time and needs an isolated working copy for each independent patch. With approximately 30 public and ~45 final changes, even 3s per patch would consume 90–135s of charged CPU before other costs. It should be **prototyped as an optional last-stage feature** for ambiguous high-risk changes rather than blindly used for all patches.

Measure: true misses avoided, selected test set reduction, full subprocess CPU, wall clock, isolation accuracy, and compatibility with read-only image/tmpfs. Reject if worse on holdout.

## 10. High-quality developer tooling is not a scoring algorithm

**Sources:** [S14]–[S22], [S25], [S28].

- **Pyright-LSP:** maintained by Anthropic's official plugin ecosystem; relevant for Python symbol navigation and type-error diagnostics. Requires independent `pyright-langserver`. Most justifiable Claude enhancement.
- **Claude `CLAUDE.md`:** first-party supported stable instruction format. Essential for long iterative sessions; keeps benchmark evidence and no-overfit rules visible.
- **Ruff, Python unittest/pytest, Docker, Git:** maintain project health and reproducibility. Strong recommendations because first-party/established, not because they lower a score themselves.
- **GitHub CLI or official GitHub MCP:** support branch/PR collaboration. Prefer CLI when it suffices. MCP is optional and must have least-privilege scopes.
- **Anthropic code-review plugin:** useful as a second-pass check, but can report false positives, use tokens and cannot certify runtime behavior.
- **Obsidian:** good user-facing Markdown organizer. Claude Code already reads `.md` in the repository; adding an Obsidian MCP server for this 36-hour challenge is additional risk with no verified score benefit.

**Proof standard:** installed tool functions correctly on Windows; produces relevant diagnostics or saves measurable iteration time; doesn't break Docker or expose credentials; can be removed without affecting the final submission. See [`TOOLING.md`](TOOLING.md).

## 11. Research priority allocation under the weekend deadline

| Area | Allocate | Why |
|---|---:|---|
| Docker + exact input contract | 15% | Invalid submission = zero utility |
| Fixture-aware semantic selector | 20% | Quick reduction in broad file selection |
| Coverage map and source graph | 35% | Biggest architectural score upside |
| Holdout tests and cost modeling | 20% | Hidden-set robustness, correct objective |
| Plugins, docs, experimental ML | 10% maximum | Avoid setup rabbit holes |

These percentages are **planning recommendations**, not experimentally measured speedups.

## 12. Definitive findings vs hypotheses

**Confirmed:** score semantics, input/output contract, deadlines, sample test/failure counts, current v0.1 score, availability of coverage contexts and official Pyright plugin.  
**Supported conceptually:** hybrid coverage + static graph, source-derived fixture map, adaptive worker planning.  
**Not proved on our exact repo:** full pinned coverage capture under 10 minutes, a valid `LibCST` speed advantage, testmon compatibility, ML score gain, runtime differential test profitability, any score below the current leaderboard.

This distinction must survive every Claude agent summary and final report.
