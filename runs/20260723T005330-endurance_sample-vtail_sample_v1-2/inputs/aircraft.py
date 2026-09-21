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

from lwpla_a1 import LWPLA_A1  # construction profile, same directory

# --- spec numbers (DESIGN_SPEC.md) ---
WING_X_LE = 0.390  # wing root LE station
TAIL_ARM = 0.700  # wing AC -> tail AC


class VTailSample:
    name = "vtail_sample_v1.2"

    def geometry(self, dv=None) -> asb.Airplane:
        sd7037 = asb.Airfoil("sd7037")
        naca0009 = asb.Airfoil("naca0009")

        wing = asb.Wing(
            name="wing",
            symmetric=True,
            xsecs=[
                # straight LE: all taper from the trailing edge
                asb.WingXSec(xyz_le=[0, 0.000, 0], chord=0.220, twist=0, airfoil=sd7037),
                asb.WingXSec(xyz_le=[0, 0.350, 0], chord=0.220, twist=0, airfoil=sd7037),
                asb.WingXSec(
                    xyz_le=[0, 0.900, 0.550 * np.sind(3)],  # 3 deg outer-panel dihedral
                    chord=0.150,
                    twist=-2,  # washout, linear across outer panel
                    airfoil=sd7037,
                ),
            ],
        ).translate([WING_X_LE, 0, 0])

        # V-tail: root LE placed so tail AC sits ~TAIL_ARM behind wing AC.
        # Wing AC ~ 25% MAC (MAC LE aligns with root LE); tail MAC ~0.131 m.
        tail_x_le = WING_X_LE + 0.25 * 0.201 + TAIL_ARM - 0.25 * 0.131
        vtail = asb.Wing(
            name="vtail",
            symmetric=True,
            xsecs=[
                asb.WingXSec(xyz_le=[0, 0, 0], chord=0.150, twist=0, airfoil=naca0009),
                asb.WingXSec(
                    xyz_le=[
                        0.040,  # 7.1 deg LE sweep over 320 mm panel
                        0.320 * np.cosd(38),
                        0.320 * np.sind(38),
                    ],
                    chord=0.110,
                    twist=0,
                    airfoil=naca0009,
                ),
            ],
        ).translate([tail_x_le, 0, 0])

        return asb.Airplane(
            name=self.name,
            wings=[wing, vtail],
            s_ref=wing.area(),
            c_ref=0.201,
            b_ref=wing.span(),
        )

    def fixed_equipment(self) -> list[PointMass]:
        # Stations from the spec's station map; refine at M1 if the Phase 1 gate
        # shows CG sensitivity to any of the rough ones.
        return [
            PointMass("battery", 0.430, 0.115),  # bay 25-205 mm, centered
            PointMass("motor_prop", 0.190, 1.330),  # boom tip, aft of tail
            PointMass("esc_wiring", 0.080, 0.230),
            PointMass("servos_aileron", 0.024, 0.470),  # in-wing
            PointMass("servos_ruddervator", 0.024, 1.250),  # tail root block
            PointMass("fc_gps_rx", 0.060, 0.300),
            PointMass("hardware_misc", 0.050, 0.450),
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
                proxy_table="apc_11x55e",  # blend toward 11x7e handled at ingest
                folding_derate=0.95,
            ),
            battery=BatteryConfig(capacity_ah=4.0, v_nominal=14.8, usable_fraction=0.80),
            esc_efficiency=0.95,
            esc_continuous_current_a=40,
            avionics_power_w=3.0,
        )

    def construction(self) -> dict[str, ConstructionProfile]:
        return {"wing": LWPLA_A1, "vtail": LWPLA_A1}


AIRCRAFT = VTailSample()
