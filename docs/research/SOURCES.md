# RWX Research — Sources and Evidence Ledger

**Compiled:** November 20, 2026 (US Central).  
**Evidence categories:** `A` = binding competition spec or directly inspected starter code; `B` = primary maintainer documentation/research; `C` = public technical talk or product claims (may have bias); `D` = candidate tool not yet benchmarked on our exact project.

**Method:** Read the uploaded starter kit and `SCORING.md` directly; independently inspected local `sample/tests.json`, `sample/answers.json`, test definitions and v0.1 source. Researched organizer rules, primary tool manuals, peer-reviewed/industrial research, official Claude docs, and video transcripts. **Reviewed transcripts for the two listed YouTube talks via vidIQ, not the video frames or hands-on demo itself.** Video takeaways are reported as *speaker claims*, not independent benchmark results. No claims that suggested plugins were installed/tested on the user's Windows PC.

## Competition and uploaded materials

### [S01] Official RWX — Blast Radius track page — **A**
https://www.joinbuilders.org/buildathon/tracks/blast-radius

Directly verified: input/output contract, official score expression, CPU and wall limits, rebuild rules, allowed pinned-SQLGlot/source-only maps, prohibition on precomputed patch answers, final scoring/tie behavior and cutoff. More authoritative than earlier chat paraphrases. **Recheck at submission time** in case organizers change the page.

### [S02] Organizer-supplied `SCORING.md`, `score.py`, `README.md`, `Makefile`, `Dockerfile` — **A**
Local copies originally uploaded in `blast-radius-sample.tar.gz` and `/mnt/data/SCORING.md`.

Line-by-line reading supports integer-ms scoring, JSONL validation, 2s worker cost, 300s missed-commit penalty, median official run and exact Docker restrictions. The local scorer does *not* charge CPU unless passed separately; `make sample` runs the container then scores. Includes a crucial note that pytest 9 `unittest.subTest` may report a parent PASS while child SUBFAILED indicates the parent test should count as failed. Local copies are authoritative for supplied version, not a claim about changes in organizers' future scorer.

### [S03] Buildathon general rules — **A**
https://www.joinbuilders.org/buildathon

Two-person teams, MIT licensing, AI permitted, Sunday Nov 22 at 11 AM Eastern cutoff, public GitHub repository required for this track; final hidden scoring decides winner. The 1-second proximity tie is on S01.

### [S04] coverage.py dynamic contexts — **B**
https://coverage.readthedocs.io/en/latest/contexts.html

Coverage can record the contexts under which code executes. Per-test contexts are supported by pytest-cov. Code outside individual test phases may have an empty context and must not be mistaken for irrelevant code. **Not proof that all dependencies are captured.**

### [S05] coverage.py `CoverageData` API — **B**
https://coverage.readthedocs.io/en/latest/api_coveragedata.html

Use supported `.measured_files()`, `.contexts_by_lineno()`, `.lines()`, `.arcs()` query APIs to construct indexes instead of depending on internal SQLite schema. API behavior depends on collected coverage options.

### [S06] Pytest 9 unittest and subtests — **B**
https://docs.pytest.org/en/stable/how-to/unittest.html
https://docs.pytest.org/en/stable/how-to/subtests.html

Pytest can collect `unittest.TestCase` test methods and supports `unittest.subTest()` in modern versions. Version matters; use organizer's pinned `pytest==9.2.0` for result-ground-truth experiments.

### [S07] pytest-cov per-test context docs — **B**
https://pytest-cov.readthedocs.io/en/latest/readme.html
https://github.com/pytest-dev/pytest-cov/blob/master/docs/contexts.rst

`--cov-context=test` captures pytest test-phase contexts including the test node ID. **Not installed in the organizer's original requirements.lock**, so verify compatible version, installation source, overhead, and Docker build fit before adopting.

### [S08] LibCST official docs — **B / D for adoption**
https://libcst.readthedocs.io/en/latest/why_libcst.html
https://libcst.readthedocs.io/en/latest/metadata.html

LibCST is lossless and preserves comments and positions, unlike AST. Useful for tricky change mapping, but extra dependency/parse overhead is unmeasured here. `ast` from stdlib should be benchmark baseline.

### [S09] Meta Engineering — Predictive Test Selection, 2018 — **B (industrial report)**
https://engineering.fb.com/2018/11/21/developer-tools/predictive-test-selection/

Documents probabilistic selection across a very large CI system. Meta reports catching >99.9% of regressions before they are visible to others and running a third of transitively dependent tests. **These are Meta deployment results, not claims achievable in this 30-label, Python-only challenge.** The case supports the general necessity of change/test history and modeling uncertainty.

### [S10] Gradle / Develocity predictive selection talk — **C (vendor demonstration, transcript reviewed)**
https://www.youtube.com/watch?v=KxfrgJCdUjc

Transcript highlights: 03:06–04:00 describes historical outcomes; 12:35–14:50 covers missed failures, simulator/shadow mode and transparency; 15:05–16:50 warns about dynamic dispatch and limitations of pure static/dynamic test impact; 17:10–20:30 describes online model training and XGBoost ensemble. Presenter is promoting a product. **Take methodology, not unverified speed claims.**

### [S11] Google Research — Regression Test Selection at Scale, 2026 — **B**
https://research.google/pubs/regression-test-selection-at-scale-2/

Hybrid call graphs plus inexpensive graph structural features used to rank dependent tests of large core libraries. Study reports 40% of failing commits caught within a fixed 0.9%-of-test-cost budget. This is evidence for combining source graph and ranking, *not* evidence of exhaustive correctness.

### [S12] Google Research — Assessing Transition-based Test Selection, ICSE 2019 — **B**
https://research.google/pubs/assessing-transition-based-test-selection-algorithms-at-google/

Industrial evaluation notes that historical-transition heuristics are less reliable than often claimed; includes flakiness and realistic evaluation pitfalls. Supports holdouts and skepticism about easy ML wins.

### [S13] “1.5 Billion Tests Per Day,” TestCon Europe 2023 — **C (transcript reviewed)**
https://www.youtube.com/watch?v=5jtQGD8qZCE
https://confpad.io/conferences/testcon-europe-2023/1-5-billion-tests-per-day

Former Meta infrastructure engineer explains universal test runners and test histories (08:30–12:50), reverse-dependency selection limitations (12:53–14:40), and predictive selection (16:15–17:30). Historical details are speaker statements and do not guarantee RWX gains. The public talk page contains an AI-written summary; our video takeaways used the retrieved captions, not only that summary.

### [S14] Anthropic — Code Intelligence Plugins (Pyright LSP) — **B**
https://code.claude.com/docs/en/plugins/code-intelligence

Official docs list `pyright-lsp` with `pyright-langserver` binary, explain installation/validation, and state terminal-session-only LSP behavior; cloud sessions do not start plugin language servers. The plugin doesn't include the binary. This is the most directly task-relevant Claude add-on.

### [S15] Anthropic — Plugin security/trust — **B**
https://code.claude.com/docs/en/plugins/security

Plugins may execute shell commands/hooks, add binaries to PATH, start MCP/LSP servers, and insert instructions into Claude context. Neither official marketplace listing nor GitHub stars prove a plugin is safe or performant. Review before installing, restrict scope, record exact version.

### [S16] Anthropic — Official marketplaces and installation — **B**
https://code.claude.com/docs/en/plugins/anthropic-marketplaces
https://code.claude.com/docs/en/plugins/install

`claude-plugins-official` exists and is auto-added to ordinary interactive Claude Code sessions (unless configuration blocks it). Use `/plugin`, Discover; install from named marketplace. The older `claude-code-plugins` marketplace is deprecated. The catalog changes frequently. Official marketplace includes partner plugins **not all Anthropic-maintained**.

### [S17] Anthropic — Project memory and `CLAUDE.md` — **B**
https://code.claude.com/docs/en/memory

Persistent project instructions and referenced files. This pack includes a short, substantive `CLAUDE.md` that points to detailed documents without duplicating all material in every context window.

### [S18] Anthropic — Skills, subagents, VS Code — **B**
https://code.claude.com/docs/en/skills
https://code.claude.com/docs/en/sub-agents
https://code.claude.com/docs/en/ide-integrations

Supports named skills, agents for context isolation, and first-party editor integration. These can improve workflow but aren't magic performance multipliers; use only if their coordination cost is worth it.

### [S19] GitHub's official MCP server — **B / D for this project**
https://github.com/github/github-mcp-server
https://github.blog/changelog/2025-04-04-github-mcp-server-public-preview/

Maintained by GitHub. Supports repo/issue/PR interactions. It's a credible optional Claude integration but adds authentication and context/tool overhead versus existing Git/`gh` commands. Verify scopes and necessity before connecting.

### [S20] GitHub CLI official documentation — **B**
https://docs.github.com/en/github-cli/github-cli/quickstart

`gh auth login`, `gh pr create` are straightforward team collaboration alternatives to an MCP server, without persistent agent integration.

### [S21] Obsidian's own storage documentation — **B**
https://obsidian.md/help/data-storage
https://obsidian.md/help/

Obsidian organizes local Markdown files. It may make these docs nicer to browse, but is **not** a test-impact engine, is not required for Claude Code to read Markdown, and does not imply that an Obsidian–Claude MCP plugin has been audited. Optional human note-taking only.

### [S22] Astral Ruff official repository — **B**
https://github.com/astral-sh/ruff
https://docs.astral.sh/ruff/

Mature, maintained, fast linter/formatter. Useful to catch Python errors and enforce discipline, not evidence of selector scoring improvement. Existing organizer `requirements.lock` includes Ruff 0.15.6; preserve the organizer runtime lock for test-label parity.

### [S23] pytest-testmon project — **B for existence, D for adopting**
https://github.com/tarpas/pytest-testmon
https://www.testmon.org/blog/determining-affected-tests/
https://pypi.org/project/pytest-testmon/

Established coverage-assisted affected-test selector. We should **experiment with it as a comparator**, not put it straight into the final image. Verify correct behavior on pinned SQLGlot, pytest 9, `unittest.subTest`, changed fixtures, cross-dialect shared code, and build budget. Public repo/stars are insufficient validation for this use case.

### [S24] SQLGlot official source — **B (upstream project), A for pinned SHA from competition**
https://github.com/tobymao/sqlglot
https://github.com/tobymao/sqlglot/tree/eb11aec4be8cb2122afe713a4816662c3f0fb2fa

The competition names the exact SHA; this research session **could not retrieve the pinned checkout file contents** because direct browsing of that GitHub path failed. All design statements about exact cross-module structure are **investigations for Claude to verify on a clone**, not asserted verified internals.

### [S25] Anthropic — Connect Claude Code via MCP — **B**
https://code.claude.com/docs/en/mcp

MCP servers and credential scopes; avoid remote MCP during final Docker runtime (network disabled). MCP is a *developer workstation* convenience, not a solver dependency.

### [S26] Ned Batchelder (coverage.py maintainer), per-test contexts — **B**
https://nedbatchelder.com/blog/201910/pytestcov_support_for_whotestswhat

Primary maintainer example on recording “who tests what” using pytest-cov dynamic contexts. Makes coverage index approach more credible, not sufficient for final confidence alone.

### [S27] Astral uv official documentation — **B / D for adopting**
https://docs.astral.sh/uv/
https://docs.astral.sh/uv/concepts/projects/sync/

Mature package manager; useful for separate development tooling. **Do not replace organizer `requirements.lock` in label reproduction** without controlled parity tests.

### [S28] Official Claude Code code-review plugin — **B / D for workflow**
https://github.com/anthropics/claude-plugins-official/blob/main/plugins/code-review/README.md

Maintained in Anthropic's official repository; useful as a second-pass audit, but automated review is not a substitute for actual Docker execution or known failing-test coverage.

### [S29] LibCST & Python parser secondary learning source — **B**
https://libcst.readthedocs.io/en/latest/tutorial.html

Provides implementation examples for structural metadata. Specific use in this pinned SQLGlot codebase remains experimental.

## What we did NOT verify

- An official score for our `Qua5eyeNimbl` team; only local public sample output was shown.
- A working Linux Docker run on the user's machine. Desktop Commander connection was offline when checked in this session.
- A measured speed gain from Pyright, Obsidian, GitHub MCP, `pytest-testmon`, LibCST, or runtime differential testing for this project.
- The content of the *pinned* SQLGlot source checkout; clone and inspect it before trusting detailed call/fixture maps.
- Any prediction of hidden-set or final score, because the hidden patches and their labels are unavailable.

## Source selection discipline

Prefer binding competition rules, source code, primary project documentation, and reproducible experiments. Vendor talks and model announcements are inspiration, not performance proof. No sponsored rankings or affiliate plugin catalogs were used to choose tools.
