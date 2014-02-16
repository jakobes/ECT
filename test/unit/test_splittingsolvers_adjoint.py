"""
Unit tests for various types of bidomain solver
"""

__author__ = "Simon W. Funke (simon@simula.no) \
        and Marie E. Rognes (meg@simula.no), 2014"
__all__ = ["TestSplittingSolverAdjoint"]

from testutils import assert_greater, medium, slow, parametrize

from dolfin import info_green, set_log_level, WARNING
from beatadjoint import CardiacModel, \
    BasicSplittingSolver, SplittingSolver, \
    FitzHughNagumoManual, \
    Constant, Expression, UnitCubeMesh, \
    replay_dolfin, Functional, assemble, \
    inner, dx, dt, FINISH_TIME, InitialConditionParameter, parameters, \
    compute_gradient_tlm, compute_gradient, taylor_test

set_log_level(WARNING)


def generate_solver(Solver, ics=None, enable_adjoint=True):

    class SolverWrapper(object):
        def __init__(self):
            self.mesh = UnitCubeMesh(5, 5, 5)

            # Create time
            self.time = Constant(0.0)

            # Create stimulus
            # NOTE: 0 domain is the whole domain
            self.stimulus = {0: Expression("2.0*t", t=self.time)}

            # Create ac
            self.applied_current = Expression("sin(2*pi*x[0])*t", t=self.time)

            # Create conductivity "tensors"
            self.M_i = 1.0
            self.M_e = 2.0

            self.cell_model = FitzHughNagumoManual()
            self.cardiac_model = CardiacModel(self.mesh, self.time,
                                              self.M_i, self.M_e,
                                              self.cell_model,
                                              self.stimulus,
                                              self.applied_current)

            dt = 0.1
            self.t0 = 0.0
            if Solver == SplittingSolver:
                # FIXME: Dolfin-adjoint fails with adaptive timestep and SplittingSolver
                self.dt = dt
            else:
                self.dt = [(0.0, dt), (dt*2, dt/2), (dt*4, dt)]
            # Test using variable dt interval but using the same dt.

            self.T = self.t0 + 5*dt

            # Create solver object
            params = Solver.default_parameters()
            
            if Solver == SplittingSolver:
                params.enable_adjoint = enable_adjoint
                params.BidomainSolver.linear_solver_type = 'direct'
                params.BidomainSolver.use_avg_u_constraint = True

            self.solver = Solver(self.cardiac_model, params=params)
            (vs_, vs, vur) = self.solver.solution_fields()

            if ics is None:
                self.ics = self.cell_model.initial_conditions()
                vs_.assign(self.ics)
            else:
                vs_.vector()[:] = ics.vector()

        def run_forward_model(self):

            solutions = self.solver.solve((self.t0, self.T), self.dt)
            for (interval, fields) in solutions:
                pass
            (vs_, vs, vur) = self.solver.solution_fields()

            return vs_, vs

    return SolverWrapper()


class TestSplittingSolverAdjoint(object):
    "Test adjoint functionality for the splitting solvers."

    def tlm_adj_setup(self, Solver):
        """ Common code for test_tlm and test_adjoint. """
        wrap = generate_solver(Solver)
        vs_, vs = wrap.run_forward_model()

        # Define functional
        form = lambda w: inner(w, w)*dx
        J = Functional(form(vs)*dt[FINISH_TIME])
        if Solver == SplittingSolver:
            m = InitialConditionParameter(vs)
        else:
            m = InitialConditionParameter(vs_)

        # Compute value of functional with current ics
        Jics = assemble(form(vs))

        # Define reduced functional
        def Jhat(ics):
            wrap = generate_solver(Solver, ics=ics, enable_adjoint=False)
            vs_, vs = wrap.run_forward_model()

            return assemble(form(vs))

        # Stop annotating
        parameters["adjoint"]["stop_annotating"] = True

        return J, Jhat, m, Jics

    @medium
    @parametrize("Solver", [BasicSplittingSolver, SplittingSolver])
    def test_ReplayOfSplittingSolver_IsExact(self, Solver):
        """Test that basic and optimised splitting solvers yield
        very comparative results when configured identically."""

        self.tlm_adj_setup(Solver)

        info_green("Replaying")
        success = replay_dolfin(tol=0, stop=True)
        assert success

    @slow
    @parametrize("Solver", [BasicSplittingSolver, SplittingSolver])
    def test_TangentLinearModelOfSplittingSolver_PassesTaylorTest(self, Solver):
        """Test that basic and optimised splitting solvers yield
        very comparative results when configured identically."""

        J, Jhat, m, Jics = self.tlm_adj_setup(Solver)

        # Check TLM correctness
        info_green("Compute gradient with tangent linear model")
        dJdics = compute_gradient_tlm(J, m, forget=False)

        assert (dJdics is not None), "Gradient is None (#fail)."
        conv_rate_tlm = taylor_test(Jhat, m, Jics, dJdics)

        # Check that minimal convergence rate is greater than some given number
        assert_greater(conv_rate_tlm, 1.9)

    @slow
    @parametrize("Solver", [BasicSplittingSolver, SplittingSolver])
    def test_AdjointModelOfSplittingSolver_PassesTaylorTest(self, Solver):
        """Test that basic and optimised splitting solvers yield
        very comparative results when configured identically."""

        J, Jhat, m, Jics = self.tlm_adj_setup(Solver)

        # Check adjoint model correctness
        info_green("Compute gradient with adjoint linear model")
        dJdics = compute_gradient(J, m, forget=False)

        assert (dJdics is not None), "Gradient is None (#fail)."
        conv_rate = taylor_test(Jhat, m, Jics, dJdics)

        # Check that minimal convergence rate is greater than some given number
        assert_greater(conv_rate, 1.9)
