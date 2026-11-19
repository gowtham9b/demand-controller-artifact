import timeit
import statistics

from sympy import symbols, Mul
from sympy.core.cache import clear_cache

def setup():
    global m
    clear_cache()
    m = Mul(*symbols('x:1000'))

def workload():
    global m
    m.is_zero

runtimes = timeit.repeat(workload, number=1, repeat=26, setup=setup)

print("Mean:", statistics.mean(runtimes[-25:]))
print("Std Dev:", statistics.stdev(runtimes[-25:]))
