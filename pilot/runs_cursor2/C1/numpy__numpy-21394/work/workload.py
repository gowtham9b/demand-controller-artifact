import timeit
import statistics

import numpy as np

x1 = np.random.rand(100,)
x2 = x1 + 1j * np.random.rand(100,)

def workload():
    np.linalg.norm(x1)
    np.linalg.norm(x2)

runtimes = timeit.repeat(workload, number=10, repeat=1000)

# Print runtime mean and std deviation.
print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))
