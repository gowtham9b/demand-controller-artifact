
import timeit
import statistics

import pandas as pd

idx = pd.IntervalIndex.from_breaks(range(10**4))
arr = idx._data

def workload():
    arr.argsort()

runtimes = timeit.repeat(workload, number=1, repeat=1000)

print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))