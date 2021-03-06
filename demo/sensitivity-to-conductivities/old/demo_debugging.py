"""
Demo for propagation of electric potential through left and right
ventricles. Simplified version with no fibers/sheets/cross-sheets,
a simplified stimulus and a coarse mesh.
"""

__author__ = "Marie E. Rognes (meg@simula.no), 2012--2014"

import math
from cbcbeat import *
import time

def setup_application_parameters():
    # Setup application parameters and parse from command-line
    application_parameters = Parameters("Application")
    application_parameters.add("T", 420.0)      # End time  (ms)
    application_parameters.add("timestep", 1.0) # Time step (ms)
    application_parameters.add("directory", "debug-results")
    application_parameters.add("stimulus_amplitude", 30.0)
    application_parameters.add("healthy", False)
    application_parameters.add("cell_model", "FitzHughNagumo")
    application_parameters.parse()
    info(application_parameters, True)
    return application_parameters

def setup_general_parameters():
    # Adjust some general FEniCS related parameters
    parameters["form_compiler"]["cpp_optimize"] = True
    flags = ["-O3", "-ffast-math", "-march=native"]
    parameters["form_compiler"]["cpp_optimize_flags"] = " ".join(flags)
    parameters["form_compiler"]["quadrature_degree"] = 2

def setup_conductivities(mesh, application_parameters):

    chi = 1400. # (1./cm)
    C_m = 1.0   # (micro F/(cm^2))

    # Set-up expressions
    g_el = Expression("6.25/(C_m*chi)", C_m=C_m, chi=chi) # Fiber
    g_et = Expression("2.36/(C_m*chi)", C_m=C_m, chi=chi) # Fiber
    g_en = Expression("2.36/(C_m*chi)", C_m=C_m, chi=chi) # Fiber
    g_il = Expression("1.74/(C_m*chi)", C_m=C_m, chi=chi) # Fiber
    g_it = Expression("0.192/(C_m*chi)", C_m=C_m, chi=chi) # Fiber
    g_in = Expression("0.192/(C_m*chi)", C_m=C_m, chi=chi) # Fiber

    # Assign fields:
    V = FunctionSpace(mesh, "CG", 1)
    g_el_field = Function(V, name="g_el")
    g_el_field.assign(g_el)
    g_et_field = Function(V, name="g_et")
    g_et_field.assign(g_et)
    g_en_field = Function(V, name="g_en")
    g_en_field.assign(g_en)
    g_il_field = Function(V, name="g_il")
    g_il_field.assign(g_il)
    g_it_field = Function(V, name="g_it")
    g_it_field.assign(g_it)
    g_in_field = Function(V, name="g_in")
    g_in_field.assign(g_in)

    M_e = diag(as_vector([g_el_field, g_et_field, g_en_field]))
    M_i = diag(as_vector([g_il_field, g_it_field, g_in_field]))

    gs = (g_il_field, g_it_field, g_in_field,
          g_el_field, g_et_field, g_en_field)

    return (M_i, M_e, gs)

def setup_cell_model(params):

    option = params["cell_model"]
    if option == "FitzHughNagumo":
        # Setup cell model based on parameters from G. T. Lines, which
        # seems to be a little more excitable than the default
        # FitzHugh-Nagumo parameters from the Sundnes et al book.
        k = 0.00004; Vrest = -85.; Vthreshold = -70.;
        Vpeak = 40.; k = 0.00004; l = 0.63; b = 0.013; v_amp = Vpeak - Vrest
        cell_parameters = {"c_1": k*v_amp**2, "c_2": k*v_amp, "c_3": b/l,
                           "a": (Vthreshold - Vrest)/v_amp, "b": l,
                           "v_rest":Vrest, "v_peak": Vpeak}
        cell_model = FitzHughNagumoManual(cell_parameters)
    elif option == "tenTusscher":
        cell_model = Tentusscher_2004_mcell()
    else:
        error("Unrecognized cell model option: %s" % option)

    return cell_model

def setup_cardiac_model(application_parameters):

    # Initialize the computational domain in time and space
    time = Constant(0.0)
    mesh = Mesh("data/mesh115_coarse.xml.gz")
    mesh.coordinates()[:] /= 1000.0 # Scale mesh from micrometer to millimeter
    mesh.coordinates()[:] /= 10.0   # Scale mesh from millimeter to centimeter
    mesh.coordinates()[:] /= 4.0    # Scale mesh as indicated by Johan/Molly
    #plot(mesh, title="The computational domain")

    # Setup conductivities
    (M_i, M_e, gs) = setup_conductivities(mesh, application_parameters)

    # Setup cell model
    cell_model = setup_cell_model(application_parameters)

    # Define some simulation protocol (use cpp expression for speed)
    from stimulation import debug_stimulus
    pulse = Expression(debug_stimulus)
    amp = application_parameters["stimulus_amplitude"]
    pulse.amplitude = amp #
    pulse.duration = 10.0 # ms
    pulse.t = time        # ms

    # Initialize cardiac model with the above input
    plot(pulse, mesh=mesh)

    heart = CardiacModel(mesh, time, M_i, M_e, cell_model, stimulus={0:pulse})
    return (heart, gs)

def main(store_solutions=True):

    set_log_level(PROGRESS)

    begin("Setting up application parameters")
    application_parameters = setup_application_parameters()
    setup_general_parameters()
    end()

    begin("Setting up cardiac model")
    (heart, gs) = setup_cardiac_model(application_parameters)
    end()

    # Extract end time and time-step from application parameters
    T = application_parameters["T"]
    k_n = application_parameters["timestep"]

    # Since we know the time-step we want to use here, set it for the
    # sake of efficiency in the bidomain solver
    begin("Setting up splitting solver")
    params = SplittingSolver.default_parameters()
    params["theta"] = 1.0
    params["ode_solver_choice"] = "BasicCardiacODESolver"
    #params["ode_solver_choice"] = "CardiacODESolver" # Diverges after 2 steps
    params["BidomainSolver"]["linear_solver_type"] = "direct"
    params["BidomainSolver"]["default_timestep"] = k_n
    solver = SplittingSolver(heart, params=params)
    end()

    # Extract solution fields from solver
    (vs_, vs, vu) = solver.solution_fields()

    # Extract and assign initial condition
    vs_.assign(heart.cell_model().initial_conditions(), solver.VS)
    #vs.assign(heart.cell_model.initial_conditions(), solver.VS)

    # Store application parameters (arbitrary whether this works in
    # parallel!)
    directory = application_parameters["directory"]
    parametersfile = File("%s/parameters.xml" % directory)
    parametersfile << application_parameters

    # Setup pvd storage
    v_pvd = File("%s/v.pvd" % directory, "compressed")
    u_pvd = File("%s/u.pvd" % directory, "compressed")
    s_pvd = File("%s/s.pvd" % directory, "compressed")

    # Set-up solve
    solutions = solver.solve((0, T), k_n)

    # (Compute) and store solutions
    begin("Solving primal")
    start = time.time()
    timestep_counter = 1
    for (timestep, fields) in solutions:

        # Extract
        (vs_, vs, vu) = fields

        # Store xml
        if store_solutions:
            begin("Storing solutions...")
            vsfile = File("%s/vs_%d.xml.gz" % (directory, timestep_counter))
            vsfile << vs
            ufile = File("%s/vu_%d.xml.gz" % (directory, timestep_counter))
            ufile << vu

            # Extract subfields
            u = vu.split()[1]
            (v, s) = vs.split()

            # Store pvd of subfields
            v_pvd << v
            plot(v, interactive=True)
            # s_pvd << s
            # u_pvd << u
            end()

        timestep_counter += 1

    stop = time.time()
    print "Time elapsed: %g" % (stop - start)
    end()

    list_timings()

    return (gs, solver)

if __name__ == "__main__":
    main()
