# Claude Code and Development Tooling — Evidence-Based Shortlist

**Goal:** improve development quality and iteration speed for RWX without wasting a short competition weekend on unverified extensions. **No item below was installed on the user's PC during this research.** Official/established software is evidence of maturity, *not proof that it will improve the RWX score*. Citations are in [`SOURCES.md`](SOURCES.md).

## Selection rubric

Adopt a tool only when:

1. Its publisher is identifiable and its documentation or source is accessible.
2. It addresses a concrete, current bottleneck, not merely a fashionable workflow.
3. It runs in the actual developer environment (Windows / WSL / Claude Code version).
4. It has an objective 5–15 minute smoke test and a rollback procedure.
5. It adds no untrusted network requirement or hidden evaluation dependency.
6. It respects license/repository limits and does not accidentally publish credentials.
7. Its benefit exceeds the setup and cognitive overhead *before Sunday*.

**Risk model:** an official marketplace can contain vendor plugins; official listing does not imply independent security review or fixed behavior. Anthropic explicitly warns that plugins can execute shell commands, start servers, and inject instructions. [S15], [S16]

## Tier 1 — install/use first (reputable + directly useful)

### A. First-party Claude Code + project `CLAUDE.md`

**Purpose:** reliable continuation, shared rules, benchmarking discipline.  
**Source:** Anthropic [S17].  
**Install:** no extension needed; place the supplied `CLAUDE.md` at repo root.  
**Smoke test:** ask Claude to summarize RWX score math, no-answer-table rule, verified baseline and next checkpoint *from the repo files*.  
**Risk:** excessive instructions waste context; keep root file concise and link to detailed docs.

### B. Official Claude Code `pyright-lsp` plugin + Pyright language server

**Purpose:** Go-to-definition, symbol references, and real-time Python diagnostics (not a static blast-radius oracle).  
**Publisher:** Anthropic's maintained code-intelligence plugin [S14].  
**Requirements:** Node/npm and a compatible `pyright-langserver` executable visible on the same terminal PATH as Claude. Check npm package publisher before installing.

**Candidate installation, terminal-based Claude Code:**

```powershell
# In your PowerShell terminal, if Node and npm are installed:
npm install -g pyright
Get-Command pyright-langserver
# Start claude; inside Claude Code (not PowerShell):
/plugin install pyright-lsp@claude-plugins-official
```

The official docs direct users to install the language-server binary first; if the binary command differs for your environment, **follow the plugin README rather than force these commands**. Claude may require a reload or restart. `pyright-lsp` doesn't package the binary. For hosted/cloud Claude sessions, the docs say plugin language servers do **not** start; do not assume this setup applies. [S14]

**Smoke test:** in a temporary feature branch, introduce a safe, reversible type/import error in a scratch file; observe LSP diagnostics, then revert the scratch file. Run `/plugin` Errors tab if it does not start.  
**Risk:** LSP can use memory and report false positives in dynamic Python; it doesn't prove a correct test mapping.

### C. Docker Desktop + WSL2 + Git/GitHub

**Purpose:** actual judge parity and team collaboration.  
**Sources:** official RWX kit [S02], GitHub CLI [S20].  
**Must do:** run `make sample` under Linux with organizer flags.  
**Optional:** `gh auth login`, `gh pr create` if your teammate is working on branches.  
**Risk:** Windows PowerShell redirection UTF-16, WSL I/O overhead on `/mnt/c`, stale Docker image, accidental push to main.  
**Value:** indispensable; much higher priority than any MCP plugin.

### D. Ruff

**Purpose:** fast Python linting/formatting; simple mistakes caught automatically.  
**Publisher:** Astral [S22]; organizer `requirements.lock` lists `ruff==0.15.6`.  
**Use:**

```powershell
python -m pip install ruff==0.15.6
ruff check selector.py tests_local
```

**Smoke test:** intentionally add an unused import to a scratch file, verify detection, then revert.  
**Risk:** replacing code formatting without review can create noisy diff; it does **not** improve predictions directly.

## Tier 2 — valuable research tools, conditional after a 5–15 minute spike

### E. `pytest-cov` and coverage.py contexts

**Purpose:** *core research infrastructure*, not Claude plugin.  
**Publisher:** pytest-dev + coverage.py maintainer [S04], [S05], [S07], [S26].  
**Recommendation:** **yes**, experiment immediately. Install into an isolated development/build image; use pinned version and `--cov-context=test` with pinned SQLGlot. Export via supported CoverageData API. Check that 10-minute clean build is achievable.

**Status:** documented feature; **no actual pinned-SQLGlot run yet**.

### F. Python `ast` / LibCST

**Purpose:** structural patch and function mapping.  
**Recommendation:** `ast` as default; **test** LibCST only if comment/position quality matters enough.  
**Source:** [S08], [S29].  
**Risk:** extra build/runtime complexity for uncertain gain.

### G. `pytest-testmon`

**Purpose:** independently compare an established change-aware Python test selector with our approach.  
**Recommendation:** experiment in a separate environment, **not automatic production integration**.  
**Source:** [S23].  
**Smoke test:** install on pinned base with matching pytest 9 and compare which tests it selects for synthetic changes; measure setup time and transitive misses.  
**Risk:** its normal database/working-tree workflow differs from RWX's per-patch output contract; may not handle fixtures or dynamic SQLGlot behavior in the way needed.

### H. Anthropic-maintained `code-review` plugin

**Purpose:** find suspicious edits, schema mistakes and forgotten edge cases in PRs.  
**Source:** [S28], [S16].  
**Candidate install inside Claude Code:** `/plugin install code-review@claude-plugins-official`.  
**Smoke test:** give it a small PR containing a deliberately invalid `workers` list and observe whether review catches it.  
**Risk:** extra tokens/time; subjective feedback, not scorer proof.

### I. GitHub's official MCP server

**Purpose:** Claude can read/open PRs and repository data through typed tools.  
**Publisher:** GitHub [S19]; Anthropic MCP docs [S25].  
**Recommendation:** conditional. If ordinary `git`, `gh`, or Claude Code GitHub support handles collaboration, **skip** MCP.  
**Smoke test:** connect with least privilege, inspect one issue/PR without writing, then test a deliberate permitted write on a disposable issue if needed.  
**Risk:** auth token scope, remote exposure and tool count overhead; not useful in offline judge runtime.

### J. Official Claude Code subagents / named skills

**Purpose:** parallel, bounded code audit vs static graph research, without massive context collisions.  
**Source:** [S18].  
**Recommendation:** use at most two focused workstreams (coverage-index builder, selector+QA). Run tasks on separate git branches/worktrees; main integrator owns `selector.py` and Dockerfile.  
**Smoke test:** have each report changed files and `git status` at end; merge only reviewed and tested commits.  
**Risk:** concurrent agents modifying same files, token expense, inconsistent assumptions.

## Tier 3 — optional human convenience; no proven score value

### K. Obsidian

**What it actually is:** established local Markdown notes application [S21]. It can display this research pack as an Obsidian vault, with backlinks and navigation. Claude Code can already read every `.md` file in the repository without Obsidian.

**Recommendation:** only install Obsidian if the team personally benefits from browsing and organizing extensive notes. **Do not install an Obsidian MCP/community integration for this competition by default.** Its safety, maintenance, and incremental benefit were not verified here. Keep the Git repo as source of truth.

**Quick proof:** open the folder containing this pack as an Obsidian vault, verify normal Markdown links. That does not install executable third-party community plugins.

### L. `uv` (Astral)

Mature and potentially faster at managing isolated developer dependencies [S27], but changing organizer's pinned test environment is a correctness risk. Optional for developer tooling only; preserve `requirements.lock` and Python base-image digest for judge-label parity.

## Tier 4 — skip until specific proof exists

| Tool/category | Current decision | Why |
|---|---|---|
| Random “AI improves Claude reasoning” MCP servers | **Avoid** | unverifiable benefit, code execution/context injection risks |
| Obsidian MCP/community plugins | **Avoid by default** | no measured contribution to test prediction; extra local server |
| Niche coverage/affected-test plugins without official docs | **Avoid** | risk of pytest 9 incompatibility and misleading coverage |
| Commercial predictive-test SaaS products | **Avoid** | runtime no-network and no historical corpus; vendor marketing is not benchmark |
| External LLM calls from judge container | **Avoid** | explicitly offline runtime; unreproducible/charged CPU cost |
| New large ML training pipeline | **Defer** | 30 public labels too few; high leakage/overfitting risk |
| Browser automation plugin | **Defer** | not needed for offline selector; submission can be done manually |
| Prompt marketplaces with unreviewed skills | **Avoid** | instructions are executable influence, no confidence in provenance |

## Tool activation checklist

Use this for every optional tool:

```markdown
Tool: 
Publisher / official source:
Version and installer:
Permission and network scope:
What exact RWX bottleneck it targets:
Pass/fail smoke test:
Test date, machine, command, result:
Measured improvement (iteration time, bug caught, or score):
Rollback/removal:
Decision: ADOPT / EXPERIMENT / SKIP
```

**Current state:** Only the competition sample selector was run and scored on the user's PC. The above extensions were researched, **not installed or independently benchmarked**. “Mature and reputable” does not mean “tested in this workspace.”
