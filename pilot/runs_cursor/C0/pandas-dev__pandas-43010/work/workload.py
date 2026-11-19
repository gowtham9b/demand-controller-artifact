import timeit
import statistics

import pandas as pd
import numpy as np

s = pd.Series(np.random.randn(100000)).astype("int")
s_func = getattr(s, "mad")

def workload():
    s_func()
    
runtimes = timeit.repeat(workload, number=5, repeat=10)

# Print runtime mean and std deviation.
print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))
