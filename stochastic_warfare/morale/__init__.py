"""Morale & Human Factors — Phase 4 of the stochastic warfare simulation.

Provides Markov-chain morale state transitions, unit cohesion modeling,
combat stress accumulation, experience progression, psychological operations,
and rout/rally/surrender mechanics. Production battle orchestration supplies
combat-derived inputs directly to ``MoraleRuntime``; morale publishes its
caused events without importing combat modules.
"""

from stochastic_warfare.morale.runtime import (
    MoraleAggregateArchive,
    MoraleAggregationPlan,
    MoraleDisaggregationPlan,
    MoraleRegistration,
    MoraleRuntime,
    MoraleRuntimeStatePlan,
    MoraleStateRecord,
)
from stochastic_warfare.morale.state import (
    MoraleConfig,
    MoraleState,
    MoraleStateMachine,
    MoraleTransitionCause,
)

__all__ = [
    "MoraleAggregateArchive",
    "MoraleAggregationPlan",
    "MoraleConfig",
    "MoraleDisaggregationPlan",
    "MoraleRegistration",
    "MoraleRuntime",
    "MoraleRuntimeStatePlan",
    "MoraleState",
    "MoraleStateMachine",
    "MoraleStateRecord",
    "MoraleTransitionCause",
]
