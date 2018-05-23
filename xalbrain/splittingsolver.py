"""This module contains splitting solvers for CardiacModel objects. 
In particular, the classes

  * SplittingSolver
  * BasicSplittingSolver

These solvers solve the bidomain (or monodomain) equations on the
form: find the transmembrane potential :math:`v = v(x, t)` in mV, the
extracellular potential :math:`u = u(x, t)` in mV, and any additional
state variables :math:`s = s(x, t)` such that

.. math::

   v_t - \mathrm{div} (M_i \mathrm{grad} v + M_i \mathrm{grad} u) = - I_{ion}(v, s) + I_s

         \mathrm{div} (M_i \mathrm{grad} v + (M_i + M_e) \mathrm{grad} u) = I_a

   s_t = F(v, s)

where

  * the subscript :math:`t` denotes the time derivative,
  * :math:`M_i` and :math:`M_e` are conductivity tensors (in mm^2/ms)
  * :math:`I_s` is prescribed input current (in mV/ms)
  * :math:`I_a` is prescribed input current (in mV/ms)
  * :math:`I_{ion}` and :math:`F` are typically specified by a cell model

Note that M_i and M_e can be viewed as scaled by :math:`\chi*C_m` where
  * :math:`\chi` is the surface-to volume ratio of cells (in 1/mm) ,
  * :math:`C_m` is the specific membrane capacitance (in mu F/(mm^2) ),

In addition, initial conditions are given for :math:`v` and :math:`s`:

.. math::

   v(x, 0) = v_0

   s(x, 0) = s_0

Finally, boundary conditions must be prescribed. These solvers assume
pure Neumann boundary conditions for :math:`v` and :math:`u` and
enforce the additional average value zero constraint for u.

The solvers take as input a
:py:class:`~xalbrain.cardiacmodels.CardiacModel` providing the
required input specification of the problem. In particular, the
applied current :math:`I_a` is extracted from the
:py:attr:`~xalbrain.cardiacmodels.CardiacModel.applied_current`
attribute, while the stimulus :math:`I_s` is extracted from the
:py:attr:`~xalbrain.cardiacmodels.CardiacModel.stimulus` attribute.

It should be possible to use the solvers interchangably. However, note
that the BasicSplittingSolver is not optimised and should be used for
testing or debugging purposes primarily.
"""

# Copyright (C) 2012-2013 Marie E. Rognes (meg@simula.no)
# Use and modify at will
# Last changed: 2013-04-15

__all__ = ["SplittingSolver", "BasicSplittingSolver",]

from xalbrain.dolfinimport import *
from xalbrain import CardiacModel

from xalbrain.cellsolver import (
    BasicCardiacODESolver,
    CardiacODESolver,
)

from xalbrain.bidomainsolver import (
    BasicBidomainSolver,
    BidomainSolver,
)

from xalbrain.monodomainsolver import (
    BasicMonodomainSolver,
    MonodomainSolver,
)

from xalbrain.utils import (
    state_space,
    TimeStepper,
    annotate_kwargs,
)

from xalbrain.parameters import (
    SplittingParameters,
    BidomainParameters,
    MonodomainParameters,
    SingleCellParameters,
    KrylovParameters,
    LUParameters
)

import numpy as np

from typing import (
    Any,
    Tuple,
    Union,
    Generator
)


class SplittingSolver:
    """
    A non-optimised solver for the bidomain equations based on the
    operator splitting scheme described in Sundnes et al 2006, p. 78
    ff.

    The solver computes as solutions:

      * "vs" (:py:class:`dolfin.Function`) representing the solution
        for the transmembrane potential and any additional state
        variables, and
      * "vur" (:py:class:`dolfin.Function`) representing the
        transmembrane potential in combination with the extracellular
        potential and an additional Lagrange multiplier.

    The algorithm can be controlled by a number of parameters. In
    particular, the splitting algorithm can be controlled by the
    parameter "theta": "theta" set to 1.0 corresponds to a (1st order)
    Godunov splitting while "theta" set to 0.5 to a (2nd order) Strang
    splitting.

    This solver has not been optimised for computational efficiency
    and should therefore primarily be used for debugging purposes. For
    an equivalent, but more efficient, solver, see
    :py:class:`xalbrain.splittingsolver.SplittingSolver`.

    *Arguments*
      model (:py:class:`xalbrain.cardiacmodels.CardiacModel`)
        a CardiacModel object describing the simulation set-up
      params (:py:class:`dolfin.Parameters`, optional)
        a Parameters object controlling solver parameters

    *Assumptions*
      * The cardiac conductivities do not vary in time

    """
    def __init__(
            self,
            model: CardiacModel,
            parameters: SplittingParameters,
            pde_parameters: BidomainParameters,
            ode_parameters: SingleCellParameters,
            linear_solver_parameters: Union[KrylovParameters, LUParameters]
    ) -> None:
        """Create solver from given Cardiac Model and (optional) parameters."""
        # Set model and parameters
        self._model = model
        self.parameters = parameters
        self.pde_parameters = pde_parameters
        self.ode_parameters = ode_parameters
        self.linear_solver_parameters = linear_solver_parameters

        msg = "Got two different values for theta."
        assert self.parameters.theta == self.pde_parameters.theta, msg

        # Extract solution domain
        self._domain = self._model.mesh
        self._time = self._model.time()

        # Create ODE solver and extract solution fields
        self.ode_solver = self._create_ode_solver()
        self.vs_, self.vs = self.ode_solver.solution_fields()
        self.VS = self.vs.function_space()

        # Create PDE solver and extract solution fields
        self.pde_solver = self._create_pde_solver()
        self.v_, self.vur = self.pde_solver.solution_fields()

        # # Create function assigner for merging v from self.vur into self.vs[0]
        if self.pde_parameters.solver in ("BasicBidomainSolver", "BidomainSolver"):
            V = self.vur.function_space().sub(0)
        else:
            V = self.vur.function_space()

        self.merger = FunctionAssigner(self.VS.sub(0), V)

        self._annotate_kwargs = annotate_kwargs(self.parameters)

    def _create_ode_solver(self) -> BasicCardiacODESolver:
        """
        Helper function to initialize a suitable ODE solver from
        the cardiac model.
        """
        # Extract cardiac cell model from cardiac model
        cell_model = self._model.cell_models()

        # Extract stimulus from the cardiac model(!)
        if self.parameters.apply_stimulus_current_to_pde:
            stimulus = None     # Apply stimulus to PDE. Set ODE stimulus to None
        else:
            stimulus = self._model.stimulus()

        # # Extract ode solver parameters
        # params = self.oparameters["BasicCardiacODESolver"]
        # # Propagate enable_adjoint to Bidomain solver
        # if params.has_key("enable_adjoint"):
        #     params["enable_adjoint"] = self.parameters["enable_adjoint"]

        if self.ode_parameters.solver == "BasicCardiacODESolver":
            solver_class = BasicCardiacODESolver
        elif self.ode_parameters.solver == "CardiacODESolver":
            solver_class = CardiacODESolver

        solver = solver_class(
            self._domain,
            self._time,
            cell_model,
            parameters = self.ode_parameters,
            I_s = stimulus,
        )
        return solver

    def _create_pde_solver(self) -> Union[BasicMonodomainSolver, BasicBidomainSolver]:
        """
        Helper function to initialize a suitable PDE solver from
        the cardiac model.
        """
        # FIXME: Not happy about this

        # Extract applied current from the cardiac model
        applied_current = self._model.applied_current()
        ect_current =  self._model.ect_current

        # Extract stimulus from the cardiac model if we should apply
        # it to the PDEs (in the other case, it is handled by the ODE solver)
        if self.parameters.apply_stimulus_current_to_pde:
            stimulus = self._model.stimulus()
        else:
            stimulus = None     # Apply stimulus to ODE. Set PDE stimulus to None

        # Extract conductivities from the cardiac model
        M_i, M_e = self._model.conductivities()

        if self.pde_parameters.solver in ("BasicBidomainSolver", "BidomainSolver"):
            if self.pde_parameters.solver == "BasicBidomainSolver":
                PDESolver = BasicBidomainSolver
            if self.pde_parameters.solver == "BidomainSolver":
                PDESolver = BidomainSolver

            kwargs = dict(
                mesh = self._domain,
                time = self._time,
                M_i = M_i,
                M_e = M_e,
                parameters = self.pde_parameters,
                linear_solver_parameters = self.linear_solver_parameters,
                I_s = stimulus,
                I_a = applied_current,
                ect_current = ect_current,
                v_ = self.vs[0],
                cell_domains = self._model.cell_domains(),
                facet_domains = self._model.facet_domains(),
            )
        else:
            if self.pde_parameters.solver == "BasicMonodomainSolver":
                PDESolver = BasicMonodomainSolver
            if self.pde_parameters.solver == "MonodomainSolver":
                PDESolver = MonodomainSolver

            kwargs = dict(
                mesh = self._domain,
                time = self._time,
                M_i = M_i,
                parameters = self.pde_parameters,
                linear_solver_parameters = self.linear_solver_parameters,
                I_s = stimulus,
                v_ = self.vs[0]
            )

        return PDESolver(**kwargs)

    def solution_fields(self) -> Tuple[Function, Function, Function]:
        """
        Return tuple of previous and current solution objects.

        Modifying these will modify the solution objects of the solver
        and thus provides a way for setting initial conditions for
        instance.

        *Returns*
          (previous vs, current vs, current vur) (:py:class:`tuple` of :py:class:`dolfin.Function`)
        """
        return self.vs_, self.vs, self.vur

    def solve(
            self,
            interval: Tuple[float, float],
            dt: float
    ) -> Generator[Tuple[Tuple[float, float], Tuple[Function, Function, Function]], None, None]:
        """
        Solve the problem given by the model on a time interval with a given time step.
        Return a generator for a tuple of the time step and the solution fields.

        Arguments:
            interval: The time interval for the solve given by (t0, t1).
            dt: The timestep for the solve.

        Returns:
          (timestep, solution_fields)

        *Example of usage*::

          # Create generator
          dt = 1e-3
          solutions = solver.solve((0.0, 1.0), dt)

          # Iterate over generator (computes solutions as you go)
          for ((t0, t1), (vs_, vs, vur)) in solutions:
            # do something with the solutions
        """
        # Create timestepper
        time_stepper = TimeStepper(interval, dt)

        for t0, t1 in time_stepper:
            info_blue("Solving on t = ({:g}, {:g})".format(t0, t1))
            self.step((t0, t1))

            # Yield solutions
            yield (t0, t1), self.solution_fields()

            # Update previous solution
            self.vs_.assign(self.vs)

    def step(self, interval: Tuple[float, float]) -> None:
        """Solve the pde for one time step.

        Arguments:
            interval: The time interval for the solve given by (t0, t1).

        Invariants:
            Given self._vs in a correct state at t0, provide v and s (in
            self.vs) and u (in self.vur) in a correct state at t1. (Note
            that self.vur[0] == self.vs[0] only if theta = 1.0.).
        """
        # Extract some parameters for readability
        theta = self.parameters.theta

        # Extract time domain
        t0, t1 = interval
        dt = t1 - t0
        t = t0 + theta*dt

        # Compute tentative membrane potential and state (vs_star)
        begin(PROGRESS, "Tentative ODE step")
        # Assumes that its vs_ is in the correct state, gives its vs
        # in the current state
        self.ode_solver.step((t0, t))
        end()

        # Compute tentative potentials vu = (v, u)
        begin(PROGRESS, "PDE step")
        # Assumes that its vs_ is in the correct state, gives vur in
        # the current state
        self.pde_solver.step((t0, t1))
        end()

        # If first order splitting, we need to ensure that self.vs is
        # up to date, but otherwise we are done.
        if theta == 1.0:
            # Assumes that the v part of its vur and the s part of its
            # vs are in the correct state, provides input argument(in
            # this case self.vs) in its correct state
            self.merge(self.vs)
            return

        # Otherwise, we do another ode_step:
        begin(PROGRESS, "Corrective ODE step")

        # Updates vs_ based on vs, the s part of vs and vs_ are now in the correct state
        self.vs_.assign(self.vs)

        # Assumes that the v part of its vur and the s part of its vs
        # are in the correct state, provides input argument (in this
        # case self.vs_) in its correct state
        self.merge(self.vs_)    # self.vs_.sub(0) <- self.vur.sub(0)
        # FIXME: Missing vs.assign(vs_)?
        # Assumes that its vs_ is in the correct state, provides vs in
        # the correct state
        self.ode_solver.step((t, t1))
        self.vs_.assign(self.vs)
        end()

    def merge(self, solution: Function) -> None:
        """Combine solutions from the PDE and the ODE to form a single mixed function.

        *Arguments*
          solution (:py:class:`dolfin.Function`)
            Function holding the combined result
        """
        timer = Timer("Merge step")

        begin(PROGRESS, "Merging")
        if self.pde_parameters.solver in ("BasicBidomainSolver", "BidomainSolver"):
            v = self.vur.sub(0)
        else:
            v = self.vur
        self.merger.assign(solution.sub(0), v, **self._annotate_kwargs)
        end()

        timer.stop()
