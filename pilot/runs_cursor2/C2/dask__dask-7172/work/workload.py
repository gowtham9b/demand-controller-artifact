import timeit
import statistics

import dask.array as da
from dask.array.percentile import merge_percentiles
import numpy as np

nquantiles = 100
ndatasets = 100

def setup():
    scale = 100
    calculated_quantiles = nquantiles//2

    global finalq, qs, vals, Ns

    finalq = np.floor(np.random.rand(nquantiles) * scale)
    qs = list(np.floor(np.random.rand(ndatasets, calculated_quantiles) * scale))
    vals = list(np.random.rand(ndatasets, calculated_quantiles))
    Ns = np.ones(ndatasets) * 100
    
def workload():
    global finalq, qs, vals, Ns

    merge_percentiles(finalq, qs, vals, Ns=Ns)

runtimes = timeit.repeat(workload, number=1, repeat=1000, setup=setup)

# Print runtime mean and std deviation.
print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))

