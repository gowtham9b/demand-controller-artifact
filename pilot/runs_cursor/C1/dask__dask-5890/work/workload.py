import timeit
import statistics

import dask.array as da
import numpy as np

a = da.from_array(np.ones((1, 1)), chunks=1)
b = da.from_array(np.zeros((1, 1)), chunks=1)
c = a + b
dsk = c.__dask_graph__()
keys = c.__dask_keys__()

def workload():
    da.optimize(dsk, keys)

runtimes = timeit.repeat(workload, number=50, repeat=200)

# Print runtime mean and std deviation.
print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))
