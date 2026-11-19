import timeit
import statistics

import numpy as np

def workload():
    np.linspace(0, 10, 2)
    np.linspace([1, 2], 10, 5)

runtimes = timeit.repeat(workload, number=5, repeat=1000)

# Print runtime mean and std deviation.
print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))
