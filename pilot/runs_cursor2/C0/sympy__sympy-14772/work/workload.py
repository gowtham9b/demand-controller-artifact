import timeit
import statistics
from sympy.crypto.crypto import _legendre
from sympy.core.cache import clear_cache


def setup():
    global a, p
    clear_cache()
    a = 87389
    p = 131071
    
def workload():
    global a, p
    _ = _legendre(a, p)

runtimes = timeit.repeat(workload, number=1, repeat=10, setup=setup)

print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))