
import timeit
import statistics

import pandas as pd
import numpy as np

N = 10000
M = 10
df_tall = pd.DataFrame(np.random.randn(N, M))
df_mixed_tall = df_tall.copy()
df_mixed_tall["foo"] = "bar"
df_mixed_tall[0] = pd.period_range("2000", periods=N)
df_mixed_tall[1] = range(N)

def workload():
    df_mixed_tall.to_numpy()

runtimes = timeit.repeat(workload, number=5, repeat=100)

# Print runtime mean and std deviation.
print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))

