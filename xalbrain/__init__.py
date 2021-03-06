"""
The xalbrain Python module is a problem and solver collection for
cardiac electrophysiology models.

To import the module, type::

  from xalbrain import *

"""

# Model imports
from xalbrain.cellmodels import *

from xalbrain.markerwisefield import rhs_with_markerwise_field
from xalbrain.models import Model

# Solver imports
from xalbrain.splittingsolver import (
    BasicSplittingSolver,
    SplittingSolver,
    MultiCellSplittingSolver,
)
from xalbrain.cellsolver import (
    BasicSingleCellSolver,
    SingleCellSolver,
    BasicCardiacODESolver,
    CardiacODESolver,
    MultiCellSolver,
    SingleMultiCellSolver,
)

from xalbrain.bidomainsolver import (
    BasicBidomainSolver,
    BidomainSolver
)

from xalbrain.monodomainsolver import (
    BasicMonodomainSolver,
    MonodomainSolver
)

# Various utility functions, mainly for internal use
from xalbrain.utils import (
    split_function,
    state_space,
    Projecter,
    time_stepper,
    import_extension_modules
)
