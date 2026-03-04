"""Course of Action development and wargaming.

Generates tactical COAs based on mission analysis, then wargames each
using simplified Lanchester-style attrition. This is analytical, not a
nested simulation -- produces rough estimates matching what real military
planning delivers. COAs are compared via weighted scoring and selected
using personality-biased softmax.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, replace
from datetime import datetime

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.c2.events import COASelectedEvent
from stochastic_warfare.c2.orders.types import MissionType
from stochastic_warfare.c2.planning.mission_analysis import MissionAnalysisResult
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ManeuverType(enum.IntEnum):
    """Maneuver scheme types available during COA development."""

    FRONTAL_ATTACK = 0
    FLANKING = 1
    ENVELOPMENT = 2
    TURNING_MOVEMENT = 3
    PENETRATION = 4
    DEFENSE_IN_DEPTH = 5
    MOBILE_DEFENSE = 6
    DELAY = 7
    WITHDRAWAL = 8
    SCREEN = 9


# ---------------------------------------------------------------------------
# Frozen dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskAssignment:
    """Assignment of a subordinate unit to a task within a COA."""

    subordinate_id: str
    task_description: str
    effort_weight: float  # fraction of force allocated (0--1)
    position: Position | None = None


@dataclass(frozen=True)
class FireSupportPlan:
    """Fire support allocation for a COA."""

    priority_target: str
    allocation: float  # fraction of fire support assets 0--1
    trigger: str  # "on_contact", "on_signal", "at_h_hour"


@dataclass(frozen=True)
class COATimeline:
    """A phase within a COA's execution timeline."""

    phase_name: str
    duration_s: float
    actions: tuple[str, ...]


@dataclass(frozen=True)
class WargameResult:
    """Output of simplified Lanchester wargaming for a single COA."""

    estimated_friendly_losses: float  # fraction 0--1
    estimated_enemy_losses: float  # fraction 0--1
    estimated_duration_s: float
    probability_of_success: float  # 0--1
    risk_level: str  # "LOW", "MODERATE", "HIGH", "EXTREME"


@dataclass(frozen=True)
class COAScore:
    """Weighted scoring of a COA across evaluation criteria."""

    mission_accomplishment: float  # 0--1
    force_preservation: float  # 0--1
    tempo: float  # 0--1
    simplicity: float  # 0--1
    total: float  # weighted sum


@dataclass(frozen=True)
class COA:
    """A Course of Action -- a potential scheme of maneuver with supporting plans."""

    coa_id: str
    name: str
    maneuver_type: ManeuverType
    main_effort_direction: float  # angle in degrees
    task_assignments: tuple[TaskAssignment, ...]
    fire_support: FireSupportPlan | None = None
    timeline: tuple[COATimeline, ...] = ()
    wargame_result: WargameResult | None = None
    score: COAScore | None = None


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class COAConfig(BaseModel):
    """Tuning parameters for COA development and wargaming."""

    max_coas: int = 3
    lanchester_exponent: float = 0.5  # 0=linear, 1=square law
    wargame_steps: int = 10
    terrain_defense_mult: float = 1.5  # defender terrain advantage
    score_weights: dict[str, float] = {
        "mission": 0.40,
        "preservation": 0.25,
        "tempo": 0.20,
        "simplicity": 0.15,
    }
    flanking_bonus: float = 0.15  # probability of success bonus for flanking
    envelopment_bonus: float = 0.25


# ---------------------------------------------------------------------------
# Offensive mission types
# ---------------------------------------------------------------------------

_OFFENSIVE_MISSIONS: frozenset[int] = frozenset({
    MissionType.ATTACK,
    MissionType.SEIZE,
    MissionType.MOVEMENT_TO_CONTACT,
    MissionType.BREACH,
    MissionType.AMBUSH,
    MissionType.RECON,
    MissionType.PATROL,
    MissionType.SUPPORT_BY_FIRE,
    MissionType.SUPPRESS,
    MissionType.SECURE,
})

_DEFENSIVE_MISSIONS: frozenset[int] = frozenset({
    MissionType.DEFEND,
    MissionType.DELAY,
})

# Simplicity scores by maneuver type (higher = simpler)
_SIMPLICITY: dict[int, float] = {
    ManeuverType.FRONTAL_ATTACK: 0.9,
    ManeuverType.FLANKING: 0.7,
    ManeuverType.ENVELOPMENT: 0.5,
    ManeuverType.TURNING_MOVEMENT: 0.4,
    ManeuverType.PENETRATION: 0.6,
    ManeuverType.DEFENSE_IN_DEPTH: 0.8,
    ManeuverType.MOBILE_DEFENSE: 0.6,
    ManeuverType.DELAY: 0.7,
    ManeuverType.WITHDRAWAL: 0.8,
    ManeuverType.SCREEN: 0.7,
}

# Echelon-based default durations (seconds)
_ECHELON_DURATION_S: dict[int, float] = {
    3: 3600.0,     # platoon
    4: 7200.0,     # company
    5: 14400.0,    # battalion (small)
    6: 28800.0,    # battalion
    7: 57600.0,    # brigade
    8: 86400.0,    # division
    9: 172800.0,   # corps
}

# Minimum echelon values for gating advanced maneuvers
_ECHELON_COMPANY = 4
_ECHELON_BATTALION = 6


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class COAEngine:
    """Develops, wargames, compares, and selects Courses of Action.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``COASelectedEvent`` when a COA is selected.
    rng : np.random.Generator
        Deterministic RNG for stochastic wargaming and selection.
    config : COAConfig | None
        Tuning parameters.  Uses defaults if ``None``.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: COAConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or COAConfig()
        self._develop_count: int = 0
        self._wargame_count: int = 0

    # -- COA development ----------------------------------------------------

    def develop_coas(  # noqa: PLR0913
        self,
        unit_id: str,
        analysis: MissionAnalysisResult,
        friendly_power: float,
        subordinate_ids: list[str],
        contacts: int,
        enemy_power: float,
        supply_level: float,
        terrain_advantage: float,
        echelon: int,
        doctrine_actions: list[str] | None = None,
    ) -> list[COA]:
        """Generate up to ``config.max_coas`` COAs based on mission analysis.

        Parameters
        ----------
        unit_id : str
            The planning unit.
        analysis : MissionAnalysisResult
            Output of mission analysis step.
        friendly_power : float
            Aggregate friendly combat power.
        subordinate_ids : list[str]
            IDs of subordinate units available for task assignment.
        contacts : int
            Number of detected enemy contacts.
        enemy_power : float
            Estimated aggregate enemy combat power.
        supply_level : float
            Current supply level (0.0--1.0).
        terrain_advantage : float
            Terrain advantage factor (>0 favors defender).
        echelon : int
            Echelon level of the planning unit.
        doctrine_actions : list[str] | None
            Optional doctrinal actions to consider (reserved for future use).

        Returns
        -------
        list[COA]
            Generated COAs, up to ``config.max_coas``.
        """
        # Determine if offensive or defensive mission
        mission_type = self._infer_mission_type(analysis)

        if mission_type in _DEFENSIVE_MISSIONS:
            coas = self._develop_defensive_coas(
                unit_id, analysis, subordinate_ids, echelon, terrain_advantage,
            )
        else:
            # Default to offensive
            coas = self._develop_offensive_coas(
                unit_id, analysis, subordinate_ids, echelon,
            )

        # Respect max_coas
        coas = coas[: self._config.max_coas]

        self._develop_count += 1

        logger.info(
            "Developed %d COAs for %s (mission=%s, echelon=%d)",
            len(coas), unit_id,
            "defensive" if mission_type in _DEFENSIVE_MISSIONS else "offensive",
            echelon,
        )

        return coas

    # -- Wargaming ----------------------------------------------------------

    def wargame_coa(  # noqa: PLR0913
        self,
        coa: COA,
        friendly_power: float,
        enemy_power: float,
        supply_level: float,
        terrain_advantage: float,
        staff_quality: float = 0.5,
    ) -> WargameResult:
        """Wargame a COA using simplified Lanchester attrition.

        Parameters
        ----------
        coa : COA
            The COA to evaluate.
        friendly_power : float
            Initial friendly combat power.
        enemy_power : float
            Initial enemy combat power.
        supply_level : float
            Current supply level (0.0--1.0).
        terrain_advantage : float
            Terrain advantage factor (>0 favors defender).
        staff_quality : float
            Staff proficiency (0.0--1.0), adds noise to results.

        Returns
        -------
        WargameResult
            Estimated outcome of the COA.
        """
        exp = self._config.lanchester_exponent
        steps = self._config.wargame_steps

        f_power = float(friendly_power)
        e_power = float(enemy_power)

        initial_f = f_power
        initial_e = e_power

        # Apply maneuver type bonuses
        maneuver = coa.maneuver_type
        if maneuver == ManeuverType.FLANKING:
            f_power *= (1.0 + self._config.flanking_bonus)
        elif maneuver == ManeuverType.ENVELOPMENT:
            f_power *= (1.0 + self._config.envelopment_bonus)
        elif maneuver in (ManeuverType.DEFENSE_IN_DEPTH, ManeuverType.MOBILE_DEFENSE):
            # Defensive maneuvers reduce effective enemy power via terrain
            e_power /= self._config.terrain_defense_mult
        elif maneuver == ManeuverType.DELAY:
            # Delay gets partial terrain benefit
            e_power /= (1.0 + (self._config.terrain_defense_mult - 1.0) * 0.5)

        # Apply terrain advantage for any defensive posture
        if terrain_advantage > 0 and maneuver not in (
            ManeuverType.DEFENSE_IN_DEPTH,
            ManeuverType.MOBILE_DEFENSE,
            ManeuverType.DELAY,
        ):
            # Non-defensive maneuvers face terrain penalty
            e_power *= (1.0 + terrain_advantage * 0.1)

        # Lanchester attrition loop
        for _ in range(steps):
            if f_power <= 0 or e_power <= 0:
                break

            # Loss rates proportional to enemy power^exponent / own power^exponent
            if f_power > 0 and e_power > 0:
                f_loss_rate = 0.02 * (e_power ** exp / max(f_power ** exp, 1e-10))
                e_loss_rate = 0.02 * (f_power ** exp / max(e_power ** exp, 1e-10))

                # Supply factor: low supply increases friendly losses
                if supply_level < 0.5:
                    f_loss_rate *= 1.5

                f_power -= f_power * f_loss_rate
                e_power -= e_power * e_loss_rate

        # Ensure non-negative
        f_power = max(0.0, f_power)
        e_power = max(0.0, e_power)

        # Compute results
        friendly_losses = 1.0 - f_power / max(initial_f, 1e-10)
        enemy_losses = 1.0 - e_power / max(initial_e, 1e-10)

        # Probability of success
        total_remaining = f_power + e_power
        if total_remaining > 0:
            p_success = f_power / total_remaining
        else:
            p_success = 0.5  # Both destroyed

        # Add staff quality noise
        noise = staff_quality * 0.1 * (self._rng.random() - 0.5) * 2.0
        p_success = max(0.0, min(1.0, p_success + noise))

        # Duration based on echelon and power ratio
        base_duration = 28800.0  # Default battalion duration
        for echelon_key in sorted(_ECHELON_DURATION_S.keys()):
            # Use the timeline if available, otherwise estimate
            base_duration = _ECHELON_DURATION_S.get(echelon_key, 28800.0)
        # Scale by power ratio -- harder fights take longer
        if friendly_power > 0:
            duration_scale = max(0.5, min(2.0, enemy_power / friendly_power))
        else:
            duration_scale = 2.0
        estimated_duration = base_duration * duration_scale

        # Risk level based on friendly losses
        if friendly_losses >= 0.5:
            risk_level = "EXTREME"
        elif friendly_losses >= 0.3:
            risk_level = "HIGH"
        elif friendly_losses >= 0.15:
            risk_level = "MODERATE"
        else:
            risk_level = "LOW"

        self._wargame_count += 1

        result = WargameResult(
            estimated_friendly_losses=friendly_losses,
            estimated_enemy_losses=enemy_losses,
            estimated_duration_s=estimated_duration,
            probability_of_success=p_success,
            risk_level=risk_level,
        )

        logger.debug(
            "Wargamed COA %s: P(success)=%.2f, friendly_losses=%.2f, risk=%s",
            coa.coa_id, p_success, friendly_losses, risk_level,
        )

        return result

    # -- Comparison ---------------------------------------------------------

    def compare_coas(
        self,
        coas: list[COA],
        score_weight_overrides: dict[str, float] | None = None,
    ) -> list[COA]:
        """Score and rank COAs by weighted criteria.

        Each COA must have a ``wargame_result`` set.

        Parameters
        ----------
        coas : list[COA]
            COAs to compare (must have wargame results).
        score_weight_overrides : dict[str, float] | None
            Override COA scoring weights (keys: ``mission``,
            ``preservation``, ``tempo``, ``simplicity``).
            ``None`` uses config defaults.

        Returns
        -------
        list[COA]
            COAs with ``score`` set, sorted by total descending.
        """
        weights = dict(self._config.score_weights)
        if score_weight_overrides:
            weights.update(score_weight_overrides)
        w_mission = weights.get("mission", 0.40)
        w_preservation = weights.get("preservation", 0.25)
        w_tempo = weights.get("tempo", 0.20)
        w_simplicity = weights.get("simplicity", 0.15)

        scored: list[COA] = []

        for coa in coas:
            if coa.wargame_result is None:
                logger.warning("COA %s has no wargame result, skipping", coa.coa_id)
                continue

            wg = coa.wargame_result

            mission_accomplishment = wg.probability_of_success
            force_preservation = 1.0 - wg.estimated_friendly_losses
            tempo = 1.0 - min(1.0, wg.estimated_duration_s / 86400.0)
            simplicity = _SIMPLICITY.get(coa.maneuver_type, 0.5)

            total = (
                w_mission * mission_accomplishment
                + w_preservation * force_preservation
                + w_tempo * tempo
                + w_simplicity * simplicity
            )

            score = COAScore(
                mission_accomplishment=mission_accomplishment,
                force_preservation=force_preservation,
                tempo=tempo,
                simplicity=simplicity,
                total=total,
            )

            scored.append(replace(coa, score=score))

        # Sort by total descending
        scored.sort(key=lambda c: c.score.total if c.score else 0.0, reverse=True)

        logger.info(
            "Compared %d COAs: top score=%.3f",
            len(scored),
            scored[0].score.total if scored and scored[0].score else 0.0,
        )

        return scored

    # -- Selection ----------------------------------------------------------

    def select_coa(
        self,
        ranked_coas: list[COA],
        risk_tolerance: float = 0.5,
        aggression: float = 0.5,
        ts: datetime | None = None,
    ) -> COA:
        """Select a COA using personality-biased softmax.

        Parameters
        ----------
        ranked_coas : list[COA]
            Scored COAs (must have ``score`` set).
        risk_tolerance : float
            Commander's risk tolerance (0=very cautious, 1=risk-taker).
        aggression : float
            Commander's aggressiveness (0=passive, 1=very aggressive).
        ts : datetime | None
            Simulation timestamp for the event.

        Returns
        -------
        COA
            The selected COA.
        """
        if not ranked_coas:
            raise ValueError("No COAs to select from")

        timestamp = ts or datetime.now()

        # Compute softmax weights with personality bias
        raw_weights: list[float] = []

        for coa in ranked_coas:
            if coa.score is None:
                raw_weights.append(1.0)
                continue

            w = math.exp(coa.score.total * 5.0)

            # Aggressive commanders: bonus for higher-risk COAs
            if coa.wargame_result is not None:
                risk = coa.wargame_result.risk_level
                if risk in ("HIGH", "EXTREME"):
                    w *= 1.0 + aggression
                elif risk == "LOW":
                    # Cautious commanders: bonus for lower-risk COAs
                    w *= 1.0 + (1.0 - risk_tolerance)

            raw_weights.append(w)

        # Normalize to probabilities
        total_weight = sum(raw_weights)
        if total_weight <= 0:
            probabilities = [1.0 / len(ranked_coas)] * len(ranked_coas)
        else:
            probabilities = [w / total_weight for w in raw_weights]

        # Select via rng.choice
        indices = np.arange(len(ranked_coas))
        selected_idx = int(self._rng.choice(indices, p=probabilities))
        selected = ranked_coas[selected_idx]

        # Publish event
        risk_level = "MODERATE"
        score_total = 0.0
        if selected.wargame_result is not None:
            risk_level = selected.wargame_result.risk_level
        if selected.score is not None:
            score_total = selected.score.total

        self._event_bus.publish(COASelectedEvent(
            timestamp=timestamp,
            source=ModuleId.C2,
            unit_id=selected.coa_id.rsplit("_coa_", 1)[0] if "_coa_" in selected.coa_id else "",
            coa_id=selected.coa_id,
            score=score_total,
            risk_level=risk_level,
        ))

        logger.info(
            "Selected COA %s (score=%.3f, risk=%s)",
            selected.coa_id, score_total, risk_level,
        )

        return selected

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict:
        """Serialize engine state for checkpoint/restore."""
        return {
            "develop_count": self._develop_count,
            "wargame_count": self._wargame_count,
            "rng_state": self._rng.bit_generator.state,
        }

    def set_state(self, state: dict) -> None:
        """Restore engine state from checkpoint."""
        self._develop_count = state["develop_count"]
        self._wargame_count = state["wargame_count"]
        self._rng.bit_generator.state = state["rng_state"]

    # -- Private helpers ----------------------------------------------------

    def _infer_mission_type(self, analysis: MissionAnalysisResult) -> int:
        """Infer mission type from the analysis restated mission text.

        Looks for keywords in the restated mission to determine if this
        is an offensive or defensive mission.
        """
        mission_lower = analysis.restated_mission.lower()
        for mt in _DEFENSIVE_MISSIONS:
            name = MissionType(mt).name.lower().replace("_", " ")
            if name in mission_lower:
                return mt

        # Default to offensive (ATTACK)
        return MissionType.ATTACK

    def _develop_offensive_coas(
        self,
        unit_id: str,
        analysis: MissionAnalysisResult,
        subordinate_ids: list[str],
        echelon: int,
    ) -> list[COA]:
        """Generate offensive COAs."""
        coas: list[COA] = []
        n_subs = len(subordinate_ids)

        # Key terrain for fire support if available
        priority_target = "objective area"
        if analysis.key_terrain_positions:
            kt = analysis.key_terrain_positions[0]
            priority_target = f"terrain at ({kt.easting:.0f}, {kt.northing:.0f})"

        # COA 1: Frontal attack (always available -- simplest)
        tasks = self._assign_tasks_frontal(subordinate_ids)
        timeline = self._build_offensive_timeline(echelon)
        fire_support = FireSupportPlan(
            priority_target=priority_target,
            allocation=0.8,
            trigger="at_h_hour",
        )
        coas.append(COA(
            coa_id=f"{unit_id}_coa_0",
            name="Frontal Attack",
            maneuver_type=ManeuverType.FRONTAL_ATTACK,
            main_effort_direction=0.0,
            task_assignments=tuple(tasks),
            fire_support=fire_support,
            timeline=tuple(timeline),
        ))

        # COA 2: Flanking maneuver (if 2+ subordinates)
        if n_subs >= 2:
            tasks = self._assign_tasks_flanking(subordinate_ids)
            timeline = self._build_offensive_timeline(echelon)
            fire_support = FireSupportPlan(
                priority_target=priority_target,
                allocation=0.6,
                trigger="on_contact",
            )
            coas.append(COA(
                coa_id=f"{unit_id}_coa_1",
                name="Flanking Maneuver",
                maneuver_type=ManeuverType.FLANKING,
                main_effort_direction=90.0,
                task_assignments=tuple(tasks),
                fire_support=fire_support,
                timeline=tuple(timeline),
            ))

        # COA 3: Envelopment (if 3+ subordinates and echelon >= company)
        if n_subs >= 3 and echelon >= _ECHELON_COMPANY:
            tasks = self._assign_tasks_envelopment(subordinate_ids)
            timeline = self._build_offensive_timeline(echelon)
            fire_support = FireSupportPlan(
                priority_target=priority_target,
                allocation=0.5,
                trigger="on_signal",
            )
            coas.append(COA(
                coa_id=f"{unit_id}_coa_2",
                name="Envelopment",
                maneuver_type=ManeuverType.ENVELOPMENT,
                main_effort_direction=180.0,
                task_assignments=tuple(tasks),
                fire_support=fire_support,
                timeline=tuple(timeline),
            ))

        return coas

    def _develop_defensive_coas(
        self,
        unit_id: str,
        analysis: MissionAnalysisResult,
        subordinate_ids: list[str],
        echelon: int,
        terrain_advantage: float,
    ) -> list[COA]:
        """Generate defensive COAs."""
        coas: list[COA] = []

        priority_target = "engagement area"
        if analysis.key_terrain_positions:
            kt = analysis.key_terrain_positions[0]
            priority_target = f"terrain at ({kt.easting:.0f}, {kt.northing:.0f})"

        # COA 1: Defense in depth (always available)
        tasks = self._assign_tasks_defense(subordinate_ids)
        timeline = self._build_defensive_timeline(echelon)
        fire_support = FireSupportPlan(
            priority_target=priority_target,
            allocation=0.7,
            trigger="on_contact",
        )
        coas.append(COA(
            coa_id=f"{unit_id}_coa_0",
            name="Defense in Depth",
            maneuver_type=ManeuverType.DEFENSE_IN_DEPTH,
            main_effort_direction=0.0,
            task_assignments=tuple(tasks),
            fire_support=fire_support,
            timeline=tuple(timeline),
        ))

        # COA 2: Mobile defense (if echelon >= battalion)
        if echelon >= _ECHELON_BATTALION:
            tasks = self._assign_tasks_mobile_defense(subordinate_ids)
            timeline = self._build_defensive_timeline(echelon)
            fire_support = FireSupportPlan(
                priority_target=priority_target,
                allocation=0.5,
                trigger="on_signal",
            )
            coas.append(COA(
                coa_id=f"{unit_id}_coa_1",
                name="Mobile Defense",
                maneuver_type=ManeuverType.MOBILE_DEFENSE,
                main_effort_direction=0.0,
                task_assignments=tuple(tasks),
                fire_support=fire_support,
                timeline=tuple(timeline),
            ))

        # COA 3: Delay (if terrain_advantage > 0)
        if terrain_advantage > 0:
            tasks = self._assign_tasks_delay(subordinate_ids)
            timeline = self._build_delay_timeline(echelon)
            fire_support = FireSupportPlan(
                priority_target=priority_target,
                allocation=0.4,
                trigger="on_contact",
            )
            coas.append(COA(
                coa_id=f"{unit_id}_coa_2",
                name="Delay",
                maneuver_type=ManeuverType.DELAY,
                main_effort_direction=0.0,
                task_assignments=tuple(tasks),
                fire_support=fire_support,
                timeline=tuple(timeline),
            ))

        return coas

    # -- Task assignment helpers --------------------------------------------

    def _assign_tasks_frontal(
        self,
        subordinate_ids: list[str],
    ) -> list[TaskAssignment]:
        """Assign tasks for frontal attack: main effort gets 0.6, rest split evenly."""
        if not subordinate_ids:
            return []

        tasks: list[TaskAssignment] = []

        # Main effort
        tasks.append(TaskAssignment(
            subordinate_id=subordinate_ids[0],
            task_description="Main effort -- assault objective",
            effort_weight=0.6,
        ))

        remaining = subordinate_ids[1:]
        if remaining:
            # Supporting effort gets 0.25, reserve 0.15
            if len(remaining) == 1:
                tasks.append(TaskAssignment(
                    subordinate_id=remaining[0],
                    task_description="Supporting effort -- suppress and support",
                    effort_weight=0.4,
                ))
            else:
                # First remaining is supporting, rest are reserve
                support_weight = 0.25
                tasks.append(TaskAssignment(
                    subordinate_id=remaining[0],
                    task_description="Supporting effort -- suppress and support",
                    effort_weight=support_weight,
                ))
                reserve_total = 0.15
                n_reserve = len(remaining) - 1
                per_reserve = reserve_total / n_reserve
                for sub_id in remaining[1:]:
                    tasks.append(TaskAssignment(
                        subordinate_id=sub_id,
                        task_description="Reserve",
                        effort_weight=per_reserve,
                    ))

        return tasks

    def _assign_tasks_flanking(
        self,
        subordinate_ids: list[str],
    ) -> list[TaskAssignment]:
        """Assign tasks for flanking: main effort (flank) 0.5, fix force 0.35, reserve 0.15."""
        tasks: list[TaskAssignment] = []

        if len(subordinate_ids) >= 1:
            tasks.append(TaskAssignment(
                subordinate_id=subordinate_ids[0],
                task_description="Main effort -- flanking maneuver",
                effort_weight=0.5,
            ))
        if len(subordinate_ids) >= 2:
            tasks.append(TaskAssignment(
                subordinate_id=subordinate_ids[1],
                task_description="Fixing force -- pin enemy frontally",
                effort_weight=0.35,
            ))
        if len(subordinate_ids) >= 3:
            reserve_total = 0.15
            n_reserve = len(subordinate_ids) - 2
            per_reserve = reserve_total / n_reserve
            for sub_id in subordinate_ids[2:]:
                tasks.append(TaskAssignment(
                    subordinate_id=sub_id,
                    task_description="Reserve",
                    effort_weight=per_reserve,
                ))

        return tasks

    def _assign_tasks_envelopment(
        self,
        subordinate_ids: list[str],
    ) -> list[TaskAssignment]:
        """Assign tasks for envelopment: two flanking forces + fix + reserve."""
        tasks: list[TaskAssignment] = []
        n = len(subordinate_ids)

        if n >= 1:
            tasks.append(TaskAssignment(
                subordinate_id=subordinate_ids[0],
                task_description="Main effort -- envelop from left",
                effort_weight=0.35,
            ))
        if n >= 2:
            tasks.append(TaskAssignment(
                subordinate_id=subordinate_ids[1],
                task_description="Supporting effort -- envelop from right",
                effort_weight=0.35,
            ))
        if n == 3:
            # No reserve -- fixing force gets the remainder
            tasks.append(TaskAssignment(
                subordinate_id=subordinate_ids[2],
                task_description="Fixing force -- pin enemy frontally",
                effort_weight=0.30,
            ))
        elif n >= 4:
            tasks.append(TaskAssignment(
                subordinate_id=subordinate_ids[2],
                task_description="Fixing force -- pin enemy frontally",
                effort_weight=0.20,
            ))
            reserve_total = 0.10
            n_reserve = n - 3
            per_reserve = reserve_total / n_reserve
            for sub_id in subordinate_ids[3:]:
                tasks.append(TaskAssignment(
                    subordinate_id=sub_id,
                    task_description="Reserve",
                    effort_weight=per_reserve,
                ))

        return tasks

    def _assign_tasks_defense(
        self,
        subordinate_ids: list[str],
    ) -> list[TaskAssignment]:
        """Assign tasks for defense in depth."""
        if not subordinate_ids:
            return []

        tasks: list[TaskAssignment] = []

        # Forward defense
        tasks.append(TaskAssignment(
            subordinate_id=subordinate_ids[0],
            task_description="Forward defense -- main battle position",
            effort_weight=0.5,
        ))

        remaining = subordinate_ids[1:]
        if remaining:
            if len(remaining) == 1:
                tasks.append(TaskAssignment(
                    subordinate_id=remaining[0],
                    task_description="Depth defense -- secondary positions",
                    effort_weight=0.5,
                ))
            else:
                tasks.append(TaskAssignment(
                    subordinate_id=remaining[0],
                    task_description="Depth defense -- secondary positions",
                    effort_weight=0.3,
                ))
                reserve_total = 0.2
                n_reserve = len(remaining) - 1
                per_reserve = reserve_total / n_reserve
                for sub_id in remaining[1:]:
                    tasks.append(TaskAssignment(
                        subordinate_id=sub_id,
                        task_description="Reserve -- counterattack force",
                        effort_weight=per_reserve,
                    ))

        return tasks

    def _assign_tasks_mobile_defense(
        self,
        subordinate_ids: list[str],
    ) -> list[TaskAssignment]:
        """Assign tasks for mobile defense: striking force is main effort."""
        if not subordinate_ids:
            return []

        tasks: list[TaskAssignment] = []

        # Striking force (main effort)
        tasks.append(TaskAssignment(
            subordinate_id=subordinate_ids[0],
            task_description="Striking force -- counterattack main effort",
            effort_weight=0.5,
        ))

        if len(subordinate_ids) >= 2:
            tasks.append(TaskAssignment(
                subordinate_id=subordinate_ids[1],
                task_description="Fixing force -- forward positions",
                effort_weight=0.35,
            ))

        if len(subordinate_ids) >= 3:
            reserve_total = 0.15
            n_reserve = len(subordinate_ids) - 2
            per_reserve = reserve_total / n_reserve
            for sub_id in subordinate_ids[2:]:
                tasks.append(TaskAssignment(
                    subordinate_id=sub_id,
                    task_description="Reserve",
                    effort_weight=per_reserve,
                ))

        return tasks

    def _assign_tasks_delay(
        self,
        subordinate_ids: list[str],
    ) -> list[TaskAssignment]:
        """Assign tasks for delay operations."""
        if not subordinate_ids:
            return []

        tasks: list[TaskAssignment] = []

        # Initial delay position
        tasks.append(TaskAssignment(
            subordinate_id=subordinate_ids[0],
            task_description="Initial delay position -- engage and disengage",
            effort_weight=0.5,
        ))

        remaining = subordinate_ids[1:]
        if remaining:
            if len(remaining) == 1:
                tasks.append(TaskAssignment(
                    subordinate_id=remaining[0],
                    task_description="Subsequent delay position",
                    effort_weight=0.5,
                ))
            else:
                weight_per = 0.5 / len(remaining)
                for sub_id in remaining:
                    tasks.append(TaskAssignment(
                        subordinate_id=sub_id,
                        task_description="Subsequent delay position",
                        effort_weight=weight_per,
                    ))

        return tasks

    # -- Timeline helpers ---------------------------------------------------

    def _build_offensive_timeline(self, echelon: int) -> list[COATimeline]:
        """Build a 3-phase offensive timeline."""
        base = _ECHELON_DURATION_S.get(echelon, 28800.0)

        return [
            COATimeline(
                phase_name="Shape",
                duration_s=base * 0.3,
                actions=("Establish support-by-fire", "Suppress enemy positions"),
            ),
            COATimeline(
                phase_name="Decisive",
                duration_s=base * 0.5,
                actions=("Main effort assault", "Destroy enemy on objective"),
            ),
            COATimeline(
                phase_name="Exploit",
                duration_s=base * 0.2,
                actions=("Consolidate on objective", "Prepare for counterattack"),
            ),
        ]

    def _build_defensive_timeline(self, echelon: int) -> list[COATimeline]:
        """Build a 3-phase defensive timeline."""
        base = _ECHELON_DURATION_S.get(echelon, 28800.0)

        return [
            COATimeline(
                phase_name="Preparation",
                duration_s=base * 0.4,
                actions=("Prepare positions", "Emplace obstacles"),
            ),
            COATimeline(
                phase_name="Defense",
                duration_s=base * 0.4,
                actions=("Engage enemy in engagement area", "Execute fires plan"),
            ),
            COATimeline(
                phase_name="Counterattack",
                duration_s=base * 0.2,
                actions=("Commit reserve", "Restore battle position"),
            ),
        ]

    def _build_delay_timeline(self, echelon: int) -> list[COATimeline]:
        """Build a 3-phase delay timeline."""
        base = _ECHELON_DURATION_S.get(echelon, 28800.0)

        return [
            COATimeline(
                phase_name="Initial Engagement",
                duration_s=base * 0.3,
                actions=("Engage from initial position", "Attrit enemy"),
            ),
            COATimeline(
                phase_name="Disengagement",
                duration_s=base * 0.3,
                actions=("Disengage under cover", "Move to next position"),
            ),
            COATimeline(
                phase_name="Subsequent Positions",
                duration_s=base * 0.4,
                actions=("Occupy subsequent positions", "Continue delay"),
            ),
        ]
