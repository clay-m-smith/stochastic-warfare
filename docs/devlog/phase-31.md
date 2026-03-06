# Phase 31 — Documentation Site (GitHub Pages)

## Summary

First Block 3 phase. Deploys a professional documentation site at `clay-m-smith.github.io/stochastic-warfare` using MkDocs + Material for MkDocs. Adds comprehensive user-facing documentation alongside the existing developer-facing docs.

**Status**: **Complete**

## What Was Built

### Infrastructure (2 new files)

- **`mkdocs.yml`** — MkDocs configuration with Material theme (blue grey primary, light/dark toggle), search plugin, markdown extensions (tables, toc, admonition, superfences, highlight, tilde, tasklist, attr_list), 8-tab navigation structure
- **`.github/workflows/docs.yml`** — GitHub Actions workflow for automatic deployment to gh-pages on push to main (triggers on `docs/**` or `mkdocs.yml` changes)

### Landing Page (1 new file)

- **`docs/index.md`** — Site landing page with project overview, key capabilities (6 bullets), architecture-at-a-glance, getting started summary, documentation section quick-links, project status table, license

### User-Facing Documentation (6 new files)

- **`docs/guide/getting-started.md`** — Complete tutorial: prerequisites, installation, first scenario run (3-step walkthrough with code), understanding output (SimulationRunResult, VictoryResult, events), Monte Carlo batch runs, next steps links
- **`docs/guide/scenarios.md`** — Scenario library: YAML format reference (all fields annotated), modern scenario catalog (27 scenarios in 3 tables), historical scenario catalog by era (14 scenarios), custom scenario creation tips
- **`docs/concepts/architecture.md`** — Public-facing architecture: 12-module dependency chain, simulation loop (tick-based + event-driven), scale resolution table, tick processing order, spatial model (3 layers), ECS-like separation, engine wiring, null-config gating, era framework, determinism/reproducibility, checkpointing
- **`docs/concepts/models.md`** — All 10 mathematical models: Markov chains, Monte Carlo, Kalman filter, Poisson process, M/M/c queue, SNR detection (erfc), Lanchester attrition, Wayne Hughes salvo, Boyd OODA, Beer-Lambert DEW. Each with intuitive explanation, key formula, worked example, usage location, key parameters
- **`docs/reference/api.md`** — Complete API reference: ScenarioLoader, SimulationEngine, EngineConfig, SimulationRunResult, SimulationRecorder, VictoryEvaluator/VictoryResult, MonteCarloHarness/Config/Result, RNGManager, EventBus, SimulationClock, CampaignScenarioConfig. 4 usage pattern examples (basic run, MC batch, step-by-step, checkpoint/restore)
- **`docs/reference/eras.md`** — All 5 eras: era framework (enum, config), per-era sections (enabled modules, sensors, C2 delay, era-specific mechanics, key units, scenarios). Detailed mechanics: WW2 bracket firing/convoy/CEP, WW1 trench/barrage/gas, Napoleonic volley/melee/cavalry/formations/courier/foraging, Ancient archery/formations/siege/oar naval/visual signals
- **`docs/reference/units.md`** — Unit/weapon/ammo YAML schemas, modern units by domain (ground 15+, air 11+, air defense 4+, naval 5+), historical units by era, doctrine templates table (8 doctrines), commander profiles table (6 archetypes)

### Configuration Changes (2 modified files)

- **`pyproject.toml`** — Added `docs = ["mkdocs-material>=9.5"]` optional dependency
- **`.gitignore`** — Added `site/` (MkDocs build output)

## Design Decisions

1. **README.md excluded from MkDocs site** — Its repo-relative links work on GitHub; the docs site has its own `index.md` landing page tailored for docs visitors
2. **User-facing + developer docs in one site** — New user docs in `guide/`, `concepts/`, `reference/`; existing dev docs stay in place under Architecture (Internal), Development Phases, Devlog, Specifications tabs
3. **CI uses plain pip, not uv** — Docs workflow only needs `mkdocs-material`, no need for full project environment
4. **No tests** — `mkdocs build --strict` in CI is the validation. Docs-only phase.
5. **LaTeX formulas in models page** — MkDocs Material renders these via MathJax when available; fallback to inline code notation

## Deviations from Plan

- None significant. Plan was followed as written.

## Issues & Fixes

1. **`brainstorm-block2.md` missing from nav** — Initial nav structure omitted this file. Added to Architecture (Internal) section.
2. **Devlog anchor links** — Pre-existing anchor mismatches in `devlog/index.md` (links to `#known-limitations--post-mvp-refinements` etc. that don't match actual heading slugs in devlog files). These are INFO-level and don't cause build failures. Pre-existing issue, not introduced by Phase 31.

## Known Limitations

- MathJax not configured — formulas in `concepts/models.md` render as raw LaTeX unless MathJax extension is added. The inline code fallback notation is readable.
- Anchor link mismatches in `devlog/index.md` are pre-existing and cosmetic.

## Lessons Learned

- MkDocs Material's `--strict` mode catches missing nav references but not broken cross-page anchors (those are INFO level)
- The `site/` directory should be gitignored from the start
- Keeping README.md separate from the docs site index avoids link-path conflicts

## Postmortem

### 1. Delivered vs Planned
Phase 31 delivered exactly what was planned: MkDocs infrastructure, 8 user-facing docs (landing + 2 guide + 2 concepts + 3 reference), GitHub Actions CI, lockstep doc updates. Scope was well-calibrated.

### 2. Integration Audit
- `mkdocs.yml` references all 50 markdown files in `docs/` — verified via `mkdocs build --strict`
- `.github/workflows/docs.yml` triggers on `docs/**` and `mkdocs.yml` changes
- `pyproject.toml` `docs` optional dep group added
- `.gitignore` excludes `site/`
- No dead modules — all new files are infrastructure/docs, not source code

### 3. Test Quality Review
No tests added (docs-only phase). `mkdocs build --strict` serves as validation. All 7,307 existing engine tests pass.

### 4. API Surface Check
No Python source changes — N/A.

### 5. Deficit Discovery
No new deficits from this phase. Pre-existing anchor link mismatches in devlog/index.md documented as known limitation.

### 6. Documentation Freshness
Cross-doc audit (19 checks) run after Phase 31. Fixes applied:
- `docs/index.md` badge updated from phase-30 to phase-31
- `docs/index.md` YAML count corrected (~273 → ~700), scenario count corrected (42 → 41)
- `docs/reference/eras.md` WW1 scenario corrected (Verdun 1916 → Cambrai 1917)
- `README.md` YAML count corrected (~220 → ~700), test count corrected (7,111 → 7,307), scenario line updated

Skills updated for user-facing docs freshness:
- `/cross-doc-audit` expanded from 13 to 19 checks (added checks 14-19 for user-facing docs)
- `/update-docs` added rules 9-10 (user-facing docs tracking, MkDocs nav completeness)
- `/postmortem` step 6 expanded with 8 user-facing doc staleness checks
- `docs/skills-and-hooks.md` updated to document expanded skill scope

### 7. Performance Sanity
No engine changes — test suite runtime unchanged.

### 8. Summary
- **Scope**: On target
- **Quality**: High — all docs accurate against source, API signatures verified
- **Integration**: Fully wired — `mkdocs build --strict` passes clean
- **Deficits**: 0 new
- **Action items**: None — all audit issues fixed
