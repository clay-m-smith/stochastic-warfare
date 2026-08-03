"""Production-path runtime evidence controls for Phase 117."""

from pathlib import Path

from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    SimulationRuntimeFactory,
)
from stochastic_warfare.validation.historical_backtest import (
    HistoricalBacktestRunner,
    HistoricalStudyLoader,
)


ROOT = Path(__file__).resolve().parents[2]
ERA_CONTROL_PLAN = ROOT / "data/validation/historical_studies/agincourt_era_control_phase117.yaml"


def test_nonmodern_factory_run_persists_exact_era_evidence_deterministically() -> None:
    plan = HistoricalStudyLoader(ROOT).load(ERA_CONTROL_PLAN)
    prepared = SimulationRuntimeFactory().prepare(
        ROOT / plan.scenario_path,
        ROOT / plan.data_root,
        (
            AnalysisVariant(
                variant_id=plan.analysis.variant_id,
                calibration_patch=plan.analysis.calibration_patch,
            ),
        ),
    )

    first = HistoricalBacktestRunner(prepared, plan).run()
    second = HistoricalBacktestRunner(prepared, plan).run()

    assert first == second
    assert first.status == "PASS"
    assert first.eligibility.promotion_eligible is False
    assert "validation_source_lineage_unknown" in first.eligibility.reason_codes
    assert first.execution.effective_era_id == "ancient_medieval"
    assert len(first.execution.era_config_sha256) == 64
    assert len(first.execution.era_runtime_contract_sha256) == 64
    assert first.execution.metric_vectors == (("english_initial_entities_active", (5.0,)),)
    run = first.execution.runs[0]
    assert run.terminal_outcome.ticks_executed == 1
    assert run.terminal_outcome.duration_s == 5.0
    assert run.terminal_outcome.right_censored is True
    assert all(
        receipt.effective_era_id == first.execution.effective_era_id
        and receipt.era_config_sha256 == first.execution.era_config_sha256
        and receipt.era_runtime_contract_sha256 == first.execution.era_runtime_contract_sha256
        for receipt in run.receipts
    )
