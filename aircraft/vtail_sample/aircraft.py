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

from planeopt import geometry
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

# The frozen v1.2 spec wing, for the dv=None validation fixture ONLY: constant
# 700 mm centre section then three 183.3 mm panels at 3 deg, chords 220 -> 150.
# Written out as literals rather than derived from DV_DEFAULTS because it is
# spec data, not a design vector — the architecture around it has been
# reparameterized three times (v2 panel ratios -> v3 dihedral curve -> v4
# superellipse) and this fixture must reproduce the same M1 numbers through all
# of them (MODEL_DETAILS section 9, validation continuity).
SPEC_WING_PANELS = [(0.350, 0.0), (0.550 / 3, 3.0), (0.550 / 3, 3.0), (0.550 / 3, 3.0)]
SPEC_WING_CHORDS = [0.220, 0.220, 196.667 / 1000, 173.333 / 1000, 0.150]
SPEC_WING_TWISTS = [0.0, 0.0, -2.0 / 3, -4.0 / 3, -2.0]


class VTailSample:
    name = "vtail_sample_v1.6"
    wing_airfoil = "sd7037"  # discrete outer-loop candidate (MODEL_DETAILS 6.3)
    span_cap_m = 2.0  # manufacturing cap on PROJECTED (front-view y) span, winglet included
    # (2.2 -> 2.0 by user decision 2026-07-24, sixth session)
    winglet = True  # tip winglet as a separate asb.Wing (parametric designs only)
    tip_dihedral_max_deg = 20.0  # raised to ~88 only by the continuous-cant study (solve.py)
    # Outer-panel cant ceiling for the two-panel dihedral form. 60 deg is a
    # MODEL limit, not a structural one: past it a Schrenk station on a
    # near-vertical panel stops meaning anything the critical-section stall
    # method can use (MODEL_DETAILS 3.4), so the wing would be optimized
    # against a stall model that cannot see it. Raise only with that model.
    outer_cant_max_deg = 60.0
    # Stations per region (fidelity, not design — geometry.station_grid). Kept
    # at 2+2 so the wing still presents four asb sections and the CasADi graph,
    # solve time and ~13 GB peak are unchanged from v3.
    WING_STATIONS_INNER = 2
    WING_STATIONS_OUTER = 2
    # Mass of one spar joiner block at a dihedral break, per side. v2 carried
    # this at every one of its three breaks and v3 deleted it with them; the
    # two-panel form has exactly one, and the study only prices honestly if the
    # kink pays for the joint it needs.
    DIHEDRAL_JOINER_KG = 0.016
    # usable fraction of the section's max thickness for a spar hole (skin +
    # liner clearance) — feeds the straight-spar fit constraint (section 9)
    SPAR_DEPTH_FRACTION = 0.70

    # --- discrete studies (MODEL_DETAILS 6.3): every entry is a candidate the
    # study PRICES via one full re-optimization — never an assumption. Only
    # genuinely discrete choices live here; everything else is continuous. ---
    fuselage_topology = "pod_boom"  # lofted pod + CF boom (spec layout)
    tail_type = "vtail"  # spec layout; conventional/T priced by the study
    # Puller adopted as the permanent default (user decision 2026-07-24,
    # after the M4.8 study: +10.7 min over the pusher — FINDINGS section 10).
    # The spec's pusher stays a candidate the study re-prices every run; the
    # dv=None fixture keeps the spec pusher layout (validation continuity).
    motor_mount = "puller"
    # Declared order = greedy study order: the mount is the biggest CG lever,
    # so it is judged first (at the baseline) and topology/tail re-judge
    # under the adopted mount.
    discrete_options = {
        "motor_mount": ["puller", "pusher"],
        # Prop freed (user decision 2026-07-27): pitch is a real, cheap,
        # buy-it-and-bolt-it-on decision, so it is priced rather than declared.
        # Judged straight after the mount because the mount's installation
        # derate composes into the prop's (see PROP_CANDIDATES).
        #
        # TOO NARROW — WIDEN BEFORE THE NEXT RUN (see HANDOFF section 5). These
        # three were the whole prop library in 2026-07-27; 443 tables ship now.
        # Screened at the 2026-07-29 champion's operating point, the adopted
        # 11x7 ranks 119th of 441, and the leaders are all far coarser (an 11 in
        # 11x13 screens +25 min, so the lever is PITCH, not diameter — this is
        # the cruise-J-above-peak-eta-J diagnostic finally cashing out).
        # The prop need NOT fold (user, 2026-07-29), so the whole catalogue is
        # in scope rather than the one folding family these three came from.
        "prop_choice": ["cam_11x6", "cam_11x55", "cam_11x7"],
        "fuselage_topology": ["pod_boom", "integrated"],
        "tail_type": ["vtail", "conventional", "ttail"],
        # Wing dihedral form (section 9). Discrete because the two are not
        # points of one family: "curve" is smooth and demands a straight spar
        # through it, "polyhedral2" has a kink and therefore a spar joint. That
        # is a build decision with a mass and a part count, so the study prices
        # it rather than assuming it — same posture as tail type and topology.
        "wing_dihedral_form": ["curve", "polyhedral2"],
    }
    wing_dihedral_form = "curve"  # v3 incumbent; polyhedral2 re-priced every run

    # --- motor-mount installation effects (MODEL_DETAILS 2.4) — declared
    # uncalibrated ballparks the study prices, adjustable data not code.
    # Pusher: the prop works in the boom+tail wake (an optimism all runs
    # before 2026-07-24 silently omitted). Puller: clean inflow, but the
    # slipstream scrubs the pod (drag factor on the pod body) and the motor
    # mass rides the nose.
    MOUNT_EFFECTS = {
        "pusher": {"prop_eta_derate": 0.95, "pod_drag_factor": 1.00},
        "puller": {"prop_eta_derate": 1.00, "pod_drag_factor": 1.10},
    }

    # --- prop candidates (MODEL_DETAILS 2.1) — the study's declared shortlist.
    # All three are the same 11 in folding CAM-class blade at different PITCHES,
    # so the study isolates the one thing actually being chosen. Held
    # deliberately to one diameter (so the 190 g motor_prop point mass stays
    # honest and ground clearance does not silently change) and one 0.95 folding
    # knockdown, which composes with the mount's installation derate as before.
    #
    # Every table is now MEASURED APC data (2026-07-28). The 11x6 used to be a
    # synthetic pitch-blend of the 11x5.5E and 11x7E, because APC's thin-electric
    # line has no 11x6 — it jumps 5.5 to 7. Retiring the blend removed the one
    # candidate that was not data, and the real 11x6 turned out to carry 11% more
    # usable advance ratio than the blend predicted. The honest caveat is now a
    # different one: the real 11x6 is APC's THICKER SPORT section, not a thin
    # electric, so this shortlist is no longer a single blade family. Blade
    # section is a confound between the 11x6 and its two neighbours — read a
    # narrow 11x6 win with that in mind.
    PROP_CANDIDATES = {
        "cam_11x55": {"name": "aeronaut_cam_11x5.5_folding",
                      "pitch_in": 5.5, "proxy_table": "apc_11x55e"},
        "cam_11x6": {"name": "aeronaut_cam_11x6_folding",
                     "pitch_in": 6.0, "proxy_table": "apc_11x6"},
        "cam_11x7": {"name": "aeronaut_cam_11x7_folding",
                     "pitch_in": 7.0, "proxy_table": "apc_11x7e"},
    }
    prop_choice = "cam_11x6"  # spec incumbent; the study re-prices it every run
    PROP_DIAMETER_M = 0.2794  # 11 in — common to every candidate
    # Folding blades cost ~5% of shaft power. Applied UNCONDITIONALLY today,
    # which was fair while every candidate was a folder — it is not any more:
    # the user confirmed 2026-07-29 that this prop does NOT have to fold, so a
    # fixed-blade candidate is currently charged ~5% it would never pay. Make
    # this a priced discrete option (see speed_sample's BLADE_DERATE) in the
    # same pass that widens PROP_CANDIDATES; the two interact.
    PROP_FOLDING_DERATE = 0.95

    # Straight trailing edge on the tail (user preference, 2026-07-29). Applies
    # to whichever tail type is built, since they share t_sweep. See the
    # constraint in constraints() for why it is close to free.
    straight_tail_te = True

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

    # Architecture v4 (user decision 2026-07-26). Two independent changes that
    # pull in opposite directions, each for its own reason:
    #
    # PLANFORM goes smooth. The three independent chord ratios (v2/v3's r1-r3)
    # and the equal-width panels they sat on are retired: they were an arbitrary
    # discretization masquerading as design freedom, and the widths were never
    # optimizable at all. Chord is now one two-parameter superellipse family
    # (MODEL_DETAILS section 9.1) — with a rectangular wing and a straight taper
    # as EXACT members, not approximations — and the leading-edge convention is
    # a third variable spanning straight-LE through straight-quarter-chord to
    # straight-TE, so the optimizer chooses it rather than inheriting it.
    #
    # DIHEDRAL may go piecewise. The v3 curve delta(eta) = dihedral_tip*eta^d_exp
    # is retained as the incumbent, but a two-panel form (one break, free break
    # station, hard-cantable outer panel) is now a priced candidate beside it:
    # the curve family cannot express a flat inner wing with a steeply canted
    # tip, which at a binding projected-span cap is a blended winglet rather
    # than a dihedral distribution. See wing_dihedral_form below.
    DV_DEFAULTS = {
        # wing planform — superellipse chord curve (section 9.1)
        "span": 1.8, "c_root": 0.22,
        "taper": 150 / 220,  # tip/root ratio; 1.0 = rectangular
        "fullness": 1.0,  # 1 = straight taper, 2 = ellipse, >2 = fuller tip
        "le_shear": 0.0,  # 0 = straight LE, 0.25 = straight c/4, 1 = straight TE
        "dihedral_tip": 3.0, "d_exp": 0.5,  # dihedral CURVE form (section 9.2)
        # Wing joint station. 0.3889 = the spec's 700 mm carry-through over the
        # 1.8 m span — i.e. exactly what v3 expressed as center_width = 0.700.
        # Keeping the default here is what holds the spar mass (and so AUW, and
        # so every M1 number) continuous across the v3 -> v4 reparameterization;
        # a rounder-looking default silently moved it by 6 g.
        "eta_break": 0.700 / 1.8,
        # dihedral POLYHEDRAL2 form (section 9.3): the two panel angles
        "dihedral_inner": 3.0, "dihedral_outer": 3.0,
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

    def _wing(self, d: dict) -> dict:
        """The whole semi-span wing as one dict, shared by geometry, constraints
        and the mass model so they cannot drift apart (the v3 rule, widened).

        Keys: `etas` (arc-fraction stations, root 0 -> tip 1), `chords`, `le_x`
        (streamwise LE offset), `widths` and `dihedrals` per panel, plus the
        running `ys`/`zs` placement, `areas`, and the arc/projected centroid of
        each panel. Symbolic-safe throughout: the only branching is on
        self.wing_dihedral_form, a plain string.

        Panels are placed by ARC length — `span` is material span and the
        front-view width falls out of each panel's cos(dihedral) — which is what
        makes the projected-span cap exact at high cant (section 9.3).
        """
        semi = d["span"] / 2
        curve = self.wing_dihedral_form == "curve"
        # The joint station exists in both forms (spar break, panel break); only
        # the two-panel form additionally changes dihedral across it.
        eta_break = d["eta_break"]
        etas = geometry.station_grid(
            eta_break, self.WING_STATIONS_INNER, self.WING_STATIONS_OUTER
        )
        chords = geometry.superellipse_chords(etas, d["c_root"], d["taper"], d["fullness"])
        le_x = geometry.le_offsets(chords, d["le_shear"])

        widths = [(etas[k + 1] - etas[k]) * semi for k in range(len(etas) - 1)]
        if curve:
            # sample delta(eta) = dihedral_tip * eta^d_exp at each panel midpoint
            # (midpoint rule for the arc integral). eta_mid > 0 always.
            dihedrals = [
                d["dihedral_tip"] * ((etas[k] + etas[k + 1]) / 2) ** d["d_exp"]
                for k in range(len(widths))
            ]
        else:
            # piecewise constant, exactly two values. The grid puts a station ON
            # the break, so which panels are inboard is an INDEX question — no
            # comparison against a design-variable value anywhere.
            n_in = self.WING_STATIONS_INNER
            dihedrals = [d["dihedral_inner"]] * n_in + [d["dihedral_outer"]] * (
                len(widths) - n_in
            )

        ys, zs = [0.0], [0.0]
        for w, ang in zip(widths, dihedrals):
            ys.append(ys[-1] + w * np.cosd(ang))
            zs.append(zs[-1] + w * np.sind(ang))
        areas = geometry.panel_areas(widths, chords)
        # Roll-moment arm for the lateral floor is the PROJECTED y of the panel
        # centroid, not its arc distance: a canted panel's restoring moment acts
        # on its front-view arm. v3 used arc distance, which barely differed at
        # 4 deg but would hand a 60 deg outer panel a 2x arm it does not have.
        y_centroids = [(ys[k] + ys[k + 1]) / 2 for k in range(len(widths))]
        return {
            "etas": etas, "chords": chords, "le_x": le_x, "widths": widths,
            "dihedrals": dihedrals, "ys": ys, "zs": zs, "areas": areas,
            "y_centroids": y_centroids, "semi": semi, "eta_break": eta_break,
        }

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
            # superellipse chord curve (section 9.1). taper = 1.0 is a
            # rectangular wing and fullness = 1.0 a straight taper, so both stay
            # exactly reachable rather than merely approachable; the upper
            # fullness bound of 4 is well past an ellipse (2) and into
            # held-chord planforms.
            "taper": (0.35, 1.0), "fullness": (1.0, 4.0),
            # LE convention as a continuous variable: 0 straight LE, 0.25
            # straight quarter-chord, 1 straight TE (section 9.1).
            "le_shear": (0.0, 1.0),
            # Where the wing is JOINTED: end of the carry-through spar, start of
            # the outer spar, and the one station a panel break may sit at. It
            # exists in both dihedral forms — a built wing is jointed somewhere
            # regardless — and inherits the freedom v3 carried as center_width.
            # The forms differ in exactly one thing: whether the dihedral is
            # allowed to CHANGE here (section 9.3).
            "eta_break": (0.25, 0.85),
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
        # Dihedral form decides which angles exist at all — the same pattern as
        # tail_type below. Declaring the unused ones anyway would leave the NLP
        # with variables no constraint touches.
        if self.wing_dihedral_form == "curve":
            # tip-angle cap matches the old per-panel cap; the exponent spans
            # simple dihedral (0) to a strongly tip-loaded curve
            bounds |= {
                "dihedral_tip": (0.0, self.tip_dihedral_max_deg), "d_exp": (0.0, 2.0),
            }
        else:
            # Two panels, breaking at the joint the wing already has. The inner
            # panel keeps the ordinary dihedral cap; only the outer one may cant
            # hard, which is the whole point of the form.
            bounds |= {
                "dihedral_inner": (0.0, self.tip_dihedral_max_deg),
                "dihedral_outer": (0.0, self.outer_cant_max_deg),
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
        w = self._wing(dv)
        c_tip = w["chords"][-1]
        # tip Reynolds floor (project rule; MODEL_DETAILS section 4)
        opti.subject_to(1.225 * V * c_tip / 1.81e-5 >= 90e3)
        # A1 print bed: chord already bounded by c_root upper bound (245 mm).
        # (v3's "outer panels must exist" constraint is gone with center_width —
        # the break station's own bounds guarantee both regions are non-empty.)
        # manufacturing span cap on PROJECTED span: the dv "span" is material
        # (arc) span; front-view width comes from each panel's cos(dihedral),
        # plus the winglet's y-projection when present
        proj_semi = w["ys"][-1]
        proj_span = 2 * proj_semi
        if self.winglet:
            proj_span = proj_span + 2 * dv["wl_len"] * np.cosd(dv["wl_cant"])
            # winglet mean-chord Reynolds floor: relaxed vs the 90k tip rule
            # (small vertical surface, tolerates more drag creep than the wing)
            c_wl_mean = c_tip * dv["wl_cr"] * (1 + dv["wl_taper"]) / 2
            opti.subject_to(1.225 * V * c_wl_mean / 1.81e-5 >= 60e3)
            # winglet stays shorter than the last wing panel (buildable socket)
            opti.subject_to(dv["wl_len"] <= w["widths"][-1])
        opti.subject_to(proj_span <= self.span_cap_m)
        # lateral-stability proxy: roll-moment-weighted dihedral floor. Dihedral's
        # restoring moment scales with panel area x spanwise arm, so the weight is
        # A_i * y_centroid_i — without the arm the optimizer games the metric by
        # piling dihedral inboard where it buys no roll stiffness. (The optimizer
        # cannot see dihedral's benefit at all — LL has no lateral DOF — so this
        # floor is the only thing keeping the wing from going flat.)
        panels = list(zip(w["areas"], w["y_centroids"], w["dihedrals"]))
        w_sum = sum(a * y for a, y, _ in panels)
        # credit per panel is sin*cos, not the raw angle: the restoring moment
        # needs both a sideflow AoA (sin) and a vertical force component (cos),
        # so credit ~ d at small angles and -> 0 as a panel goes vertical — a
        # near-vertical panel (continuous-cant study) cannot game the floor.
        # The winglet is excluded entirely (conservative).
        credit = lambda d: (180 / np.pi) * np.sind(d) * np.cosd(d)
        eff_dihedral = sum(a * y * credit(d) for a, y, d in panels) / w_sum
        opti.subject_to(eff_dihedral >= self.min_effective_dihedral_deg)

        # --- spar fit: the tube must fit inside the section it runs through ---
        # Build standard (unchanged): both tube spars are STRAIGHT, so spar
        # holes are drillable in a straight line. What differs between the two
        # dihedral forms is whether the wing bends AROUND that straight spar.
        # A design that cannot pass a sufficiently sized spar is unbuildable, so
        # this is a hard geometry constraint, not a priced penalty.
        eta_b = w["eta_break"]
        tc = asb.Airfoil(self.wing_airfoil).max_thickness()  # numeric (discrete outer loop)
        depth = lambda c: self.SPAR_DEPTH_FRACTION * tc * c
        # chord at a station, from the same curve the geometry uses
        c_at = lambda e: geometry.superellipse_chords(
            [0.0, e, 1.0], dv["c_root"], dv["taper"], dv["fullness"]
        )[1]
        c_root_dv = w["chords"][0]

        if self.wing_dihedral_form == "curve":
            # The curve sags away from every straight line drawn through it, so
            # each spar run has to carry that sag plus its own diameter. At
            # d_exp = 0 the sag is identically zero: simple dihedral always fits.
            def sag(eta_a, eta_bb, eta_x):
                # vertical deviation of the (convex) analytic curve below the
                # straight chord between the spar's ends, at station eta_x.
                # eta arguments must stay > 0: CasADi's symbolic-exponent power
                # is exp(q ln eta), whose q-derivative is NaN at eta = 0.
                za, zb = self._wing_curve_z(dv, eta_a), self._wing_curve_z(dv, eta_bb)
                chord_z = za + (zb - za) * (eta_x - eta_a) / (eta_bb - eta_a)
                return chord_z - self._wing_curve_z(dv, eta_x)

            sag_center = self._wing_curve_z(dv, eta_b) / 2 - self._wing_curve_z(dv, eta_b / 2)
            opti.subject_to(sag_center + dv["spar_od_center"] <= depth(c_root_dv))
            eta_o = eta_b + 0.85 * (1 - eta_b)  # outer spar end (structures run)
            for frac in (0.35, 0.7):  # sag deepest inboard, chord thinnest outboard
                eta_x = eta_b + frac * (eta_o - eta_b)
                opti.subject_to(sag(eta_b, eta_o, eta_x) + dv["spar_od_outer"] <= depth(c_at(eta_x)))
        else:
            # Two straight panels: each spar runs inside a PLANAR panel, so the
            # sag against its own run is identically zero and the kink is carried
            # by a joiner block instead (DIHEDRAL_JOINER_KG, charged in
            # structure_extras). What remains is the ordinary fit check — the
            # tube must clear the section depth at the thinnest station of its
            # run, which is that run's outboard end.
            opti.subject_to(dv["spar_od_center"] <= depth(c_at(eta_b)))
            eta_o = eta_b + 0.85 * (1 - eta_b)
            opti.subject_to(dv["spar_od_outer"] <= depth(c_at(eta_o)))

        # --- tail (MODEL_DETAILS section 8) ---
        t_c_mean = dv["t_c_root"] * (1 + dv["t_taper"]) / 2
        if self.straight_tail_te:
            # Build convention (user decision 2026-07-29), pinned as a SHAPE not
            # a number so it survives whatever taper and span the optimizer picks:
            # sweep the leading edge back by exactly the chord the taper removes,
            # and the trailing edge comes out vertical.
            #
            # Free: sweep is defined at the LE, so with t_sweep = 0 the taper
            # rakes the TE forward — and the optimizer parks there because sweep
            # is a flat direction (the AC placement in _tail_wings cancels the
            # moment arm it would otherwise buy). Costs a degree of freedom that
            # was not buying anything, and the root moves slightly forward, which
            # shortens the boom a little.
            #
            # Worth more than looks: the hinge is a constant CHORD FRACTION, so a
            # vertical TE also makes the hinge line square to the root — the
            # control surface becomes a plain trapezoid to cut, seal and set.
            semi_t = dv["t_span"] / 2
            opti.subject_to(
                semi_t * np.tand(dv["t_sweep"]) == dv["t_c_root"] * (1 - dv["t_taper"])
            )
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
        w = self._wing(dv)
        semi = w["semi"]
        inner = w["eta_break"] * semi  # carry-through / inner spar run
        m_center = structures.semispan_root_moment(weight_n, n_lim, semi)
        structures.spar_constraints(
            opti, dv["spar_od_center"], dv["spar_wall_center"], inner, m_center
        )
        # outer segment: lift outboard of the joint (area fraction), centroid arm
        # 0.424 x outer length. Areas come from the panel list, so the split
        # follows the break station instead of assuming equal thirds.
        outer = semi - inner
        n_in = self.WING_STATIONS_INNER
        s_half = sum(w["areas"])
        f_outer = sum(w["areas"][n_in:]) / s_half
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
        # Parametric designs ride the v4 wing (superellipse chord curve, chosen
        # LE convention, curve or two-panel dihedral — section 9). The dv=None
        # fixture keeps the frozen v1.2 spec wing forever.
        if parametric:
            w = self._wing(dv)
            chords, le_x, ys, zs = w["chords"], w["le_x"], w["ys"], w["zs"]
            # washout linear in arc fraction, zero at the root
            twists = [dv["washout_tip"] * eta for eta in w["etas"]]
        else:
            chords, twists = SPEC_WING_CHORDS, SPEC_WING_TWISTS
            le_x = [0.0] * len(chords)  # spec wing: straight LE
            ys, zs = [0.0], [0.0]
            for width, ang in SPEC_WING_PANELS:
                ys.append(ys[-1] + width * np.cosd(ang))
                zs.append(zs[-1] + width * np.sind(ang))

        wing = asb.Wing(
            name="wing",
            symmetric=True,
            xsecs=[
                asb.WingXSec(
                    xyz_le=[le_x[k], ys[k], zs[k]], chord=chords[k],
                    twist=twists[k], airfoil=wing_af,
                )
                for k in range(len(chords))
            ],
        ).translate([WING_X_LE, 0, 0])

        # winglet: separate Wing rooted at the tip (parametric designs only —
        # the v1.2 spec fixture has none). Separate so the Schrenk stall
        # stations, dihedral proxy, and Wing.span() of the main wing stay clean;
        # LiftingLine picks up the nonplanar induced benefit either way
        # (verified against VLM, MODEL_DETAILS 3.6).
        winglet = None
        if self.winglet and parametric:
            c_tip = chords[-1]
            wl_cr = c_tip * dv["wl_cr"]
            wl_ct = wl_cr * dv["wl_taper"]
            # root TE flush with the wing-tip TE (which the LE shear has moved),
            # tip raked back 25% of length
            x0 = WING_X_LE + le_x[-1] + c_tip - wl_cr
            dy = dv["wl_len"] * np.cosd(dv["wl_cant"])
            dz = dv["wl_len"] * np.sind(dv["wl_cant"])
            winglet = asb.Wing(
                name="winglet",
                symmetric=True,
                xsecs=[
                    asb.WingXSec(
                        xyz_le=[x0, ys[-1], zs[-1]], chord=wl_cr,
                        twist=dv["wl_toe"], airfoil=wing_af,
                    ),
                    asb.WingXSec(
                        xyz_le=[x0 + 0.25 * dv["wl_len"], ys[-1] + dy, zs[-1] + dz],
                        chord=wl_ct, twist=dv["wl_toe"], airfoil=wing_af,
                    ),
                ],
            )

        c_mean = wing.area() / wing.span()
        if parametric:
            # Tail placed off the wing's TRUE quarter-chord AC, computed from the
            # panels themselves. With a straight LE the old 0.25*c_mean proxy was
            # close; once le_shear can sweep the planform the AC moves aft with
            # it, and a tail hung off the root LE would collect moment arm the
            # boom never pays for (section 9.1).
            _, x_ac_local = geometry.mac_and_ac(w["widths"], chords, le_x)
            tails = self._tail_wings(dv, WING_X_LE + x_ac_local)
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
            b_ref=2 * ys[-1],
        )

    def _tail_wings(self, d: dict, x_ac_wing) -> list:
        """Tail surfaces for the current tail_type (MODEL_DETAILS section 8).

        Per-dimension variables (tail_scale retired). The pitch surface's AC is
        placed exactly tail_arm behind the WING's AC (`x_ac_wing`, an absolute
        station) including the tail's own sweep offset — so neither surface can
        buy moment arm the boom-length accounting does not pay for. Symbolic-safe:
        branches only on self.tail_type (a plain string), never on dv values."""
        naca0009 = asb.Airfoil("naca0009")
        ac_x = x_ac_wing + d["tail_arm"]
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
        # motor rides the declared mount: boom tip aft of the tail (pusher) or
        # inside the pod nose (puller) — the biggest CG lever the study moves.
        # The dv=None fixture stays the frozen spec pusher regardless of the
        # parametric default (M1 validation continuity).
        mount = self.motor_mount if dv is not None else "pusher"
        x_motor = x_tail + 0.08 if mount == "pusher" else p["nose_tip"] + 0.02
        return [
            PointMass("battery", 0.430, d["x_battery"]),  # inside the lofted bay
            PointMass("motor_prop", 0.190, x_motor),
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
        w = self._wing(d)
        inner = w["eta_break"] * w["semi"]  # carry-through half-length
        outer = w["semi"] - inner
        spar_mass = (
            structures.tube_mass(d["spar_od_center"], d["spar_wall_center"], 2 * inner)
            + 2 * structures.tube_mass(d["spar_od_outer"], d["spar_wall_outer"], 0.85 * outer)
            + 0.035  # root V-joint + center-outer joiner blocks + pins
        )
        if self.wing_dihedral_form != "curve":
            # One spar joint per side, where the two panels meet at an angle.
            # This is the price of the kink: the v3 curve bought its smoothness
            # by having no interior dihedral break, and the two-panel form only
            # earns its place in the study if it carries the joint it needs.
            spar_mass = spar_mass + 2 * self.DIHEDRAL_JOINER_KG
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
        pod = fuselage.body_dict(self.fuselage_lofts(dv)[0], p["length"], p["w"], p["h"])
        # puller slipstream scrubs the pod: declared drag factor (MODEL_DETAILS 2.4)
        pod["form_factor"] = pod["form_factor"] * self.MOUNT_EFFECTS[self.motor_mount]["pod_drag_factor"]
        bodies = [pod]
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
        prop = self.PROP_CANDIDATES[self.prop_choice]
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
                name=prop["name"],
                # per candidate now: the folding tables span 9-16 in, so diameter
                # is no longer one constant. Falls back to the class value.
                diameter_m=prop.get("diameter_in", self.PROP_DIAMETER_M / 0.0254) * 0.0254,
                pitch_m=prop["pitch_in"] * 0.0254,
                proxy_table=prop["proxy_table"],
                # blade knockdown x declared mount installation derate
                # (pusher-in-wake, MODEL_DETAILS 2.4) — composed multiplicatively.
                # A candidate backed by MEASURED folding data declares 1.00: the
                # folding penalty is already in the measurement, and applying the
                # proxy derate on top would charge it twice.
                folding_derate=(
                    prop.get("blade_derate", self.PROP_FOLDING_DERATE)
                    * self.MOUNT_EFFECTS[self.motor_mount]["prop_eta_derate"]
                ),
            ),
            battery=BatteryConfig(capacity_ah=4.0, v_nominal=14.8, usable_fraction=0.80),
            esc_efficiency=0.95,
            esc_continuous_current_a=40,
            avionics_power_w=3.0,
        )

    def manufacturing(self, dv: dict | None = None, auw_kg: float | None = None) -> dict:
        """Framework hook (report/manufacturing): architecture-specific build data.

        Sections map to either {label: value} rows or a list of uniform dicts
        (rendered as a table AND written as its own CSV). Everything here mirrors
        the models that actually sized the parts — `structure_constraints` for the
        spars, the mass model for the boom — so the cut list cannot disagree with
        what was optimized.
        """
        from planeopt import structures

        d = self.DV_DEFAULTS | (dv or {})
        w = self._wing(d)
        semi = w["semi"]
        inner = w["eta_break"] * semi  # carry-through run, per side
        outer = semi - inner
        weight_n = (auw_kg if auw_kg else 1.8) * 9.81
        n_lim = 5.0

        # identical decomposition to structure_constraints(), so the reported
        # margins are the ones the optimizer actually held
        m_center = structures.semispan_root_moment(weight_n, n_lim, semi)
        f_outer = sum(w["areas"][self.WING_STATIONS_INNER:]) / sum(w["areas"])
        m_outer = n_lim * (weight_n / 2) * f_outer * 0.424 * outer

        centre = structures.spar_report(
            d["spar_od_center"], d["spar_wall_center"], inner, m_center
        )
        # the constraint sizes ONE cantilever half; the part is a single tube
        # through the centre, so the stock length is both halves
        centre_stock = round(2 * inner * 1000, 1)
        tip = structures.spar_report(
            d["spar_od_outer"], d["spar_wall_outer"], 0.85 * outer, m_outer
        )

        spars = [
            dict(part="centre carry-through", qty=1, **centre, stock_length_mm=centre_stock),
            dict(part="outer panel", qty=2, **tip, stock_length_mm=tip["length_mm"]),
        ]

        x_spar = WING_X_LE + 0.30 * d["c_root"]
        p = self.pod_dims(d)
        x_tail = WING_X_LE + 0.25 * 0.201 + d["tail_arm"]
        pod_end = p["bay_end"] + p["tail_len"]
        boom_len = (x_tail - pod_end) + 0.05  # + sockets, as the mass model has it

        stock = [
            {"item": "CF tube, centre spar", "spec":
             f"{centre['od_mm']:.1f} x {centre['wall_mm']:.2f} mm wall",
             "length_mm": centre_stock, "qty": 1},
            {"item": "CF tube, outer spar", "spec":
             f"{tip['od_mm']:.1f} x {tip['wall_mm']:.2f} mm wall",
             "length_mm": tip["length_mm"], "qty": 2},
        ]
        if self.fuselage_topology == "pod_boom":
            stock.append({"item": "CF boom tube", "spec": "12 x 10 mm (1 mm wall)",
                          "length_mm": round(boom_len * 1000, 1), "qty": 1})
        if self.wing_dihedral_form == "polyhedral2":
            stock.append({"item": "spar joiner block, at the dihedral break",
                          "spec": f"{self.DIHEDRAL_JOINER_KG * 1000:.0f} g each",
                          "length_mm": "", "qty": 2})

        mm = lambda v: f"{v * 1000:.0f} mm"
        throw_deg = float(self.trim_deflection_limit_deg(dv))
        c_cs = d["cs_frac"] * d["t_c_root"] * (1 + d["t_taper"]) / 2
        return {
            "Spars (sized at 5 g limit load)": spars,
            "Stock list": stock,
            "Spar and joint stations": {
                "reading the spar margins": (
                    f"0% means the constraint is ACTIVE — the optimizer sized the tube "
                    f"exactly to its limit, which is the expected outcome, not a warning. "
                    f"The {structures.SAFETY_FACTOR:.0f}x safety factor is already inside "
                    f"the {structures.SIGMA_ALLOW / 1e6:.0f} MPa allowable, so the quoted "
                    f"allowable is {structures.SIGMA_ALLOW / structures.SAFETY_FACTOR / 1e6:.0f} MPa."
                ),
                "load case": f"{n_lim:.0f} g limit, elliptical lift, no inertia relief",
                "spar line, aft of nose datum": mm(x_spar),
                "as a fraction of root chord": "30%",
                "wing joint (centre spar ends, outer begins)":
                    f"{mm(inner)} from centreline (eta = {float(w['eta_break']):.3f})",
                "semi-span": mm(semi),
                "dihedral form": self.wing_dihedral_form,
                "spar hole must clear": f"{self.SPAR_DEPTH_FRACTION:.0%} of section thickness",
            },
            "Control throws": {
                "pitch surface": self.pitch_control_name,
                "control chord (mean)": mm(c_cs),
                "available TE throw (linkage)": f"+/- {mm(self.TAIL_THROW_TE_M)}",
                "trim may use": f"{self.TRIM_THROW_FRACTION:.0%} of it "
                                f"(= +/- {throw_deg:.1f} deg)",
                "as-trimmed deflection": "see report.html / run.json",
            },
        }

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
