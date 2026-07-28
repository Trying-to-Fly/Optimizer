"""Speed fixture: conventional-tail, nose-mounted (puller) sport plane.

A starting point for a max-speed study on the same powertrain as
`aircraft/vtail_sample` — identical motor, prop, 4S pack and ESC — so the two
runs differ in airframe and objective, not in hardware.

Written from the framework contracts rather than copied from the V-tail sample.
That is deliberate: it is the second aircraft, and the point of the iron rule
("nothing in src/planeopt may assume the sample's architecture") is only proven
by a second aircraft that shares no code with the first.

Architecture, and what is free vs declared:

- **Wing**: single tapered trapezoid, straight leading edge, uniform dihedral.
  Span, root chord, taper, dihedral and washout are free. No winglet — at a
  speed objective the wing wants to be small and lightly loaded in induced
  drag, so a winglet is wetted area looking for a job. (Run the sample's
  winglet study if you want that priced rather than asserted.)
- **Tail**: conventional — horizontal stabiliser carrying the elevator, plus a
  vertical fin. Both sized by free variables against declared tail-volume
  floors; the arm is free, so overall length is an outcome.
- **Fuselage**: declared pod (it has to hold the same 4S pack and electronics,
  which sets its size) plus a boom whose length falls out of the tail arm. The
  pod is *not* optimised here — see `vtail_sample` for the parametric loft. For
  a first speed study the wing and tail are what move the answer.
- **Powertrain**: identical to the endurance plane, by request.

Symbolic-safety rule (types.py): once design variables flow in, no branching on
their values, and no non-smooth numpy on them.
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

from lwpla_a1 import (
    LWPLA_A1_SPEED,
    LWPLA_A1_SPEED_FIN,
    LWPLA_A1_SPEED_TAIL,
    LWPLA_A1_SPEED_WINGLET,
)

# --- what has to be carried (stations in m aft of the nose tip) ---
# These are component envelopes, not fuselage dimensions: the fuselage is sized
# by the optimiser around them, so nothing about its shape is asserted here.
BATT_L, BATT_W, BATT_H = 0.145, 0.045, 0.030  # the 4S 4Ah pack
STACK_LEN = 0.070  # ESC + FC + RX + wiring, packed behind the battery
MOTOR_LEN = 0.055  # motor can + spinner ahead of the firewall
WALL = 0.006  # printed shell + clearance, per side
SHELL_KG_M2 = 0.60  # printed fuselage shell + formers, per m2 of wetted area
BOOM_OD, BOOM_WALL = 0.012, 0.0008  # CF tube, only used by the pod_boom topology

# Props the optimiser may choose between. Diameter is no longer a data limit —
# the whole published APC catalogue ships (443 tables, `planeopt props`) — so
# this list is a DESIGN decision: 11 in is what fits the airframe and keeps the
# 190 g motor_prop point mass honest. Pitch and usable advance ratio are what
# differ, and the J ceiling matters here because it caps V/(nD) directly.
# Widen this list (or add diameters) when the airframe can take them.
PROP_OPTIONS = {
    "apc_11x55e": {"name": "APC 11x5.5E", "diameter_m": 0.2794, "pitch_m": 0.1397},
    "apc_11x6": {"name": "APC 11x6", "diameter_m": 0.2794, "pitch_m": 0.1524},
    "apc_11x7e": {"name": "APC 11x7E", "diameter_m": 0.2794, "pitch_m": 0.1778},
}
# Folding blades cost ~5% of shaft power. A speed airframe has no reason to fold
# unless you want the option, so both are priced.
BLADE_DERATE = {"folding": 0.95, "fixed": 1.00}


class SpeedSample:
    name = "speed_sample_v1.0"

    # Lowest-camber thin section of the candidates (2.4% camber, 8.7% thick):
    # a speed design cruises at low CL, where camber is drag. This is a starting
    # point, not a finding — `planeopt airfoils` prices the alternatives.
    wing_airfoil = "mh32"

    # Same manufacturing cap as the endurance plane (printed sections, 2.0 m
    # projected). The lower bound is deliberately wide: a speed objective should
    # be free to shrink the wing, and how far it goes is the interesting output.
    span_cap_m = 2.0

    # Never-exceed speed. Flutter and divergence are outside this model, so the
    # cap is declared by the airframe rather than predicted — treat it as a
    # placard for a 3D-printed sport airframe, and revisit it before flying.
    placard_speed_ms = 45.0

    # Conventional tail: the pitch surface is an elevator, and the framework
    # threads this name through trim (no hardcoded surface anywhere).
    pitch_control_name = "elevator"

    # This airframe's speed envelope, for the M1 evaluation sweep. The framework
    # default (8-17 m/s) is a loiter window: this plane stalls above its bottom
    # end, which would leave the power curve with three points on it.
    speed_sweep_ms = (12.0, 42.0, 1.0)

    # Aspect-ratio floor — a model-validity limit, not a style preference.
    # LiftingLine assumes a high-aspect-ratio wing; left free, a speed objective
    # drives the planform to AR ~1.5 (short span, huge chord) because induced
    # drag is cheap at low CL and a short spar is light. The optimiser is then
    # exploiting a region where the aerodynamics being reported is not valid.
    aspect_ratio_min = 4.5

    # Tail arm as a multiple of the wing's mean chord. Tail *volume* alone can be
    # bought with arm instead of area, which satisfies the floor with a long boom
    # and a minimal stabiliser — and a small surface runs out of elevator throw
    # however long the arm is. Sport aircraft sit near 2.5-3.5 chords.
    tail_arm_max_chords = 4.0

    # Tail-volume floors (declared practice, MODEL_DETAILS section 8): enough
    # tail to be controllable and damped, not an optimisation outcome.
    # Raised from 0.45: the elevator saturated its throw at that value, which is
    # the model telling us the surface is too small to trim this airframe.
    h_tail_volume_min = 0.60
    v_tail_volume_min = 0.030
    min_effective_dihedral_deg = 2.0  # lateral stability proxy for an aileron ship

    # "Consider a winglet", not "have one". solve.optimize runs a paired on/off
    # re-optimisation at the same span cap and keeps the winglet only if it wins
    # (MODEL_DETAILS section 3.6); if the off-solve is better, IT becomes the
    # champion. The same study also frees the tip panel's cant as a cross-check:
    # does something winglet-shaped emerge from the planform on its own?
    winglet = True
    tip_dihedral_max_deg = 20.0  # raised to ~88 only by the continuous-cant study
    TIP_PANEL_FRAC = 0.15  # outboard fraction of the semi-span that can cant

    # Whether the tail rides a boom or an extended fuselage is a genuine
    # discrete choice, so it is enumerated and priced by a study rather than
    # asserted (MODEL_DETAILS section 7.4). The champion adopts whichever wins.
    fuselage_topology = "pod_boom"

    # Prop and blade type are enumerated, not assumed. Listed first because the
    # J ceiling differs between tables (0.607 vs 0.758) and that ceiling has been
    # an active constraint — it is likely the biggest single lever here.
    # The 11x6 cannot sustain level flight anywhere in this aircraft's speed
    # range: at the slowest rpm its fitted table covers, it already makes more
    # thrust than this airframe needs, so the operating point falls off the end
    # of the data. The 11x7E solves across the whole envelope, so it is the
    # starting point — the study still prices all three.
    prop_table = "apc_11x7e"
    prop_blades = "folding"

    discrete_options = {
        "prop_table": list(PROP_OPTIONS),
        "prop_blades": list(BLADE_DERATE),
        "fuselage_topology": ["pod_boom", "integrated"],
    }

    # Gust load factor the spar is sized to. Higher than the loiter plane's 5 g:
    # the same gust at twice the speed is a much bigger load factor.
    n_limit = 6.0

    DV_DEFAULTS = {
        "span": 1.10,
        "c_root": 0.165,
        "taper": 0.62,
        "dihedral": 3.0,
        "washout_tip": -1.0,
        "tail_arm": 0.520,
        "t_span": 0.380,
        "t_c_root": 0.110,
        "t_taper": 0.75,
        "t_incidence": -1.0,
        "fin_height": 0.170,
        "fin_c_root": 0.130,
        "fin_taper": 0.60,
        "cs_frac": 0.30,
        "spar_od": 0.011,
        "spar_wall": 0.0011,
        "ballast_kg": 0.0,
        "x_battery": 0.145,
        # fuselage: sized by the optimiser around the components above
        "x_wing_le": 0.300,
        "fus_w": 0.072,
        "fus_h": 0.062,
        "nose_len": 0.080,
        "bay_len": 0.230,
        "boat_len": 0.130,
        # tip panel + winglet
        "tip_cant": 4.0,
        "wl_len": 0.070,
        "wl_cant": 75.0,
        "wl_c_root": 0.060,
        "wl_taper": 0.60,
    }

    BOUNDS = {
        "span": (0.50, span_cap_m),
        "c_root": (0.060, 0.320),
        "taper": (0.45, 1.00),
        "dihedral": (0.0, 12.0),
        "washout_tip": (-4.0, 2.0),
        "tail_arm": (0.25, 1.30),
        "t_span": (0.15, 1.10),
        "t_c_root": (0.040, 0.300),
        "t_taper": (0.50, 1.00),
        # Stabiliser incidence: without it every bit of trim has to come from
        # elevator deflection, which pins the design against the throw cap and
        # makes it trim-limited rather than power-limited. Real aircraft set the
        # stabiliser so the elevator sits near neutral in cruise.
        "t_incidence": (-6.0, 2.0),
        "fin_height": (0.060, 0.450),
        "fin_c_root": (0.040, 0.260),
        "fin_taper": (0.45, 1.00),
        "cs_frac": (0.20, 0.55),
        "spar_od": (0.006, 0.018),
        "spar_wall": (0.0005, 0.0025),
        "ballast_kg": (0.0, 0.200),
        "x_battery": (0.030, 0.600),
        # Fuselage geometry is free. Packaging and streamlining floors in
        # geometry_constraints keep it buildable; nothing here presumes a shape,
        # a length, or whether there is a boom at all.
        "x_wing_le": (0.05, 0.95),
        "fus_w": (0.050, 0.150),
        "fus_h": (0.040, 0.150),
        "nose_len": (0.030, 0.300),
        "bay_len": (0.150, 0.700),
        "boat_len": (0.050, 0.600),
        # Outboard panel cant. Normally a mild polyhedral tip; the
        # continuous-cant study raises the ceiling so the planform can grow its
        # own winglet if that is genuinely better than a bolted-on one.
        "tip_cant": (0.0, tip_dihedral_max_deg),
    }

    # Winglet variables exist only when a winglet is under consideration —
    # otherwise they would be free variables the geometry never reads, which is
    # a null space for the solver to wander in.
    WINGLET_BOUNDS = {
        "wl_len": (0.030, 0.220),
        "wl_cant": (55.0, 90.0),  # degrees from horizontal; 90 = vertical
        "wl_c_root": (0.030, 0.140),
        "wl_taper": (0.35, 1.00),
    }

    # ------------------------------------------------------------------ geometry

    # Numerical brackets for the operating point, widened from the framework
    # defaults, which were sized around a 9-11 m/s loiter design. Leaving them
    # at the default caps this aircraft at 25 m/s and 15 degrees of elevator —
    # limits of the solver's box, not of the airplane.
    operating_bounds = {
        "V_ms": (8.0, 50.0),  # above the 45 m/s placard, so the placard binds first
        "alpha_deg": (-6.0, 18.0),
        "deflection_deg": (-32.0, 32.0),
        "prop_rev_s": (20.0, 260.0),  # 900 kv on 4S unloaded is ~222 rev/s
    }

    # Declared mechanical throw, not derived from a fixed horn arc.
    #
    # The sample plane derives its cap from a 12 mm horn travel, which shrinks
    # as the control chord grows — on this larger tail that policy yields about
    # 6 degrees and makes the design trim-limited rather than power-limited. A
    # real linkage is sized to the surface it drives, so the honest declaration
    # here is the throw the builder will set up.
    trim_deflection_limit_deg = 27.0

    @staticmethod
    def _trapezoid(c_root, taper, semi):
        """(mean aerodynamic chord, spanwise station of the MAC)."""
        mac = c_root * (2 / 3) * (1 + taper + taper**2) / (1 + taper)
        y_mac = semi * (1 + 2 * taper) / (3 * (1 + taper))
        return mac, y_mac

    def _wing_panels(self, d: dict) -> list:
        """[(arc width, cant angle)] per semi-span panel, root outward.

        Arc width, not projected: the span variable is material span, and the
        projected-span cap is applied to the cosine sum in geometry_constraints.
        """
        semi = d["span"] / 2
        return [
            (semi * (1 - self.TIP_PANEL_FRAC), d["dihedral"]),
            (semi * self.TIP_PANEL_FRAC, d["tip_cant"]),
        ]

    def _wing_mac(self, d: dict):
        return self._trapezoid(d["c_root"], d["taper"], d["span"] / 2)

    def geometry(self, dv=None) -> asb.Airplane:
        """dv=None -> the declared baseline; otherwise the parametric design.

        Symbolic-safe: works with floats or Opti variables, and never branches
        on a dv value.
        """
        d = self.DV_DEFAULTS | (dv or {})
        wing_af = asb.Airfoil(self.wing_airfoil)
        tail_af = asb.Airfoil("naca0009")  # symmetric section for both tail surfaces

        semi = d["span"] / 2
        c_tip = d["c_root"] * d["taper"]
        mac, y_mac = self._wing_mac(d)

        # Straight leading edge, taper off the trailing edge. Two panels: an
        # inboard panel at the wing dihedral, and a short outboard panel with
        # its own cant — mild polyhedral normally, and the degree of freedom the
        # continuous-cant cross-check opens up.
        panels = self._wing_panels(d)  # [(arc width, cant angle)], root outward
        y1 = panels[0][0] * np.cosd(panels[0][1])
        z1 = panels[0][0] * np.sind(panels[0][1])
        y2 = y1 + panels[1][0] * np.cosd(panels[1][1])
        z2 = z1 + panels[1][0] * np.sind(panels[1][1])
        c_break = d["c_root"] * (1 - (1 - d["taper"]) * (1 - self.TIP_PANEL_FRAC))

        wing = asb.Wing(
            name="wing",
            symmetric=True,
            xsecs=[
                asb.WingXSec(
                    xyz_le=[d["x_wing_le"], 0, 0],
                    chord=d["c_root"],
                    twist=0,
                    airfoil=wing_af,
                    control_surfaces=[
                        asb.ControlSurface(name="aileron", symmetric=False, deflection=0)
                    ],
                ),
                asb.WingXSec(
                    xyz_le=[d["x_wing_le"], y1, z1],
                    chord=c_break,
                    twist=d["washout_tip"] * (1 - self.TIP_PANEL_FRAC),
                    airfoil=wing_af,
                ),
                asb.WingXSec(
                    xyz_le=[d["x_wing_le"], y2, z2],
                    chord=c_tip,
                    twist=d["washout_tip"],
                    airfoil=wing_af,
                ),
            ],
        )

        surfaces = [wing]
        if self.winglet:
            # A separate surface at the wing tip, not a bent-up panel: its own
            # length, cant, chords. Branching on self.winglet (a plain bool the
            # study flips) is symbolic-safe; branching on a dv value would not be.
            surfaces.append(
                asb.Wing(
                    name="winglet",
                    symmetric=True,
                    xsecs=[
                        asb.WingXSec(
                            xyz_le=[d["x_wing_le"] + 0.25 * (c_tip - d["wl_c_root"]), y2, z2],
                            chord=d["wl_c_root"], twist=0, airfoil=wing_af,
                        ),
                        asb.WingXSec(
                            xyz_le=[
                                d["x_wing_le"] + 0.25 * (c_tip - d["wl_c_root"] * d["wl_taper"]),
                                y2 + d["wl_len"] * np.cosd(d["wl_cant"]),
                                z2 + d["wl_len"] * np.sind(d["wl_cant"]),
                            ],
                            chord=d["wl_c_root"] * d["wl_taper"], twist=0, airfoil=wing_af,
                        ),
                    ],
                )
            )

        # Tail surfaces are placed so the horizontal tail's AC sits exactly
        # `tail_arm` behind the wing AC — the arm is the variable, the station
        # is derived from it.
        ac_x = d["x_wing_le"] + 0.25 * mac + d["tail_arm"]
        t_mac, t_y_mac = self._trapezoid(d["t_c_root"], d["t_taper"], d["t_span"] / 2)
        t_le = ac_x - 0.25 * t_mac
        elevator = asb.ControlSurface(
            name=self.pitch_control_name,
            symmetric=True,
            deflection=0,
            hinge_point=1 - d["cs_frac"],
        )
        hstab = asb.Wing(
            name="hstab",
            symmetric=True,
            xsecs=[
                asb.WingXSec(
                    xyz_le=[t_le, 0, 0], chord=d["t_c_root"], twist=d["t_incidence"],
                    airfoil=tail_af, control_surfaces=[elevator],
                ),
                asb.WingXSec(
                    xyz_le=[t_le, d["t_span"] / 2, 0],
                    chord=d["t_c_root"] * d["t_taper"], twist=d["t_incidence"],
                    airfoil=tail_af,
                ),
            ],
        )

        f_mac, _ = self._trapezoid(d["fin_c_root"], d["fin_taper"], d["fin_height"])
        fin_le = ac_x - 0.25 * f_mac
        fin = asb.Wing(
            name="fin",
            symmetric=False,  # a fin is one surface, not a mirrored pair
            xsecs=[
                asb.WingXSec(
                    xyz_le=[fin_le, 0, 0], chord=d["fin_c_root"], twist=0,
                    airfoil=tail_af,
                    control_surfaces=[
                        asb.ControlSurface(name="rudder", symmetric=False, deflection=0)
                    ],
                ),
                asb.WingXSec(
                    xyz_le=[fin_le, 0, d["fin_height"]],
                    chord=d["fin_c_root"] * d["fin_taper"], twist=0, airfoil=tail_af,
                ),
            ],
        )

        return asb.Airplane(
            name=self.name,
            wings=[*surfaces, hstab, fin],  # wings[0] is the main wing, by contract
            xyz_ref=[d["x_wing_le"] + 0.25 * mac, 0, 0],
        )

    def fus_dims(self, d: dict) -> dict:
        """Fuselage stations derived from the design vector (symbolic-safe).

        In the integrated topology the body runs all the way to the tail, so the
        boat-tail length is whatever is left after the nose and bay; in pod_boom
        it ends where the boom socket starts. Branching is on the topology
        string, never on a variable's value.
        """
        bay_end = d["nose_len"] + d["bay_len"]
        if self.fuselage_topology == "integrated":
            boat = self._tail_station(d) - bay_end
        else:
            boat = d["boat_len"]
        return {
            "nose": d["nose_len"], "bay": d["bay_len"], "boat": boat,
            "bay_start": d["nose_len"], "bay_end": bay_end,
            "length": bay_end + boat,
            "w": d["fus_w"], "h": d["fus_h"],
            "d_eq": (d["fus_w"] * d["fus_h"]) ** 0.5,
        }

    def fuselage_lofts(self, dv: dict | None = None) -> list:
        """Viz twin only — the aero airplane stays wings-only so the flat-plate
        buildup in parasite_bodies is not double-counted (MODEL_DETAILS 7)."""
        from planeopt import fuselage

        d = self.DV_DEFAULTS | (dv or {})
        f = self.fus_dims(d)
        # End cap: a boom socket when there is a boom, a small tail cap when the
        # body carries the tail itself.
        r_cap = BOOM_OD / f["d_eq"] if self.fuselage_topology == "pod_boom" else 0.10
        return [
            fuselage.loft(
                nose_len=f["nose"], bay_len=f["bay"], tail_len=f["boat"],
                width=f["w"], height=f["h"],
                x_nose=0.0,
                z_c=-f["h"] / 2 + 0.006,  # wing root plane embeds 6 mm into the body
                r_cap=r_cap,
                name="fuselage",
            )
        ]

    # --------------------------------------------------------------- constraints

    def design_variables(self, opti, inits: dict | None = None) -> dict:
        """Declare every free variable with its bounds and a starting value."""
        start = self.DV_DEFAULTS | (inits or {})
        bounds = dict(self.BOUNDS)
        # The continuous-cant study mutates tip_dihedral_max_deg, so the tip
        # panel's ceiling is read at declare time rather than frozen in BOUNDS.
        bounds["tip_cant"] = (0.0, self.tip_dihedral_max_deg)
        if self.winglet:
            bounds |= self.WINGLET_BOUNDS
        dv = {}
        for key, (lo, hi) in bounds.items():
            dv[key] = opti.variable(init_guess=start[key], lower_bound=lo, upper_bound=hi)
        return dv

    def geometry_constraints(self, opti, dv, V, deflection_deg=None) -> None:
        """Manufacturing, packaging and handling limits (all symbolic-safe)."""
        d = dv
        semi = d["span"] / 2
        mac, _ = self._wing_mac(d)
        s_wing = 2 * semi * d["c_root"] * (1 + d["taper"]) / 2

        # Tip Reynolds floor: below ~90k the polars this model trusts stop being
        # trustworthy, which matters more here because a speed wing is small.
        c_tip = d["c_root"] * d["taper"]
        opti.subject_to(1.225 * V * c_tip / 1.81e-5 >= 90e3)

        # Manufacturing cap on PROJECTED span (front-view width): each panel
        # contributes its arc width times the cosine of its cant, and a winglet
        # adds its own y-projection — otherwise a winglet would be free width.
        proj_semi = sum(w * np.cosd(cant) for w, cant in self._wing_panels(d))
        proj_span = 2 * proj_semi
        if self.winglet:
            proj_span = proj_span + 2 * d["wl_len"] * np.cosd(d["wl_cant"])
        opti.subject_to(proj_span <= self.span_cap_m)

        # Aspect-ratio floor (model validity — see the class attribute).
        opti.subject_to(d["span"] ** 2 / s_wing >= self.aspect_ratio_min)
        # Tail arm in wing chords: keeps the tail sized by area, not by leverage.
        opti.subject_to(d["tail_arm"] <= self.tail_arm_max_chords * mac)

        # Lateral stability proxy: an aileron ship still needs some dihedral.
        opti.subject_to(d["dihedral"] >= self.min_effective_dihedral_deg)

        # Tail volumes against declared floors — enough tail to fly, sized by the
        # optimiser above that.
        s_h = 2 * (d["t_span"] / 2) * d["t_c_root"] * (1 + d["t_taper"]) / 2
        s_v = d["fin_height"] * d["fin_c_root"] * (1 + d["fin_taper"]) / 2
        opti.subject_to(s_h * d["tail_arm"] / (s_wing * mac) >= self.h_tail_volume_min)
        opti.subject_to(s_v * d["tail_arm"] / (s_wing * d["span"]) >= self.v_tail_volume_min)

        # The horizontal tail must be smaller than the wing it trims, and its
        # span must clear the fin root sensibly.
        opti.subject_to(d["t_span"] <= 0.55 * d["span"])
        opti.subject_to(d["t_c_root"] <= 0.90 * d["c_root"])

        # --- fuselage: sized around what it carries, shaped to stay buildable ---
        f = self.fus_dims(d)
        # cross-section must swallow the pack with wall and clearance
        opti.subject_to(f["w"] >= BATT_W + 2 * WALL)
        opti.subject_to(f["h"] >= BATT_H + 2 * WALL)
        # bay must hold the pack plus the electronics stack behind it
        opti.subject_to(f["bay"] >= BATT_L + STACK_LEN)
        # nose must clear the motor, and stay long enough to fair into the bay
        opti.subject_to(f["nose"] >= MOTOR_LEN)
        opti.subject_to(f["nose"] >= 1.0 * f["d_eq"])
        # boat-tail proportion floor: shorter than this and the flow separates,
        # which the flat-plate buildup would not notice but the airplane would
        opti.subject_to(f["boat"] >= 1.8 * f["d_eq"])
        # the battery lives inside the bay
        opti.subject_to(d["x_battery"] >= f["bay_start"] + BATT_L / 2)
        opti.subject_to(d["x_battery"] <= f["bay_end"] - BATT_L / 2)
        # wing saddle: the root has to be carried by the body, not float above it
        opti.subject_to(d["x_wing_le"] >= f["bay_start"] - 0.010)
        opti.subject_to(d["x_wing_le"] + 0.60 * d["c_root"] <= f["bay_end"])
        # tail group sits aft of the body (pod_boom leaves room for a boom;
        # integrated meets it exactly, enforced by fus_dims)
        if self.fuselage_topology == "pod_boom":
            opti.subject_to(self._tail_station(d) >= f["length"] + 0.030)

        # Elevator throw: the commanded deflection must be inside the horn's arc.
        if deflection_deg is not None:
            cap = self.trim_deflection_limit_deg  # declared constant, not a policy
            opti.subject_to(deflection_deg <= cap)
            opti.subject_to(deflection_deg >= -cap)

    def structure_constraints(self, opti, dv, weight_n) -> None:
        """One-piece wing spar sized at the declared gust load factor."""
        from planeopt import structures

        semi = dv["span"] / 2
        moment = structures.semispan_root_moment(weight_n, self.n_limit, semi)
        structures.spar_constraints(opti, dv["spar_od"], dv["spar_wall"], semi, moment)
        # The spar has to fit inside the section it is buried in: usable depth is
        # ~70% of the tip thickness (the sample's rule, same printing reality).
        t_over_c = asb.Airfoil(self.wing_airfoil).max_thickness()
        opti.subject_to(dv["spar_od"] <= 0.70 * t_over_c * dv["c_root"] * dv["taper"])

    # ---------------------------------------------------------------- mass & drag

    def _tail_station(self, d: dict):
        """Station of the tail group (its quarter-chord), derived from the arm."""
        mac, _ = self._wing_mac(d)
        return d["x_wing_le"] + 0.25 * mac + d["tail_arm"]

    def _boom_length(self, d: dict):
        """Exposed boom: zero-length by construction in the integrated topology."""
        if self.fuselage_topology == "integrated":
            return 0.0
        return self._tail_station(d) - self.fus_dims(d)["length"]

    def powertrain(self) -> PowertrainConfig:
        """Identical to aircraft/vtail_sample — the point of this fixture is to
        change the airframe and the objective, not the hardware.

        The prop is the same folding unit; its folding knockdown stays, but the
        pusher-installation derate does not apply to a nose mount (MODEL_DETAILS
        section 2.4), so the puller carries no install penalty here.
        """
        return PowertrainConfig(
            motor=MotorConfig(
                name="D3548-900kv",
                kv_rpm_per_volt=900,
                resistance_ohm=0.025,  # vendor data, uncalibrated
                no_load_current_a=1.8,
                max_current_a=55,  # burst — what max_speed is allowed to use
            ),
            prop=PropConfig(
                name=f"{PROP_OPTIONS[self.prop_table]['name']} ({self.prop_blades})",
                diameter_m=PROP_OPTIONS[self.prop_table]["diameter_m"],
                pitch_m=PROP_OPTIONS[self.prop_table]["pitch_m"],
                proxy_table=self.prop_table,
                # Blade-type knockdown only; a nose mount carries no installation
                # derate (MODEL_DETAILS section 2.4).
                folding_derate=BLADE_DERATE[self.prop_blades],
            ),
            battery=BatteryConfig(capacity_ah=4.0, v_nominal=14.8, usable_fraction=0.80),
            esc_efficiency=0.95,
            esc_continuous_current_a=40,
            avionics_power_w=3.0,
        )

    def construction(self) -> dict[str, ConstructionProfile]:
        return {
            "wing": LWPLA_A1_SPEED,
            "winglet": LWPLA_A1_SPEED_WINGLET,
            "hstab": LWPLA_A1_SPEED_TAIL,
            "fin": LWPLA_A1_SPEED_FIN,
        }

    def fixed_equipment(self, dv: dict | None = None) -> list[PointMass]:
        """Same equipment as the endurance plane, restationed for a nose motor."""
        d = self.DV_DEFAULTS | (dv or {})
        x_tail = self._tail_station(d)
        return [
            PointMass("battery", 0.430, d["x_battery"]),
            PointMass("motor_prop", 0.190, 0.020),  # puller: on the firewall
            PointMass("esc_wiring", 0.080, d["x_battery"] + BATT_L / 2 + 0.020),
            PointMass("servos_aileron", 0.024, d["x_wing_le"] + 0.60 * d["c_root"]),
            PointMass("servos_tail", 0.024, x_tail),
            PointMass("fc_gps_rx", 0.060, d["x_battery"] + BATT_L / 2 + 0.045),
            PointMass("hardware_misc", 0.050, d["x_wing_le"]),
        ]

    def structure_extras(self, dv: dict | None = None) -> list[PointMass]:
        """Spar, pod shell, boom and ballast — everything not a printed surface."""
        from planeopt import structures

        d = self.DV_DEFAULTS | (dv or {})
        f = self.fus_dims(d)
        boom_len = self._boom_length(d)
        boom_scale = 0.0 if self.fuselage_topology == "integrated" else 1.0
        return [
            PointMass(
                "wing_spar",
                structures.tube_mass(d["spar_od"], d["spar_wall"], d["span"]) + 0.020,
                d["x_wing_le"] + 0.30 * d["c_root"],
            ),
            # Shell mass scales with the wetted area the optimiser buys — a
            # bigger or longer fuselage has to pay for itself.
            PointMass(
                "fuselage_shell",
                SHELL_KG_M2 * self.parasite_bodies(dv)[0]["wetted_area_m2"] + 0.030,
                f["bay_start"] + 0.45 * f["bay"],
            ),
            PointMass(
                "boom",
                structures.tube_mass(BOOM_OD, BOOM_WALL, boom_len) + 0.012 * boom_scale,
                f["length"] + boom_len / 2,
            ),
            PointMass("ballast", d["ballast_kg"], 0.030),  # nose ballast if needed
        ] + (
            # Root sockets and pins, counted only when a winglet is fitted, so
            # the on/off study compares like with like.
            [PointMass("winglet_joiners", 0.016, d["x_wing_le"] + 0.30 * d["c_root"])]
            if self.winglet
            else []
        )

    def parasite_bodies(self, dv: dict | None = None) -> list[dict]:
        """Pod + boom, through the same flat-plate/Munk contract as the sample."""
        from planeopt import fuselage

        d = self.DV_DEFAULTS | (dv or {})
        f = self.fus_dims(d)
        body = fuselage.body_dict(self.fuselage_lofts(dv)[0], f["length"], f["w"], f["h"])
        # Puller: the slipstream scrubs the whole body (MODEL_DETAILS section 2.4).
        body["form_factor"] = body["form_factor"] * 1.10
        bodies = [body]
        if self.fuselage_topology == "pod_boom":
            bodies.append(fuselage.boom_body(self._boom_length(d), od=BOOM_OD))
        return bodies


AIRCRAFT = SpeedSample()
