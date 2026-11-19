import timeit
import statistics
import numpy as np
import astropy.units as u
from astropy.coordinates import ICRS

def setup():
    global c
    c = ICRS(np.arange(30.)*u.deg, np.arange(30.)*u.deg)

def workload():
    global c
    c[1:2]

runtimes = timeit.repeat(workload, number=10, repeat=200, setup = setup)

print("Mean:", statistics.mean(runtimes[-100:]))
print("Std Dev:", statistics.stdev(runtimes[-100:]))