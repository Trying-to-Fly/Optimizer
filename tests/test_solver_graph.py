"""The NLP's large symbolic subgraphs are shared rather than copied."""

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

    compatible = asb.Opti()
    compatible.variable(init_guess=2.0, lower_bound=0.0)
    compatible.subject_to(compatible.x[0] <= 3.0)
    assert solve._apply_solver_seed(compatible, seed)

    incompatible = asb.Opti()
    incompatible.variable(init_guess=np.ones(2))
    assert not solve._apply_solver_seed(incompatible, seed)


def test_hot_start_kwargs_carry_the_operating_state_and_private_seed():
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
    assert kwargs["solver_seed"] is result["_solver_seed"]
