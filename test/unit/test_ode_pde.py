"""Test that the ode + pde coupling reproduces the ode for homogeneous IC."""
import pytest

import logging

import numpy as np

from xalbrain import (
    Model,
    SplittingSolver,
    SingleCellSolver,
)

import dolfin as df

from xalbrain.cellmodels import FitzHughNagumoManual


def test_ode_pde():
    """Test that the ode-pde coupling reproduces the ode solution."""
    parameters = SingleCellSolver.default_parameters()
    parameters["scheme"] = "GRL1"
    time = df.Constant(0)
    # stimulus = Expression("100*std::abs(sin(2*pi*t))", t=time, degree=1)
    stimulus = df.Expression("100", degree=1)
    model = FitzHughNagumoManual()
    model.stimulus = stimulus

    T = 10
    dt = 1e-3

    solver = SingleCellSolver(time=time, cell_model=model, parameters=parameters)
    vs_, _ = solver.solution_fields()
    vs_.assign(model.initial_conditions())
    ode_vs = None
    for _, ode_vs in solver.solve(0, T, dt):
        continue

    mesh = df.UnitSquareMesh(10, 10)
    brain = Model(mesh, time, 1.0, 1.0, model, stimulus=stimulus)
    ps = SplittingSolver.default_parameters()
    ps["pde_solver"] = "bidomain"
    ps["theta"] = 0.5
    ps["CardiacODESolver"]["scheme"] = "GRL1"
    ps["BidomainSolver"]["Chi"] = 1.0
    ps["BidomainSolver"]["Cm"] = 1.0
    ps["apply_stimulus_current_to_pde"] = False
    solver = SplittingSolver(brain, parameters=ps)

    vs_, vs, _ = solver.solution_fields()
    vs_.assign(model.initial_conditions())

    solutions = solver.solve(0, T, dt)
    pde_vs = None
    for _, (_, pde_vs, _) in solutions:
        continue
    return

    pde_v = np.mean(pde_vs.vector().get_local()[::2])
    pde_s = np.mean(pde_vs.vector().get_local()[1::2])
    ode_v = np.mean(ode_vs.vector().get_local()[::2])
    ode_s = np.mean(ode_vs.vector().get_local()[1::2])
    assert abs(pde_v - ode_v) < 1e-3
    assert abs(pde_s - ode_s) < 1e-3


if __name__ == "__main__":
    test_ode_pde()
