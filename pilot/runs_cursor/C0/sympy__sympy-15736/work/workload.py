import timeit
import statistics
from sympy.matrices import matrix_multiply_elementwise
from sympy.matrices import Matrix
from sympy.core.cache import clear_cache

def setup():
    global A, B
    clear_cache()
    A = Matrix([[0, 1, 2], [3, 4, 5]])
    B = Matrix([[1, 10, 100], [100, 10, 1]])

def workload():
    global A, B
    _ = matrix_multiply_elementwise(A, B)

runtimes = timeit.repeat(workload, number=5, repeat=1000, setup=setup)

print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))