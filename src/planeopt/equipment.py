"""Equipment manifest — the parts list as a MODEL, not as a lump.

WHAT THIS REPLACES

Until now every aircraft in this project carried its avionics as a handful of
lumped point masses at literal stations: `esc_wiring` at 0.393 of the pod
length, `fc_gps_rx` at 0.513, `hardware_misc` at 0.450. Those numbers were read
off a frozen 585 mm pod and never moved again, so once the loft became
parametric they described a fuselage that no longer existed — and no artifact
ever reported a station for any of them, only a mass. A builder asking "where
does the receiver go" got nothing back.

A manifest is the same information, declared per PART, with the requirement
that decides where it goes attached to it. From that the framework can do three
things it could not do before:

1. **Place** each part — one bounded station variable per item, so where the
   equipment sits is an optimization outcome priced against nose ballast rather
   than a literal inherited from a drawing.
2. **Pack** it — items in a lane cannot overlap lengthwise, lanes that share a
   cross-section must fit across it, and separations that matter (an RF one, an
   I2C cable run) are constraint rows instead of prose.
3. **Report** it — a station per part, and a max-weight closure check that says
   whether the aeroplane still balances with every part at the heaviest
   substitute its own spec allows.

THE IRON RULE STILL HOLDS (EXECUTION_PLAN section 3)

Nothing here knows what a pod is. A `Lane` is a 1-D corridor with an optional
cross-section, an `Item` is a mass with a size and a lane, and the aircraft
supplies both — including every station, which may be symbolic. A flying wing
with three bays or a twin-boom aeroplane declares different lanes and gets the
same machinery.

SYMBOLIC-SAFETY (MODEL_DETAILS section 4)

Lane bounds and item stations are design EXPRESSIONS. Item dimensions and
masses are declared floats, so `max()` over sizes is a plain Python max over
data and never a branch on a design-variable value. There is no `abs()` and no
`min()` on anything symbolic anywhere in this module: ordering within a lane is
DECLARED (list order is fore-to-aft), which is what lets every non-overlap and
separation row be a smooth one-sided inequality.

WHAT THIS MODEL DOES NOT CHECK, AND SAYS SO

Most placement requirements on a real BOM are not one-dimensional. "Antenna
tips 90 degrees apart", "arrow FORWARD and level", "sky view unobstructed",
"in the nose-inlet to tail-exit cooling stream", "USB reachable through the
hatch" — none of those are functions of a station, and a model that silently
dropped them would be claiming to have checked something it never looked at.
Every item therefore carries an `unenforced` tuple, verbatim, and the report
prints it beside the placement. A requirement this module cannot see is a
requirement the BUILDER still owns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .types import PointMass

#: Mass bases an aircraft may solve against. "est" is the manufacturer figure
#: for the example part; "max" is the heaviest acceptable substitute, i.e. the
#: aeroplane you are still allowed to build after swapping every part for a
#: legal alternative. They are different aircraft and the artifact says which.
MASS_BASES = ("est", "max")


@dataclass
class Item:
    """One line of the bill of materials, with the requirement that places it.

    `size_m` is (length, width, height) in the aircraft axes — length along x
    (streamwise), so it is the dimension that packs against its lane neighbours.
    A part mounted on its side is declared with its dimensions already permuted:
    the manifest describes the INSTALLED orientation, because that is the one
    the packing arithmetic is about.
    """

    name: str
    group: str  # BOM category, for reporting only
    mass_kg: float  # estimated / example-part mass
    mass_max_kg: float | None = None  # heaviest acceptable substitute
    size_m: tuple[float, float, float] | None = None  # (L, W, H), installed
    lane: str | None = None  # packing lane; None -> station comes from `rides`
    #: Placed at another item's station, because it has no freedom of its own:
    #: a card in a slot, a prop on a shaft. Not a modelling shortcut — an SD
    #: card cannot be anywhere except in the reader that holds it.
    rides: str | None = None
    #: Fore-to-aft rank within the lane. Explicit rather than taken from
    #: declaration order so a manifest can stay grouped the way its source BOM
    #: is grouped — by category, which is how a person reads and checks it —
    #: while the LAYOUT is stated separately, which is how the packer reads it.
    #: Ties keep declaration order.
    order: float = 0.0
    fitted: bool = True  # in this build at all
    airborne: bool = True  # False -> ground/bench item: no mass, no station
    example_part: str = ""
    purpose: str = ""
    requirement: str = ""  # verbatim from the source BOM
    #: Requirements this model cannot check. Printed verbatim beside the
    #: placement so they stay the builder's, rather than quietly vanishing.
    unenforced: tuple[str, ...] = ()

    def mass(self, basis: str = "est") -> float:
        """Mass on the chosen basis. Falls back to the estimate when a part
        declares no maximum — a part with no legal substitute is its own cap."""
        if basis == "max" and self.mass_max_kg is not None:
            return self.mass_max_kg
        return self.mass_kg

    @property
    def length(self) -> float:
        return self.size_m[0] if self.size_m else 0.0

    @property
    def width(self) -> float:
        return self.size_m[1] if self.size_m else 0.0

    @property
    def height(self) -> float:
        return self.size_m[2] if self.size_m else 0.0


@dataclass
class Lane:
    """A 1-D corridor items pack along, with an optional cross-section.

    `x_lo`/`x_hi` are stations (may be symbolic) bounding the USABLE interior —
    the aircraft has already taken its wall thickness off them. `width_m` and
    `height_m`, when given, are the section available to this lane alone, and
    are checked per item rather than summed: two items in one lane never occupy
    the same station, so they never stack across it.

    `end_margin_m` is the clearance kept at each end, and `gap_m` the clearance
    between neighbours — declared build allowances, not fudge factors.
    """

    name: str
    x_lo: Any
    x_hi: Any
    width_m: Any = None
    height_m: Any = None
    end_margin_m: float = 0.003
    gap_m: float = 0.003
    note: str = ""


@dataclass
class Separation:
    """A required fore/aft distance between two items, in a declared direction.

    `b` sits AFT of `a` by at least `min_m` and at most `max_m`. The direction
    is declared rather than derived because the alternative is `abs(x_a - x_b)`,
    which is not differentiable at zero and would put a kink in the middle of
    the feasible set for the solver to get stuck in. Which side of which is a
    build fact the layout already knows.

    Both bounds are real requirements and they point opposite ways: `min_m` is
    usually RF or thermal ("keep the compass away from the current path"),
    `max_m` is usually a cable ("this is an I2C run, not a bus you can extend").
    """

    a: str
    b: str
    min_m: float | None = None
    max_m: float | None = None
    why: str = ""


@dataclass
class SectionStack:
    """Lanes that coexist at the same stations and so share a cross-section.

    Within a lane, items are ordered and never overlap, so the section only has
    to hold the widest one. ACROSS lanes there is no such guarantee — an ESC on
    the left wall and a receiver on the shelf are at liberty to end up at the
    same station — so their widths (or heights) add.

    `axis` is "width" or "height". `extra_m` is the declared build allowance the
    stack carries beyond the parts themselves (liners, tie-downs, the shelf
    itself). `available` is the section the stack must fit inside, and may be
    symbolic — that is the whole point: this is what ties a bill of materials to
    the fuselage cross-section the optimizer is choosing.
    """

    name: str
    lanes: tuple[str, ...]
    axis: str
    available: Any
    extra_m: float = 0.0
    note: str = ""


# --------------------------------------------------------------------------
# manifest queries
# --------------------------------------------------------------------------


def carried(items: list[Item]) -> list[Item]:
    """Items this build actually flies with."""
    return [i for i in items if i.fitted and i.airborne]


def placed(items: list[Item]) -> list[Item]:
    """Items that get a station variable of their own."""
    return [i for i in carried(items) if i.lane is not None and i.rides is None]


def by_lane(items: list[Item], lane: str) -> list[Item]:
    """Items in one lane, fore to aft — sorted by the declared `order`.

    `sorted` is stable, so items sharing a rank keep declaration order. The
    ordering is DECLARED rather than solved for, and that is what keeps every
    non-overlap row a smooth one-sided inequality instead of an `abs()` or a
    combinatorial choice (see `Separation`).
    """
    return sorted((i for i in placed(items) if i.lane == lane), key=lambda i: i.order)


def lookup(items: list[Item], name: str) -> Item:
    for i in items:
        if i.name == name:
            return i
    raise KeyError(f"no equipment item named {name!r}")


# --------------------------------------------------------------------------
# the NLP side
# --------------------------------------------------------------------------


def variables(
    opti,
    items: list[Item],
    inits: dict,
    box: tuple[float, float],
    declared: dict | None = None,
) -> dict:
    """One station variable per placed item, keyed `x_<name>`.

    The box is a wide NUMERIC backstop, exactly as `x_battery`'s always was: the
    real bounds are the symbolic containment rows in `constraints`, because a
    lane's ends move with the loft the optimizer is designing. Declaring the box
    tightly instead would be declaring where the equipment goes, which is the
    question being asked.

    `declared` is whatever the aircraft has already put in its design vector.
    Keys it already holds are skipped rather than redeclared — an aeroplane
    whose balance knob was always `x_battery` keeps that variable and simply
    gains a battery ITEM that reads it, so nothing downstream has to learn a new
    name for the same number.
    """
    lo, hi = box
    have = declared or {}
    out = {}
    for item in placed(items):
        key = f"x_{item.name}"
        if key in have:
            continue
        out[key] = opti.variable(init_guess=inits[key], lower_bound=lo, upper_bound=hi)
    return out


def _station(item: Item, x: dict, items: list[Item], derived: dict, _seen=()):
    """Where one item ends up: its own variable, its host's, or an aircraft-
    supplied derived station (a servo in a wing, a motor on a mount)."""
    if item.rides is not None:
        if item.name in _seen:
            raise ValueError(f"circular `rides` chain through {item.name!r}")
        host = lookup(items, item.rides)
        return _station(host, x, items, derived, (*_seen, item.name))
    key = f"x_{item.name}"
    if key in x:
        return x[key]
    if item.name in derived:
        return derived[item.name]
    raise KeyError(
        f"{item.name!r} has no station: it declares no lane, no host to ride, "
        "and the aircraft supplied no derived station for it"
    )


def stations(items: list[Item], x: dict, derived: dict | None = None) -> dict:
    """Station of every carried item — variables, hosts and derived alike."""
    derived = derived or {}
    return {i.name: _station(i, x, items, derived) for i in carried(items)}


def constraints(
    opti,
    items: list[Item],
    lanes: dict[str, Lane],
    x: dict,
    separations: tuple[Separation, ...] = (),
    stacks: tuple[SectionStack, ...] = (),
) -> None:
    """Every placement row: containment, ordering, section fit, separations.

    Rows are written dimensionless wherever a natural scale exists (FINDINGS
    section 14.5 — a constraint vector spanning ten decades is what made the
    hard corners take hundreds of iterations). Lengths here are all of order
    10-100 mm, so they are divided by the clearance they are about rather than
    left as raw metres.
    """
    for lane_name, lane in lanes.items():
        contents = by_lane(items, lane_name)
        if not contents:
            continue
        # --- lengthwise: each item inside the lane, in declared order ---
        prev = None
        for item in contents:
            xi = x[f"x_{item.name}"]
            half = item.length / 2
            # Nose end / tail end of the corridor, with the declared margin.
            #
            # RAW METRES, and the only rows in this module that are — the
            # module rule is "dimensionless WHEREVER A NATURAL SCALE EXISTS"
            # and for these two it does not. What they measure is how far an
            # item sits from a lane end, which ranges from 0 to the length of
            # the lane (200 mm here); the only constants available to divide by
            # are the 3 mm end margin and the item's own length, and the lane
            # length itself is a design expression, so dividing by it would
            # trade a scaling problem for a nonlinearity. Dividing by the margin
            # was tried on 2026-08-06 and measured WORSE: these rows went from
            # 0.18 to 60-75 at the initial point, because a 200 mm clearance
            # over a 3 mm margin is 67 and not 1. At raw metres they sit at
            # 0.18-0.22, inside a decade of 1, which is what the rule is
            # protecting. Left alone deliberately.
            opti.subject_to(xi - half >= lane.x_lo + lane.end_margin_m)
            opti.subject_to(xi + half <= lane.x_hi - lane.end_margin_m)
            if prev is not None:
                gap = (prev.length + item.length) / 2 + lane.gap_m
                # `item` is declared AFT of `prev`, so this is one-sided and
                # smooth — no absolute value anywhere in the packing.
                #
                # RAW METRES, like the two containment rows above, and this one
                # was MEASURED rather than argued. Dividing by `gap` is the
                # textbook application of the module rule — the required spacing
                # is the distance the row is about, items pack at it, and it
                # moves the row from 0.047 to 1.05 at the initial point. It was
                # tried on 2026-08-06 and REVERTED the same day.
                #
                # It is solution-preserving, exactly as FINDINGS 14.5.1 says a
                # positive constant must be: across nine members of the
                # `vtail_rcv2` battery the objectives matched to EIGHT
                # significant figures (relative 2.4e-08 to 1.3e-07). What it was
                # not is free. Converged members ran ~45% slower,
                # `winglet_study__off` went 5.18 -> 27.50 min, and
                # `winglet_study__continuous_cant` — 11.97 min and converged
                # before — ran out of its 30-minute budget at iteration 314 with
                # inf_du 1.9e-01 and mu descending, i.e. still converging and
                # simply too slow. A rescale that costs a member is not a
                # scaling fix.
                #
                # 14.5.1's rescale earned its place with a measured 228 -> 194
                # iterations. This one measured the other way, so it goes. The
                # rule is "dimensionless wherever a natural scale exists"; the
                # scale exists here and using it still loses, which is worth
                # knowing before anyone reaches for it again.
                opti.subject_to(xi - x[f"x_{prev.name}"] >= gap)
            prev = item
        # --- across the section: the lane must admit its widest occupant ---
        if lane.width_m is not None:
            widest = max(i.width for i in contents)
            if widest > 0:
                opti.subject_to(lane.width_m / widest >= 1.0)
        if lane.height_m is not None:
            tallest = max(i.height for i in contents)
            if tallest > 0:
                opti.subject_to(lane.height_m / tallest >= 1.0)

    # --- lanes that share a cross-section: their occupants ADD across it ---
    for stack in stacks:
        needed = stack.extra_m
        for lane_name in stack.lanes:
            contents = by_lane(items, lane_name)
            if not contents:
                continue
            needed += max(getattr(i, stack.axis) for i in contents)
        if needed > 0:
            opti.subject_to(stack.available / needed >= 1.0)

    # --- declared separations ---
    for sep in separations:
        xa, xb = x[f"x_{sep.a}"], x[f"x_{sep.b}"]
        if sep.min_m is not None:
            opti.subject_to((xb - xa) / sep.min_m >= 1.0)
        if sep.max_m is not None:
            opti.subject_to((xb - xa) / sep.max_m <= 1.0)


#: Slack under which a placement row counts as PINNED. 50 um is below any
#: tolerance a builder can hold, and nearly three orders below the smallest real
#: free play this manifest has ever produced (39.5 mm, the GPS held off the lane
#: front by its RF separation), so nothing here is sensitive to the exact value.
PINNED_TOL_M = 50e-6


def placement_activity(
    items: list[Item],
    lanes: dict[str, Lane],
    where: dict,
    separations: tuple[Separation, ...] = (),
) -> dict:
    """Which placed items are HELD by a row, and which have room to move.

    **The measurement `EQUIPMENT_PLAN.md` pre-registered**, and it has to live
    here rather than come out of `active_bounds` — which is what that plan said
    would answer it. A placement variable's declared box is a wide numeric
    backstop (`PLACEMENT_BOX`); its real bounds are the symbolic lane rows in
    `g`. Bound-activity reporting only ever inspects declared boxes, so it was
    silent about every placement variable in the 2026-08-05 battery and would
    have stayed silent in every battery after it. The promise — "every placement
    variable that ends pinned at a lane end is reported by name, and if they all
    pin the freedom bought nothing" — was unkeepable as written, which is worse
    than a wrong answer: the decision it was attached to had no way to come due.

    Slack is measured PER DIRECTION, because the two readings the plan needs are
    different questions and a single "nearest row" number conflates them:

    - `room_fwd_mm` / `room_aft_mm` — how far the item could actually move each
      way before a row stops it. An item with zero of both is DETERMINED: its
      variable holds a number the rows already fix, and solving for it is
      solving for nothing.
    - `pinned_by` — the rows with no slack, named. An item hard against one side
      only is still a live variable; it is telling you the objective pushed it
      that way and something stopped it, which is the ordinary meaning of an
      active bound and NOT evidence that the freedom was wasted.

    Rows are sorted into the direction they block. A lane front, the neighbour
    ahead, and a `min` separation measured from an item in front all stop the
    item moving FORWARD; the lane aft end, the neighbour behind, and a `max`
    separation to an item behind stop it moving AFT.

    **Room is measured with every OTHER item held fixed**, which is what makes
    it a per-item number instead of a rank computation. Read it that way: a
    hard-packed train reports every member determined, and that is true of each
    member individually even though the train can still slide as a body. The
    collective freedom that remains is the lane's own position, which for this
    manifest is `x_battery` — a variable the aircraft declared for balance long
    before there was a manifest, and the one placement knob that was never in
    question.

    Reported, never enforced. This says what the solve DID, so the choice
    between a station variable and derived packing is settled against a run
    rather than against an argument.
    """
    tol = PINNED_TOL_M
    x = {k: float(v) for k, v in where.items()}
    rows_out, determined = [], 0
    for lane_name, lane in lanes.items():
        contents = by_lane(items, lane_name)
        x_lo, x_hi = float(lane.x_lo), float(lane.x_hi)
        for k, item in enumerate(contents):
            xi, half = x[item.name], item.length / 2
            fwd = {f"lane {lane_name} front": (xi - half) - (x_lo + lane.end_margin_m)}
            aft = {f"lane {lane_name} aft": (x_hi - lane.end_margin_m) - (xi + half)}
            if k:
                prev = contents[k - 1]
                fwd[f"gap behind {prev.name}"] = (xi - x[prev.name]) - (
                    (prev.length + item.length) / 2 + lane.gap_m
                )
            if k + 1 < len(contents):
                nxt = contents[k + 1]
                aft[f"gap ahead of {nxt.name}"] = (x[nxt.name] - xi) - (
                    (item.length + nxt.length) / 2 + lane.gap_m
                )
            for sep in separations:
                if sep.min_m is not None:
                    d = x[sep.b] - x[sep.a] - sep.min_m
                    if item.name == sep.b:
                        fwd[f"separation from {sep.a}"] = d
                    elif item.name == sep.a:
                        aft[f"separation to {sep.b}"] = d
                if sep.max_m is not None:
                    d = sep.max_m - (x[sep.b] - x[sep.a])
                    if item.name == sep.b:
                        aft[f"separation to {sep.a}"] = d
                    elif item.name == sep.a:
                        fwd[f"separation from {sep.b}"] = d
            r_fwd, r_aft = min(fwd.values()), min(aft.values())
            determined += r_fwd <= tol and r_aft <= tol
            rows_out.append({
                "item": item.name,
                "lane": lane_name,
                # `or 0.0` so a residual that rounds to negative zero prints as
                # 0.0 — "-0.00 mm of room" is not a thing, and a reader who sees
                # it starts wondering which rows are slightly violated
                "station_mm": round(xi * 1000, 2) or 0.0,
                "room_fwd_mm": round(r_fwd * 1000, 3) or 0.0,
                "room_aft_mm": round(r_aft * 1000, 3) or 0.0,
                "determined": bool(r_fwd <= tol and r_aft <= tol),
                "pinned_by": sorted(
                    k2 for k2, v in (fwd | aft).items() if v <= tol
                ),
            })
    n = len(rows_out)
    fwd_stop = sum(r["room_fwd_mm"] <= tol * 1000 for r in rows_out)
    return {
        "tolerance_mm": tol * 1000,
        "n_placed": n,
        "n_determined": determined,
        #: Items sitting on their forward stop. On an aeroplane whose static
        #: margin wants mass forward this is the number that carries the
        #: finding: if it equals `n_placed`, forward-most derived packing would
        #: reproduce the solved layout exactly, which is the same convention
        #: `nose_split` already uses for the bulkhead.
        "n_at_forward_stop": fwd_stop,
        "items": sorted(rows_out, key=lambda r: r["station_mm"]),
        "verdict": (
            "nothing is placed by a station variable" if not n else
            f"all {n} placed items sit on their FORWARD stop"
            + (
                " and are boxed in on both sides — the station variables hold "
                "numbers the packing rows already fix, so forward-most derived "
                "packing would reproduce this layout exactly "
                "(EQUIPMENT_PLAN.md, 'measured, then deleted')"
                if determined == n else
                f"; {n - determined} of them still have room aft, held forward "
                "by the objective rather than by a row, so derived packing "
                "would reproduce the layout but would stop pricing that choice"
            )
            if fwd_stop == n else
            f"{n - fwd_stop} of {n} placed items are off their forward stop — "
            "the placement freedom is doing something derived packing would not"
        ),
    }


# --------------------------------------------------------------------------
# the mass-model side
# --------------------------------------------------------------------------


def point_masses(
    items: list[Item], x: dict, derived: dict | None = None, basis: str = "est"
) -> list[PointMass]:
    """The manifest as the mass model sees it: one PointMass per carried item.

    Items with zero mass on this basis are still emitted, because a component
    list that silently drops rows is a component list nobody can reconcile
    against the BOM it came from.
    """
    if basis not in MASS_BASES:
        raise ValueError(f"mass basis must be one of {MASS_BASES}, got {basis!r}")
    where = stations(items, x, derived)
    return [PointMass(i.name, i.mass(basis), where[i.name]) for i in carried(items)]


def totals(items: list[Item], basis: str = "est") -> dict:
    """Group and grand totals on one basis — the BOM's own summary row, derived.

    Worth deriving rather than transcribing: the RC v2 sheet's stated max-weight
    cap was 55 g below the sum of its own max column (2026-08-05), and nothing
    would have caught that except adding the column up.
    """
    flying = carried(items)
    groups: dict[str, float] = {}
    for i in flying:
        groups[i.group] = groups.get(i.group, 0.0) + i.mass(basis)
    return {
        "basis": basis,
        "groups_kg": {g: round(m, 4) for g, m in sorted(groups.items())},
        "total_kg": round(sum(i.mass(basis) for i in flying), 4),
        "n_items": len(flying),
    }


def point_masses_from_stations(items, where, basis="est"):
    """Point masses from an already-resolved {name: station} mapping."""
    return [PointMass(i.name, i.mass(basis), where[i.name]) for i in carried(items)]


def mass_closure(
    items: list[Item], where: dict, other: list[PointMass], solved_basis: str
) -> dict:
    """AUW and CG on BOTH mass bases, at the placement the run produced.

    `other` is every point mass that is not equipment — printed surfaces,
    spars, boom, pod, ballast — taken from the champion, so the comparison
    isolates the substitution and nothing else. Stations are held fixed on
    purpose: this asks "if I built the same aeroplane out of the heaviest parts
    the BOM permits, where does it balance", which is the question a builder
    standing at a bench with a different ESC in their hand is actually asking.
    It is NOT a re-optimization, and the artifact must not read as one — a
    re-solve would move the wing, the ballast and the battery to absorb it.
    """
    from . import massmodel

    out = {"solved_basis": solved_basis}
    for basis in MASS_BASES:
        components = point_masses_from_stations(items, where, basis) + list(other)
        t = massmodel.totals(components)
        out[basis] = {
            "equipment_kg": round(sum(i.mass(basis) for i in carried(items)), 4),
            "auw_kg": round(float(t["auw_kg"]), 4),
            "x_cg_m": round(float(t["x_cg_m"]), 5),
        }
    out["delta"] = {
        "equipment_kg": round(out["max"]["equipment_kg"] - out["est"]["equipment_kg"], 4),
        "auw_kg": round(out["max"]["auw_kg"] - out["est"]["auw_kg"], 4),
        "x_cg_m": round(out["max"]["x_cg_m"] - out["est"]["x_cg_m"], 5),
    }
    return out


def rows(items: list[Item], where: dict, basis: str = "est") -> list[dict]:
    """The placement sheet: one row per BOM line, flying or not.

    This is what a builder reads. Every column is either declared data or a
    station the optimizer produced, and the `not checked here` column carries
    the requirements this model never looked at — see the module docstring.
    """
    out = []
    for i in items:
        station = where.get(i.name)
        out.append({
            "item": i.name,
            "group": i.group,
            "example part": i.example_part,
            "station_mm": (
                "" if station is None else round(float(station) * 1000, 1)
            ),
            "mass_g": round(i.mass(basis) * 1000, 1) if i.airborne and i.fitted else "",
            "mass_basis": basis if i.airborne and i.fitted else "",
            "max_g": (
                round(i.mass_max_kg * 1000, 1) if i.mass_max_kg is not None else ""
            ),
            "size_mm": (
                " x ".join(f"{d * 1000:.1f}" for d in i.size_m) if i.size_m else ""
            ),
            "lane": (
                i.lane if i.lane
                else f"rides {i.rides}" if i.rides
                else "" if not i.airborne
                # not packed into a bay: its station comes from structure (a
                # mount, a wing pocket, the centroid of a cable run), which is a
                # placement too and must not read as a blank
                else "derived from structure"
            ),
            "status": (
                "ground/bench — no airframe constraint" if not i.airborne
                else "not fitted" if not i.fitted
                else "placed"
            ),
            "requirement": i.requirement,
            "not checked here": " | ".join(i.unenforced),
        })
    return out
