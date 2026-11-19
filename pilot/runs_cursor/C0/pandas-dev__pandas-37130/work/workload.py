
import timeit
import statistics

import pandas as pd
import numpy as np

n = 100_000
rng1 = pd.RangeIndex(n)
rng2 = pd.RangeIndex(n)

def workload():
    rng1 == rng2

runtimes = timeit.repeat(workload, number=1, repeat=1000)

print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))