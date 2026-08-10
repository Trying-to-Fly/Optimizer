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


def test_complete_solver_seed_round_trips_and_checks_dimensions():
    original = asb.Opti()
    variable = original.variable(init_guess=2.0, lower_bound=0.0)
    original.subject_to(original.x[0] <= 3.0)
    original.minimize((variable - 1.0) ** 2)
    solution = original.solve(verbose=False)
    seed = solve._capture_solver_seed(original, solution)

    assert seed is not None
    assert (seed["nx"], seed["ng"]) == (1, 2)

    # SAME `init_guess`, so same scale — the one case where replaying raw `x`
    # means anything. See the scaling test below for why that is not the case a
    # hot start produces.
    compatible = asb.Opti()
    compatible.variable(init_guess=2.0, lower_bound=0.0)
    compatible.subject_to(compatible.x[0] <= 3.0)
    assert solve._apply_solver_seed(compatible, seed)

    incompatible = asb.Opti()
    incompatible.variable(init_guess=np.ones(2))
    assert not solve._apply_solver_seed(incompatible, seed)


def test_a_solver_seed_is_meaningless_once_init_guess_moves():
    """Why `_hot_start_kwargs` does not carry `solver_seed`.

    `nx`/`ng` match, so `_apply_solver_seed` accepts the seed — and the restored
    PHYSICAL value is wrong, because AeroSandbox normalizes by `init_guess`
    (`var = scale * raw`). This is the exact shape of the 2026-08-10 rcv2
    failure: a hot start sets `init_guess` to the champion, which changes the
    scale, so replaying the champion's ratios applies the design twice.
    """
    original = asb.Opti()
    variable = original.variable(init_guess=2.0, lower_bound=0.0)
    original.minimize((variable - 8.0) ** 2)
    solution = original.solve(verbose=False)
    converged = float(solution.value(variable))
    seed = solve._capture_solver_seed(original, solution)
    # stored as a RATIO against init_guess=2.0, not as the physical 8.0
    assert seed["x"][0] == pytest.approx(converged / 2.0, rel=1e-6)

    # A hot start re-declares the variable AT the champion's value.
    target = asb.Opti()
    hot = target.variable(init_guess=converged, lower_bound=0.0)
    assert solve._apply_solver_seed(target, seed) is True   # the guard passes...
    restored = float(target.value(hot, target.initial()))
    # ...and the physical starting point is the design squared over its guess.
    assert restored == pytest.approx(converged**2 / 2.0, rel=1e-6)
    assert restored != pytest.approx(converged, rel=1e-3)


def test_hot_start_kwargs_carry_the_operating_state_but_never_the_seed():
    result = {
        "dv": {"span": 2.0},
        "V_ms": 9.5,
        "alpha_deg": 5.0,
        "deflection_deg": -2.0,
        "rpm": 3600.0,
        "_solver_seed": {"nx": 1, "ng": 0, "x": [1.0], "lam_g": []},
    }

    kwargs = solve._hot_start_kwargs(result)
    assert kwargs["inits"] == {
        "span": 2.0,
        "V": 9.5,
        "alpha_deg": 5.0,
        "deflection_deg": -2.0,
        "prop_rev_s": 60.0,
    }
    # The seed is recorded on the member but deliberately NOT replayed: it is a
    # per-member ratio vector and a hot start is exactly when the basis moves.
    assert "solver_seed" not in kwargs


def test_hot_start_asks_for_the_warm_start_options_the_seed_used_to_carry():
    """`_solve_nlp` gates `WARM_START_OPTIONS` on `warm_start or hot_start_used`.

    `hot_start_used` is now always False, because `_hot_start_kwargs` no longer
    carries a seed for `_apply_solver_seed` to accept. Without `warm_start`
    riding along, dropping the seed would also drop the options — leaving every
    battery hot start in the seed-only configuration `WARM_START_OPTIONS`
    measures at +27% against cold, since IPOPT's default `bound_push` shoves a
    champion off the eight bounds it sits on before iteration 0.
    """
    kwargs = solve._hot_start_kwargs({"dv": {"span": 2.0}})

    assert kwargs["warm_start"] is True
    # and the flag has to be the one `_solve_nlp` actually reads
    assert "warm_start" in inspect.signature(solve._solve_nlp).parameters
