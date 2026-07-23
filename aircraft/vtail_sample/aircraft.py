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

from lwpla_a1 import (  # construction profiles
    LWPLA_A1,
    LWPLA_A1_FIN,
    LWPLA_A1_TAIL,
    LWPLA_A1_WINGLET,
)

# --- spec numbers (DESIGN_SPEC.md) ---
WING_X_LE = 0.390  # wing root LE station
TAIL_ARM = 0.700  # wing AC -> tail AC


class VTailSample:
    name = "vtail_sample_v1.4"
    wing_airfoil = "sd7037"  # discrete outer-loop candidate (MODEL_DETAILS 6.3)
    span_cap_m = 2.2  # manufacturing cap on PROJECTED (front-view y) span, winglet included
    winglet = True  # tip winglet as a separate asb.Wing (parametric designs only)
    tip_dihedral_max_deg = 20.0  # raised to ~88 only by the continuous-cant study (solve.py)
    # usable fraction of the section's max thickness for a spar hole (skin +
    # liner clearance) — feeds the straight-spar fit constraint (section 9)
    SPAR_DEPTH_FRACTION = 0.70

    # --- discrete studies (MODEL_DETAILS 6.3): every entry is a candidate the
    # study PRICES via one full re-optimization — never an assumption. Only
    # genuinely discrete choices live here; everything else is continuous. ---
    fuselage_topology = "pod_boom"  # lofted pod + CF boom (spec layout)
    tail_type = "vtail"  # spec layout; conventional/T priced by the study
    discrete_options = {
        "fuselage_topology": ["pod_boom", "integrated"],
        "tail_type": ["vtail", "conventional", "ttail"],
    }

    # --- tail policy + directional floor (MODEL_DETAILS section 8) ---
    TAIL_THROW_TE_M = 0.012  # available +/- TE throw at low rates (linkage geometry)
    TRIM_THROW_FRACTION = 1 / 3  # policy: cruise trim uses <= 1/3 of available throw
    # LL has no yaw axis, so without a floor fins optimize to zero and V-tails
    # shed angle. Declared value 0.030: the spec's own tail works out to
    # Vv = 0.034, and ~0.02-0.04 is the class practice band.
    v_tail_volume_min = 0.030
    # stab-on-fin mount for the T-tail candidate: reinforced fin tip + joiner
    # hardware (declared ballpark, same uncalibrated caveat as the profiles)
    TTAIL_FIN_MOUNT_KG = 0.020
    POD_BAY_END_X = 0.410  # default bay aft end (spec); a variable since the saddle rework
    SADDLE_CHORD_FRAC = 0.60  # bay must carry the wing root to 60% chord (no floating wing)
    SADDLE_EMBED = 0.006  # pod top embeds this far above the wing chord plane
    POD_XS_SPEC = (0.068, 0.088)  # spec cross-section (w, h) at pod_xs = 1
    POD_WALL_CLEARANCE = 0.0035  # printed wall + foam liner per side
    # packaging envelopes (m) — user-input data in the app (M5); spec values here
    COMPONENT_ENVELOPES = {
        "battery": {"length": 0.130, "width": 0.043, "height": 0.033},
        "esc": {"length": 0.055},
        "fc_gps": {"length": 0.060},
    }

    # Architecture v3 (dihedral curve, user decision 2026-07-23): the piecewise
    # per-panel dihedral (v2's d0-d3) is retired — it complicated spar holes
    # (a joiner at every break) and the champion showed the distribution to be
    # a flat direction anyway. Local dihedral is now one smooth family,
    # delta(eta) = dihedral_tip * eta^d_exp (eta = arc fraction from root):
    # d_exp = 0 is a single simple dihedral angle, d_exp > 0 a fully curved
    # wing (flat at the root, curvature building outboard). Chord ratios
    # r1-r3 keep the planform freedom.
    DV_DEFAULTS = {
        # wing planform
        "span": 1.8, "c_root": 0.22, "center_width": 0.700,
        "r1": 196.667 / 220, "r2": 173.333 / 196.667, "r3": 150 / 173.333,
        "dihedral_tip": 3.0, "d_exp": 0.5,  # dihedral curve (section 9)
        "washout_tip": -2.0,
        # winglet (consumed only when self.winglet; lengths m, angles deg,
        # wl_cr is winglet-root chord as a fraction of the wing tip chord)
        "wl_len": 0.12, "wl_cant": 75.0, "wl_cr": 0.80, "wl_taper": 0.70, "wl_toe": -1.0,
        # fuselage loft (defaults reproduce the spec pod exactly — nose tip at
        # station 0, length 0.585; pod_bay_end variable since the saddle rework)
        "pod_nose": 0.030, "pod_bay": 0.380, "pod_tail": 0.175, "pod_xs": 1.0,
        "pod_bay_end": 0.410,
        # tail (per-dimension, MODEL_DETAILS section 8; tail_scale retired).
        # Defaults reproduce the spec V-tail: 320 mm panels, chords 150 -> 110,
        # in-plane LE sweep atan(40/320) = 7.125 deg, 38 deg V-angle, hinge at
        # 73% chord (cs_frac 0.27). Fin vars consumed by conventional/T only.
        "tail_arm": 0.700,
        "t_span": 0.640, "t_c_root": 0.150, "t_taper": 110 / 150,
        "t_sweep": 7.125, "t_dihedral": 38.0, "cs_frac": 0.27,
        "fin_height": 0.180, "fin_c_root": 0.120, "fin_taper": 0.70,
        "fin_sweep": 15.0,
        # balance + structure
        "spar_od_center": 0.010, "spar_wall_center": 0.001,
        "spar_od_outer": 0.008, "spar_wall_outer": 0.001,
        "ballast_kg": 0.070, "x_battery": 0.115,
    }
    min_effective_dihedral_deg = 2.0  # lateral-stability proxy for an aileron ship

    @property
    def pitch_control_name(self) -> str:
        """Framework hook (aero trim / solve): the pitch-trim surface's name."""
        return "ruddervator" if self.tail_type == "vtail" else "elevator"

    def trim_deflection_limit_deg(self, dv: dict | None = None):
        """Framework hook (solve): the throw POLICY made geometric — trim may
        use <= 1/3 of the declared TE throw, so the degree cap follows from the
        control chord (cs_frac x tail mean chord). A bigger control fraction
        buys effectiveness per degree but pays in allowed degrees — a real
        trade, not a free knob. Symbolic-safe."""
        d = self.DV_DEFAULTS | (dv or {})
        c_cs = d["cs_frac"] * d["t_c_root"] * (1 + d["t_taper"]) / 2
        return (180 / np.pi) * self.TRIM_THROW_FRACTION * self.TAIL_THROW_TE_M / c_cs

    @staticmethod
    def _wing_panels(d: dict) -> list:
        """[(width, local dihedral deg)] for the four arc-length panels per
        side, sampling the dihedral curve delta(eta) = dihedral_tip * eta^d_exp
        at each panel's midpoint (midpoint rule for the arc integral).
        Geometry and constraints share this — they cannot drift apart.
        Symbolic-safe: eta > 0 always (center_width floor), power via exp/log."""
        semi = d["span"] / 2
        cw2 = d["center_width"] / 2
        w3 = (semi - cw2) / 3
        panels, s = [], 0
        for w in (cw2, w3, w3, w3):
            eta_mid = (s + w / 2) / semi
            panels.append((w, d["dihedral_tip"] * eta_mid ** d["d_exp"]))
            s = s + w
        return panels

    def _wing_curve_z(self, d: dict, eta):
        """Analytic curve height z(eta) via the small-angle integral
        semi * delta_tip[rad] * eta^(d_exp+1) / (d_exp+1) — feeds the
        straight-spar sag constraint (documented approximation, section 9;
        sin(delta) ~ delta is <= 11% high at the 20 deg tip-angle cap)."""
        q1 = d["d_exp"] + 1
        return (d["span"] / 2) * (np.pi / 180) * d["dihedral_tip"] * eta**q1 / q1

    @staticmethod
    def _trapezoid(c_root, taper, panel_len):
        """(MAC, arc distance root -> MAC station) of one linearly tapered
        panel — places a surface's AC including sweep. Symbolic-safe."""
        mac = (2 / 3) * c_root * (1 + taper + taper**2) / (1 + taper)
        s_mac = panel_len * (1 + 2 * taper) / (3 * (1 + taper))
        return mac, s_mac

    def design_variables(self, opti, inits: dict | None = None) -> dict:
        """Full-vehicle variables (M3+). Architecture mapping: span and taper act
        on the outer wing panels; the tail is per-dimension (span, root chord,
        taper, sweep, V-/fin angle, hinge fraction — MODEL_DETAILS section 8) and
        slides on the boom via tail_arm; spars are continuously sized
        (MODEL_DETAILS 1.3); balance via ballast mass and battery station.
        Cruise-state vars live in solve, not here."""
        i = self.DV_DEFAULTS | (inits or {})
        bounds = {
            "span": (1.5, self.span_cap_m), "c_root": (0.16, 0.245),
            "center_width": (0.10, 1.20),
            "r1": (0.55, 1.0), "r2": (0.55, 1.0), "r3": (0.55, 1.0),
            # dihedral curve: tip-angle cap matches the old per-panel cap; the
            # exponent spans simple dihedral (0) to a strongly tip-loaded curve
            "dihedral_tip": (0.0, self.tip_dihedral_max_deg), "d_exp": (0.0, 2.0),
            "washout_tip": (-4.0, 0.0),
            # tail_arm drives overall aircraft length + boom length — genuinely
            # wide bounds so total length is an optimization outcome
            "tail_arm": (0.40, 1.20),
            # per-dimension tail (section 8): span/chord/taper/sweep free within
            # a type; hinge fraction free per the user's 0.2-0.4 decision
            "t_span": (0.25, 1.20), "t_c_root": (0.06, 0.22),
            "t_taper": (0.40, 1.0), "t_sweep": (0.0, 25.0),
            "cs_frac": (0.20, 0.40),
            "spar_od_center": (0.006, 0.014), "spar_wall_center": (0.0006, 0.002),
            "spar_od_outer": (0.005, 0.012), "spar_wall_outer": (0.0005, 0.0018),
            # x_battery's real bounds are symbolic (inside the lofted bay,
            # geometry_constraints) — the box bound is just a wide backstop
            "ballast_kg": (0.0, 0.200), "x_battery": (-0.10, 0.40),
            "pod_nose": (0.030, 0.25), "pod_bay": (0.20, 0.55),
            "pod_xs": (0.75, 1.30), "pod_bay_end": (0.40, 0.62),
        }
        if self.fuselage_topology == "pod_boom":
            # integrated topology derives its cone length from tail_arm instead
            bounds["pod_tail"] = (0.10, 0.45)
        if self.tail_type == "vtail":
            # V-angle free: trades vertical vs horizontal tail effectiveness
            # against the declared Vv floor
            bounds["t_dihedral"] = (20.0, 55.0)
        else:
            # conventional / T-tail: the fin gets its own dimensions
            bounds |= {
                "fin_height": (0.08, 0.40), "fin_c_root": (0.05, 0.20),
                "fin_taper": (0.40, 1.0), "fin_sweep": (0.0, 35.0),
            }
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
        bay_end = d["pod_bay_end"]
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
        # pod top always meets the wing root plane (z = 0) with a small embed —
        # derived from pod height, so a shrunken pod can never leave the wing
        # floating above the fuselage
        z_c = self.SADDLE_EMBED - p["h"] / 2
        return [
            fuselage.loft(
                d["pod_nose"], d["pod_bay"], p["tail_len"], p["w"], p["h"],
                x_nose=p["nose_tip"], z_c=z_c,
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
        wing_panels = self._wing_panels(dv)  # [(width, local dihedral)] — v3 curve
        w3 = wing_panels[1][0]
        proj_semi = sum(w * np.cosd(delta) for w, delta in wing_panels)
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
        d0, d1, d2, d3 = (delta for _, delta in wing_panels)  # sampled curve
        panels = [
            (cw2 * c0, cw2 / 2, d0),
            (outer3 * (c0 + c1) / 2, cw2 + 0.5 * outer3, d1),
            (outer3 * (c1 + c2) / 2, cw2 + 1.5 * outer3, d2),
            (outer3 * (c2 + c3) / 2, cw2 + 2.5 * outer3, d3),
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

        # --- straight-spar fit (section 9, user decision 2026-07-23): both
        # tube spars stay STRAIGHT (the build standard — no segment joiners);
        # the dihedral curve's sag across each spar's run must leave room for
        # the tube inside the usable section depth, so spar holes are always
        # drillable in a straight line. A design that cannot pass a
        # sufficiently sized straight spar is unbuildable, hence a hard
        # geometry constraint, not a priced penalty. At d_exp = 0 the sag is
        # identically zero: simple dihedral always fits. ---
        semi = dv["span"] / 2
        tc = asb.Airfoil(self.wing_airfoil).max_thickness()  # numeric (discrete outer loop)
        depth = lambda c: self.SPAR_DEPTH_FRACTION * tc * c

        def sag(eta_a, eta_b, eta_x):
            # vertical deviation of the (convex) analytic curve below the
            # straight chord between the spar's ends, at station eta_x.
            # eta arguments must stay > 0: CasADi's symbolic-exponent power is
            # exp(q ln eta), whose q-derivative is NaN at eta = 0.
            za, zb = self._wing_curve_z(dv, eta_a), self._wing_curve_z(dv, eta_b)
            chord_z = za + (zb - za) * (eta_x - eta_a) / (eta_b - eta_a)
            return chord_z - self._wing_curve_z(dv, eta_x)

        eta_c = cw2 / semi  # center spar: root -> center edge; z(0) = 0 exactly
        sag_center = self._wing_curve_z(dv, eta_c) / 2 - self._wing_curve_z(dv, eta_c / 2)
        opti.subject_to(sag_center + dv["spar_od_center"] <= depth(c0))
        eta_o = (cw2 + 0.85 * 3 * outer3) / semi  # outer spar end (structures run)
        for eta_x, c_x in [
            ((cw2 + outer3) / semi, c1),  # interior panel breaks: deepest
            ((cw2 + 2 * outer3) / semi, c2),  # sag meets shrinking chord
        ]:
            opti.subject_to(sag(eta_c, eta_o, eta_x) + dv["spar_od_outer"] <= depth(c_x))

        # --- tail (MODEL_DETAILS section 8) ---
        t_c_mean = dv["t_c_root"] * (1 + dv["t_taper"]) / 2
        # tail mean-chord Reynolds floor: relaxed vs the 90k wing-tip rule
        # (small surface — same precedent as the winglet's 60k)
        opti.subject_to(1.225 * V * t_c_mean / 1.81e-5 >= 60e3)
        if deflection_deg is not None:
            # throw policy made geometric: the degree cap follows from the free
            # hinge fraction (see trim_deflection_limit_deg)
            limit = self.trim_deflection_limit_deg(dv)
            opti.subject_to(deflection_deg <= limit)
            opti.subject_to(deflection_deg >= -limit)
        # directional proxy (MODEL_DETAILS 3.4): LL has no yaw axis, so a
        # declared vertical-tail-volume floor stands in — without it fins
        # optimize to zero and V-tails shed angle. l_v ~ tail_arm (CG sits near
        # the wing AC at this fidelity); reference S*b is the wing's.
        s_wing = 2 * sum(a for a, _, _ in panels)
        if self.tail_type == "vtail":
            # effective vertical area of a V-tail: S_tail * sin^2(dihedral)
            s_v_eff = dv["t_span"] * t_c_mean * np.sind(dv["t_dihedral"]) ** 2
        else:
            fin_c_mean = dv["fin_c_root"] * (1 + dv["fin_taper"]) / 2
            opti.subject_to(1.225 * V * fin_c_mean / 1.81e-5 >= 60e3)
            s_v_eff = dv["fin_height"] * fin_c_mean
        vv = s_v_eff * dv["tail_arm"] / (s_wing * 2 * proj_semi)
        opti.subject_to(vv >= self.v_tail_volume_min)

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
        # wing saddle carry-through (MODEL_DETAILS 7.2): the constant-section
        # bay must physically carry the wing root — start ahead of the LE and
        # run to SADDLE_CHORD_FRAC of root chord. Without this the optimizer
        # shrinks the pod and leaves the wing floating (unbuildable).
        opti.subject_to(p["bay_start"] <= WING_X_LE - 0.010)
        opti.subject_to(p["bay_end"] >= WING_X_LE + self.SADDLE_CHORD_FRAC * dv["c_root"])
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
        # from each panel's local dihedral, so projected span = sum(w*cos d) —
        # exact at high cant (continuous-cant study). Parametric designs sample
        # the v3 dihedral CURVE (section 9); the dv=None fixture keeps the
        # frozen v1.2 spec panels (flat center, 3 deg outer) forever.
        if parametric:
            placements = self._wing_panels(dv)
        else:
            placements = [(cw2, 0.0), (outer3, 3.0), (outer3, 3.0), (outer3, 3.0)]
        ys, zs = [0.0], [0.0]
        for width, ang in placements:
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

        c_mean = wing.area() / wing.span()
        if parametric:
            tails = self._tail_wings(dv, c_mean)
        else:
            # frozen v1.2 spec V-tail (dv=None fixture — validation continuity;
            # keeps the pre-section-8 root-LE formula, so M1 numbers never move)
            ruddervator = asb.ControlSurface(
                name="ruddervator", symmetric=True, deflection=0, hinge_point=0.73
            )
            tails = [
                asb.Wing(
                    name="vtail",
                    symmetric=True,
                    xsecs=[
                        asb.WingXSec(
                            xyz_le=[0, 0, 0], chord=0.150, twist=0,
                            airfoil=naca0009, control_surfaces=[ruddervator],
                        ),
                        asb.WingXSec(
                            xyz_le=[0.040, 0.320 * np.cosd(38), 0.320 * np.sind(38)],
                            chord=0.110, twist=0, airfoil=naca0009,
                        ),
                    ],
                ).translate([WING_X_LE + 0.25 * c_mean + TAIL_ARM - 0.25 * 0.131, 0, 0])
            ]

        return asb.Airplane(
            name=self.name,
            wings=[wing] + tails + ([winglet] if winglet is not None else []),
            s_ref=wing.area(),
            c_ref=wing.area() / wing.span(),  # mean chord (symbolic-safe MAC proxy)
            # projected (front-view y) span: the manufacturing-capped quantity,
            # and the b the y-based Schrenk stations are consistent with
            b_ref=2 * ys[4],
        )

    def _tail_wings(self, d: dict, c_mean_wing) -> list:
        """Tail surfaces for the current tail_type (MODEL_DETAILS section 8).

        Per-dimension variables (tail_scale retired). The pitch surface's AC is
        placed exactly tail_arm behind the wing AC including the sweep offset —
        sweeping the tail shifts its root LE forward, so sweep cannot buy free
        moment arm against the boom-length accounting. Symbolic-safe: branches
        only on self.tail_type (a plain string), never on dv values."""
        naca0009 = asb.Airfoil("naca0009")
        ac_x = WING_X_LE + 0.25 * c_mean_wing + d["tail_arm"]
        semi = d["t_span"] / 2
        c_r, c_t = d["t_c_root"], d["t_c_root"] * d["t_taper"]
        mac, s_mac = self._trapezoid(d["t_c_root"], d["t_taper"], semi)
        x_le_root = ac_x - s_mac * np.tand(d["t_sweep"]) - 0.25 * mac
        pitch_cs = asb.ControlSurface(
            name=self.pitch_control_name, symmetric=True, deflection=0,
            hinge_point=1 - d["cs_frac"],  # chord fraction free (0.2-0.4)
        )

        if self.tail_type == "vtail":
            gamma = d["t_dihedral"]
            return [
                asb.Wing(
                    name="vtail",
                    symmetric=True,
                    xsecs=[
                        asb.WingXSec(
                            xyz_le=[0, 0, 0], chord=c_r, twist=0,
                            airfoil=naca0009, control_surfaces=[pitch_cs],
                        ),
                        asb.WingXSec(
                            xyz_le=[
                                semi * np.tand(d["t_sweep"]),
                                semi * np.cosd(gamma),
                                semi * np.sind(gamma),
                            ],
                            chord=c_t, twist=0, airfoil=naca0009,
                        ),
                    ],
                ).translate([x_le_root, 0, 0])
            ]

        # conventional / T-tail: flat hstab + centerline fin. The T-tail mounts
        # the hstab at the fin tip (z offset); the mount itself is priced as a
        # declared mass (TTAIL_FIN_MOUNT_KG), not modeled structurally.
        z_stab = d["fin_height"] if self.tail_type == "ttail" else 0.0
        hstab = asb.Wing(
            name="hstab",
            symmetric=True,
            xsecs=[
                asb.WingXSec(
                    xyz_le=[0, 0, 0], chord=c_r, twist=0,
                    airfoil=naca0009, control_surfaces=[pitch_cs],
                ),
                asb.WingXSec(
                    xyz_le=[semi * np.tand(d["t_sweep"]), semi, 0],
                    chord=c_t, twist=0, airfoil=naca0009,
                ),
            ],
        ).translate([x_le_root, 0, z_stab])
        h = d["fin_height"]
        f_mac, f_s_mac = self._trapezoid(d["fin_c_root"], d["fin_taper"], h)
        fin_x_le = ac_x - f_s_mac * np.tand(d["fin_sweep"]) - 0.25 * f_mac
        fin = asb.Wing(
            name="fin",
            symmetric=False,
            xsecs=[
                asb.WingXSec(
                    xyz_le=[0, 0, 0], chord=d["fin_c_root"], twist=0, airfoil=naca0009
                ),
                asb.WingXSec(
                    xyz_le=[h * np.tand(d["fin_sweep"]), 0, h],
                    chord=d["fin_c_root"] * d["fin_taper"], twist=0, airfoil=naca0009,
                ),
            ],
        ).translate([fin_x_le, 0, 0])
        return [hstab, fin]

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
            PointMass("servos_tail", 0.024, x_tail),  # tail root block (2 micro servos, any type)
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
            + 0.035  # root V-joint + center-outer joiner blocks + pins
            # (v2's per-break polyhedral joiners are gone — the v3 curve has no
            # interior dihedral breaks; print-section joints live in k_joint)
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
            x_tail = WING_X_LE + 0.25 * 0.201 + d["tail_arm"]
            swet = self.fuselage_lofts(dv)[0].area_wetted()
            # k_skin x Swet + overhead, calibrated to reproduce the frozen 250 g
            # at the spec loft (Swet 0.1365 m2) — same uncalibrated caveat as wings
            extras.append(
                PointMass("pod", 1.465 * swet + 0.050, p["nose_tip"] + 0.51 * p["length"])
            )
            if self.tail_type == "ttail":
                # stab-on-fin mount penalty (declared, MODEL_DETAILS section 8)
                extras.append(PointMass("ttail_fin_mount", self.TTAIL_FIN_MOUNT_KG, x_tail))
            if self.fuselage_topology == "pod_boom":
                # boom spans pod tail cap -> tail block (+50 mm sockets); its
                # length is an outcome of tail_arm and the loft, not a constant
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

    def design_brief(self, dv: dict | None = None, shadow_per_g=None) -> dict:
        """Designer-facing numbers for the CAD round-trip (report/brief.py).
        Everything here derives from declared data + the champion design vector."""
        d = self.DV_DEFAULTS | (dv or {})
        p = self.pod_dims(d)
        env, clr = self.COMPONENT_ENVELOPES, self.POD_WALL_CLEARANCE
        batt = env["battery"]
        d_eq = (p["w"] * p["h"]) ** 0.5
        half = batt["length"] / 2
        x_tail = WING_X_LE + 0.25 * 0.201 + d["tail_arm"]
        pod_end = p["bay_end"] + p["tail_len"]
        mm = lambda v: f"{v * 1000:.0f} mm"

        brief = {
            "Cross-section (front view)": {
                "inner floor (battery + 4 mm play)": f"{mm(batt['width'] + 0.004)} W x {mm(batt['height'] + 0.004)} H",
                "wall + foam liner allowance, per side": mm(clr),
                "champion outer section": f"{mm(p['w'])} W x {mm(p['h'])} H (rounded rectangle)",
            },
            "Length budget (champion optimum)": {
                "nose (elliptical, floor 1.0 x d_eq)": f"{mm(d['pod_nose'])} (floor {mm(1.0 * d_eq)})",
                "equipment bay (constant section)": mm(d["pod_bay"]),
                "boat-tail (floor 1.8 x d_eq)": f"{mm(p['tail_len'])} (floor {mm(1.8 * d_eq)})",
                "overall pod": mm(p["length"]),
                "fineness (L / d_eq)": f"{p['length'] / d_eq:.2f}",
            },
            "Balance — battery must reach these stations": {
                "bay interior spans": f"{mm(p['bay_start'])} to {mm(p['bay_end'])} aft of nose datum",
                "battery CG window (3 mm end margins)": f"{mm(p['bay_start'] + 0.003 + half)} to {mm(p['bay_end'] - 0.003 - half)}",
                "champion battery CG": mm(d["x_battery"]),
            },
            "Fixed interfaces": {
                "wing saddle: full-section bay must span": (
                    f"{mm(WING_X_LE - 0.010)} to {mm(WING_X_LE + self.SADDLE_CHORD_FRAC * d['c_root'])}"
                    f" (LE - 10 mm to {self.SADDLE_CHORD_FRAC:.0%} root chord); champion bay"
                    f" {mm(p['bay_start'])} to {mm(p['bay_end'])}"
                ),
                "pod top embeds into wing root plane": mm(self.SADDLE_EMBED),
                "boom socket at tail cap (pod-boom topology)": f"12 mm OD at station {mm(pod_end)}",
                "tail block station (champion tail arm)": mm(x_tail),
                "ESC / FC+GPS stack lengths": f"{mm(env['esc']['length'])} / {mm(env['fc_gps']['length'])}",
            },
        }
        if shadow_per_g is not None:
            g_per_swet = 1.465 * 1000  # pod skin model: grams per m2 wetted
            brief["Deviation prices (mass route only — drag adds on top)"] = {
                "+0.01 m2 wetted area": f"{abs(shadow_per_g) * g_per_swet * 0.01:.2f} objective units",
                "+100 g anywhere": f"{abs(shadow_per_g) * 100:.2f} objective units",
            }
        return brief

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
        # every surface any tail type can generate has a profile — massmodel
        # maps by wing name, so the mapping must cover the whole declared list
        return {
            "wing": LWPLA_A1,
            "vtail": LWPLA_A1_TAIL,
            "hstab": LWPLA_A1_TAIL,
            "fin": LWPLA_A1_FIN,
            "winglet": LWPLA_A1_WINGLET,
        }


AIRCRAFT = VTailSample()
