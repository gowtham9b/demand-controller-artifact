import timeit
import statistics

from scipy.stats import truncnorm
import numpy as np

beta = np.array([-1.25,  -1,  -0.5])
x1 = np.random.uniform(-2.0,  2.0, size=900 * 3).reshape(900,  -1)
x1[:,  0] = 1

def workload():
    truncnorm(-x1@beta, np.inf, loc=x1@beta).rvs()

runtimes = timeit.repeat(workload, number=1, repeat=50)

print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))
