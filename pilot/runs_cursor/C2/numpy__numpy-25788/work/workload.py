import timeit
import statistics

import numpy as np

n = 64
A = np.random.rand(n, n)
B = np.random.rand(n, n)

def workload():
    np.tensordot(A, B)

runtimes = timeit.repeat(workload, number=10, repeat=1000)

# Print runtime mean and std deviation.
print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))
