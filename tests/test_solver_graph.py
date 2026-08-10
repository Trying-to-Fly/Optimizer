"""The NLP's large symbolic subgraphs are shared rather than copied."""

import inspect
from types import SimpleNamespace

import aerosandbox as asb
import casadi as cas
import numpy as np
import pytest

from planeopt import solve


def test_the_measured_exact_hessian_policy_is_explicit():
    assert solve.EXACT_HESSIAN_OPTIONS == {
        "ipopt.hessian_approximation": "exact"
    }


def test_lifting_line_graph_is_built_once_and_reused(monkeypatch):
    builds = []

    class Airplane:
        def __init__(self, deflection=0.0):
            self.deflection = deflection

        def with_control_deflections(self, controls):
            return Airplane(controls["elevator"])

    class LiftingLine:
        def __init__(self, airplane, op_point, xyz_ref, vortex_core_radius):
            builds.append((airplane, op_point, xyz_ref, vortex_core_radius))
            self.airplane = airplane
            self.op_point = op_point
            self.xyz_ref = xyz_ref

        def run(self):
            value = (
                self.op_point.velocity
                + self.op_point.alpha
                + self.airplane.deflection
                + self.xyz_ref[0]
            )
            return {"L": value, "D": 2 * value, "CL": 3 * value, "Cm": 4 * value}

    monkeypatch.setattr(asb, "LiftingLine", LiftingLine)
    monkeypatch.setattr(
        asb,
        "OperatingPoint",
        lambda velocity, alpha: SimpleNamespace(velocity=velocity, alpha=alpha),
    )

    opti = asb.Opti()
    velocity = opti.variable(init_guess=5.0, lower_bound=1.0)
    at = solve._shared_lifting_line(
        opti, Airplane(), velocity, 0.5 * velocity, "elevator"
    )
    first = at(2.0, 3.0)
    second = at(-1.0)
    batch = at(cas.horzcat(2.0, -1.0), cas.horzcat(3.0, 0.0))

    evaluate = cas.Function(
        "evaluate_shared_calls",
        [opti.x],
        [
            cas.horzcat(
                first["L"], first["D"], second["L"], second["Cm"],
                batch["L"], batch["Cm"],
            )
        ],
    )
    # AeroSandbox scales this variable by its initial guess, so opti.x=1 is
    # the declared physical velocity of 5.
    got = np.asarray(evaluate(1.0)).ravel()

    assert len(builds) == 1
    assert got == pytest.approx([12.5, 25.0, 6.5, 26.0, 12.5, 6.5, 50.0, 26.0])


def test_lifting_line_batches_reject_mismatched_lengths(monkeypatch):
    class Airplane:
        def with_control_deflections(self, controls):
            return self

    class LiftingLine:
        def __init__(self, airplane, op_point, xyz_ref, vortex_core_radius):
            self.op_point = op_point

        def run(self):
            value = self.op_point.velocity + self.op_point.alpha
            return {"L": value, "D": value, "CL": value, "Cm": value}

    monkeypatch.setattr(asb, "LiftingLine", LiftingLine)
    monkeypatch.setattr(
        asb,
        "OperatingPoint",
        lambda velocity, alpha: SimpleNamespace(velocity=velocity, alpha=alpha),
    )
    opti = asb.Opti()
    velocity = opti.variable(init_guess=5.0, lower_bound=1.0)
    at = solve._shared_lifting_line(opti, Airplane(), velocity, 0.0, "elevator")

    with pytest.raises(ValueError, match="equal lengths"):
        at(cas.DM([1.0, 2.0]), cas.DM([1.0, 2.0, 3.0]))


def test_ipopts_raw_vectors_are_ratios_against_a_basis_a_hot_start_moves():
    """Why `_hot_start_kwargs` seeds BY NAME and nothing here replays `opti.x`.

    This is the 2026-08-10 rcv2 failure in miniature, and it outlives the
    functions that fell for it (`_apply_solver_seed`/`_capture_solver_seed`,
    deleted): AeroSandbox normalizes as `var = scale * raw` with `scale` taken
    from `init_guess`, so a converged `opti.x` is a RATIO against the member
    that produced it. A hot start is exactly when that basis moves, because
    `init_guess` becomes the champion's value — replaying the ratio there
    applies the design twice, and the dimensions match perfectly while it
    happens. On rcv2 that meant sixteen constraint rows NaN and
    `Invalid_Number_Detected` at iteration 0, on members that converge cold.
    """
    original = asb.Opti()
    variable = original.variable(init_guess=2.0, lower_bound=0.0)
    original.minimize((variable - 8.0) ** 2)
    solution = original.solve(verbose=False)
    converged = float(solution.value(variable))

    # Stored as a ratio against init_guess=2.0, NOT as the physical 8.0.
    raw = float(np.asarray(solution.value(original.x)).ravel()[0])
    assert raw == pytest.approx(converged / 2.0, rel=1e-6)

    # A hot start re-declares the variable AT the champion's value, so the same
    # physical point is now the ratio 1.0 — and the two bases have identical
    # dimensions, which is why no shape check could ever have told them apart.
    target = asb.Opti()
    hot = target.variable(init_guess=converged, lower_bound=0.0)
    assert int(target.x.numel()) == int(original.x.numel())

    target.set_initial(target.x, np.array([[raw]]))
    replayed = float(target.value(hot, target.initial()))
    # The design, squared over its guess — not the design.
    assert replayed == pytest.approx(converged**2 / 2.0, rel=1e-6)
    assert replayed != pytest.approx(converged, rel=1e-3)

    # What `_hot_start_kwargs` does instead, and why it survives the move.
    correct = asb.Opti()
    by_name = correct.variable(init_guess=converged, lower_bound=0.0)
    assert float(correct.value(by_name, correct.initial())) == pytest.approx(
        converged, rel=1e-9
    )


def test_hot_start_kwargs_carry_the_operating_state_by_name():
    result = {
        "dv": {"span": 2.0},
        "V_ms": 9.5,
        "alpha_deg": 5.0,
        "deflection_deg": -2.0,
        "rpm": 3600.0,
    }

    kwargs = solve._hot_start_kwargs(result)
    assert kwargs["inits"] == {
        "span": 2.0,
        "V": 9.5,
        "alpha_deg": 5.0,
        "deflection_deg": -2.0,
        "prop_rev_s": 60.0,
    }
    # Physical values keyed by name is the ONLY thing that survives the basis
    # move — see the scaling test above. Everything a hot start sends must be
    # something `Opti.variable(init_guess=...)` can scale on the way in.
    assert set(kwargs) == {"inits"}
    assert not any(k.endswith("seed") for k in kwargs)


def test_a_champion_seed_does_not_drag_the_warm_start_options_with_it():
    """§35: those options are why five of six members failed, so `inits` travels alone.

    `WARM_START_OPTIONS` pins the start point to the bounds and sets `mu_init`
    two orders below IPOPT's default, which is correct only for a point that is
    near-optimal INCLUDING its duals — and duals are exactly what
    `_hot_start_kwargs` cannot carry (they are ratios against a basis a hot
    start moves). §34.4 measured the pairing on ONE member, `mass_bump`, a +20 g
    perturbation and the most favourable seed in a battery, where it converged
    in 13 iterations against 31 cold. The full rcv2 battery measured the rest:
    46, 54, 57, 57 and 74 iterations, all failures, on members main converges
    cold in 4.5-7 minutes.

    `inits` alone stays because it is not what failed — the 02:08 control run
    converged `mass_bump` on `inits` alone in 11.93 min, slower than main's
    7.41-7.78 but converged.
    """
    kwargs = solve._hot_start_kwargs({"dv": {"span": 2.0}})

    assert "warm_start" not in kwargs
    # The parameter must still EXIST — `--warm-start` is an explicit user
    # request and still pairs the seed with the options. What changed is that
    # seeding no longer implies it, which is the failure mode this pins.
    assert "warm_start" in inspect.signature(solve._solve_nlp).parameters
    # Every key it emits must be something `_solve_nlp` actually accepts;
    # a stray kwarg would be a TypeError inside a forked worker.
    accepted = inspect.signature(solve._solve_nlp).parameters
    assert set(kwargs) <= set(accepted)
