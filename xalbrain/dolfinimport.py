"""Allow for * import from dolfin with some degree of control."""

import dolfin

from dolfin import (
    Mesh,
    Constant,
    Parameters,
    FacetFunction,
    lhs,
    rhs,
    debug,
    Expression,
    Function,
    VectorSpaceBasis,
    LinearVariationalProblem,
    inner,
    grad,
    LinearVariationalSolver,
    Measure,
    assemble,
    system,
    TrialFunction,
    TestFunction,
    PETScKrylovSolver,
    LUSolver,
    TrialFunctions,
    TestFunctions,
    FunctionAssigner,
    Timer,
    info,
    MeshFunction,
    FiniteElement,
    FunctionSpace,
    MixedElement,
    CellFunction,
    dx,
    error,
    GenericFunction,
    VectorFunctionSpace,
    DirichletBC,
    solve,
    parameters,
    NonlinearVariationalSolver,
    NonlinearVariationalProblem,
    KrylovSolver,
    info_blue,
    begin,
    end,
    PROGRESS,
    derivative,
    Vector,
    as_backend_type,
)


try:
    import dolfin_adjoint
except:
    dolfin_adjoint = None


__all__ = [
    "dolfin",
    "Mesh",
    "Constant",
    "Parameters",
    "FacetFunction",
    "lhs",
    "rhs",
    "debug",
    "Expression",
    "Function",
    "VectorSpaceBasis",
    "LinearVariationalProblem",
    "inner",
    "grad",
    "LinearVariationalSolver",
    "Measure",
    "assemble",
    "system",
    "TrialFunction",
    "TestFunction",
    "PETScKrylovSolver",
    "LUSolver",
    "TrialFunctions",
    "TestFunctions",
    "FunctionAssigner",
    "Timer",
    "info",
    "MeshFunction",
    "FiniteElement",
    "FunctionSpace",
    "MixedElement",
    "CellFunction",
    "dx",
    "error",
    "GenericFunction",
    "VectorFunctionSpace",
    "DirichletBC",
    "solve",
    "parameters",
    "NonlinearVariationalSolver",
    "NonlinearVariationalProblem",
    "KrylovSolver",
    "info_blue",
    "begin",
    "end",
    "PROGRESS",
    "derivative",
    "Vector",
    "dolfin_adjoint",
    "as_backend_type",
]