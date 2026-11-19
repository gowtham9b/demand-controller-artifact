
import timeit
import statistics

import pandas as pd
import numpy as np

rng = pd.RangeIndex(1_000_000)

def workload():
    rng.get_loc(np.int64(900_000))

runtimes = timeit.repeat(workload, number=1, repeat=100)

print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))