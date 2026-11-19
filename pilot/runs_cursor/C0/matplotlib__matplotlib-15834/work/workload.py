import timeit
import statistics
from matplotlib.colors import _to_rgba_no_colorcycle
import numpy as np

def setup():
    global t
    t = (0.2, 0.5, 0.8, 0.3)

def workload():
    global t
    _to_rgba_no_colorcycle(t)

runtimes = timeit.repeat(workload, number=10, repeat=2000, setup=setup)

print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))