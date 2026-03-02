"""Combat-layer events published on the EventBus.

All events are frozen dataclasses inheriting from :class:`Event`.
Morale and other downstream modules subscribe to these events without
importing combat modules directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from stochastic_warfare.core.events import Event


# -- Direct fire / general engagement ------------------------------------


@dataclass(frozen=True)
class EngagementEvent(Event):
    """Published when a unit engages a target."""

    attacker_id: str
    target_id: str
    weapon_id: str
    ammo_type: str
    result: str  # "hit", "miss", "suppression_only", "aborted"


@dataclass(frozen=True)
class HitEvent(Event):
    """Published when a projectile strikes a target."""

    target_id: str
    weapon_id: str
    damage_type: str  # "KINETIC", "BLAST", "FRAGMENTATION", etc.
    penetrated: bool


@dataclass(frozen=True)
class DamageEvent(Event):
    """Published when a unit sustains damage."""

    target_id: str
    damage_amount: float
    damage_type: str
    location: str  # "hull", "turret", "tracks", "engine", etc.


@dataclass(frozen=True)
class SuppressionEvent(Event):
    """Published when suppression state changes."""

    target_id: str
    suppression_level: int  # SuppressionLevel value
    source_direction: float  # radians from north


@dataclass(frozen=True)
class AmmoExpendedEvent(Event):
    """Published when ammunition is consumed."""

    unit_id: str
    ammo_type: str
    quantity: int


@dataclass(frozen=True)
class FratricideEvent(Event):
    """Published when a friendly-fire incident occurs."""

    shooter_id: str
    victim_id: str
    weapon_id: str
    cause: str  # "misidentification", "danger_close", "crossfire"


# -- Artillery / indirect fire -------------------------------------------


@dataclass(frozen=True)
class ArtilleryFireEvent(Event):
    """Published when an artillery battery fires a mission."""

    battery_id: str
    target_pos: tuple[float, float, float]
    ammo_type: str
    round_count: int


# -- Missiles ------------------------------------------------------------


@dataclass(frozen=True)
class MissileLaunchEvent(Event):
    """Published when a missile is launched."""

    launcher_id: str
    missile_id: str
    target_id: str
    missile_type: str


@dataclass(frozen=True)
class MissileInterceptEvent(Event):
    """Published when an interceptor engages an incoming missile."""

    defender_id: str
    missile_id: str
    interceptor_type: str
    success: bool


# -- Air engagements -----------------------------------------------------


@dataclass(frozen=True)
class AirEngagementEvent(Event):
    """Published for air-to-air or air-to-ground engagements."""

    attacker_id: str
    target_id: str
    engagement_type: str  # "BVR", "WVR", "GUNS", "CAS", "SEAD", etc.


# -- Naval engagements ---------------------------------------------------


@dataclass(frozen=True)
class NavalEngagementEvent(Event):
    """Published for surface naval engagements."""

    attacker_id: str
    target_id: str
    weapon_type: str  # "ASHM", "NAVAL_GUN", "TORPEDO", etc.


@dataclass(frozen=True)
class ShipDamageEvent(Event):
    """Published when a ship sustains damage."""

    ship_id: str
    damage_type: str  # "missile", "torpedo", "gunfire", "mine"
    severity: float  # 0.0–1.0 hull integrity loss
    system_affected: str  # "propulsion", "weapons", "sensors", etc.


@dataclass(frozen=True)
class TorpedoEvent(Event):
    """Published for torpedo launches and outcomes."""

    shooter_id: str
    target_id: str
    torpedo_id: str
    result: str  # "hit", "evaded", "decoyed", "malfunction"


@dataclass(frozen=True)
class MineEvent(Event):
    """Published when a mine is triggered or swept."""

    mine_id: str
    victim_id: str
    mine_type: str
    result: str  # "detonated", "swept", "neutralized", "miss"


@dataclass(frozen=True)
class CarrierSortieEvent(Event):
    """Published for carrier flight operations."""

    carrier_id: str
    aircraft_id: str
    mission_type: str  # "CAP", "STRIKE", "ASW", "AEW", etc.


# -- Shore bombardment / amphibious assault --------------------------------


@dataclass(frozen=True)
class ShoreBombardmentEvent(Event):
    """Published when a naval vessel fires on a shore target."""

    ship_id: str
    target_pos: tuple[float, float, float]
    round_count: int
    hits_in_lethal_radius: int


@dataclass(frozen=True)
class AmphibiousAssaultEvent(Event):
    """Published when an amphibious wave is launched."""

    wave_id: str
    wave_size: int
    landed: int
    casualties: int
    phase: str  # AssaultPhase name
