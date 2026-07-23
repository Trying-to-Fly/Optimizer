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

from lwpla_a1 import LWPLA_A1, LWPLA_A1_TAIL, LWPLA_A1_WINGLET  # construction profiles

# --- spec numbers (DESIGN_SPEC.md) ---
WING_X_LE = 0.390  # wing root LE station
TAIL_ARM = 0.700  # wing AC -> tail AC


class VTailSample:
    name = "vtail_sample_v1.3"
    wing_airfoil = "sd7037"  # discrete outer-loop candidate (MODEL_DETAILS 6.3)
    trim_deflection_limit_deg = 5.5  # <= 1/3 of the +/-12 mm low-rate throw
    span_cap_m = 2.2  # manufacturing cap on PROJECTED (front-view y) span, winglet included
    winglet = True  # tip winglet as a separate asb.Wing (parametric designs only)
    d3_max_deg = 20.0  # raised to ~88 only by the continuous-cant study (solve.py)

    # --- fuselage (MODEL_DETAILS section 7) ---
    # "pod_boom": lofted pod + CF boom (spec layout); "integrated": the pod's
    # tail cone runs all the way to the tail block, no separate boom (the
    # topology study in solve.optimize flips this attr)
    fuselage_topology = "pod_boom"
    POD_BAY_END_X = 0.410  # bay/wing-saddle joint station — the loft's anchor
    POD_XS_SPEC = (0.068, 0.088)  # spec cross-section (w, h) at pod_xs = 1
    POD_WALL_CLEARANCE = 0.0035  # printed wall + foam liner per side
    # packaging envelopes (m) — user-input data in the app (M5); spec values here
    COMPONENT_ENVELOPES = {
        "battery": {"length": 0.130, "width": 0.043, "height": 0.033},
        "esc": {"length": 0.055},
        "fc_gps": {"length": 0.060},
    }

    # Architecture v2 (planform generalization): variable-width flat/dihedral
    # center panel + 3 outer panels per side, each with its own dihedral and
    # chord ratio -> covers straight-tapered, polyhedral ("curved glider"), and
    # near-elliptical families. Defaults reproduce the v1.2 spec exactly
    # (linear taper 220->150, flat 700 mm center, 3 deg outer dihedral).
    DV_DEFAULTS = {
        # wing planform
        "span": 1.8, "c_root": 0.22, "center_width": 0.700,
        "r1": 196.667 / 220, "r2": 173.333 / 196.667, "r3": 150 / 173.333,
        "d0": 0.0, "d1": 3.0, "d2": 3.0, "d3": 3.0,  # per-panel dihedral, deg
        "washout_tip": -2.0,
        # winglet (consumed only when self.winglet; lengths m, angles deg,
        # wl_cr is winglet-root chord as a fraction of the wing tip chord)
        "wl_len": 0.12, "wl_cant": 75.0, "wl_cr": 0.80, "wl_taper": 0.70, "wl_toe": -1.0,
        # fuselage loft (anchor: bay end fixed at POD_BAY_END_X; defaults
        # reproduce the spec pod exactly — nose tip at station 0, length 0.585)
        "pod_nose": 0.030, "pod_bay": 0.380, "pod_tail": 0.175, "pod_xs": 1.0,
        # tail + balance + structure
        "tail_arm": 0.700, "tail_scale": 1.0,
        "spar_od_center": 0.010, "spar_wall_center": 0.001,
        "spar_od_outer": 0.008, "spar_wall_outer": 0.001,
        "ballast_kg": 0.070, "x_battery": 0.115,
    }
    min_effective_dihedral_deg = 2.0  # lateral-stability proxy for an aileron ship

    def design_variables(self, opti, inits: dict | None = None) -> dict:
        """Full-vehicle variables (M3). Architecture mapping: the 700 mm
        constant-chord center section is fixed (print sections); span and taper act
        on the outer panels; the V-tail scales uniformly and slides on the boom;
        spars are continuously sized (MODEL_DETAILS 1.3); balance via ballast mass
        and battery station. Cruise-state vars live in solve, not here."""
        i = self.DV_DEFAULTS | (inits or {})
        bounds = {
            "span": (1.5, self.span_cap_m), "c_root": (0.16, 0.245),
            "center_width": (0.10, 1.20),
            "r1": (0.55, 1.0), "r2": (0.55, 1.0), "r3": (0.55, 1.0),
            "d0": (0.0, 10.0), "d1": (0.0, 20.0), "d2": (0.0, 20.0),
            "d3": (0.0, self.d3_max_deg),
            "washout_tip": (-4.0, 0.0),
            # tail_arm drives overall aircraft length + boom length — genuinely
            # wide bounds so total length is an optimization outcome
            "tail_arm": (0.40, 1.20), "tail_scale": (0.70, 1.40),
            "spar_od_center": (0.006, 0.014), "spar_wall_center": (0.0006, 0.002),
            "spar_od_outer": (0.005, 0.012), "spar_wall_outer": (0.0005, 0.0018),
            # x_battery's real bounds are symbolic (inside the lofted bay,
            # geometry_constraints) — the box bound is just a wide backstop
            "ballast_kg": (0.0, 0.200), "x_battery": (-0.10, 0.40),
            "pod_nose": (0.030, 0.25), "pod_bay": (0.20, 0.55),
            "pod_xs": (0.75, 1.30),
        }
        if self.fuselage_topology == "pod_boom":
            # integrated topology derives its cone length from tail_arm instead
            bounds["pod_tail"] = (0.10, 0.45)
        if self.winglet:
            # cant floor 55 deg keeps the panel a genuine winglet — below that it
            # is a span extension the Schrenk stall model cannot see (it is
            # excluded from the main wing's stations)
            bounds |= {
                "wl_len": (0.05, 0.30), "wl_cant": (55.0, 88.0),
                "wl_cr": (0.40, 0.95), "wl_taper": (0.50, 1.0), "wl_toe": (-3.0, 3.0),
            }
        return {
            k: opti.variable(init_guess=i[k], lower_bound=lo, upper_bound=hi)
            for k, (lo, hi) in bounds.items()
        }

    def pod_dims(self, d: dict) -> dict:
        """Loft stations from a (default-filled) design dict. Symbolic-safe.

        Anchor: the bay's aft end is fixed at POD_BAY_END_X (wing-saddle joint);
        the nose grows forward from it, the tail cone aft. Integrated topology
        runs the cone to the tail block (station from tail_arm) instead of
        using the pod_tail variable."""
        w = self.POD_XS_SPEC[0] * d["pod_xs"]
        h = self.POD_XS_SPEC[1] * d["pod_xs"]
        bay_end = self.POD_BAY_END_X
        bay_start = bay_end - d["pod_bay"]
        nose_tip = bay_start - d["pod_nose"]
        if self.fuselage_topology == "integrated":
            tail_len = (WING_X_LE + 0.25 * 0.201 + d["tail_arm"]) - bay_end
        else:
            tail_len = d["pod_tail"]
        return {
            "w": w, "h": h, "nose_tip": nose_tip, "bay_start": bay_start,
            "bay_end": bay_end, "tail_len": tail_len,
            "length": d["pod_nose"] + d["pod_bay"] + tail_len,
        }

    def fuselage_lofts(self, dv: dict | None = None) -> list:
        """Framework hook (solve.run viz twin + parasite_bodies): the pod loft."""
        from planeopt import fuselage

        d = self.DV_DEFAULTS | (dv or {})
        p = self.pod_dims(d)
        return [
            fuselage.loft(
                d["pod_nose"], d["pod_bay"], p["tail_len"], p["w"], p["h"],
                x_nose=p["nose_tip"], z_c=-0.030,
            )
        ]

    def geometry_constraints(self, opti, dv, V, deflection_deg=None) -> None:
        """Aircraft-specific manufacturing/geometry/throw constraints (symbolic-safe)."""
        c_tip = dv["c_root"] * dv["r1"] * dv["r2"] * dv["r3"]
        # tip Reynolds floor (project rule; MODEL_DETAILS section 4)
        opti.subject_to(1.225 * V * c_tip / 1.81e-5 >= 90e3)
        # A1 print bed: chord already bounded by c_root upper bound (245 mm)
        # outer panels must exist
        opti.subject_to(dv["span"] >= dv["center_width"] + 0.20)
        # manufacturing span cap on PROJECTED span: the dv "span" is material
        # (arc) span; front-view width comes from each panel's cos(dihedral),
        # plus the winglet's y-projection when present
        cw2_p = dv["center_width"] / 2
        w3 = (dv["span"] / 2 - cw2_p) / 3
        proj_semi = cw2_p * np.cosd(dv["d0"]) + w3 * (
            np.cosd(dv["d1"]) + np.cosd(dv["d2"]) + np.cosd(dv["d3"])
        )
        proj_span = 2 * proj_semi
        if self.winglet:
            proj_span = proj_span + 2 * dv["wl_len"] * np.cosd(dv["wl_cant"])
            # winglet mean-chord Reynolds floor: relaxed vs the 90k tip rule
            # (small vertical surface, tolerates more drag creep than the wing)
            c_wl_mean = c_tip * dv["wl_cr"] * (1 + dv["wl_taper"]) / 2
            opti.subject_to(1.225 * V * c_wl_mean / 1.81e-5 >= 60e3)
            # winglet stays shorter than the last wing panel (buildable socket)
            opti.subject_to(dv["wl_len"] <= w3)
        opti.subject_to(proj_span <= self.span_cap_m)
        # lateral-stability proxy: roll-moment-weighted dihedral floor. Dihedral's
        # restoring moment scales with panel area x spanwise arm, so the weight is
        # A_i * y_centroid_i — without the arm the optimizer games the metric by
        # piling dihedral inboard where it buys no roll stiffness. (The optimizer
        # cannot see dihedral's benefit at all — LL has no lateral DOF — so this
        # floor is the only thing keeping the wing from going flat.)
        cw2 = dv["center_width"] / 2
        outer3 = (dv["span"] / 2 - cw2) / 3
        c0, c1 = dv["c_root"], dv["c_root"] * dv["r1"]
        c2, c3 = c1 * dv["r2"], c1 * dv["r2"] * dv["r3"]
        panels = [
            (cw2 * c0, cw2 / 2, dv["d0"]),
            (outer3 * (c0 + c1) / 2, cw2 + 0.5 * outer3, dv["d1"]),
            (outer3 * (c1 + c2) / 2, cw2 + 1.5 * outer3, dv["d2"]),
            (outer3 * (c2 + c3) / 2, cw2 + 2.5 * outer3, dv["d3"]),
        ]
        w_sum = sum(a * y for a, y, _ in panels)
        # credit per panel is sin*cos, not the raw angle: the restoring moment
        # needs both a sideflow AoA (sin) and a vertical force component (cos),
        # so credit ~ d at small angles and -> 0 as a panel goes vertical — a
        # near-vertical panel (continuous-cant study) cannot game the floor.
        # The winglet is excluded entirely (conservative).
        credit = lambda d: (180 / np.pi) * np.sind(d) * np.cosd(d)
        eff_dihedral = sum(a * y * credit(d) for a, y, d in panels) / w_sum
        opti.subject_to(eff_dihedral >= self.min_effective_dihedral_deg)
        if deflection_deg is not None:
            opti.subject_to(deflection_deg <= self.trim_deflection_limit_deg)
            opti.subject_to(deflection_deg >= -self.trim_deflection_limit_deg)

        # fuselage packaging (MODEL_DETAILS 7.2) — envelopes are declared data
        # (user input in the app), spec values for the sample
        p = self.pod_dims(dv)
        env, clr = self.COMPONENT_ENVELOPES, self.POD_WALL_CLEARANCE
        batt = env["battery"]
        w_in, h_in = p["w"] - 2 * clr, p["h"] - 2 * clr
        opti.subject_to(w_in >= batt["width"] + 0.004)
        opti.subject_to(h_in >= batt["height"] + 0.004)
        # battery (its CG is x_battery) stays inside the bay with end margins
        half = batt["length"] / 2
        opti.subject_to(dv["x_battery"] - half >= p["bay_start"] + 0.003)
        opti.subject_to(dv["x_battery"] + half <= p["bay_end"] - 0.003)
        opti.subject_to(dv["pod_bay"] >= batt["length"] + 0.050)  # travel + leads
        # full stack must fit in bay + cone root
        opti.subject_to(
            dv["pod_bay"] + p["tail_len"]
            >= batt["length"] + env["esc"]["length"] + env["fc_gps"]["length"] + 0.06
        )
        # proportion floors (streamlined family, MODEL_DETAILS 7.2): nose >= 1.0
        # d_eq, boat-tail >= 1.8 d_eq — every candidate stays fuselage-shaped
        # (the spec pod's 30 mm nose predates these; dv=None fixture is exempt)
        d_eq = (p["w"] * p["h"]) ** 0.5
        opti.subject_to(dv["pod_nose"] >= 1.0 * d_eq)
        if self.fuselage_topology == "pod_boom":
            opti.subject_to(dv["pod_tail"] >= 1.8 * d_eq)
            # an exposed boom must exist: pod tail cap clears the tail block
            x_tail = WING_X_LE + 0.25 * 0.201 + dv["tail_arm"]
            opti.subject_to(p["bay_end"] + p["tail_len"] + 0.10 <= x_tail)

    def structure_constraints(self, opti, dv, weight_n) -> None:
        """Spar sizing constraints at n = 5 g limit load (MODEL_DETAILS 1.3)."""
        from planeopt import structures

        n_lim = 5.0
        semi = dv["span"] / 2
        cw2 = dv["center_width"] / 2
        m_center = structures.semispan_root_moment(weight_n, n_lim, semi)
        structures.spar_constraints(
            opti, dv["spar_od_center"], dv["spar_wall_center"], cw2, m_center
        )
        # outer segment: lift outboard of the first joint (area fraction approx),
        # centroid arm 0.424 x outer length
        outer = semi - cw2
        c1 = dv["c_root"] * dv["r1"]
        c3 = c1 * dv["r2"] * dv["r3"]
        s_half = cw2 * dv["c_root"] + outer * (dv["c_root"] + c3) / 2
        f_outer = (outer * (dv["c_root"] + c3) / 2) / s_half
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

        parametric = dv is not None
        if dv is None:
            dv = {}
        dv = self.DV_DEFAULTS | dv
        span, c_root = dv["span"], dv["c_root"]
        cw2 = dv["center_width"] / 2
        outer3 = (span / 2 - cw2) / 3  # three equal-width outer panels per side

        # chords at the panel breaks (straight LE: all taper from the TE)
        chords = [
            c_root,
            c_root,
            c_root * dv["r1"],
            c_root * dv["r1"] * dv["r2"],
            c_root * dv["r1"] * dv["r2"] * dv["r3"],
        ]
        # arc-length panels: "span" is material span along the panels; y/z come
        # from each panel's dihedral, so projected span = sum(w*cos d) — exact at
        # high cant (continuous-cant study), 0.1% from the old flat-y placement
        # at the spec's 3 deg
        ys, zs = [0.0], [0.0]
        for width, ang in [
            (cw2, dv["d0"]), (outer3, dv["d1"]), (outer3, dv["d2"]), (outer3, dv["d3"])
        ]:
            ys.append(ys[-1] + width * np.cosd(ang))
            zs.append(zs[-1] + width * np.sind(ang))
        # washout: 0 across the center panel, linear to washout_tip at the tip
        twists = [0.0, 0.0]
        for k in (1, 2, 3):
            twists.append(dv["washout_tip"] * k / 3)

        wing = asb.Wing(
            name="wing",
            symmetric=True,
            xsecs=[
                asb.WingXSec(
                    xyz_le=[0, ys[k], zs[k]], chord=chords[k], twist=twists[k], airfoil=wing_af
                )
                for k in range(5)
            ],
        ).translate([WING_X_LE, 0, 0])

        # winglet: separate Wing rooted at the tip (parametric designs only —
        # the v1.2 spec fixture has none). Separate so the Schrenk stall
        # stations, dihedral proxy, and Wing.span() of the main wing stay clean;
        # LiftingLine picks up the nonplanar induced benefit either way
        # (verified against VLM, MODEL_DETAILS 3.6).
        winglet = None
        if self.winglet and parametric:
            wl_cr = chords[4] * dv["wl_cr"]
            wl_ct = wl_cr * dv["wl_taper"]
            # root TE flush with the wing-tip TE; tip raked back 25% of length
            x0 = WING_X_LE + chords[4] - wl_cr
            dy = dv["wl_len"] * np.cosd(dv["wl_cant"])
            dz = dv["wl_len"] * np.sind(dv["wl_cant"])
            winglet = asb.Wing(
                name="winglet",
                symmetric=True,
                xsecs=[
                    asb.WingXSec(
                        xyz_le=[x0, ys[4], zs[4]], chord=wl_cr,
                        twist=dv["wl_toe"], airfoil=wing_af,
                    ),
                    asb.WingXSec(
                        xyz_le=[x0 + 0.25 * dv["wl_len"], ys[4] + dy, zs[4] + dz],
                        chord=wl_ct, twist=dv["wl_toe"], airfoil=wing_af,
                    ),
                ],
            )

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
            wings=[wing, vtail] + ([winglet] if winglet is not None else []),
            s_ref=wing.area(),
            c_ref=wing.area() / wing.span(),  # mean chord (symbolic-safe MAC proxy)
            # projected (front-view y) span: the manufacturing-capped quantity,
            # and the b the y-based Schrenk stations are consistent with
            b_ref=2 * ys[4],
        )

    def fixed_equipment(self, dv: dict | None = None) -> list[PointMass]:
        # Stations from the spec's station map; battery station and tail-group
        # stations follow the design vector (balance + tail-arm variables).
        # ESC/FC ride the pod as length fractions (spec: 0.230/0.585, 0.300/0.585)
        # so the stack moves with a stretched or shrunk loft.
        d = self.DV_DEFAULTS | (dv or {})
        p = self.pod_dims(d)
        x_tail = WING_X_LE + 0.25 * 0.201 + d["tail_arm"]  # ~tail AC station
        return [
            PointMass("battery", 0.430, d["x_battery"]),  # inside the lofted bay
            PointMass("motor_prop", 0.190, x_tail + 0.08),  # boom tip, aft of tail
            PointMass("esc_wiring", 0.080, p["nose_tip"] + 0.3932 * p["length"]),
            PointMass("servos_aileron", 0.024, 0.470),  # in-wing
            PointMass("servos_ruddervator", 0.024, x_tail),  # tail root block
            PointMass("fc_gps_rx", 0.060, p["nose_tip"] + 0.5128 * p["length"]),
            PointMass("hardware_misc", 0.050, 0.450),
        ]

    def structure_extras(self, dv: dict | None = None) -> list[PointMass]:
        """Spar mass from the sizing variables, boom from tail arm, ballast from
        its variable, pod frozen (MODEL_DETAILS 1.1/1.3)."""
        from planeopt import structures

        d = self.DV_DEFAULTS | (dv or {})
        outer = d["span"] / 2 - d["center_width"] / 2
        spar_mass = (
            structures.tube_mass(d["spar_od_center"], d["spar_wall_center"], d["center_width"])
            + 2 * structures.tube_mass(d["spar_od_outer"], d["spar_wall_outer"], 0.85 * outer)
            + 0.035  # dihedral-joint joiner blocks + pins
            + 0.016  # 2 extra polyhedral-break joiners per side (arch v2)
        )
        x_spar = WING_X_LE + 0.30 * d["c_root"]
        extras = [PointMass("wing_spars_joiners", spar_mass, x_spar)]

        # --- fuselage group (section 7): frozen numbers for the spec fixture,
        # loft-driven for parametric designs ---
        if dv is None:
            extras += [
                PointMass("boom", 0.056 * (d["tail_arm"] + 0.05), 0.583 + (d["tail_arm"] + 0.05) / 2),
                PointMass("pod", 0.250, 0.300),  # printed pod incl. hatch (frozen)
                PointMass("nose_ballast", d["ballast_kg"], 0.015),
            ]
        else:
            p = self.pod_dims(d)
            swet = self.fuselage_lofts(dv)[0].area_wetted()
            # k_skin x Swet + overhead, calibrated to reproduce the frozen 250 g
            # at the spec loft (Swet 0.1365 m2) — same uncalibrated caveat as wings
            extras.append(
                PointMass("pod", 1.465 * swet + 0.050, p["nose_tip"] + 0.51 * p["length"])
            )
            if self.fuselage_topology == "pod_boom":
                # boom spans pod tail cap -> tail block (+50 mm sockets); its
                # length is an outcome of tail_arm and the loft, not a constant
                x_tail = WING_X_LE + 0.25 * 0.201 + d["tail_arm"]
                pod_end = p["bay_end"] + p["tail_len"]
                boom_len = (x_tail - pod_end) + 0.05
                extras.append(
                    PointMass("boom", 0.056 * boom_len, (pod_end + x_tail) / 2)  # 12x10 CF g/m
                )
            else:
                # integrated: printed cone replaces the boom; an internal 8 mm CF
                # stiffener keeps the printed tail credible at this fidelity
                stiff = structures.tube_mass(0.008, 0.0007, p["tail_len"])
                extras.append(
                    PointMass("tail_stiffener", stiff, p["bay_end"] + p["tail_len"] / 2)
                )
            # ballast rides the (possibly stretched) nose tip
            extras.append(PointMass("nose_ballast", d["ballast_kg"], p["nose_tip"] + 0.015))
        if self.winglet and dv is not None:
            # tip sockets + pins, ~8 g per side (printed surface mass itself
            # comes from the winglet ConstructionProfile via massmodel)
            extras.append(PointMass("winglet_joiners", 0.016, x_spar))
        return extras

    _BOOM_BODY = {
        "name": "boom", "wetted_area_m2": 0.0245, "length_m": 0.650,
        "form_factor": 1.10, "volume_m3": 7.3e-5, "munk_factor": 0.95,
    }

    def parasite_bodies(self, dv: dict | None = None) -> list[dict]:
        """dv=None -> the frozen M1 baseline numbers (validation continuity;
        the 0.183 m2 pod assumed an untapered prism). Parametric designs use the
        loft's own integrals — symbolic-safe, FF from fineness (section 7)."""
        from planeopt import fuselage

        if dv is None:
            # pod: ~68x88 mm rounded rect x 585 mm; boom: 12 mm x ~650 mm exposed
            return [
                {"name": "pod", "wetted_area_m2": 0.183, "length_m": 0.585,
                 "form_factor": 1.25, "volume_m3": 0.00263, "munk_factor": 0.9},
                dict(self._BOOM_BODY),
            ]
        d = self.DV_DEFAULTS | dv
        p = self.pod_dims(d)
        bodies = [fuselage.body_dict(self.fuselage_lofts(dv)[0], p["length"], p["w"], p["h"])]
        if self.fuselage_topology == "pod_boom":
            x_tail = WING_X_LE + 0.25 * 0.201 + d["tail_arm"]
            bodies.append(fuselage.boom_body(x_tail - (p["bay_end"] + p["tail_len"])))
        return bodies

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
        return {"wing": LWPLA_A1, "vtail": LWPLA_A1_TAIL, "winglet": LWPLA_A1_WINGLET}


AIRCRAFT = VTailSample()
