import timeit
import statistics

import pandas as pd
import numpy as np

arr = np.arange(1_000_000, dtype="float32")

def workload():
    pd.DataFrame(arr, dtype="int32", copy=True)
    
runtimes = timeit.repeat(workload, number=1, repeat=1000)

# Print runtime mean and std deviation.
print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))
