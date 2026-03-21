"""Typed calibration schema for scenario configuration.

Replaces the free-form ``dict[str, Any]`` with a pydantic model that
validates keys at parse time.  Unknown keys cause ``ValidationError``.

A ``model_validator(mode="before")`` converts the existing flat YAML
format (``blue_cohesion: 0.9``, ``morale_base_degrade_rate: 0.01``)
into the structured nested form expected by the schema.

The ``.get(key, default)`` method preserves backward compatibility with
all ~51 existing ``cal.get()`` call sites across battle.py, engine.py,
scenario.py, scenario_runner.py, and campaign.py.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, model_validator


class SideCalibration(BaseModel):
    """Per-side calibration overrides."""

    model_config = ConfigDict(extra="forbid")

    cohesion: float | None = None
    force_ratio_modifier: float | None = None
    start_x: float | None = None
    start_y: float | None = None
    formation_spacing_m: float | None = None
    hit_probability_modifier: float | None = None
    target_size_modifier: float | None = None


class MoraleCalibration(BaseModel):
    """Morale subsystem calibration overrides.

    Defaults match :class:`~stochastic_warfare.morale.state.MoraleConfig`.
    """

    model_config = ConfigDict(extra="forbid")

    base_degrade_rate: float = 0.05
    base_recover_rate: float = 0.10
    casualty_weight: float = 2.0
    suppression_weight: float = 1.5
    leadership_weight: float = 0.3
    cohesion_weight: float = 0.4
    force_ratio_weight: float = 0.5
    transition_cooldown_s: float = 30.0
    degrade_rate_modifier: float = 1.0
    check_interval: int = 1


class CalibrationSchema(BaseModel):
    """Typed calibration overrides validated at parse time.

    ``extra="forbid"`` causes ``ValidationError`` for unknown keys,
    catching typos that previously failed silently.
    """

    model_config = ConfigDict(extra="forbid")

    # -- Global scalars ---------------------------------------------------
    hit_probability_modifier: float = 1.0
    target_size_modifier: float = 1.0
    visibility_m: float | None = None
    thermal_contrast: float = 1.0
    morale_degrade_rate_modifier: float = 1.0
    max_engagers_per_side: int = 0
    formation_spacing_m: float = 50.0

    # -- Thresholds -------------------------------------------------------
    destruction_threshold: float = 0.5
    disable_threshold: float = 0.3
    dew_disable_threshold: float = 0.5

    # -- Behavioral -------------------------------------------------------
    defensive_sides: list[str] = []
    dig_in_ticks: int = 30
    wave_interval_s: float = 300.0
    target_selection_mode: str = "threat_scored"
    roe_level: str | None = None
    enable_air_routing: bool = False

    # -- EW / SEAD --------------------------------------------------------
    jammer_coverage_mult: float = 1.0
    stealth_detection_penalty: float = 0.0
    sigint_detection_bonus: float = 0.0
    sam_suppression_modifier: float = 0.0
    sead_effectiveness: float | None = None
    sead_arm_effectiveness: float | None = None
    iads_degradation_rate: float | None = None
    drone_provocation_prob: float | None = None

    # -- Morale (nested) --------------------------------------------------
    morale: MoraleCalibration = MoraleCalibration()

    # -- Night gradation (Phase 52a) ----------------------------------------
    night_thermal_floor: float = 0.8

    # -- Weather → ballistics/sensors (Phase 52b) ---------------------------
    wind_accuracy_penalty_scale: float = 0.03
    rain_attenuation_factor: float = 1.0

    # -- C2 (Phase 53b) ----------------------------------------------------
    c2_min_effectiveness: float = 0.3
    enable_fog_of_war: bool = False

    # -- Concealment -------------------------------------------------------
    observation_decay_rate: float = 0.05
    engagement_concealment_threshold: float = 0.5

    # -- Target value weights (override BattleConfig defaults) -------------
    target_value_weights: dict[str, float] | None = None

    # -- Rout cascade (per-scenario tuning) ---------------------------------
    rout_cascade_radius_m: float | None = None
    rout_cascade_base_chance: float | None = None
    rout_cascade_shaken_susceptibility: float | None = None

    # -- Gas casualty (Phase 56f) ------------------------------------------
    gas_casualty_floor: float = 0.1
    gas_protection_scaling: float = 0.8

    # -- Weibull per-subsystem (Phase 56c) ---------------------------------
    subsystem_weibull_shapes: dict[str, float] = {}

    # -- Posture protection (Phase 58d) ------------------------------------
    posture_blast_protection: dict[str, float] | None = None
    posture_frag_protection: dict[str, float] | None = None

    # -- Seasonal & environment effects (Phase 59) -------------------------
    enable_seasonal_effects: bool = False
    enable_equipment_stress: bool = False
    enable_obstacle_effects: bool = False

    # -- Obscurants, fire, & visual environment (Phase 60) -----------------
    enable_obscurants: bool = False
    enable_fire_zones: bool = False
    enable_thermal_crossover: bool = False
    enable_nvg_detection: bool = False

    # -- Maritime, acoustic, & EM environment (Phase 61) -------------------
    enable_sea_state_ops: bool = False
    enable_acoustic_layers: bool = False
    enable_em_propagation: bool = False

    # -- Human factors & altitude (Phase 62) --------------------------------
    enable_human_factors: bool = False
    heat_casualty_base_rate: float = 0.02
    cold_casualty_base_rate: float = 0.015
    mopp_fov_reduction_4: float = 0.7
    mopp_reload_factor_4: float = 1.5
    mopp_comms_factor_4: float = 0.5
    altitude_sickness_threshold_m: float = 2500.0
    altitude_sickness_rate: float = 0.03

    # -- CBRN-environment interaction (Phase 62) -----------------------------
    enable_cbrn_environment: bool = False
    cbrn_washout_coefficient: float = 1e-4
    cbrn_arrhenius_ea: float = 50000.0
    cbrn_inversion_multiplier: float = 8.0
    cbrn_uv_degradation_rate: float = 0.1

    # -- Air combat environmental coupling (Phase 62) -----------------------
    enable_air_combat_environment: bool = False
    cloud_ceiling_min_attack_m: float = 500.0
    icing_maneuver_penalty: float = 0.15
    icing_power_penalty: float = 0.10
    icing_radar_penalty_db: float = 3.0
    wind_bvr_missile_speed_mps: float = 1000.0

    # -- Cross-module feedback loops (Phase 63) ----------------------------
    enable_event_feedback: bool = False
    enable_missile_routing: bool = False
    enable_c2_friction: bool = False
    degraded_equipment_threshold: float = 0.3

    # -- C2 friction & command delay (Phase 64) ----------------------------
    planning_available_time_s: float = 7200.0
    stratagem_concentration_bonus: float = 0.08
    stratagem_deception_bonus: float = 0.10
    order_propagation_delay_sigma: float = 0.4
    order_misinterpretation_base: float = 0.05

    # -- Space & EW sub-engine activation (Phase 65) -----------------------
    enable_space_effects: bool = False

    # -- Consequence enforcement (Phase 68) --------------------------------
    enable_fuel_consumption: bool = False
    enable_ammo_gate: bool = False
    fire_damage_per_tick: float = 0.01
    stratagem_duration_ticks: int = 100
    retreat_distance_m: float = 2000.0
    misinterpretation_radius_m: float = 500.0

    # -- Unconventional & mine warfare (Phase 66) -------------------------
    enable_unconventional_warfare: bool = False
    enable_mine_persistence: bool = False
    guerrilla_disengage_threshold: float = 0.3
    human_shield_pk_reduction: float = 0.5

    # -- Collections ------------------------------------------------------
    weapon_assignments: dict[str, str] = {}
    victory_weights: dict[str, float] | None = None

    # -- Per-side overrides -----------------------------------------------
    side_overrides: dict[str, SideCalibration] = {}

    # -- Dead-key safety list (silently dropped by before-validator) -------
    _DEAD_KEYS: ClassVar[set[str]] = {"advance_speed"}

    # Keys whose suffix identifies a per-side field
    _SIDE_SUFFIX_FIELDS: ClassVar[set[str]] = {
        "cohesion", "force_ratio_modifier",
        "start_x", "start_y", "formation_spacing_m",
        "hit_probability_modifier",
    }

    # Keys whose prefix identifies a per-side field
    _SIDE_PREFIX_FIELDS: ClassVar[set[str]] = {
        "target_size_modifier",
    }

    # Keys routed to nested morale config
    _MORALE_KEY_MAP: ClassVar[dict[str, str]] = {
        "morale_base_degrade_rate": "base_degrade_rate",
        "morale_base_recover_rate": "base_recover_rate",
        "morale_casualty_weight": "casualty_weight",
        "morale_suppression_weight": "suppression_weight",
        "morale_leadership_weight": "leadership_weight",
        "morale_cohesion_weight": "cohesion_weight",
        "morale_force_ratio_weight": "force_ratio_weight",
        "morale_transition_cooldown_s": "transition_cooldown_s",
        "morale_degrade_rate_modifier": "degrade_rate_modifier",
        "morale_check_interval": "check_interval",
    }

    @model_validator(mode="before")
    @classmethod
    def _flatten_to_structured(cls, data: Any) -> Any:  # noqa: C901
        """Convert flat YAML keys to nested structure.

        Handles three patterns:
        - ``morale_base_degrade_rate`` → ``morale.base_degrade_rate``
        - ``blue_cohesion`` → ``side_overrides.blue.cohesion``
        - ``target_size_modifier_red`` → ``side_overrides.red.target_size_modifier``
        - ``advance_speed`` → silently dropped (dead data)
        """
        if not isinstance(data, dict):
            return data

        # If already structured (from set_state/checkpoint), pass through
        if "side_overrides" in data or "morale" in data:
            return data

        result: dict[str, Any] = {}
        side_overrides: dict[str, dict[str, Any]] = {}
        morale: dict[str, Any] = {}

        for key, value in data.items():
            # Dead keys — silently drop
            if key in cls._DEAD_KEYS:
                continue

            # morale_degrade_rate_modifier is a top-level field that
            # battle.py reads directly — keep it there AND route to morale
            if key == "morale_degrade_rate_modifier":
                result[key] = value
                morale[cls._MORALE_KEY_MAP[key]] = value
                continue

            # Morale keys — route to nested morale dict
            if key in cls._MORALE_KEY_MAP:
                morale[cls._MORALE_KEY_MAP[key]] = value
                continue

            # Side-prefixed keys (prefix_{side}): target_size_modifier_red
            matched_prefix = False
            for prefix in cls._SIDE_PREFIX_FIELDS:
                if key.startswith(f"{prefix}_"):
                    side_name = key[len(prefix) + 1:]
                    if side_name not in side_overrides:
                        side_overrides[side_name] = {}
                    side_overrides[side_name][prefix] = value
                    matched_prefix = True
                    break
            if matched_prefix:
                continue

            # Side-suffixed keys ({side}_suffix): blue_cohesion
            matched_suffix = False
            for suffix in cls._SIDE_SUFFIX_FIELDS:
                if key.endswith(f"_{suffix}"):
                    side_name = key[:-(len(suffix) + 1)]
                    if side_name not in side_overrides:
                        side_overrides[side_name] = {}
                    side_overrides[side_name][suffix] = value
                    matched_suffix = True
                    break
            if matched_suffix:
                continue

            # Everything else → top-level field
            result[key] = value

        if morale:
            result["morale"] = morale
        if side_overrides:
            result["side_overrides"] = side_overrides

        return result

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-compatible accessor for backward compatibility.

        Supports all access patterns used by battle.py, scenario.py,
        scenario_runner.py, and campaign.py.
        """
        # 1. Direct field access
        if key in self.__class__.model_fields:
            val = getattr(self, key)
            # Return default for None-able fields when None
            if val is None:
                return default
            return val

        # 2. Morale prefix: morale_base_degrade_rate → morale.base_degrade_rate
        if key in self._MORALE_KEY_MAP:
            morale_field = self._MORALE_KEY_MAP[key]
            return getattr(self.morale, morale_field, default)

        # 3. Side-suffixed: {side}_cohesion → side_overrides[side].cohesion
        for suffix in self._SIDE_SUFFIX_FIELDS:
            if key.endswith(f"_{suffix}"):
                side_name = key[:-(len(suffix) + 1)]
                side = self.side_overrides.get(side_name)
                if side is not None:
                    val = getattr(side, suffix, None)
                    if val is not None:
                        return val
                return default

        # 4. Side-prefixed: target_size_modifier_{side}
        for prefix in self._SIDE_PREFIX_FIELDS:
            if key.startswith(f"{prefix}_"):
                side_name = key[len(prefix) + 1:]
                side = self.side_overrides.get(side_name)
                if side is not None:
                    val = getattr(side, prefix, None)
                    if val is not None:
                        return val
                return default

        return default

    def __contains__(self, key: str) -> bool:
        """Support ``key in calibration`` checks."""
        # Direct field
        if key in self.__class__.model_fields:
            val = getattr(self, key)
            # None means not explicitly set
            return val is not None

        # Morale prefix
        if key in self._MORALE_KEY_MAP:
            morale_field = self._MORALE_KEY_MAP[key]
            return hasattr(self.morale, morale_field)

        # Side-suffixed
        for suffix in self._SIDE_SUFFIX_FIELDS:
            if key.endswith(f"_{suffix}"):
                side_name = key[:-(len(suffix) + 1)]
                side = self.side_overrides.get(side_name)
                if side is not None:
                    return getattr(side, suffix, None) is not None
                return False

        # Side-prefixed
        for prefix in self._SIDE_PREFIX_FIELDS:
            if key.startswith(f"{prefix}_"):
                side_name = key[len(prefix) + 1:]
                side = self.side_overrides.get(side_name)
                if side is not None:
                    return getattr(side, prefix, None) is not None
                return False

        return False
