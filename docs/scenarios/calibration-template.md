# Block 11 Scenario Calibration Template

> **Phase 117 historical-claim supersession (2026-08-02):** This archived page
> preserves implementation history. Its historical-winner, outcome, casualty,
> duration, calibration, plausibility, envelope, and tolerance statements are
> not accepted historical validation. Any engine figures below are regression
> history only, not predictive evidence or calibration authority; the typed
> claim ledger and accepted production artifacts, if any, are authoritative.

> **Phase 112 integrity supersession (2026-07-30):** This page preserves the
> Block 11 calibration and regression template as development history. Its
> worked seeds, winner thresholds, helper calls, and sample configuration are
> not a current, provenance-bearing, held-out production validation contract
> and must not be cited as historical-accuracy evidence. Scenario availability,
> source citations, fitted inputs, and current-engine regression do not by
> themselves establish historical validation. REM-030/Phase 117 owns the
> replacement catalog-wide outcome-envelope contract and the disposition of
> every retained claim.

Block 11 treated each so-called golden scenario as if a local **outcome
envelope** and regression assertion validated historical fidelity. That premise
is retained here only as development history. These fragments are not strict
study plans, their helper tests are not historical verdicts, and none can
support `production_validated` without the Phase 117 ledger, production runner,
artifact, and explicit promotion contract.

This historical document records:

1. The envelope format
2. Permitted vs. forbidden calibration techniques
3. Citation discipline
4. Worked example

---

## 1. Legacy Envelope Format (Not a Validation Plan)

Block 11 described an envelope with four components. The examples below omit
required source-lineage, exact unit/extractor/event-boundary, immutable
predeclaration, production provenance, joint acceptance, and reload-validated
artifact fields. Treat a legacy helper result as
`current_engine_regression_only` only when it actually uses the production
factory path; otherwise it is `unsupported`.

### 1.1 Winner envelope

```yaml
winner_envelope:
  expected_winner: blue       # or "red" or "draw"
  min_rate: 0.7               # historical winner wins in ≥70% of 10-iteration MC
```

Historical rationale recorded by Block 11: history is one realization, so the
template used a modal-winner threshold. Under the current contract,
winner-only gating is invalid and winner agreement cannot substitute for an
independently sourced outcome metric.

### 1.2 Duration envelope

```yaml
duration_envelope:
  historical_s: 21600         # 6 hours main engagement
  tolerance: 0.5              # 10th–90th percentile spans 3h–9h (i.e., 50% of historical)
```

Historical rationale recorded by Block 11: weather, reaction time, and supply
delays motivated a broad duration range. The current contract does not invent a
percentage tolerance: it requires a source-backed inclusive range, exact unit,
comparable event boundary, and explicit cutoff censoring before results are
observed.

### 1.3 Casualty envelope (per side)

```yaml
casualty_envelopes:
  - side: red
    historical: 25            # Iraqi armor destroyed (rough historical figure)
    tolerance: 0.4            # 10th–90th percentile spans 15–35
  - side: blue
    historical: 0             # 0 KIA among SF team during main engagement
    max: 3                    # hard ceiling — higher means calibration is off
```

Historical rationale recorded by Block 11: casualty uncertainty motivated
broad percentage ranges and asymmetric ceilings. Under the current contract,
the source must support the actual range and population. KIA, total casualties,
people, vehicles, formations, and generic unit records are not interchangeable,
and a convenient tolerance cannot repair a unit mismatch.

### 1.4 Key-dynamic envelope

Scenario-specific assertions that a defining tactical moment gets reproduced.

```yaml
key_dynamics:
  - name: javelin_dominance
    description: "Javelin ATGM should dominate Iraqi armor kills"
    assertion: "javelin_clm caused >= 50% of Iraqi armor destructions"
  - name: cas_present
    description: "CAS should meaningfully engage"
    assertion: "at least 1 CAS engagement event per run"
```

Block 11 called these "depth tests." Today they are diagnostics unless a closed
production extractor, exact source assertion, unit, population, and
source-synchronous event boundary are predeclared. A proxy such as a weapon
share over a different vehicle population does not establish the historical
mechanism.

---

## 2. Historical Calibration Guidance

The lists below preserve Block 11's intended guardrails; they are not blanket
authorization to set fields or values. Current calibration requires a
schema-valid, production-wired parameter, traceable source/rationale, a frozen
backtest contract, separate training and held-out seeds, and validation on the
factory-owned route. Unsupported fields and unexercised overrides remain
explicitly unsupported.

### Permitted

- **Commander CEV** (`force_ratio_modifier`) within Dupuy-documented ranges (0.8–2.5 for symmetric forces; up to 3.0 for elite vs. conscript asymmetry with explicit historical justification)
- **ROE setting** (`WEAPONS_FREE`, `WEAPONS_TIGHT`, `HOLD_FIRE`) based on documented historical record
- **Initial morale state** per side from documented unit readiness AARs
- **Training level** per side from documented unit histories (e.g., conscript Iraqi armor: 0.3; Republican Guard: 0.6; US SF: 0.95)
- **Doctrine school** assignment explicit in historical record where documented (e.g., Fallujah Marines: `combined_arms_assault`)
- **Weather, terrain, time-of-day** from historical meteorological and geographical records
- **Enabling/configuring** existing `enable_*` flags to match scenario context (e.g., `enable_unconventional_warfare: true` for Fallujah)
- **IED density, emplacement patterns** from documented historical figures (per-kilometer or per-structure rates)
- **Per-side equipment allocation** (e.g., Iraqi T-55 vs. T-62 mix) per documented OOB

### Forbidden

- **Tuning per-weapon `Pk` values** to force a specific outcome. The weapon's Pk comes from manufacturer specs, operational testing (FM-series), or Jane's — never from "what makes this scenario work".
- **Disabling engines** to simplify modeling. If an engine produces unphysical behavior under a scenario, the fix is upstream in a follow-on block, not a per-scenario disable.
- **Implausible `force_ratio_modifier`** (>3.0 for any force; >2.5 for symmetric-era forces). Such values indicate the scenario's asymmetry needs a different representation (e.g., different unit types, better sensors, different posture).
- **Reducing IED/device density to "win faster"**. IED employment is a documented historical rate — matching that rate is the point.
- **Synthetic "historical" data**. Every calibration value cites a source.

### When the frozen envelope is missed

If after applying all permitted techniques the envelope is still missed by a wide margin, the correct response is:

1. **Document the miss** in the phase devlog with quantitative detail (what the engine produces vs. what's expected)
2. **Keep the frozen study and its `FAIL` artifact**; do not change its range,
   threshold, metrics, seeds, population, or event boundary after seeing the
   result
3. **Classify the historical claim as `unsupported`** (or classify a separate
   output snapshot as `current_engine_regression_only` when that is all it
   proves)
4. **Record a remediation item** for the specific model, extraction, source,
   unit, or scenario-representation gap
5. **Predeclare any later study independently** with a documented source or
   modeling rationale; never tune on its held-out seeds or describe reused
   evidence as independent validation

---

## 3. Citation Discipline

Every calibration value in a scenario YAML that overrides a default gets a comment citing the source:

```yaml
calibration_overrides:
  # Per Wong, "A Different Kind of War" (Combat Studies Institute 2011), p. 94:
  # Iraqi 34th Bde mech battalion in 2003 was a reserve formation with
  # notably low training readiness; estimate 0.3 vs. standard 0.5.
  red_training_override: 0.3

  # Per USCENTAF Operations Summary 2003: ROE permitted direct engagement
  # of any armored target north of 36th parallel.
  red_roe: WEAPONS_FREE
```

Sources must satisfy the `/research-military` skill's tiered source rules:

- **Tier 1** (required for primary calibration values): official military publications, AARs, FFRDC reports, unit histories
- **Tier 2** (acceptable): peer-reviewed military journals, academic presses
- **Tier 3** (supplementary cross-reference only): Jane's, IISS, reputable secondary scholarship (Bing West, Harel & Issacharoff)

Not acceptable: blogs, Wikipedia claims without primary citations, YouTube, unsourced news coverage.

---

## 4. Worked Example — Debecka Pass (from Phase 99)

The following YAML and tests are preserved as the Block 11 illustration. They
are not known to be a current schema-valid configuration, do not use the strict
claim ledger or study plan, and do not produce a reload-validated artifact.
They therefore cannot support a historical-validation claim. Debecka's current
catalog metadata also conflicts with the source-scoped duration and vehicle
counts, so it remains explicitly unsupported pending remediation and a new
predeclared production study.

```yaml
# data/scenarios/debecka_pass/scenario.yaml
name: "Debecka Pass 2003 — Task Force Viking vs. Iraqi 34th Bde mech"
date: "2003-04-06T13:00:00+04:00"
# ... OOB ...

calibration_overrides:
  # Per Wong "A Different Kind of War" Ch. 4:
  # Iraqi 34th Bde was understrength reserve formation
  red_training_override: 0.3
  red_cohesion: 0.4

  # Per USASOC 3rd SFG AAR + Wong p. 94-108:
  # ODB team pre-positioned with Javelins, observed OPFOR advance
  blue_posture: DEFENSIVE
  blue_roe: WEAPONS_FREE

  # Per CENTCOM Air Operations Center sortie logs:
  # Sustained CAS availability — 2x F-14D, 4x A-10 sorties during engagement
  enable_cas_routing: true
  cas_sortie_availability_per_hour: 2
```

```python
# tests/validation/test_debecka_pass.py
# Historical Block 11 regression sketch; not a historical-validation route.
def test_debecka_pass_envelope():
    results = run_scenario_batch(
        "data/scenarios/debecka_pass/scenario.yaml",
        overrides={},
        num_iterations=10, base_seed=42, max_ticks=5000,
        metric_names=["win_blue", "blue_destroyed", "red_destroyed", "ticks_executed"],
        data_dir="data",
    )
    # Winner envelope
    blue_win_rate = sum(results.metric_values("win_blue")) / 10
    assert blue_win_rate >= 0.7, f"Expected ≥70% blue wins, got {blue_win_rate:.0%}"

    # Casualty envelope
    avg_red_destroyed = sum(results.metric_values("red_destroyed")) / 10
    assert 15 <= avg_red_destroyed <= 40, \
        f"Iraqi destructions outside envelope: {avg_red_destroyed:.1f}"

    avg_blue_destroyed = sum(results.metric_values("blue_destroyed")) / 10
    assert avg_blue_destroyed <= 3, \
        f"SF casualties too high (historical: 0, max: 3): {avg_blue_destroyed:.1f}"

    # Duration envelope
    avg_ticks = sum(results.metric_values("ticks_executed")) / 10
    # 6 hours ± 50%, tick_duration_seconds=5.0 → 2160-6480 ticks
    assert 2160 <= avg_ticks <= 6480, f"Duration outside envelope: {avg_ticks:.0f} ticks"
```

The historical template also proposed a separate Javelin-dominance helper.
That proxy compared incompatible populations and had no source-synchronous
event boundary, so Phase 117 removed the sketch rather than preserving it as a
validation example.

---

## 5. Phase 117 Helper Removal

Phase 117 removed `stochastic_warfare/tools/envelope_check.py` and its synthetic
unit tests. The unused helpers returned local boolean `PASS`/`FAIL` labels or
event counts without loading the claim ledger and predeclared study plan,
executing the typed historical-study boundary, or writing a reload-validated
artifact. No compatibility shim remains.

Current historical work uses `HistoricalClaimLedgerLoader ->
HistoricalStudyLoader -> SimulationRuntimeFactory.prepare ->
HistoricalBacktestRunner -> load_historical_artifact`. A completed `PASS` still
requires a separate clean-revision, immutable-predeclaration, exact-metric
ledger promotion before any claim becomes `production_validated`.
