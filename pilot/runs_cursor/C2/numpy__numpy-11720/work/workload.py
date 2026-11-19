import timeit
import statistics

import numpy as np

b = np.random.random((5, 2))
t = np.random.random((5, 5, 2))
p = np.random.random((2, 5))

def workload():
    out = np.einsum('ij,ixy,ji->xy', b, t, p)

runtimes = timeit.repeat(workload, number=10, repeat=1000)

# Print runtime mean and std deviation.
print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))

