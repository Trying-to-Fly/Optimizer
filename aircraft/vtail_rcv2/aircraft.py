"""`vtail_sample` carrying the RC v2 electronics bill of materials, per part.

SOURCE: `Planes/RC/RC v2/ELECTRONICS_SPEC.xlsx`, v1.2 (2026-08-05) — sheets BOM,
FC Ports + Wiring, Power Budget, Weight + Placement. Every mass, dimension and
placement requirement below is transcribed from it; nothing here is invented.

WHAT IS DIFFERENT FROM THE SAMPLE

The sample aeroplane carries its avionics as seven lumped point masses at
literal stations read off a frozen 585 mm pod — `esc_wiring` at 0.3932 of the
pod length, `fc_gps_rx` at 0.5128, `hardware_misc` at a flat 0.450 m. Those were
right once and have been describing a fuselage that no longer exists since the
loft became parametric, and no run artifact ever reported a station for any of
them. This package replaces them with **19 airborne parts and 4 ground items**,
each with its own mass, installed envelope, packing lane and requirement, and
each getting a station the optimizer chooses (`planeopt.equipment`).

THREE THINGS THE TRANSCRIPTION TURNED UP

1. **The BOM's stated max-weight cap is 55 g light.** The sheet's totals row
   says "≈ 895 cap"; its own Max-wt column sums to **950 g**. This package is
   solved on the max basis (user decision, 2026-08-05), so it is the 950 g
   aeroplane — 127 g heavier in equipment than the sample's 858 g lump, which
   will cost endurance. `equipment.totals` derives the number rather than
   transcribing it, so the sheet cannot drift from the model again.

2. **The BOM was written for a PUSHER; this aeroplane is a PULLER.** Every
   placement note assumes the tail-pusher layout of DESIGN_SPEC.md — motor at
   the boom tip, nose bay free for the companion computer, "pusher prop = every-
   thing forward is clean" for the pitot. The optimizer priced the pusher twice
   and it lost by 9.5-10.7 min at the same static-margin floor, so the mount has
   been `puller` since 2026-07-24 (FINDINGS section 10/15) and the nose is full
   of motor. Nothing is assumed away: the nose bay is modelled and used when the
   mount IS a pusher, and under a puller the Pi and its BEC take **the fallback
   the BOM itself names** ("fallback: beside FC tray"). The pitot moves to the
   outer wing LE, which the BOM lists first anyway.

3. **The spec's 68 mm pod section is within a millimetre of not holding its own
   electronics.** ESC (8 mm on the left wall) + the widest shelf item (36 mm FC)
   + SiK air unit (10.7 mm on the right wall) + 6 mm of build play is 60.7 mm
   against an interior width of 61.0 mm at the spec section. That is now a
   constraint row rather than a coincidence, and it is the first thing in this
   project that ties a parts list to `pod_wh`.

WHAT IS INHERITED, AND WHY THIS IS A SUBCLASS

Everything else: wing, tail, loft, spars, powertrain, studies, caps. A subclass
rather than a copy so any difference between this package's answer and the
sample's is attributable to the equipment model alone — the same discipline
`aircraft/vtail_span300/` used for the span cap.

WHAT THIS MODEL STILL DOES NOT CHECK

Most of the BOM's placement column is not a function of a station: antenna tips
90 degrees apart, the compass sitting under RF-transparent skin with no carbon
above it, the FC's arrow pointing forward, the USB port reachable through the
hatch, the ESC sitting in the nose-inlet-to-tail-exit cooling stream. Those ride
along on every item as `unenforced` text and are printed verbatim beside the
placement on the build sheet. A requirement this model cannot see stays the
builder's, and says so.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import aerosandbox.numpy as np

from planeopt import equipment, geometry
from planeopt.equipment import Item, Lane, SectionStack, Separation

_BASE = Path(__file__).resolve().parent.parent / "vtail_sample" / "aircraft.py"

# Loaded by path under a DISTINCT module name — see aircraft/vtail_span300 for
# why: `cli._load_attr` registers what it loads as `sys.modules["aircraft"]`,
# so importing the sibling under its own stem would collide.
_spec = importlib.util.spec_from_file_location("vtail_sample_base", _BASE)
_base = importlib.util.module_from_spec(_spec)
sys.modules["vtail_sample_base"] = _base
sys.path.insert(0, str(_BASE.parent))  # it imports its own construction profile
try:
    _spec.loader.exec_module(_base)
finally:
    sys.path.remove(str(_BASE.parent))

WING_X_LE = _base.WING_X_LE


class VTailRCv2(_base.VTailSample):
    #: DERIVED from the base name (the span300 rule): a package that shares the
    #: sample's feasible set everywhere except the equipment model must not be
    #: able to drift into claiming a version it no longer matches.
    name = _base.VTailSample.name + "_rcv2"

    #: Which mass column the NLP designs against (user decision, 2026-08-05).
    #: "max" is the aeroplane you are still allowed to build after swapping
    #: every part for the heaviest substitute its own spec permits — 950 g of
    #: airborne electronics against the example parts' 825 g. Conservative by
    #: construction: every endurance number this package reports is the number
    #: for the WORST legal build, and `equipment_closure` in the artifact shows
    #: what the example-part build would weigh and balance at instead.
    equipment_mass_basis = "max"

    #: "full" is the autopilot-development build the BOM describes. "core" drops
    #: the parts the sheet marks Optional or Recommended — companion Pi, its
    #: dedicated BEC and card, the airspeed sensor, the SiK telemetry radio —
    #: which is 51 g est / 77 g max, most of it forward.
    equipment_fit = "full"
    OPTIONAL_ITEMS = frozenset({
        "companion_pi", "bec_pi", "sd_card_pi",
        "airspeed_board", "pitot_probe", "telemetry_sik",
    })

    #: PRICED, NEVER ADOPTED (solve.optimize). Dropping the optional kit is
    #: strictly lighter, so a study that adopted its winner would delete the
    #: companion computer this aeroplane exists to carry and call it an
    #: improvement. The model can see the grams and cannot see the capability,
    #: which is exactly the posture `span_cap_m` takes toward the print bed: the
    #: run measures the price and the user makes the call.
    priced_options = {"equipment_fit": ["core"]}

    #: Build allowances, declared. `LANE_PLAY` is the lateral clearance between
    #: the three things that share the aft-bay section (two walls and the
    #: shelf); `SHELF_PLATE` is the printed shelf and top deck themselves.
    LANE_PLAY = 0.006
    SHELF_PLATE = 0.004
    #: Wiring is one BOM row (30 g est / 40 g max, "distributed") and two
    #: genuinely different places: the harness inside the pod, and the ~700 mm
    #: run down the boom carrying motor phase wires one side and twisted servo
    #: leads the other. Splitting it 60/40 is a DECLARED estimate, and it
    #: matters because the boom half is aft mass on an aeroplane whose whole
    #: balance problem is aft mass.
    WIRING_POD_KG = (0.018, 0.024)
    WIRING_BOOM_KG = (0.012, 0.016)

    #: Aileron servo station as a chord fraction at its semi-span station: an
    #: MG90S with a direct linkage sits just ahead of the hinge, and the hinge is
    #: at the aileron LE. Declared, like every other install convention here.
    AILERON_SERVO_ETA = 0.65
    AILERON_SERVO_CHORD_FRAC = 0.60
    #: Pitot: outer wing LE at 2/3 semi-span, protruding at least 40 mm ahead of
    #: the surface so the probe is out of the wing's own upwash.
    PITOT_ETA = 2 / 3
    PITOT_PROTRUSION_M = 0.040

    # ------------------------------------------------------------------
    # the manifest
    # ------------------------------------------------------------------

    def manifest(self) -> list[Item]:
        """The BOM as `equipment.Item`s, with this build's `fitted` flags.

        Built per call rather than declared as a class constant because two
        masses are outcomes rather than data: the propeller's comes from the
        prop study's current choice, and `fitted` comes from `equipment_fit`.

        `size_m` is the INSTALLED orientation (length along x, then width across
        the fuselage, then height), not the datasheet's L x W x H. A 60 x 25 x 8
        ESC bolted to a sidewall presents 8 mm across the fuselage and 25 mm up
        it, and the packing arithmetic is about the installed part.
        """
        fit = self.equipment_fit
        on = lambda name: fit != "core" or name not in self.OPTIONAL_ITEMS  # noqa: E731
        # Pi + BEC want the nose bay; under a puller the motor is already there,
        # so they take the fallback the BOM names. A branch on a plain string
        # attribute, not on a design-variable value (symbolic-safety rule).
        pi_lane = "nose_bay" if self.motor_mount == "pusher" else "bay_shelf"

        items = [
            # --- Propulsion ---
            Item(
                name="motor", group="Propulsion",
                mass_kg=0.160, mass_max_kg=0.170,
                example_part="D3548 900 kV brushless outrunner",
                purpose="Tail pusher in the source spec; puller on this airframe.",
                requirement=(
                    "Bolts to the motor plate; prop plane 50-65 mm behind the "
                    "ruddervator TE (pusher). HARD limit — the farthest-aft mass "
                    "on the aircraft."
                ),
                unenforced=(
                    "0 deg thrust line with +-2 deg shim provision",
                    "mount must match the 19/25 mm M3 cross on the tail-block plate, "
                    "or use a <=10 g adapter",
                    "open-sided venting around the can",
                    "UNDER A PULLER this row's pusher geometry does not apply — the "
                    "can sits inside the nose, sized by the motor-fit constraint",
                ),
            ),
            Item(
                name="propeller", group="Propulsion",
                mass_kg=self.prop_assembly_mass_kg(),
                mass_max_kg=self.prop_assembly_mass_kg(),
                purpose=(
                    "Not a BOM row — the sheet folds it into 'Motor + folding "
                    "prop 190 g' on the Weight sheet. Carried separately because "
                    "its mass is the prop study's outcome, not a constant."
                ),
                requirement="On the shaft, at the spinner.",
            ),
            Item(
                name="esc", group="Propulsion",
                mass_kg=0.055, mass_max_kg=0.075,
                size_m=(0.060, 0.008, 0.025), lane="bay_left",
                example_part="Hobbywing Skywalker 60A V2 (or AM32 equivalent, no BEC)",
                purpose="36 g bare, ~55 g with wires.",
                requirement=(
                    "Left sidewall, aft of the battery. May overlap the FC-tray "
                    "zone lengthwise — different wall."
                ),
                unenforced=(
                    "must sit in the nose-inlet -> tail-exit cooling stream",
                    "battery leads <=100 mm; phase wires exit rear into the LEFT "
                    "boom channel, twisted + heat-shrunk every ~100 mm",
                ),
            ),
            Item(
                name="battery", group="Propulsion",
                mass_kg=0.430, mass_max_kg=0.460,
                size_m=(0.138, 0.044, 0.032), lane="bay_floor",
                example_part="4S 4,000 mAh 30C LiPo",
                purpose="Endurance pack; the primary CG adjustment.",
                requirement=(
                    "Battery bay, hard against the F1 crash bulkhead via printed "
                    "spacer blocks. Its station IS the balance variable."
                ),
                unenforced=(
                    "2 velcro straps through floor slots + 3 mm foam",
                    "must be rigidly retained — belly lander; a loose pack through "
                    "F1 is the crash mode",
                ),
            ),
            # --- Actuation: four MG90S, and they do NOT go in one place ---
            Item(
                name="servo_aileron_left", group="Actuation",
                mass_kg=0.0135, mass_max_kg=0.014,
                size_m=(0.0228, 0.0122, 0.0285),
                example_part="MG90S metal gear (9 g class)",
                requirement="Wing, 65% semi-span, direct linkage.",
                unenforced=("body must fit the printed 23.2 x 12.4 mm pocket, lugs outboard",),
            ),
            Item(
                name="servo_aileron_right", group="Actuation",
                mass_kg=0.0135, mass_max_kg=0.014,
                size_m=(0.0228, 0.0122, 0.0285),
                example_part="MG90S metal gear (9 g class)",
                requirement="Wing, 65% semi-span, direct linkage.",
                unenforced=("body must fit the printed 23.2 x 12.4 mm pocket, lugs outboard",),
            ),
            Item(
                name="servo_ruddervator_left", group="Actuation",
                mass_kg=0.0135, mass_max_kg=0.014,
                size_m=(0.0228, 0.0122, 0.0285),
                example_part="MG90S metal gear (9 g class)",
                requirement="Bay in the tail root block, 70 mm x 2 mm pushrod.",
                unenforced=(
                    "counts against the <=120 g tail-group budget — NO heavier "
                    "substitutes at the tail, ever",
                ),
            ),
            Item(
                name="servo_ruddervator_right", group="Actuation",
                mass_kg=0.0135, mass_max_kg=0.014,
                size_m=(0.0228, 0.0122, 0.0285),
                example_part="MG90S metal gear (9 g class)",
                requirement="Bay in the tail root block, 70 mm x 2 mm pushrod.",
                unenforced=(
                    "counts against the <=120 g tail-group budget — NO heavier "
                    "substitutes at the tail, ever",
                ),
            ),
            # --- Autopilot core ---
            Item(
                name="flight_controller", order=30, group="Autopilot core",
                mass_kg=0.030, mass_max_kg=0.040,
                size_m=(0.054, 0.036, 0.013), lane="bay_shelf",
                example_part="Matek H743-WING V3 (spec minimum: F405-Wing class)",
                purpose="Runs ArduPilot — the always-on safety layer.",
                requirement="FC tray on the avionics shelf, aft of the battery.",
                unenforced=(
                    "30.5 x 30.5 mm pattern, arrow FORWARD and level",
                    "soft-mount (foam tape / grommets) — pusher prop vibration "
                    "comes down the boom",
                    "keep off the ESC wall (heat)",
                    "USB port reachable through the hatch for bench work",
                ),
            ),
            Item(
                name="sd_card_fc", group="Autopilot core",
                mass_kg=0.001, mass_max_kg=0.001,
                size_m=(0.015, 0.011, 0.001), rides="flight_controller",
                example_part="32 GB class-10",
                purpose="Dataflash logs — the primary debugging tool.",
                requirement="FC card slot (no freedom of its own).",
                unenforced=("slot must face somewhere reachable through the hatch",),
            ),
            Item(
                name="gps_compass", order=10, group="Autopilot core",
                mass_kg=0.008, mass_max_kg=0.022,
                size_m=(0.020, 0.020, 0.0124), lane="bay_deck",
                example_part="Matek M10Q-5883 (M10 GNSS + QMC5883L mag)",
                purpose="Position + heading. The compass is the placement-sensitive half.",
                requirement=(
                    "Top deck, highest point in the pod. >=80 mm from the battery "
                    "leads and from the ESC."
                ),
                unenforced=(
                    "directly under the LW-PLA hatch skin — RF-transparent, no "
                    "carbon or metal above it",
                    "all high-current wiring routed below the deck shelf",
                    "sky view unobstructed",
                ),
            ),
            Item(
                name="airspeed_board", order=50, group="Autopilot core",
                mass_kg=0.004, mass_max_kg=0.006,
                size_m=(0.022, 0.016, 0.008), lane="bay_shelf",
                fitted=on("airspeed_board"),
                example_part="Matek ASPD-4525 (MS4525DO / DLVR based)",
                purpose="Makes TECS speed/energy control work. I2C to FC.",
                requirement="Within 300 mm of the FC — this is an I2C run, not a bus.",
                unenforced=("tubing kink-free",),
            ),
            Item(
                name="pitot_probe", group="Autopilot core",
                mass_kg=0.006, mass_max_kg=0.009,
                fitted=on("pitot_probe"),
                purpose="The probe, mast and 40 cm of tubing.",
                requirement=(
                    "Clean air: outer wing LE at ~2/3 semi-span, protruding "
                    ">=40 mm ahead of the surface, clear of the fuselage boundary "
                    "layer."
                ),
                unenforced=(
                    "a handling hazard on a hand launch — position away from the grip",
                    "its own parasite drag is NOT in the buildup at this fidelity",
                ),
            ),
            Item(
                name="buzzer", order=20, group="Autopilot core",
                mass_kg=0.002, mass_max_kg=0.003,
                size_m=(0.012, 0.012, 0.0095), lane="bay_deck",
                example_part="Passive buzzer on FC BUZ pads",
                purpose="Arming/failsafe alerts; lost-model locator.",
                requirement="Anywhere in the pod — no structural requirement.",
                unenforced=("unobstructed sound path — near the hatch seam or a cooling exit",),
            ),
            # --- Companion compute ---
            Item(
                name="companion_pi", order=10, group="Companion compute",
                mass_kg=0.011, mass_max_kg=0.020,
                size_m=(0.065, 0.030, 0.013), lane=pi_lane,
                fitted=on("companion_pi"),
                example_part="Raspberry Pi Zero 2 W",
                purpose="Runs custom flight software commanding ArduPilot over MAVLink.",
                requirement=(
                    "Nose bay preferred, flat against the F1 bulkhead face (max "
                    "forward moment). Fallback: beside the FC tray — which is "
                    "where a PULLER puts it, the nose being full of motor."
                ),
                unenforced=(
                    "keep the WiFi antenna end clear of carbon",
                    "common ground with the FC",
                    "verify nose-cap internal clearance in CAD",
                ),
            ),
            Item(
                name="bec_pi", order=20, group="Companion compute",
                mass_kg=0.008, mass_max_kg=0.012,
                size_m=(0.0203, 0.0178, 0.005), lane=pi_lane,
                fitted=on("bec_pi"),
                example_part="Matek mini BEC / Pololu D24V22F5, 5 V / 3 A",
                purpose="Dedicated clean 5 V rail — never share the servo rail.",
                requirement="Within ~50 mm of the Pi; twisted input pair from the PDB tap.",
                unenforced=("common ground with the FC",),
            ),
            Item(
                name="sd_card_pi", group="Companion compute",
                mass_kg=0.001, mass_max_kg=0.001,
                size_m=(0.015, 0.011, 0.001), rides="companion_pi",
                fitted=on("sd_card_pi"),
                example_part="32 GB A1",
                requirement="Pi card slot (no freedom of its own).",
                unenforced=("orient the slot toward the hatch",),
            ),
            # --- RC link ---
            Item(
                name="receiver_elrs", order=40, group="RC link",
                mass_kg=0.0046, mass_max_kg=0.005,
                size_m=(0.022, 0.013, 0.004), lane="bay_shelf",
                example_part="RadioMaster RP3 V2 (ELRS 2.4 GHz diversity)",
                purpose="CRSF to FC — RC + basic telemetry on one UART.",
                requirement="Behind the FC tray.",
                unenforced=(
                    "THE ANTENNAS ARE THE REAL CONSTRAINT, NOT THE BOARD: tips 90 "
                    "deg apart and >=30 mm from ANY carbon (boom, wing spar), from "
                    "the phase wires and from the GPS puck",
                ),
            ),
            # --- Telemetry ---
            Item(
                name="telemetry_sik", group="Telemetry / GCS",
                mass_kg=0.020, mass_max_kg=0.030,
                size_m=(0.053, 0.0107, 0.028), lane="bay_right",
                fitted=on("telemetry_sik"),
                example_part="Holybro SiK Radio V3, 915 MHz 100 mW (air unit)",
                purpose="Live MAVLink to the laptop GCS.",
                requirement=(
                    "RIGHT sidewall, opposite the ESC. >=100 mm from the GPS puck "
                    "(desense)."
                ),
                unenforced=(
                    "antenna vertical; do not lay it along the boom",
                    ">=100 mm from the ELRS antennas",
                ),
            ),
            # --- Wiring, split where it actually runs ---
            Item(
                name="wiring_pod", group="Support",
                mass_kg=self.WIRING_POD_KG[0], mass_max_kg=self.WIRING_POD_KG[1],
                purpose="Pod harness: XT60 pigtail, PDB taps, servo extensions, foam, velcro.",
                requirement="Distributed through the bay; charged at the bay centroid.",
                unenforced=("keep every harness clear of the RX antennas",),
            ),
            Item(
                name="wiring_boom", group="Support",
                mass_kg=self.WIRING_BOOM_KG[0], mass_max_kg=self.WIRING_BOOM_KG[1],
                purpose="~700 mm boom run: motor phase wires + twisted servo leads.",
                requirement=(
                    "Motor phase wires in the LEFT boom channel, servo leads in the "
                    "RIGHT; charged at the boom's midpoint."
                ),
                unenforced=(
                    "zip-tie slots at both boom ends",
                    "aileron leads pass through the wing saddle",
                ),
            ),
            # --- Ground / bench: in the manifest so the BOM reconciles, but
            # carrying no mass and no station ---
            Item(
                name="transmitter", group="RC link", mass_kg=0.0, airborne=False,
                example_part="RadioMaster Boxer ELRS 2.4 GHz",
                purpose="Manual control; hardware mode switch always overrides the "
                        "custom code path. Doubles as a USB joystick for SITL.",
                requirement="Ground item — no airframe constraint.",
            ),
            Item(
                name="ground_station", group="Telemetry / GCS", mass_kg=0.0, airborne=False,
                example_part="Laptop + Mission Planner / QGroundControl",
                purpose="Parameters, missions, live tuning, log analysis, SITL.",
                requirement="Ground item — no airframe constraint.",
            ),
            Item(
                name="charger", group="Support", mass_kg=0.0, airborne=False,
                example_part="ISDT / ToolkitRC >=100 W balance charger",
                requirement="Bench item — no airframe constraint.",
            ),
            Item(
                name="lipo_checker", group="Support", mass_kg=0.0, airborne=False,
                example_part="Any cell-voltage checker",
                requirement="Field-box item — no airframe constraint.",
            ),
        ]
        return items

    def separations(self) -> tuple[Separation, ...]:
        """Required fore/aft distances, in the direction the layout puts them.

        Directions are declared rather than derived because the alternative is
        `abs(x_a - x_b)`, which puts a kink in the middle of the feasible set
        (`equipment.Separation`). Both of these come off the BOM's placement
        column and both are one-sided in the spec's own layout.
        """
        seps = [
            Separation(
                a="esc", b="gps_compass", min_m=0.080,
                why="compass desense: >=80 mm from the ESC and the battery leads",
            ),
        ]
        if self.equipment_fit != "core":
            seps += [
                # The SiK goes FORWARD of the GPS, not aft: aft of it there is
                # only the boat-tail, and 100 mm aft of a top-deck GPS lands
                # outside the bay entirely.
                Separation(
                    a="telemetry_sik", b="gps_compass", min_m=0.100,
                    why="915 MHz air unit desenses the GNSS puck within 100 mm",
                ),
                Separation(
                    a="flight_controller", b="airspeed_board", max_m=0.300,
                    why="I2C run — the sensor board cannot be extended away from the FC",
                ),
                # "within ~50 mm" — the tilde is doing real work, and 50 mm flat
                # against a 65 mm Pi and a 20 mm BEC leaves a 4 mm window the
                # solver would have to thread. 60 mm is the same requirement with
                # the tolerance the word "~" implies.
                Separation(
                    a="companion_pi", b="bec_pi", max_m=0.060,
                    why="twisted input pair kept short so servo transients cannot "
                        "brown out the companion",
                ),
            ]
        return tuple(seps)

    # ------------------------------------------------------------------
    # zones — the BOM's absolute stations, re-expressed against the loft
    # ------------------------------------------------------------------

    def _nose_clear_station(self, d: dict, need_m: float):
        """First station where the nose interior admits a part `need_m` across.

        The same closed-form inversion `nose_split` uses for the motor can,
        generalized: the nose arc is `r(t) = sqrt(1 - (1-t)^2)`, so the interior
        first clears a required half-breadth at `t = 1 - sqrt(1 - r_req^2)`.
        Against the NARROW section dimension (`d_min`), because a part has to get
        past the smaller of width and height. Symbolic-safe — the guard is the
        same smooth floor, so an iterate whose section is narrower than the part
        cannot produce sqrt(negative).
        """
        p = self.pod_dims(d)
        r_req = (need_m + 2 * self.POD_WALL_CLEARANCE) / p["d_min"]
        behind = np.sqrt(geometry.smooth_floor(1 - r_req**2))
        return p["nose_tip"] + d["pod_nose"] * (1 - behind)

    def lanes(self, d: dict, items: list[Item]) -> dict[str, Lane]:
        """The packing corridors, all parametric on the loft. Symbolic-safe.

        THE MAPPING FROM THE SPEC'S STATION MAP. The BOM's stations are absolute
        millimetres on the frozen 585 mm pod (battery 25-205, ESC 205-260, FC
        tray 240-310, RX behind, GPS deck 330-385). Those numbers cannot be used
        directly — `pod_nose`, `pod_bay`, `pod_bay_end`, `pod_xs` and `pod_wh`
        are all design variables now, so a literal station would describe a
        fuselage the optimizer had already stopped building. What survives the
        translation is the LAYOUT: the battery occupies the front of the bay, and
        everything else lives aft of it in three lanes that share the section
        (left wall, shelf, right wall) plus a top deck above them.

        So the battery's aft face IS the F2 bulkhead, and it is where the
        avionics start. That makes the balance variable do double duty — pushing
        the pack aft for CG squeezes the avionics — which is a real trade this
        aeroplane has and no previous model could see.
        """
        p = self.pod_dims(d)
        clr = self.POD_WALL_CLEARANCE
        w_in, h_in = p["w"] - 2 * clr, p["h"] - 2 * clr
        battery = equipment.lookup(items, "battery")
        # F2: the bulkhead behind the pack. Everything else is aft of it.
        x_f2 = d["x_battery"] + battery.length / 2

        lanes = {
            "bay_floor": Lane(
                "bay_floor", p["bay_start"], p["bay_end"],
                # the base model's +4 mm play on the pack, kept exactly
                width_m=w_in - 0.004, height_m=h_in - 0.004,
                note="battery on the floor, low CG; its station is the balance variable",
            ),
            "bay_left": Lane(
                "bay_left", x_f2 + 0.003, p["bay_end"],
                note="left sidewall, in the cooling stream (ESC)",
            ),
            "bay_right": Lane(
                "bay_right", x_f2 + 0.003, p["bay_end"],
                note="right sidewall, opposite the ESC (telemetry)",
            ),
            "bay_shelf": Lane(
                "bay_shelf", x_f2 + 0.003, p["bay_end"],
                note="electronics shelf above the floor, aft of the pack",
            ),
            # The BOM's ">=80 mm from battery leads" for the compass, made a
            # corridor bound rather than a separation: the leads leave the pack's
            # aft face, which is exactly this lane's datum.
            "bay_deck": Lane(
                "bay_deck", x_f2 + 0.080, p["bay_end"],
                note="top deck under the hatch skin, >=80 mm aft of the battery leads",
            ),
        }
        if self.motor_mount == "pusher":
            # The nose bay only exists when there is no motor in it. Its forward
            # end is where the growing nose section first admits its widest
            # occupant, not the nose tip — the tip is a point.
            #
            # At the INHERITED defaults this lane is 30 mm long and cannot hold
            # a 65 mm Pi, so a pusher start is infeasible on two rows. That is
            # the spec's legacy `pod_nose = 0.030` rather than a modelling
            # fault: it already violates the model's own nose >= 1.0 * d_eq
            # proportion floor (77 mm at the spec section), which is why the
            # sample's docstring calls the dv=None fixture exempt. Any converged
            # pusher carries a nose of at least that, and the board fits.
            # Nothing is exercised here today in any case — `discrete_options`
            # has carried `motor_mount: ["puller"]` since 2026-07-31.
            nose_items = equipment.by_lane(items, "nose_bay")
            need = max((max(i.width, i.height) for i in nose_items), default=0.0)
            lanes["nose_bay"] = Lane(
                "nose_bay",
                self._nose_clear_station(d, need),
                p["bay_start"],
                note="nose bay ahead of F1 — maximum forward moment, substitutes "
                     "ballast nearly 1:1",
            )
        return lanes

    def section_stacks(self, d: dict, items: list[Item]) -> tuple[SectionStack, ...]:
        """Lanes that coexist at the same stations, so their parts add across
        the section. THE constraint that ties this BOM to `pod_wh`/`pod_xs`.

        Width: the two sidewalls and the shelf are at liberty to put parts at
        the same station — the BOM says so outright ("may overlap the FC-tray
        zone lengthwise — different wall") — so the worst case is the widest
        occupant of each, side by side, plus build play.

        Height: the shelf and the deck stack vertically over the same stations
        by construction, with the printed plates between them. The battery is
        NOT in this stack: it is forward of both lanes, on the floor.
        """
        p = self.pod_dims(d)
        clr = self.POD_WALL_CLEARANCE
        return (
            SectionStack(
                "aft_bay_width", ("bay_left", "bay_shelf", "bay_right"),
                axis="width", available=p["w"] - 2 * clr, extra_m=self.LANE_PLAY,
                note="ESC on one wall + widest shelf part + telemetry on the other",
            ),
            SectionStack(
                "aft_bay_height", ("bay_shelf", "bay_deck"),
                axis="height", available=p["h"] - 2 * clr,
                extra_m=2 * self.SHELF_PLATE,
                note="shelf part + top-deck part + the two printed plates",
            ),
        )

    def derived_stations(self, d: dict) -> dict:
        """Stations for the parts that are not packed into a bay, because their
        placement is set by structure rather than chosen. Symbolic-safe.

        None of these is a free variable and none of them should be: a servo in
        a wing pocket is at the semi-span station the linkage needs, a motor is
        wherever its mount is, and a harness is charged at the centroid of the
        run it makes. Giving them variables would be inventing freedom the
        aeroplane does not have.
        """
        p = self.pod_dims(d)
        x_tail = WING_X_LE + 0.25 * 0.201 + d["tail_arm"]
        pod_end = p["bay_end"] + p["tail_len"]

        # chord and LE offset at an arbitrary semi-span station, from the same
        # curve the geometry is built on
        def at(eta):
            c = geometry.superellipse_chords(
                [0.0, eta, 1.0], d["c_root"], d["taper"], d["fullness"]
            )[1]
            return c, d["le_shear"] * (d["c_root"] - c)

        c_srv, le_srv = at(self.AILERON_SERVO_ETA)
        x_servo = WING_X_LE + le_srv + self.AILERON_SERVO_CHORD_FRAC * c_srv
        _, le_pitot = at(self.PITOT_ETA)
        x_pitot = WING_X_LE + le_pitot - self.PITOT_PROTRUSION_M

        if self.motor_mount == "puller":
            split = self.nose_split(d)
            x_motor = split["x_motor"]
            # the disc sits ahead of the can, at the spinner
            x_prop = p["nose_tip"] + 0.005
        else:
            x_motor = x_tail + 0.08
            x_prop = x_motor + self.COMPONENT_ENVELOPES["motor"]["length"] / 2 + 0.010
        if self.fuselage_topology == "pod_boom":
            x_boom_harness = (pod_end + x_tail) / 2
        else:
            x_boom_harness = (p["bay_end"] + x_tail) / 2

        return {
            "motor": x_motor,
            "propeller": x_prop,
            "servo_aileron_left": x_servo,
            "servo_aileron_right": x_servo,
            "servo_ruddervator_left": x_tail,
            "servo_ruddervator_right": x_tail,
            "pitot_probe": x_pitot,
            "wiring_pod": (p["bay_start"] + p["bay_end"]) / 2,
            "wiring_boom": x_boom_harness,
        }

    # ------------------------------------------------------------------
    # framework hooks
    # ------------------------------------------------------------------

    #: Placement inits. Feasible against every row in `packaging_constraints` at
    #: the declared loft — checked by tests/test_equipment.py, because an
    #: infeasible starting point on ten new variables is a solve that spends its
    #: first hundred iterations finding the bay rather than the aeroplane.
    DV_DEFAULTS = _base.VTailSample.DV_DEFAULTS | {
        "x_esc": 0.220,
        "x_telemetry_sik": 0.217,
        "x_companion_pi": 0.223,
        "x_bec_pi": 0.270,
        "x_flight_controller": 0.311,
        "x_receiver_elrs": 0.353,
        "x_airspeed_board": 0.379,
        "x_gps_compass": 0.320,
        "x_buzzer": 0.340,
    }

    #: Wide NUMERIC backstop for placement variables — the real bounds are the
    #: symbolic lane rows, exactly as `x_battery`'s always were.
    PLACEMENT_BOX = (-0.10, 1.60)

    def design_variables(self, opti, inits: dict | None = None) -> dict:
        dv = super().design_variables(opti, inits)
        i = self.DV_DEFAULTS | (inits or {})
        dv |= equipment.variables(
            opti, self.manifest(), i, self.PLACEMENT_BOX, declared=dv
        )
        return dv

    def packaging_constraints(self, opti, dv, p) -> None:
        """Supersedes the sample's four lumped rows with the real manifest.

        The base rows are deliberately NOT called: they price a battery, an ESC
        length and an FC length against the bay, which is a strictly weaker
        statement than packing every part into a lane. Keeping both would leave
        the solver with redundant rows and `active_bounds` with duplicates
        naming the same physical limit twice.
        """
        d = self.DV_DEFAULTS | dict(dv)
        items = self.manifest()
        equipment.constraints(
            opti, items, self.lanes(d, items), d,
            separations=self.separations(),
            stacks=self.section_stacks(d, items),
        )
        # travel + leads for the pack, the one base row that is about the BAY
        # rather than about a part, so it has no manifest equivalent
        battery = equipment.lookup(items, "battery")
        opti.subject_to(dv["pod_bay"] >= battery.length + 0.050)

    def fixed_equipment(self, dv: dict | None = None):
        """The manifest, as the mass model sees it — one point mass per part."""
        d = self.DV_DEFAULTS | (dv or {})
        items = self.manifest()
        return equipment.point_masses(
            items, d, self.derived_stations(d), basis=self.equipment_mass_basis
        )

    def placements(self, dv: dict | None = None) -> dict:
        """{part: station} for every carried part — the answer to the question
        this package exists to answer."""
        d = self.DV_DEFAULTS | (dv or {})
        items = self.manifest()
        return equipment.stations(items, d, self.derived_stations(d))

    def equipment_report(self, dv: dict | None = None, other=None) -> dict:
        """Everything the artifact should carry about the manifest.

        `other` is the champion's non-equipment point masses; with it the
        max-weight closure check can be answered, and without it the block still
        carries the placements and the totals.
        """
        d = self.DV_DEFAULTS | (dv or {})
        items = self.manifest()
        where = {k: float(v) for k, v in self.placements(dv).items()}
        block = {
            "basis_solved": self.equipment_mass_basis,
            "fit": self.equipment_fit,
            "totals_est": equipment.totals(items, "est"),
            "totals_max": equipment.totals(items, "max"),
            "placements_mm": {k: round(v * 1000, 1) for k, v in where.items()},
            "rows": equipment.rows(items, where, self.equipment_mass_basis),
            # Whether a free station per item bought this aeroplane anything —
            # the measurement EQUIPMENT_PLAN.md attached to that decision, which
            # `active_bounds` could not make (see `equipment.placement_activity`)
            "placement_activity": equipment.placement_activity(
                items, self.lanes(d, items), where, self.separations()
            ),
        }
        if other is not None:
            block["closure"] = equipment.mass_closure(
                items, where, other, self.equipment_mass_basis
            )
            block["tail_group"] = self._tail_group(dv, items, where, other)
        return block

    #: DESIGN_SPEC's tail-group budget, and the reason the servo rows say "NO
    #: heavier substitutes at the tail, ever": aft mass is ~2x expensive here
    #: (1 g at the motor needs ~1.9 g of nose ballast to rebalance).
    TAIL_GROUP_BUDGET_KG = 0.120

    def _tail_group(self, dv, items, where, other) -> dict:
        """Everything aft of the tail block, against the spec's 120 g budget.

        REPORTED, NOT ENFORCED, and that distinction is the whole content of
        this method. The budget is a real requirement and the model already
        blows it — the printed V-tail alone comes out above 120 g at the fixed
        design — so writing it as a constraint row would not discipline the
        design, it would delete the aeroplane. What it would actually be
        constraining is the printed-surface mass model, whose constants are
        UNCALIBRATED until `tools/fit_profile.py` runs on slicer data
        (MODEL_DETAILS 1.4). Enforcing a budget against an uncalibrated estimate
        is how a modelling constant quietly becomes a design decision.

        So the number goes in the artifact with its own verdict, and the person
        reading it decides whether the tail is too heavy or the tail mass model
        is too pessimistic.
        """
        d = self.DV_DEFAULTS | (dv or {})
        # Cut at the TAIL BLOCK, not at the pod cap. The spec's weight budget
        # lists "tail <= 120 g" and "boom + hardware" as separate lines, so a
        # cut that swept up the boom and its harness would be comparing a
        # five-part group against a three-part budget and calling the difference
        # a finding.
        x_block = WING_X_LE + 0.25 * 0.201 + d["tail_arm"]
        cut = float(x_block) - 1e-9  # the servos sit exactly on it
        basis = self.equipment_mass_basis
        parts = {
            i.name: round(i.mass(basis), 4)
            for i in equipment.carried(items)
            if where[i.name] >= cut
        }
        parts |= {
            c.name: round(float(c.mass_kg), 4)
            for c in other
            if float(c.x_m) >= cut
        }
        total = sum(parts.values())
        return {
            "budget_kg": self.TAIL_GROUP_BUDGET_KG,
            "cut_station_mm": round(cut * 1000, 1),
            "tail_block_mm": round(float(x_block) * 1000, 1),
            "parts_kg": dict(sorted(parts.items(), key=lambda kv: -kv[1])),
            "total_kg": round(total, 4),
            "over_by_kg": round(total - self.TAIL_GROUP_BUDGET_KG, 4),
            "verdict": (
                "within budget" if total <= self.TAIL_GROUP_BUDGET_KG
                else "OVER the DESIGN_SPEC budget — reported, not enforced; the "
                     "printed-surface mass constants are uncalibrated, so this "
                     "may be the model rather than the tail"
            ),
        }

    def design_brief(self, dv: dict | None = None, shadow_per_g=None) -> dict:
        brief = super().design_brief(dv, shadow_per_g=shadow_per_g)
        d = self.DV_DEFAULTS | (dv or {})
        items = self.manifest()
        where = self.placements(dv)
        p = self.pod_dims(d)
        clr = self.POD_WALL_CLEARANCE
        mm = lambda v: f"{float(v) * 1000:.0f} mm"  # noqa: E731

        # the aft-bay width budget, itemised — the row most likely to bind
        left = max((i.width for i in equipment.by_lane(items, "bay_left")), default=0.0)
        shelf = max((i.width for i in equipment.by_lane(items, "bay_shelf")), default=0.0)
        right = max((i.width for i in equipment.by_lane(items, "bay_right")), default=0.0)
        need = left + shelf + right + self.LANE_PLAY

        brief["Equipment — where every part goes"] = {
            "manifest": f"{len(equipment.carried(items))} airborne parts, "
                        f"fit '{self.equipment_fit}', solved on the "
                        f"'{self.equipment_mass_basis}' mass basis",
            "airborne electronics (est / max)": (
                f"{equipment.totals(items, 'est')['total_kg'] * 1000:.0f} g / "
                f"{equipment.totals(items, 'max')['total_kg'] * 1000:.0f} g"
            ),
            **{f"station — {k}": mm(v) for k, v in sorted(where.items())},
        }
        brief["Equipment — aft-bay section budget"] = {
            "interior width available": mm(p["w"] - 2 * clr),
            "left wall (widest)": mm(left),
            "shelf (widest)": mm(shelf),
            "right wall (widest)": mm(right),
            "declared build play": mm(self.LANE_PLAY),
            "total required": f"{mm(need)} — margin {mm(p['w'] - 2 * clr - need)}",
        }
        return brief

    def manufacturing(self, dv: dict | None = None, auw_kg: float | None = None) -> dict:
        sheet = super().manufacturing(dv, auw_kg=auw_kg)
        items = self.manifest()
        where = {k: float(v) for k, v in self.placements(dv).items()}
        # A LIST renders as a table and is written beside the build document as
        # its own CSV (report/manufacturing.py) — so this goes to the bench as a
        # spreadsheet with a station against every line of the BOM.
        sheet["Equipment placement (stations mm from nose datum)"] = equipment.rows(
            items, where, self.equipment_mass_basis
        )
        return sheet


AIRCRAFT = VTailRCv2()
