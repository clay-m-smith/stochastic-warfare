# Phase 14: Tooling & Developer Experience

## Overview
Phase 14 adds developer tooling: a Claude Code MCP server, analysis utilities, visualization tools, and 6 new Claude skills. All new code lives in `stochastic_warfare/tools/` — purely additive, no modifications to existing simulation code.

**Test count**: 125 new tests (4,372 total passing)

## Sub-phases

### 14a: MCP Server (36 tests)
- `tools/__init__.py` — Package init
- `tools/serializers.py` — JSON serialization for numpy, datetime, enum, Position, inf/nan, dataclasses, pydantic models
- `tools/result_store.py` — LRU cache (max 20) for run results with `store/get/latest/list_runs/clear`
- `tools/mcp_server.py` — FastMCP server with 7 tools: `run_scenario`, `query_state`, `run_monte_carlo`, `compare_results`, `list_scenarios`, `list_units`, `modify_parameter`
- `tools/mcp_resources.py` — 3 resource providers: `scenario://{name}/config`, `unit://{category}/{type}`, `result://{run_id}`

Key decisions:
- `asyncio.to_thread()` for blocking simulation calls
- All tools return JSON; errors return `{"error": true, "error_type": "...", "message": "..."}`
- `mcp[cli]>=1.2.0` as optional dependency (`uv sync --extra mcp`)
- Console script entry point: `stochastic-warfare-mcp`

### 14b: Analysis Tools (63 tests)
- `tools/narrative.py` — Registry-based template system with ~15 built-in formatters for event types. `generate_narrative()` groups events by tick, `format_narrative()` supports full/summary/timeline styles.
- `tools/tempo_analysis.py` — FFT spectral analysis of event frequency by 5 categories (Combat, Detection, C2, Morale, Movement). OODA cycle timing extraction from `OODAPhaseChangeEvent` sequences. 3-panel plot (time series, FFT spectrum, OODA boxplot).
- `tools/comparison.py` — A/B statistical comparison using Mann-Whitney U test with rank-biserial effect size. `compare_distributions()` for direct use, `run_comparison()` for full scenario-based comparison.
- `tools/sensitivity.py` — Parameter sweep over calibration overrides. Same seed sequence at every point. Errorbar plot output.
- `tools/_run_helpers.py` — Shared batch runner used by comparison and sensitivity modules. Temp YAML pattern from `CampaignRunner`.

### 14c: Visualization (26 tests)
- `tools/charts.py` — 6 chart functions: `force_strength_chart`, `engagement_network`, `supply_flow_diagram`, `engagement_timeline`, `morale_progression`, `mc_distribution_grid`. All return `matplotlib.figure.Figure`, no `plt.show()`.
- `tools/replay.py` — Animated battle replay via `FuncAnimation`. `extract_replay_frames()` from snapshot data, `create_replay()` with side-colored scatter plots and engagement lines, `save_replay()` to GIF/MP4.

Key decisions:
- `matplotlib.use("Agg")` at module level to avoid Tk backend issues on headless/Windows
- `networkx` graph for engagement network visualization (already a dependency)

### 14d: Claude Skills (no tests)
6 new skill files in `.claude/skills/`:
- `/scenario` — Interactive scenario creation/editing walkthrough
- `/compare` — Run two configs and summarize with statistical interpretation
- `/what-if` — Quick parameter sensitivity from natural language questions
- `/timeline` — Generate narrative from simulation run
- `/orbat` — Interactive order of battle builder
- `/calibrate` — Auto-tune calibration overrides to match historical metrics

## pyproject.toml Changes
- Added `mcp = ["mcp[cli]>=1.2.0"]` optional dependency group
- Added `stochastic-warfare-mcp` console script entry point

## Files Created
| File | Lines | Purpose |
|------|-------|---------|
| `tools/__init__.py` | 1 | Package init |
| `tools/serializers.py` | 92 | JSON serialization |
| `tools/result_store.py` | 80 | LRU result cache |
| `tools/mcp_server.py` | 310 | MCP server + 7 tools |
| `tools/mcp_resources.py` | 72 | MCP resource providers |
| `tools/narrative.py` | 240 | Battle narrative generation |
| `tools/tempo_analysis.py` | 270 | FFT tempo analysis |
| `tools/comparison.py` | 145 | A/B statistical comparison |
| `tools/sensitivity.py` | 130 | Parameter sweep |
| `tools/_run_helpers.py` | 165 | Shared batch runner |
| `tools/charts.py` | 230 | 6 chart functions |
| `tools/replay.py` | 220 | Animated replay |
| 7 skill SKILL.md files | ~150 each | Claude skill templates |
| 7 test files | 125 tests | Full test coverage |

## Lessons Learned
- **IntEnum vs Enum serialization**: `IntEnum` subclasses `int`, so the `isinstance(obj, int)` check fires before `isinstance(obj, enum.Enum)`. Must check enum first.
- **matplotlib Agg backend**: On Windows without proper Tk installation, `matplotlib.pyplot` fails to create figures. Setting `matplotlib.use("Agg")` at module level avoids the issue.
- **Mann-Whitney U with identical values**: `scipy.stats.mannwhitneyu` raises `ValueError` when all values are identical. Must catch and return p=1.0.
- **Temp YAML pattern reuse**: The `CampaignRunner` pattern of writing temp YAML for `ScenarioLoader` works well for parameter sweeps and comparisons.
- **No simulation code modified**: Phase 14 is purely additive — all 4,247 existing tests continue to pass unchanged.

## Postmortem

### 1. Delivered vs Planned
- **Scope**: On target. All 4 sub-phases delivered as planned (MCP server, analysis tools, visualization, skills).
- **Unplanned additions**: `/postmortem` skill created during postmortem process.
- **No items dropped or deferred**.

### 2. Integration Audit
- **Critical fix**: `mcp_resources.py` `register_resources()` was never called from `_create_server()` — dead code. **Fixed**: wired into `_create_server()`.
- All other modules properly imported and tested.
- All 6 new skills listed in both CLAUDE.md and `docs/skills-and-hooks.md`.
- `/postmortem` skill added to both locations.

### 3. Test Quality Review
- 7 test files covering all source modules.
- Integration tests verify run→query and run→compare chains.
- Resource provider tests added during postmortem (7 tests: valid/missing for each provider).
- Tests use fast paths (max_ticks=5, mock data) — no `@pytest.mark.slow` needed.

### 4. API Surface Check
- **Fixed**: `_run_single` return type annotation said `-> dict[str, Any]` but returned `tuple[dict, Any, Any]`. Corrected to `-> tuple[dict[str, Any], Any, Any]`.
- **Fixed**: `max_workers` parameter accepted but unused (no-op). Removed from `_tool_run_monte_carlo` and async wrapper.
- All public functions have type hints.
- `get_logger(__name__)` used consistently.

### 5. Deficit Discovery
- **Fixed**: `set()` used in `_tool_compare_results` violating deterministic iteration convention. Replaced with `sorted(dict.fromkeys(...))`.
- **Fixed**: Magic numbers (`[:500]`, `[:100]`, `max_size=20`) extracted to named constants `_MAX_STORE_SIZE`, `_MAX_STORED_EVENTS`, `_MAX_QUERY_EVENTS`.
- **Fixed**: `charts.py` supply threshold `0.2` hardcoded twice. Extracted to `_SUPPLY_CRITICAL_THRESHOLD`.
- **Minor (accepted)**: `_run_helpers.py` fragile `data_dir` derivation via `Path(scenario_path).parent.parent`. Acceptable since scenario paths always follow `data/scenarios/{name}/scenario.yaml` convention.

### 6. Documentation Freshness
- All lockstep docs updated: CLAUDE.md, project-structure.md, development-phases-post-mvp.md, devlog/index.md, README.md, MEMORY.md, skills-and-hooks.md.
- `/postmortem` skill added to CLAUDE.md skill table and skills-and-hooks.md.

### 7. Performance Sanity
- Phase 14 tests: 125 tests in ~2.1s. No performance regression.
- Full suite: 4,372 tests passing.

### 8. Summary
- **Scope**: On target
- **Quality**: High — all critical issues found and fixed
- **Integration**: Fully wired (after postmortem fix)
- **Deficits**: 0 new (all found items resolved in-phase)
- **Action items**: None — all issues resolved
