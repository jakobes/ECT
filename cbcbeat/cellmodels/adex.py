"""This module contains a AdEx neuronal cell model

The module was written by hand, in particular it was not
autogenerated.
"""

from __future__ import division

__author__ = "Jakob E. Schrein (jakob@xal.no), 2017"
__all__ = ["AdExManual"]

from collections import OrderedDict
from cbcbeat.dolfinimport import Parameters, Expression
from cbcbeat.cellmodels import CardiacCellModel

from dolfin import exp, assign, conditional, lt

import numpy as np


class AdExManual(CardiacCellModel):
    """
    FIXME: add reference for AdEx

    This is a model containing two nonlinear, ODEs for the evolution
    of the transmembrane potential v and one additional state variable
    w.

    TODO: Update routine might be slow
    """
    def __init__(self, params=None, init_conditions=None):
        "Create neuronal cell model, optionally from given parameters."
        CardiacCellModel.__init__(self, params, init_conditions)

    @staticmethod
    def default_parameters():
        "Set-up and return default parameters."
        params = OrderedDict([("C", 281),           # Membrane capacitance (pF)
                              ("g_L", 30),          # Leak conductance (nS)
                              ("E_L", -70.6),       # Leak reversal potential (mV)
                              ("V_T", -50.4),       # Spike threshold (mV)
                              ("Delta_T", 2),       # Slope factor (mV)
                              ("tau_w", 144),       # Adaptation time constant (ms)
                              ("a", 4),             # Subthreshold adaptation (nS)
                              ("spike", 20),        # When to reset (mV)
                              ("b", 0.0805)])       # Spike-triggered adaptation (nA)
        return params

    def I(self, V, w, time=None):
        "Return the ionic current."

        # Extract parameters
        C = self._parameters["C"]
        g_L = self._parameters["g_L"]
        E_L = self._parameters["E_L"]
        V_T = self._parameters["V_T"]
        Delta_T = self._parameters["Delta_T"]
        spike = self._parameters["spike"]
        tol = 0

        # Add set I to 0 if V -> \infty, this will still trigger a reset
        I = conditional(lt(V, spike + tol), 1./C*(g_L*Delta_T*exp((V - V_T)/Delta_T) -
                                                  g_L*(V - E_L) - w), 0)
        return -I

    def F(self, V, w, time=None):
        "Return right-hand side for state variable evolution."

        # Extract parameters

        a = self._parameters["a"]
        E_L = self._parameters["E_L"]
        tau_w = self._parameters["tau_w"]

        # Define model
        F = 1./tau_w*(a*(V - E_L) - w)
        return -F

    #@staticmethod
    def default_initial_conditions(self):
        """ Return default intial conditions. FIXME: I have no idea about values
        """
        ic = OrderedDict([("V", self._parameters["E_L"]),
                          ("w", 0.0)])
        return ic

    def num_states(self):
        "Return number of state variables."
        return 1

    def update(self, vs):
        spike = self._parameters["spike"]
        E_L = self._parameters["E_L"]
        b = self._parameters["b"]
        v, s = vs.split(deepcopy=True)
        v_idx = v.vector().array() > spike

        v.vector()[v_idx] = E_L
        s.vector()[v_idx] += b
        assign(vs.sub(0), v)
        assign(vs.sub(1), s)

        if np.sum(v_idx) > 0:
            print(" *** Spike *** ")

    def __str__(self):
        "Return string representation of class."
        return "(Manual) AdEx neuronal cell model"
