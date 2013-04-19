"""
Demo for propagation of electric potential through left and right
ventricles.
"""

# Marie E. Rognes <meg@simula.no>
# Last changed: 2012-10-27

import math
from dolfin import *
from dolfin_adjoint import *
from beatadjoint import *
import time

set_log_level(PROGRESS)

# Setup application parameters and parse from command-line
application_parameters = Parameters("Application")
application_parameters.add("T", 200.0)      # End time  (ms)
application_parameters.add("timestep", 1.0) # Time step (ms)
application_parameters.add("directory", "default-adjoint-results")
application_parameters.add("backend", "PETSc")
application_parameters.add("stimulus_amplitude", 30.0)
application_parameters.add("use_avg_u", False)
application_parameters.add("functional", "default")
application_parameters.parse()
info(application_parameters, True)

# Update backend from application parameters
parameters["linear_algebra_backend"] = application_parameters["backend"]

# Adjust some general parameters
parameters["reorder_dofs_serial"] = False # Crucial!
parameters["form_compiler"]["cpp_optimize"] = True
parameters["form_compiler"]["optimize"] = True

# Generic cardiac parameters
#chi = 1400.0   # Membrane surface-to-volume ratio (1/cm)
# NB : If not 1 => must scale ionic current! see book p. 55
#C_m = 1.0      # Membrane capacitance per unit area (micro F/(cm^2))

# Initialize domain
mesh = Mesh("data/mesh115_refined.xml.gz")
mesh.coordinates()[:] /= 1000.0 # Scale mesh from micrometer to millimeter
mesh.coordinates()[:] /= 10.0   # Scale mesh from millimeter to centimeter
mesh.coordinates()[:] /= 4.0    # Scale mesh as indicated by Johan/Molly

# Extract time and time-step
T = application_parameters["T"]
k_n = application_parameters["timestep"]

# Load fibers and sheets
Vv = VectorFunctionSpace(mesh, "DG", 0)
fiber = Function(Vv)
File("data/fibers.xml.gz") >> fiber
sheet = Function(Vv)
File("data/sheet.xml.gz") >> sheet
cross_sheet = Function(Vv)
File("data/cross_sheet.xml.gz") >> cross_sheet

# Extract conductivity data
V = FunctionSpace(mesh, "CG", 1)
g_el_field = Function(V, "data/g_el_field.xml.gz", name="g_el_field")
g_et_field = Function(V, "data/g_et_field.xml.gz", name="g_et_field")
g_il_field = Function(V, "data/g_il_field.xml.gz", name="g_il_field")
g_it_field = Function(V, "data/g_it_field.xml.gz", name="g_it_field")

# Construct conductivity tensors from directions and conductivity
# values relative to that coordinate system
A = as_matrix([[fiber[0], sheet[0], cross_sheet[0]],
               [fiber[1], sheet[1], cross_sheet[1]],
               [fiber[2], sheet[2], cross_sheet[2]]])
M_e_star = diag(as_vector([g_el_field, g_et_field, g_et_field]))
M_i_star = diag(as_vector([g_il_field, g_it_field, g_it_field]))
M_e = A*M_e_star*A.T
M_i = A*M_i_star*A.T

# Model of the whole heart given a cell-model, using the above domain
# and conductivities
class MyHeart(CardiacModel):
    def __init__(self, cell_model):
        CardiacModel.__init__(self, cell_model)
    def domain(self):
        return mesh
    def conductivities(self):
        return (M_i, M_e)

# Setup cell model based on parameters from Glenn, which seems to be a
# little more excitable than the default FitzHugh-Nagumo parameters
# from the book.
k = 0.00004; Vrest = -85.; Vthreshold = -70.;
Vpeak = 40.; k = 0.00004; l = 0.63; b = 0.013; v_amp = Vpeak - Vrest
cell_parameters = {"c_1": k*v_amp**2, "c_2": k*v_amp, "c_3": b/l,
                   "a": (Vthreshold - Vrest)/v_amp, "b": l,
                   "v_rest":Vrest, "v_peak": Vpeak}
cell = OriginalFitzHughNagumo(cell_parameters)
heart = MyHeart(cell)

# Define some simulation protocol (use cpp expression for speed)
stimulation_cells = MeshFunction("uint", mesh, "data/stimulation_cells.xml.gz")
from stimulation import cpp_stimulus
pulse = Expression(cpp_stimulus)
pulse.cell_data = stimulation_cells
amp = application_parameters["stimulus_amplitude"]
pulse.amplitude = amp #
pulse.duration = 10.0 # ms
pulse.t = 0.0         # ms

heart.stimulus = pulse

# Set-up solver
begin("Setting-up solver")
Solver = SplittingSolver
ps = Solver.default_parameters()
ps["use_avg_u_constraint"] = application_parameters["use_avg_u"] # NB!
ps["default_timestep"] = k_n
ps["enable_adjoint"] = True
ps["linear_variational_solver"]["linear_solver"] = "direct"
solver = Solver(heart, parameters=ps)
end()

# Define initial condition here (no need to annotate this step)
begin("Projecting initial condition")
ic = project(cell.initial_conditions(), solver.VS, annotate=False)
end()

# Assign initial condition
(vs_, vs, u) = solver.solution_fields()
vs_.adj_name = "vs_"
vs.adj_name = "vs"
u.adj_name = "u"
vs_.assign(ic, annotate=True)

# Store application parameters (arbitrary whether this works in
# parallel!)
directory = application_parameters["directory"]
parametersfile = File("%s/parameters.xml" % directory)
parametersfile << application_parameters

# Set-up solve
solutions = solver.solve((0, T), k_n)

# (Compute) and store solutions
begin("Solving primal")
start = time.time()
timestep_counter = 1
for (timestep, vs, u) in solutions:

    # Store xml.gz
    vsfile = File("%s/vs_%d.xml.gz" % (directory, timestep_counter))
    vsfile << vs
    ufile = File("%s/u_%d.xml.gz" % (directory, timestep_counter))
    ufile << u

    timestep_counter += 1

(v, s) = split(vs)

stop = time.time()
forward_time = (stop - start)
end()

# Store
adj_html("%s/forward.html" % directory, "forward")
adj_html("%s/adjoint.html" % directory, "adjoint")

## Functional B: Average L^2(O) difference, at given "interesting"
## time, between the unhealthy and healthy transmembrane potential (v)
if application_parameters["functional"] == "ill-versus-healthy":
    info_green("Using ill-versus-healthy functional")
    # Extract synthetic observed data:
    vs_obs = Function(solver.VS, name="vs_obs")
    File("data/vs_healthy_T200.xml.gz") >> vs_obs
    v_obs = split(vs_obs)[0]
    J = Functional(inner(v - v_obs, v - v_obs)*dx*dt[FINISH_TIME])

## Default functional: Average surface transmembrane potential over time
else:
    info_green("Using default (average surface) functional")
    J = Functional(inner(v, v)*ds*dt)

# Define variables that we want to differentiate with respect to (all
# conductivities)
variables = [g_el_field, g_et_field, g_il_field, g_it_field]
icvariables = [InitialConditionParameter(v) for v in variables]

# Compute the gradient
info_blue("Computing gradient")
start = time.time()
dJdg_s = compute_gradient(J, icvariables, forget=False)
stop = time.time()
gradient_time = (stop - start)

# Store the results
for (i, dJdg) in enumerate(dJdg_s):
    name = variables[i].adj_name
    #plot(dJdg, title="%s" % name)
    file = File("%s/%s_sensitivity.xml.gz" % (directory, name))
    file << dJdg

# Output some timings
print "Time for forward problem: %g" % (forward_time)
print "Time for computing gradient: %g" % (gradient_time)
list_timings()

#interactive()
