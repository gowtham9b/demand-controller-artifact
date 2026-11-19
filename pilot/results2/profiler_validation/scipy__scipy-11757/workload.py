import timeit
import statistics

import scipy.stats
import numpy as np

inp = np.random.rand(9999).reshape(3,3333)*200

subbin_x_edges = np.arange(0, 200, dtype=np.float32)
subbin_y_edges = np.arange(0, 200, dtype=np.float64)

def workload():
    stat = 'std'
    binned_stat, _, _, binnumbers = scipy.stats.binned_statistic_2d(
        inp[0], inp[1], values=inp[2], statistic=stat,
        bins=[subbin_x_edges, subbin_y_edges], expand_binnumbers=True)

runtimes = timeit.repeat(workload, number=1, repeat=50)

print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))
