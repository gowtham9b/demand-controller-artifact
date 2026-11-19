import timeit
import statistics
import numpy as np
import astropy.units as u
from astropy.coordinates import Angle

def setup():
    global a
    a = Angle(np.arange(10.), 'degree')

def workload():
    global a
    np.add.reduce(a)

runtimes = timeit.repeat(workload, number=10, repeat=200, setup = setup)

print("Mean:", statistics.mean(runtimes[-100:]))
print("Std Dev:", statistics.stdev(runtimes[-100:]))