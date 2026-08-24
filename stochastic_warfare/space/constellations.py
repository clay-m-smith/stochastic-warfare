"""Constellation management, SpaceConfig, and top-level SpaceEngine.

Manages satellite constellations (GPS, GLONASS, imaging, SIGINT, early
warning, SATCOM) as collections of :class:`SatelliteState` objects.
Distributes satellites across orbital planes, propagates orbits, and
provides per-type/per-side queries.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Mapping, Sequence

import numpy as np

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.runtime_failure import (
    RuntimeFailureHandler,
    RuntimeFailurePolicyBinding,
)
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.space.config import (
    ASATAssetConfig,
    ASATOrderConfig,
    ASATType,
    ASATWeaponDefinition,
    ConstellationDefinition,
    ConstellationType,
    OrbitalElementsTemplate,
    SpaceConfig,
)
from stochastic_warfare.space.events import ConstellationDegradedEvent
from stochastic_warfare.space.orbits import (
    OrbitalElements,
    OrbitalMechanicsEngine,
    SatelliteState,
)

if TYPE_CHECKING:
    from stochastic_warfare.detection.intel_fusion import (
        IntelDeliveryReceipt,
        IntelFusionEngine,
    )
    from stochastic_warfare.entities.base import Unit
    from stochastic_warfare.space.isr import SpaceISREngine, SpaceISRUpdatePlan

logger = get_logger(__name__)


def _validated_float(
    value: Any,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Normalize a finite real number without leaking conversion errors."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be finite")
    try:
        normalized = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(normalized):
        raise ValueError(f"{label} must be finite")
    if minimum is not None and normalized < minimum:
        raise ValueError(f"{label} is outside its valid range")
    if maximum is not None and normalized > maximum:
        raise ValueError(f"{label} is outside its valid range")
    return normalized


__all__ = [
    "ASATAssetConfig",
    "ASATOrderConfig",
    "ASATType",
    "ASATWeaponDefinition",
    "ConstellationDefinition",
    "ConstellationManager",
    "ConstellationType",
    "OrbitalElementsTemplate",
    "SpaceConfig",
    "SpaceEngine",
]


# ---------------------------------------------------------------------------
# ConstellationManager
# ---------------------------------------------------------------------------


class ConstellationManager:
    """Manages satellite constellations — creation, propagation, queries."""

    def __init__(
        self,
        orbits: OrbitalMechanicsEngine,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: SpaceConfig | None = None,
    ) -> None:
        self._orbits = orbits
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or SpaceConfig()
        self._constellations: dict[str, ConstellationDefinition] = {}
        self._satellites: dict[str, SatelliteState] = {}
        self._constellation_sats: dict[str, list[str]] = {}
        self._sim_time_s: float = 0.0

    def add_constellation(self, definition: ConstellationDefinition) -> None:
        """Add a constellation and distribute satellites across planes."""
        cid = definition.constellation_id
        if cid in self._constellations:
            raise ValueError(f"Duplicate constellation_id {cid!r}")

        template = definition.orbital_elements_template
        pending: list[SatelliteState] = []
        pending_ids: set[str] = set()
        for p in range(definition.plane_count):
            raan = (
                template.raan_deg
                + 360.0 / definition.plane_count * p
            ) % 360.0
            for s in range(definition.sats_per_plane):
                nu = (
                    template.true_anomaly_deg
                    + 360.0 / definition.sats_per_plane * s
                ) % 360.0
                sid = f"{cid}_p{p}_s{s}"
                if sid in pending_ids or sid in self._satellites:
                    raise ValueError(f"Duplicate generated satellite_id {sid!r}")
                pending_ids.add(sid)
                elems = OrbitalElements(
                    semi_major_axis_m=template.semi_major_axis_m,
                    eccentricity=template.eccentricity,
                    inclination_deg=template.inclination_deg,
                    raan_deg=raan,
                    arg_perigee_deg=template.arg_perigee_deg,
                    true_anomaly_deg=nu,
                )
                pending.append(SatelliteState(
                    satellite_id=sid,
                    constellation_id=cid,
                    elements=elems,
                    side=definition.side,
                    current_true_anomaly_deg=nu,
                    current_raan_deg=raan,
                ))

        if len(pending) != definition.num_satellites:
            raise ValueError(
                f"Constellation {cid!r} generated {len(pending)} satellites, "
                f"expected {definition.num_satellites}",
            )

        self._constellations[cid] = definition
        self._constellation_sats[cid] = [
            satellite.satellite_id
            for satellite in pending
        ]
        for satellite in pending:
            self._satellites[satellite.satellite_id] = satellite

    def update(self, dt_s: float, sim_time_s: float) -> None:
        """Propagate all active satellites by *dt_s*."""
        normalized_dt = _validated_float(
            dt_s,
            "dt_s",
            minimum=0.0,
        )
        normalized_sim_time = _validated_float(
            sim_time_s,
            "sim_time_s",
            minimum=0.0,
        )
        self._sim_time_s = normalized_sim_time
        for sat in self._satellites.values():
            if sat.is_active:
                self._orbits.propagate(sat, normalized_dt)

    def visible_satellites(
        self,
        constellation_id: str,
        theater_lat: float,
        theater_lon: float,
        sim_time_s: float,
        min_elev: float = 5.0,
    ) -> list[SatelliteState]:
        """Return satellites in a constellation visible from a ground point."""
        result: list[SatelliteState] = []
        for sid in self._constellation_sats.get(constellation_id, []):
            sat = self._satellites[sid]
            if sat.is_active and self._orbits.is_visible_from(
                sat, theater_lat, theater_lon, sim_time_s, min_elev,
            ):
                result.append(sat)
        return result

    def get_constellations_by_type(
        self, ctype: ConstellationType,
    ) -> list[ConstellationDefinition]:
        """Return constellation definitions of a given type."""
        return [
            d for d in self._constellations.values()
            if d.constellation_type == int(ctype)
        ]

    def get_constellations_by_side(self, side: str) -> list[ConstellationDefinition]:
        """Return constellation definitions for a given side."""
        return [d for d in self._constellations.values() if d.side == side]

    def get_constellation(
        self,
        constellation_id: str,
    ) -> ConstellationDefinition | None:
        """Return one exact loaded constellation definition."""
        return self._constellations.get(constellation_id)

    def all_constellations(self) -> tuple[ConstellationDefinition, ...]:
        """Return loaded definitions in deterministic insertion order."""
        return tuple(self._constellations.values())

    def deactivate_satellite(
        self,
        satellite_id: str,
        cause: str,
        timestamp: Any,
    ) -> list[Exception]:
        """Deactivate one exact active satellite and publish its degradation.

        The transition is committed before observers are notified.  Observer
        failures are returned so an orchestrator can finish publishing its
        complete event batch before reporting them.
        """
        satellite = self._satellites.get(satellite_id)
        if satellite is None:
            raise ValueError(f"Unknown satellite_id {satellite_id!r}")
        if not satellite.is_active:
            raise ValueError(f"Satellite {satellite_id!r} is already inactive")

        previous_count = self.active_count(satellite.constellation_id)
        satellite.is_active = False
        event = ConstellationDegradedEvent(
            timestamp=timestamp,
            source=ModuleId.SPACE,
            constellation_id=satellite.constellation_id,
            previous_count=previous_count,
            new_count=previous_count - 1,
            cause=cause,
        )
        return self._event_bus.publish_collecting(event)

    def degrade_constellation(
        self,
        constellation_id: str,
        count: int,
        cause: str,
        timestamp: Any = None,
    ) -> list[str]:
        """Deactivate *count* active satellites from a constellation.

        Returns list of deactivated satellite IDs.
        """
        if constellation_id not in self._constellations:
            raise ValueError(f"Unknown constellation_id {constellation_id!r}")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("count must be a non-negative integer")
        sids = self._constellation_sats.get(constellation_id, [])
        active = [sid for sid in sids if self._satellites[sid].is_active]
        prev_count = len(active)
        to_kill = min(count, len(active))

        # Deactivate from the end (arbitrary but deterministic)
        killed: list[str] = []
        for i in range(to_kill):
            sid = active[-(i + 1)]
            self._satellites[sid].is_active = False
            killed.append(sid)

        if killed and timestamp is not None:
            failures = self._event_bus.publish_collecting(ConstellationDegradedEvent(
                timestamp=timestamp,
                source=ModuleId.SPACE,
                constellation_id=constellation_id,
                previous_count=prev_count,
                new_count=prev_count - len(killed),
                cause=cause,
            ))
            if failures:
                raise ExceptionGroup(
                    "Constellation degradation subscriber failures after "
                    "state commit",
                    failures,
                )

        return killed

    def active_count(self, constellation_id: str) -> int:
        """Number of active satellites in a constellation."""
        return sum(
            1 for sid in self._constellation_sats.get(constellation_id, [])
            if self._satellites[sid].is_active
        )

    def health_fraction(self, constellation_id: str) -> float:
        """Fraction of active satellites in a constellation."""
        sids = self._constellation_sats.get(constellation_id, [])
        if not sids:
            return 0.0
        active = sum(1 for sid in sids if self._satellites[sid].is_active)
        return active / len(sids)

    def get_satellite(self, satellite_id: str) -> SatelliteState | None:
        """Look up a satellite by ID."""
        return self._satellites.get(satellite_id)

    def all_satellites(self) -> list[SatelliteState]:
        """Return all satellites."""
        return list(self._satellites.values())

    # ── State persistence ────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        state: dict[str, Any] = {"sim_time_s": self._sim_time_s, "satellites": {}}
        for sid, sat in self._satellites.items():
            state["satellites"][sid] = {
                "is_active": sat.is_active,
                "true_anomaly_deg": sat.current_true_anomaly_deg,
                "raan_deg": sat.current_raan_deg,
            }
        return state

    def stage_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """Validate a complete manager snapshot without mutating live state."""
        if not isinstance(state, dict):
            raise ValueError("Constellation state must be a mapping")
        expected_keys = {"sim_time_s", "satellites"}
        if set(state) != expected_keys:
            raise ValueError(
                "Constellation state keys must be exactly "
                f"{sorted(expected_keys)!r}",
            )

        normalized_time = _validated_float(
            state["sim_time_s"],
            "Constellation sim_time_s",
            minimum=0.0,
        )

        raw_satellites = state["satellites"]
        if not isinstance(raw_satellites, dict):
            raise ValueError("Constellation satellites state must be a mapping")
        expected_ids = set(self._satellites)
        actual_ids = set(raw_satellites)
        if actual_ids != expected_ids:
            raise ValueError(
                "Constellation satellite topology mismatch: "
                f"missing={sorted(expected_ids - actual_ids)!r}, "
                f"extra={sorted(actual_ids - expected_ids)!r}",
            )

        staged_satellites: dict[str, dict[str, Any]] = {}
        satellite_keys = {
            "is_active",
            "true_anomaly_deg",
            "raan_deg",
        }
        for satellite_id in self._satellites:
            raw_satellite = raw_satellites[satellite_id]
            if not isinstance(raw_satellite, dict):
                raise ValueError(
                    f"State for satellite {satellite_id!r} must be a mapping",
                )
            if set(raw_satellite) != satellite_keys:
                raise ValueError(
                    f"State keys for satellite {satellite_id!r} must be "
                    f"exactly {sorted(satellite_keys)!r}",
                )
            is_active = raw_satellite["is_active"]
            if not isinstance(is_active, bool):
                raise ValueError(
                    f"Satellite {satellite_id!r} is_active must be boolean",
                )
            angles: dict[str, float] = {}
            for field_name in ("true_anomaly_deg", "raan_deg"):
                try:
                    angle = _validated_float(
                        raw_satellite[field_name],
                        f"Satellite {satellite_id!r} {field_name}",
                        minimum=0.0,
                        maximum=360.0,
                    )
                except ValueError as exc:
                    raise ValueError(
                        f"Satellite {satellite_id!r} {field_name} must be "
                        "finite and in [0, 360)",
                    ) from exc
                if angle >= 360.0:
                    raise ValueError(
                        f"Satellite {satellite_id!r} {field_name} must be "
                        "finite and in [0, 360)",
                    )
                angles[field_name] = angle
            staged_satellites[satellite_id] = {
                "is_active": is_active,
                **angles,
            }

        return {
            "sim_time_s": normalized_time,
            "satellites": staged_satellites,
        }

    def commit_state(self, staged_state: dict[str, Any]) -> None:
        """Commit a snapshot previously returned by :meth:`stage_state`."""
        self._sim_time_s = staged_state["sim_time_s"]
        for satellite_id, satellite_state in staged_state["satellites"].items():
            satellite = self._satellites[satellite_id]
            satellite.is_active = satellite_state["is_active"]
            satellite.current_true_anomaly_deg = satellite_state[
                "true_anomaly_deg"
            ]
            satellite.current_raan_deg = satellite_state["raan_deg"]

    def view_from_staged_state(
        self,
        staged_state: dict[str, Any],
    ) -> ConstellationManager:
        """Return an isolated manager view for cross-engine validation."""
        view = ConstellationManager(
            self._orbits,
            self._event_bus,
            self._rng,
            self._config,
        )
        for definition in self._constellations.values():
            view.add_constellation(definition)
        view.commit_state(staged_state)
        return view

    def set_state(self, state: dict[str, Any]) -> None:
        """Validate and atomically restore a complete manager snapshot."""
        self.commit_state(self.stage_state(state))


# ---------------------------------------------------------------------------
# SpaceEngine — top-level orchestrator
# ---------------------------------------------------------------------------


class SpaceEngine:
    """Top-level orchestrator wrapping all space sub-engines.

    Each sub-engine (GPS, ISR, early warning, SATCOM, ASAT) is optional
    and set after construction.
    """

    def __init__(
        self,
        config: SpaceConfig,
        constellation_manager: ConstellationManager,
        gps_engine: Any = None,
        isr_engine: SpaceISREngine | None = None,
        early_warning_engine: Any = None,
        satcom_engine: Any = None,
        asat_engine: Any = None,
        catalog_fingerprint: str = "",
    ) -> None:
        if not isinstance(catalog_fingerprint, str):
            raise ValueError("catalog_fingerprint must be a string")
        if catalog_fingerprint != catalog_fingerprint.strip():
            raise ValueError(
                "catalog_fingerprint must not contain surrounding whitespace",
            )
        self._config = config
        self._constellation_manager = constellation_manager
        self._gps_engine = gps_engine
        self._isr_engine = isr_engine
        self._early_warning_engine = early_warning_engine
        self._satcom_engine = satcom_engine
        self._asat_engine = asat_engine
        self._catalog_fingerprint = catalog_fingerprint
        self._runtime_failure_handler: RuntimeFailurePolicyBinding | None = None
        self._runtime_asat_owner: Any = None

    def bind_runtime_failure_handler(
        self,
        handler: RuntimeFailureHandler,
    ) -> None:
        """Bind one production failure-policy owner across the space facade."""
        binding = RuntimeFailurePolicyBinding(handler)
        existing = (
            self._runtime_failure_handler.resolve()
            if self._runtime_failure_handler is not None
            else None
        )
        if existing is not None and existing != handler:
            raise RuntimeError(
                "SpaceEngine already has a different runtime failure-policy "
                "owner",
            )
        if (
            existing is not None
            and self._asat_engine is not self._runtime_asat_owner
        ):
            raise RuntimeError(
                "SpaceEngine ASAT owner changed after runtime construction",
            )
        self._runtime_failure_handler = binding
        if existing is None:
            self._runtime_asat_owner = self._asat_engine
        if self._asat_engine is not None:
            bind = getattr(
                self._asat_engine,
                "bind_runtime_failure_handler",
                None,
            )
            if callable(bind):
                bind(handler)

    def validate_runtime_failure_handler(
        self,
        handler: RuntimeFailureHandler,
    ) -> None:
        """Reject failure-policy drift in this facade or its ASAT owner."""
        bound = (
            self._runtime_failure_handler.resolve()
            if self._runtime_failure_handler is not None
            else None
        )
        if bound != handler:
            raise RuntimeError(
                "SpaceEngine runtime failure-policy binding changed",
            )
        if self._asat_engine is not self._runtime_asat_owner:
            raise RuntimeError(
                "SpaceEngine ASAT owner changed after runtime construction",
            )
        if self._asat_engine is not None:
            validate = getattr(
                self._asat_engine,
                "validate_runtime_failure_handler",
                None,
            )
            if callable(validate):
                validate(handler)

    @property
    def constellation_manager(self) -> ConstellationManager:
        return self._constellation_manager

    @property
    def gps_engine(self) -> Any:
        return self._gps_engine

    @property
    def isr_engine(self) -> SpaceISREngine | None:
        return self._isr_engine

    @property
    def early_warning_engine(self) -> Any:
        return self._early_warning_engine

    @property
    def satcom_engine(self) -> Any:
        return self._satcom_engine

    @property
    def asat_engine(self) -> Any:
        return self._asat_engine

    @property
    def catalog_fingerprint(self) -> str:
        """Canonical fingerprint of the selected space runtime topology."""
        return self._catalog_fingerprint

    def update(
        self,
        dt_s: float,
        sim_time_s: float,
        em_environment: Any = None,
        comms_engine: Any = None,
        targets_by_side: Mapping[str, Sequence[Unit]] | None = None,
        cloud_cover: float = 0.0,
        timestamp: Any = None,
        intel_fusion: IntelFusionEngine | None = None,
    ) -> None:
        """Update all space sub-engines for the current tick."""
        if not self._config.enable_space:
            return

        # Freeze the complete imagery target topology before constellation,
        # ASAT, GPS, event, or shared SPACE state can mutate.
        isr_plan = self.preflight_update(
            dt_s,
            sim_time_s,
            targets_by_side=targets_by_side,
            cloud_cover=cloud_cover,
            intel_fusion=intel_fusion,
        )

        # 1. Propagate constellations
        self._constellation_manager.update(dt_s, sim_time_s)

        # 2. Advance existing ASAT timers/debris, then execute newly due
        # actions.  Production supplies the logical scenario timestamp.
        if self._asat_engine is not None:
            if timestamp is None:
                self._asat_engine.update(dt_s, sim_time_s)
            else:
                self._asat_engine.update(dt_s, sim_time_s, timestamp)
            if getattr(self._config, "enable_asat", False):
                self._asat_engine.execute_due_orders(sim_time_s, timestamp)

        # 3. GPS → drives EM environment
        if self._gps_engine is not None:
            self._gps_engine.update(dt_s, sim_time_s)
            if em_environment is not None and hasattr(em_environment, "set_constellation_accuracy"):
                # Use worst-case (max) accuracy across sides — EMEnvironment
                # is a shared state, not per-side.
                worst_accuracy = 0.0
                for side in ("blue", "red"):
                    gps_state = self._gps_engine.compute_gps_accuracy(side, sim_time_s)
                    worst_accuracy = max(worst_accuracy, gps_state.position_accuracy_m)
                em_environment.set_constellation_accuracy(worst_accuracy)

        # 4. ISR
        if self._isr_engine is not None:
            self._isr_engine.apply_update(
                isr_plan,
                intel_fusion=intel_fusion,
            )

        # 5. Early warning
        if self._early_warning_engine is not None:
            self._early_warning_engine.update(dt_s, sim_time_s)

        # 6. SATCOM → drives comms engine
        if self._satcom_engine is not None:
            self._satcom_engine.update(dt_s, sim_time_s)
            if comms_engine is not None and hasattr(comms_engine, "set_satcom_reliability"):
                for side in ("blue", "red"):
                    factor = self._satcom_engine.get_reliability_factor(side, sim_time_s)
                    comms_engine.set_satcom_reliability(factor)

    def preflight_update(
        self,
        dt_s: float,
        sim_time_s: float,
        *,
        targets_by_side: Mapping[str, Sequence[Unit]] | None = None,
        cloud_cover: float = 0.0,
        intel_fusion: IntelFusionEngine | None = None,
    ) -> SpaceISRUpdatePlan | None:
        """Validate Space ISR inputs and fusion lifecycle without mutation."""
        if not self._config.enable_space or self._isr_engine is None:
            return None
        from stochastic_warfare.space.isr import SpaceISRIntegrityError

        try:
            return self._isr_engine.prepare_update(
                dt_s,
                sim_time_s,
                targets_by_side,
                cloud_cover,
                intel_fusion=intel_fusion,
            )
        except SpaceISRIntegrityError:
            raise
        except Exception as exc:
            raise SpaceISRIntegrityError(
                "Unexpected Space ISR generation preflight failure",
            ) from exc

    # ── Phase 54e: public GPS convenience API ───────────────────────

    def get_gps_cep(self, side: str = "", sim_time_s: float = 0.0) -> float:
        """Get GPS CEP in metres.  Returns large value if GPS unavailable."""
        if self._gps_engine is None:
            return 100.0
        try:
            state = self._gps_engine.compute_gps_accuracy(side, sim_time_s)
            cep = state.position_accuracy_m
            if (
                isinstance(cep, bool)
                or not isinstance(cep, (int, float))
                or not math.isfinite(float(cep))
                or float(cep) < 0.0
            ):
                raise ValueError(
                    "GPS owner returned an invalid position_accuracy_m",
                )
            return float(cep)
        except Exception as exc:
            binding = getattr(
                self,
                "_runtime_failure_handler",
                None,
            )
            handler = (
                binding.resolve()
                if binding is not None
                else None
            )
            if handler is None or not handler(
                "space.gps",
                "get_cep",
                exc,
            ):
                raise
            return 100.0

    # ── State persistence ────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        state: dict[str, Any] = {
            "catalog_fingerprint": self._catalog_fingerprint,
        }
        state["constellation_manager"] = self._constellation_manager.get_state()
        for name, eng in [
            ("gps_engine", self._gps_engine),
            ("isr_engine", self._isr_engine),
            ("early_warning_engine", self._early_warning_engine),
            ("satcom_engine", self._satcom_engine),
            ("asat_engine", self._asat_engine),
        ]:
            if eng is not None and hasattr(eng, "get_state"):
                state[name] = eng.get_state()
        return state

    def stage_state(
        self,
        state: dict[str, Any],
        *,
        expected_elapsed_s: float | None = None,
        expected_tick_count: int | None = None,
        expected_sides: tuple[str, ...] | None = None,
        expected_units_by_side: Mapping[str, Sequence[Unit]] | None = None,
        delivered_receipts: Sequence[IntelDeliveryReceipt] = (),
    ) -> dict[str, Any]:
        """Validate a complete space snapshot without mutating live engines."""
        if not isinstance(state, dict):
            raise ValueError("Space engine state must be a mapping")
        normalized_elapsed: float | None = None
        if expected_elapsed_s is not None:
            normalized_elapsed = _validated_float(
                expected_elapsed_s,
                "Expected space elapsed time",
                minimum=0.0,
            )
        normalized_tick_count: int | None = None
        if expected_tick_count is not None:
            if (
                isinstance(expected_tick_count, bool)
                or not isinstance(expected_tick_count, int)
                or expected_tick_count < 0
            ):
                raise ValueError(
                    "Expected space tick count must be a non-negative integer",
                )
            normalized_tick_count = expected_tick_count

        engines = [
            ("gps_engine", self._gps_engine),
            ("isr_engine", self._isr_engine),
            ("early_warning_engine", self._early_warning_engine),
            ("satcom_engine", self._satcom_engine),
            ("asat_engine", self._asat_engine),
        ]
        expected_keys = {
            "catalog_fingerprint",
            "constellation_manager",
        }
        expected_keys.update(
            name
            for name, engine in engines
            if engine is not None and hasattr(engine, "get_state")
        )
        if set(state) != expected_keys:
            raise ValueError(
                "Space engine state topology mismatch: "
                f"missing={sorted(expected_keys - set(state))!r}, "
                f"extra={sorted(set(state) - expected_keys)!r}",
            )
        fingerprint = state["catalog_fingerprint"]
        if not isinstance(fingerprint, str):
            raise ValueError(
                "Space engine catalog_fingerprint must be a string",
            )
        if fingerprint != self._catalog_fingerprint:
            raise ValueError(
                "Space engine catalog fingerprint does not match runtime "
                "configuration",
            )

        staged: dict[str, Any] = {
            "catalog_fingerprint": fingerprint,
            "constellation_manager": (
                self._constellation_manager.stage_state(
                    state["constellation_manager"],
                )
            ),
        }
        if (
            normalized_elapsed is not None
            and not math.isclose(
                staged["constellation_manager"]["sim_time_s"],
                normalized_elapsed,
                rel_tol=0.0,
                abs_tol=1.0e-9,
            )
        ):
            raise ValueError(
                "Constellation simulation time does not match the checkpoint "
                "clock elapsed time",
            )
        staged_manager = self._constellation_manager.view_from_staged_state(
            staged["constellation_manager"],
        )
        for name, eng in [
            ("gps_engine", self._gps_engine),
            ("isr_engine", self._isr_engine),
            ("early_warning_engine", self._early_warning_engine),
            ("satcom_engine", self._satcom_engine),
            ("asat_engine", self._asat_engine),
        ]:
            if eng is None or name not in state:
                continue
            raw_engine_state = state[name]
            if not isinstance(raw_engine_state, dict):
                raise ValueError(f"{name} state must be a mapping")
            if name in {"gps_engine", "satcom_engine"}:
                staged[name] = eng.stage_state(
                    raw_engine_state,
                    constellation_manager=staged_manager,
                    sim_time_s=staged[
                        "constellation_manager"
                    ]["sim_time_s"],
                    expected_tick_count=normalized_tick_count,
                )
            elif name == "isr_engine":
                assert self._isr_engine is not None
                staged[name] = self._isr_engine.stage_state(
                    raw_engine_state,
                    expected_elapsed_s=normalized_elapsed,
                    expected_sides=expected_sides,
                    expected_units_by_side=expected_units_by_side,
                    delivered_receipts=delivered_receipts,
                )
            elif hasattr(eng, "stage_state"):
                staged[name] = eng.stage_state(raw_engine_state)
            elif hasattr(eng, "validate_state"):
                if name == "asat_engine":
                    staged[name] = eng.validate_state(
                        raw_engine_state,
                        expected_elapsed_s=normalized_elapsed,
                        expected_tick_count=normalized_tick_count,
                    )
                else:
                    staged[name] = eng.validate_state(raw_engine_state)
            else:
                staged[name] = self._stage_service_state(
                    name,
                    raw_engine_state,
                    constellation_manager=staged_manager,
                    sim_time_s=staged[
                        "constellation_manager"
                    ]["sim_time_s"],
                )
        self._validate_cross_engine_state(staged)
        return staged

    def _stage_service_state(
        self,
        name: str,
        state: dict[str, Any],
        *,
        constellation_manager: ConstellationManager,
        sim_time_s: float,
    ) -> dict[str, Any]:
        """Strictly stage legacy space-service state at the runtime boundary."""
        if name == "early_warning_engine":
            if state:
                raise ValueError("early_warning_engine state must be empty")
            return {}
        raise ValueError(f"Unsupported space service state {name!r}")

    def _validate_cross_engine_state(self, staged: dict[str, Any]) -> None:
        """Validate invariants jointly owned by ASAT and constellation state."""
        asat_state = staged.get("asat_engine")
        if not isinstance(asat_state, dict):
            return
        completed = asat_state.get("completed_orders")
        if not isinstance(completed, dict):
            return

        satellite_state = staged["constellation_manager"]["satellites"]
        total_by_constellation: dict[str, int] = {}
        active_by_constellation: dict[str, int] = {}
        for runtime_satellite in self._constellation_manager.all_satellites():
            satellite_id = runtime_satellite.satellite_id
            constellation_id = runtime_satellite.constellation_id
            total_by_constellation[constellation_id] = (
                total_by_constellation.get(constellation_id, 0) + 1
            )
            if satellite_state[satellite_id]["is_active"]:
                active_by_constellation[constellation_id] = (
                    active_by_constellation.get(constellation_id, 0) + 1
                )

        latest_count_by_constellation: dict[str, tuple[float, int]] = {}
        for order_id, result in completed.items():
            target_id = result["target_satellite_id"]
            target_state = satellite_state.get(target_id)
            if target_state is None:
                raise ValueError(
                    f"Completed ASAT order {order_id!r} references a target "
                    "outside constellation state",
                )
            if result["hit"] and target_state["is_active"]:
                raise ValueError(
                    f"Completed ASAT hit {order_id!r} has an active target "
                    f"{target_id!r} in constellation state",
                )
            if (
                result["reason"] == "target_inactive"
                and target_state["is_active"]
            ):
                raise ValueError(
                    f"Completed ASAT target_inactive rejection {order_id!r} "
                    f"has an active target {target_id!r} in constellation "
                    "state",
                )
            constellation_id = result["target_constellation_id"]
            total_count = total_by_constellation.get(constellation_id)
            if total_count is None:
                raise ValueError(
                    f"Completed ASAT order {order_id!r} references unknown "
                    f"constellation {constellation_id!r}",
                )
            final_active = active_by_constellation.get(constellation_id, 0)
            prior_count = latest_count_by_constellation.get(constellation_id)
            if prior_count is not None:
                prior_execution_time, prior_new_count = prior_count
                if (
                    result["previous_constellation_count"] > prior_new_count
                    or (
                        result["execution_time_s"] == prior_execution_time
                        and result["previous_constellation_count"]
                        != prior_new_count
                    )
                ):
                    raise ValueError(
                        f"Completed ASAT order {order_id!r} constellation "
                        "count history is not chronological",
                    )
            latest_count_by_constellation[constellation_id] = (
                result["execution_time_s"],
                result["new_constellation_count"],
            )
            if (
                result["previous_constellation_count"] > total_count
                or result["new_constellation_count"] > total_count
                or final_active > result["new_constellation_count"]
            ):
                raise ValueError(
                    f"Completed ASAT order {order_id!r} constellation counts "
                    "disagree with staged constellation state",
                )

    def commit_state(self, staged_state: dict[str, Any]) -> None:
        """Commit a plan previously returned by :meth:`stage_state`."""
        self._constellation_manager.commit_state(
            staged_state["constellation_manager"],
        )
        for name, eng in [
            ("gps_engine", self._gps_engine),
            ("isr_engine", self._isr_engine),
            ("early_warning_engine", self._early_warning_engine),
            ("satcom_engine", self._satcom_engine),
            ("asat_engine", self._asat_engine),
        ]:
            if (
                eng is not None
                and name in staged_state
            ):
                if hasattr(eng, "commit_state"):
                    eng.commit_state(staged_state[name])
                elif hasattr(eng, "set_state"):
                    eng.set_state(staged_state[name])

    def set_state(self, state: dict[str, Any]) -> None:
        """Validate and atomically restore the complete space snapshot."""
        self.commit_state(self.stage_state(state))
