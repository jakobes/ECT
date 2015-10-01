"""
Unit tests for various types of solvers for cardiac cell models.
"""

__author__ = "Marie E. Rognes (meg@simula.no), 2013, and Simon W. Funke (simon@simula.no) 2014"
__all__ = ["TestBidomainSolversAdjoint"]

import pytest
from testutils import assert_equal, fast, slow, \
        adjoint, parametrize, assert_greater

from cbcbeat.dolfinimport import info_green, info_red
from cbcbeat import BasicBidomainSolver, BidomainSolver, \
        UnitCubeMesh, Constant, Expression, inner, dx, dt, \
        assemble, parameters, Control, \
        replay_dolfin, Functional, FINISH_TIME, \
        compute_gradient_tlm, compute_gradient, \
        taylor_test, Function


class TestBidomainSolversAdjoint(object):
    """Test adjoint functionality for the basic bidomain solver."""

    def setup(self):
        self.mesh = UnitCubeMesh(5, 5, 5)
        self.time = Constant(0.0)

        # Create stimulus
        self.stimulus = Expression("2.0")

        # Create applied current
        self.applied_current = Expression("sin(2*pi*x[0])*t", t=self.time)

        # Create conductivity "tensors"
        self.M_i = 1.0
        self.M_e = 2.0

        self.t0 = 0.0
        self.dt = 0.1
        self.T = 5*self.dt

    def _setup_solver(self, Solver, solver_type, enable_adjoint=True):
        """Creates the bidomain solver."""

        # Create solver
        params = Solver.default_parameters()

        if Solver == BasicBidomainSolver:
            params.linear_variational_solver.linear_solver = \
                            "gmres" if solver_type == "iterative" else "lu"
            params.linear_variational_solver.krylov_solver.relative_tolerance = 1e-12
            params.linear_variational_solver.preconditioner = 'jacobi'
        else:
            params.linear_solver_type = solver_type
            params.enable_adjoint = enable_adjoint
            if solver_type == "iterative":
                params.krylov_solver.relative_tolerance = 1e-12
            else:
                params.use_avg_u_constraint = True  # NOTE: In contrast to iterative
                    # solvers, the direct solver does not handle nullspaces consistently,
                    # i.e. the solution differes from solve to solve, and hence the Taylor
                    # testes would not pass.

        self.solver = Solver(self.mesh, self.time, self.M_i, self.M_e,
                        I_s=self.stimulus,
                        I_a=self.applied_current, params=params)


    def _solve(self, ics=None):
        """ Runs the forward model with the basic bidomain solver. """
        print("Running forward basic model")

        (vs_, vs) = self.solver.solution_fields()

        solutions = self.solver.solve((self.t0, self.t0 + self.T), self.dt)

        # Set initial conditions
        if ics is not None:
            vs_.interpolate(ics)

        # Solve
        for (interval, fields) in solutions:
            pass

        return vs

    @adjoint
    @fast
    @parametrize(("Solver", "solver_type", "tol"), [
        (BasicBidomainSolver, "direct", 0.),
        (BasicBidomainSolver, "iterative", 0.),
        (BidomainSolver, "direct", 0.),
        (BidomainSolver, "iterative", 1e-10),  # NOTE: The replay is not exact because
            # dolfin-adjoint's overloaded Krylov method is not constent with DOLFIN's
            # (it orthogonalizes the rhs vector as an additional step)
        ])
    def test_replay(self, Solver, solver_type, tol):
        "Test that replay of basic bidomain solver reports success."

        self._setup_solver(Solver, solver_type)
        self._solve()

        # Check replay
        info_green("Running replay basic (%s)" % solver_type)
        success = replay_dolfin(stop=True, tol=tol)
        assert_equal(success, True)

    def tlm_adj_setup(self, Solver, solver_type):
        """ Common code for test_tlm and test_adjoint. """
        self._setup_solver(Solver, solver_type)
        self._solve()
        (vs_, vs) = self.solver.solution_fields()

        # Define functional
        form = lambda w: inner(w, w)*dx
        J = Functional(form(vs)*dt[FINISH_TIME])
        m = Control(vs_)

        # Compute value of functional with current ics
        Jics = assemble(form(vs))

        # Define reduced functional
        def Jhat(ics):
            self._setup_solver(Solver, solver_type, enable_adjoint=False)
            vs = self._solve(ics)
            return assemble(form(vs))

        # Stop annotating
        parameters["adjoint"]["stop_annotating"] = True

        return J, Jhat, m, Jics


    @adjoint
    @slow
    @parametrize(("Solver", "solver_type"), [
        (BasicBidomainSolver, "direct"),
        (BasicBidomainSolver, "iterative"),
        (BidomainSolver, "iterative"),
        (BidomainSolver, "direct")
        ])
    def test_tlm(self, Solver, solver_type):
        """Test that tangent linear model of basic bidomain solver converges at 2nd order."""
        info_green("Running tlm basic (%s)" % solver_type)

        J, Jhat, m, Jics = self.tlm_adj_setup(Solver, solver_type)

        # Check TLM correctness
        dJdics = compute_gradient_tlm(J, m, forget=False)
        assert (dJdics is not None), "Gradient is None (#fail)."
        conv_rate_tlm = taylor_test(Jhat, m, Jics, dJdics)

        # Check that minimal convergence rate is greater than some given number
        assert_greater(conv_rate_tlm, 1.9)


    @adjoint
    @slow
    @parametrize(("Solver", "solver_type"), [
        (BasicBidomainSolver, "direct"),
        (BasicBidomainSolver, "iterative"),
        (BidomainSolver, "iterative"),
        (BidomainSolver, "direct"),
        ])
    def test_adjoint(self, Solver, solver_type):
        """Test that adjoint model of basic bidomain solver converges at 2nd order."""
        info_green("Running adjoint basic (%s)" % solver_type)

        J, Jhat, m, Jics = self.tlm_adj_setup(Solver, solver_type)

        # Check adjoint correctness
        dJdics = compute_gradient(J, m, forget=False)
        assert (dJdics is not None), "Gradient is None (#fail)."
        conv_rate = taylor_test(Jhat, m, Jics, dJdics, seed=1e-3)

        # Check that minimal convergence rate is greater than some given number
        assert_greater(conv_rate, 1.9)
