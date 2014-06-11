import sys
import os
import pytest
import beatadjoint
import dolfin_adjoint

# Automatically parallelize over all cpus
def pytest_cmdline_preparse(args):
    if 'xdist' in sys.modules: # pytest-xdist plugin
        import multiprocessing
        num = multiprocessing.cpu_count()
        args[:] = ["-n", str(num)] + args

del dolfin_adjoint.test_initial_condition_adjoint
del dolfin_adjoint.test_initial_condition_tlm
del dolfin_adjoint.test_scalar_parameters_adjoint
del dolfin_adjoint.test_initial_condition_adjoint_cdiff
del dolfin_adjoint.test_scalar_parameter_adjoint

default_params = beatadjoint.parameters.copy()
def pytest_runtest_setup(item):
    """ Hook function which is called before every test """

    # Reset dolfin parameter dictionary
    beatadjoint.parameters.update(default_params)

    # Reset adjoint state
    if beatadjoint.dolfin_adjoint:
        beatadjoint.adj_reset()
