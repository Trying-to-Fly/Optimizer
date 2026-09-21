"""Sample/test aircraft: the DESIGN_SPEC.md 1800 mm V-tail pusher.

This is the framework's development fixture — nothing in src/planeopt may assume
its architecture or numbers. Stations are meters aft of the nose tip (spec's
station map / 1000). M0 scope: fixed design only — `geometry()` ignores the design
vector and returns the spec'd airplane; the architecture mapping (design vector ->
geometry) becomes real at M2.

Symbolic-safety rule applies here (types.py docstring): once design variables flow
in, no branching on their values.
"""

from __future__ import annotations

import aerosandbox as asb
import aerosandbox.numpy as np

from planeopt.types import (
    BatteryConfig,
    ConstructionProfile,
    MotorConfig,
    PointMass,
    PowertrainConfig,
    PropConfig,
)

from lwpla_a1 import LWPLA_A1, LWPLA_A1_TAIL  # construction profiles, same directory

# --- spec numbers (DESIGN_SPEC.md) ---
WING_X_LE = 0.390  # wing root LE station
TAIL_ARM = 0.700  # wing AC -> tail AC


class VTailSample:
    name = "vtail_sample_v1.2"
    wing_airfoil = "sd7037"  # discrete outer-loop candidate (MODEL_DETAILS 6.3)
    trim_deflection_limit_deg = 5.5  # <= 1/3 of the +/-12 mm low-rate throw

    DV_DEFAULTS = {
        # wing (M2)
        "span": 1.8, "c_root": 0.22, "taper": 150 / 220,
        # tail + balance + structure (M3)
        "tail_arm": 0.700, "tail_scale": 1.0,
        "spar_od_center": 0.010, "spar_wall_center": 0.001,
        "spar_od_outer": 0.008, "spar_wall_outer": 0.001,
        "ballast_kg": 0.070, "x_battery": 0.115,
    }

    def design_variables(self, opti, inits: dict | None = None) -> dict:
        """Full-vehicle variables (M3). Architecture mapping: the 700 mm
        constant-chord center section is fixed (print sections); span and taper act
        on the outer panels; the V-tail scales uniformly and slides on the boom;
        spars are continuously sized (MODEL_DETAILS 1.3); balance via ballast mass
        and battery station. Cruise-state vars live in solve, not here."""
        i = self.DV_DEFAULTS | (inits or {})
        bounds = {
            "span": (1.5, 2.2), "c_root": (0.16, 0.245), "taper": (0.40, 1.0),
            "tail_arm": (0.55, 0.85), "tail_scale": (0.70, 1.40),
            "spar_od_center": (0.006, 0.014), "spar_wall_center": (0.0006, 0.002),
            "spar_od_outer": (0.005, 0.012), "spar_wall_outer": (0.0005, 0.0018),
            "ballast_kg": (0.0, 0.200), "x_battery": (0.095, 0.135),
        }
        return {
            k: opti.variable(init_guess=i[k], lower_bound=lo, upper_bound=hi)
            for k, (lo, hi) in bounds.items()
        }

    def geometry_constraints(self, opti, dv, V, deflection_deg=None) -> None:
        """Aircraft-specific manufacturing/geometry/throw constraints (symbolic-safe)."""
        c_tip = dv["c_root"] * dv["taper"]
        # tip Reynolds floor (project rule; MODEL_DETAILS section 4)
        opti.subject_to(1.225 * V * c_tip / 1.81e-5 >= 90e3)
        # A1 print bed: chord already bounded by c_root upper bound (245 mm)
        # outer panel must exist
        opti.subject_to(dv["span"] >= 0.75 + 0.1)
        if deflection_deg is not None:
            opti.subject_to(deflection_deg <= self.trim_deflection_limit_deg)
            opti.subject_to(deflection_deg >= -self.trim_deflection_limit_deg)

    def structure_constraints(self, opti, dv, weight_n) -> None:
        """Spar sizing constraints at n = 5 g limit load (MODEL_DETAILS 1.3)."""
        from planeopt import structures

        n_lim = 5.0
        semi = dv["span"] / 2
        m_center = structures.semispan_root_moment(weight_n, n_lim, semi)
        structures.spar_constraints(
            opti, dv["spar_od_center"], dv["spar_wall_center"], 0.350, m_center
        )
        # outer segment: lift outboard of the joint (area fraction approx),
        # centroid arm 0.424 x outer length
        outer = semi - 0.350
        s_half = 0.350 * dv["c_root"] + outer * dv["c_root"] * (1 + dv["taper"]) / 2
        f_outer = (outer * dv["c_root"] * (1 + dv["taper"]) / 2) / s_half
        m_outer = n_lim * (weight_n / 2) * f_outer * 0.424 * outer
        structures.spar_constraints(
            opti, dv["spar_od_outer"], dv["spar_wall_outer"], 0.85 * outer, m_outer
        )
        # outer spar must socket into the center-spar joiner
        opti.subject_to(dv["spar_od_outer"] <= dv["spar_od_center"])

    def geometry(self, dv=None) -> asb.Airplane:
        """dv=None -> the fixed v1.2 spec design; else the parametric architecture
        (works with floats or Opti symbolics — no branching on dv *values*)."""
        wing_af = asb.Airfoil(self.wing_airfoil)
        naca0009 = asb.Airfoil("naca0009")

        if dv is None:
            dv = {}
        dv = self.DV_DEFAULTS | dv
        span, c_root, taper = dv["span"], dv["c_root"], dv["taper"]
        semi_center = 0.350  # center section half-width (fixed: spar + print sections)
        outer = span / 2 - semi_center

        wing = asb.Wing(
            name="wing",
            symmetric=True,
            xsecs=[
                # straight LE: all taper from the trailing edge
                asb.WingXSec(xyz_le=[0, 0.000, 0], chord=c_root, twist=0, airfoil=wing_af),
                asb.WingXSec(xyz_le=[0, semi_center, 0], chord=c_root, twist=0, airfoil=wing_af),
                asb.WingXSec(
                    xyz_le=[0, span / 2, outer * np.sind(3)],  # 3 deg outer-panel dihedral
                    chord=c_root * taper,
                    twist=-2,  # washout, linear across outer panel
                    airfoil=wing_af,
                ),
            ],
        ).translate([WING_X_LE, 0, 0])

        # V-tail: root LE placed so tail AC sits ~tail_arm behind wing AC.
        # Wing AC ~ 25% mean chord (straight LE); tail MAC ~0.131 m x tail_scale.
        ts = dv["tail_scale"]
        c_mean = wing.area() / wing.span()
        tail_x_le = WING_X_LE + 0.25 * c_mean + dv["tail_arm"] - 0.25 * 0.131 * ts
        # ruddervator: 40 mm constant chord -> hinge at ~73% of root chord
        ruddervator = asb.ControlSurface(
            name="ruddervator", symmetric=True, deflection=0, hinge_point=0.73
        )
        vtail = asb.Wing(
            name="vtail",
            symmetric=True,
            xsecs=[
                asb.WingXSec(
                    xyz_le=[0, 0, 0],
                    chord=0.150 * ts,
                    twist=0,
                    airfoil=naca0009,
                    control_surfaces=[ruddervator],
                ),
                asb.WingXSec(
                    xyz_le=[
                        0.040 * ts,  # 7.1 deg LE sweep, scaled with the panel
                        0.320 * ts * np.cosd(38),
                        0.320 * ts * np.sind(38),
                    ],
                    chord=0.110 * ts,
                    twist=0,
                    airfoil=naca0009,
                ),
            ],
        ).translate([tail_x_le, 0, 0])

        return asb.Airplane(
            name=self.name,
            wings=[wing, vtail],
            s_ref=wing.area(),
            c_ref=wing.area() / wing.span(),  # mean chord (symbolic-safe MAC proxy)
            b_ref=wing.span(),
        )

    def fixed_equipment(self, dv: dict | None = None) -> list[PointMass]:
        # Stations from the spec's station map; battery station and tail-group
        # stations follow the design vector (balance + tail-arm variables).
        d = self.DV_DEFAULTS | (dv or {})
        x_tail = WING_X_LE + 0.25 * 0.201 + d["tail_arm"]  # ~tail AC station
        return [
            PointMass("battery", 0.430, d["x_battery"]),  # bay 25-205 mm, +/-20 mm travel
            PointMass("motor_prop", 0.190, x_tail + 0.08),  # boom tip, aft of tail
            PointMass("esc_wiring", 0.080, 0.230),
            PointMass("servos_aileron", 0.024, 0.470),  # in-wing
            PointMass("servos_ruddervator", 0.024, x_tail),  # tail root block
            PointMass("fc_gps_rx", 0.060, 0.300),
            PointMass("hardware_misc", 0.050, 0.450),
        ]

    def structure_extras(self, dv: dict | None = None) -> list[PointMass]:
        """Spar mass from the sizing variables, boom from tail arm, ballast from
        its variable, pod frozen (MODEL_DETAILS 1.1/1.3)."""
        from planeopt import structures

        d = self.DV_DEFAULTS | (dv or {})
        outer = d["span"] / 2 - 0.350
        spar_mass = (
            structures.tube_mass(d["spar_od_center"], d["spar_wall_center"], 0.700)
            + 2 * structures.tube_mass(d["spar_od_outer"], d["spar_wall_outer"], 0.85 * outer)
            + 0.035  # joiner blocks + pins (constant)
        )
        x_spar = WING_X_LE + 0.30 * d["c_root"]
        boom_len = d["tail_arm"] + 0.05  # socket to tail block
        return [
            PointMass("wing_spars_joiners", spar_mass, x_spar),
            PointMass("boom", 0.056 * boom_len, 0.583 + boom_len / 2),  # 12x10 CF g/m
            PointMass("pod", 0.250, 0.300),  # printed pod incl. hatch (frozen geometry)
            PointMass("nose_ballast", d["ballast_kg"], 0.015),
        ]

    def parasite_bodies(self) -> list[dict]:
        # pod: ~68x88 mm rounded rect x 585 mm; boom: 12 mm x ~650 mm exposed
        return [
            {"name": "pod", "wetted_area_m2": 0.183, "length_m": 0.585, "form_factor": 1.25},
            {"name": "boom", "wetted_area_m2": 0.0245, "length_m": 0.650, "form_factor": 1.10},
        ]

    def powertrain(self) -> PowertrainConfig:
        return PowertrainConfig(
            motor=MotorConfig(
                name="D3548-900kv",
                kv_rpm_per_volt=900,
                # vendor data, uncalibrated (MODEL_DETAILS.md 2.3) — no measurement path
                resistance_ohm=0.025,
                no_load_current_a=1.8,
                max_current_a=55,
            ),
            prop=PropConfig(
                name="aeronaut_cam_11x6_folding",
                diameter_m=0.2794,
                pitch_m=0.1524,
                proxy_table="apc_11x6_blend",  # pitch-blended 11x5.5E/11x7E (tools/ingest_props.py)
                folding_derate=0.95,
            ),
            battery=BatteryConfig(capacity_ah=4.0, v_nominal=14.8, usable_fraction=0.80),
            esc_efficiency=0.95,
            esc_continuous_current_a=40,
            avionics_power_w=3.0,
        )

    def construction(self) -> dict[str, ConstructionProfile]:
        return {"wing": LWPLA_A1, "vtail": LWPLA_A1_TAIL}


AIRCRAFT = VTailSample()
