
        
import timeit
import statistics

import pandas as pd
import numpy as np

import operator

arr = np.arange(10 ** 6).reshape(1000, -1)
df = pd.DataFrame(arr)
df["C"] = 1.0
df = df
ser = df[0]
row = df.iloc[0]
        
def workload():
    operator.floordiv(df, ser)

runtimes = timeit.repeat(workload, number=5, repeat=25)

# Print runtime mean and std deviation.
print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))
