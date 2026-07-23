"""Shared contracts between modules.

These dataclasses are the interfaces the docs promise (EXECUTION_PLAN.md section 4).
Everything that crosses a module boundary is one of these types — the CLI, the report
pipeline, and the future GUI all consume them, never module internals.

Symbolic-safety rule (MODEL_DETAILS.md section 4): any field that may hold a design
expression must accept CasADi symbolics. Config authors must not branch (`if`) on
such values or call non-smooth numpy ops on them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class PointMass:
    """One (mass, station) entry of the mass model — MODEL_DETAILS.md section 1.6.

    Stations are meters aft of the aircraft's nose datum.
    """

    name: str
    mass_kg: Any  # float or CasADi expression
    x_m: Any  # float or CasADi expression


@dataclass
class ConstructionProfile:
    """Calibration constants for one material/printer/print-strategy combination.

    MODEL_DETAILS.md section 1.2. Units chosen so terms multiply out to kg:
      skin:   k_skin_kg_m2 * wetted_area_m2
      ribs:   k_rib_kg_m2 * span_m * mean_chord_m**2 / rib_pitch_m
      joints: k_joint_kg * span_m / section_length_m   (continuous, not ceil'd)
    """

    name: str
    k_skin_kg_m2: float
    k_rib_kg_m2: float
    rib_pitch_m: float
    k_joint_kg: float
    section_length_m: float
    overhead_kg: float
    finish_factor: float = 1.05
    calibrated: bool = False  # False until fitted from slicer/scale data (section 1.4)


@dataclass
class BatteryConfig:
    capacity_ah: float
    v_nominal: float  # discharge-average bus voltage, not full-charge
    usable_fraction: float

    @property
    def usable_energy_wh(self) -> float:
        return self.capacity_ah * self.v_nominal * self.usable_fraction


@dataclass
class MotorConfig:
    """Equivalent-circuit parameters — MODEL_DETAILS.md section 2.1."""

    name: str
    kv_rpm_per_volt: float
    resistance_ohm: float
    no_load_current_a: float
    max_current_a: float  # burst; continuous rating on the ESC side


@dataclass
class PropConfig:
    name: str
    diameter_m: float
    pitch_m: float
    proxy_table: str  # key into data/props/ (APC proxy, MODEL_DETAILS.md section 2.1)
    folding_derate: float = 1.0


@dataclass
class PowertrainConfig:
    motor: MotorConfig
    prop: PropConfig
    battery: BatteryConfig
    esc_efficiency: float = 0.95
    esc_continuous_current_a: float = 40.0
    avionics_power_w: float = 3.0


@dataclass
class MissionSpec:
    """Everything a run needs beyond the aircraft — MODEL_DETAILS.md section 5.

    Mission-type constraint values live here (not in the aircraft config): they
    describe what the aircraft is *for*, not what it *is*.
    """

    name: str
    objective: str  # registry key, planeopt.mission.OBJECTIVES
    v_wind_ms: float = 0.0
    penetration_margin_ms: float = 0.0
    v_stall_max_ms: float | None = None
    static_margin_range: tuple[float, float] = (0.08, 0.15)
    ballast_max_kg: float | None = None
    sweeps: dict[str, list[float]] = field(default_factory=dict)  # epsilon-constraint axes
    notes: str = ""

    @property
    def v_min_ms(self) -> float:
        return self.v_wind_ms + self.penetration_margin_ms


@runtime_checkable
class AircraftDefinition(Protocol):
    """What every `aircraft/*/aircraft.py` module's AIRCRAFT object provides.

    M0 uses geometry/fixed_equipment/powertrain/construction; design_variables
    joins at M2 when the optimizer arrives.
    """

    name: str

    def geometry(self, dv: Any | None) -> Any:  # -> asb.Airplane
        ...

    def fixed_equipment(self) -> list[PointMass]: ...

    def structure_extras(self) -> list[PointMass]:
        """Non-surface structure: spars, boom, pod, ballast. Fixed values at M1;
        spar/ballast entries become design-variable-driven at M2/M3."""
        ...

    def powertrain(self) -> PowertrainConfig: ...

    def construction(self) -> dict[str, ConstructionProfile]: ...

    def parasite_bodies(self, dv: dict | None = None) -> list[dict]:
        """Non-lifting bodies for the drag buildup (MODEL_DETAILS.md section 3.1):
        [{name, wetted_area_m2, length_m, form_factor}]. dv=None -> the fixed
        baseline; with a design vector, entries may be symbolic (parametric
        fuselage loft, section 7)."""
        ...


@dataclass
class RunResult:
    """The single artifact of a run; serialized verbatim into run.json."""

    aircraft: str
    mission: str
    objective: str
    status: str
    created: str  # ISO timestamp
    geometry: dict[str, Any] = field(default_factory=dict)
    masses: dict[str, Any] = field(default_factory=dict)
    performance: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
