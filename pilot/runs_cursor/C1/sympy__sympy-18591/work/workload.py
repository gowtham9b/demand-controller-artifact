import timeit
import statistics

from sympy.ntheory import is_mersenne_prime, is_perfect
from sympy.core.cache import clear_cache

m = 2 ** 31 -1
p = 31
per = (2**(p - 1)) * (2**p - 1)

def setup():
    clear_cache()

def workload():
    _ = is_mersenne_prime(m)
    _ = is_perfect(per)

runtimes = timeit.repeat(workload, number=5, repeat=1000, setup=setup)

print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))