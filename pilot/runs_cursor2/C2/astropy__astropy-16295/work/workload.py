import timeit
import statistics
import astropy.io.fits
import numpy as np
from astropy.coordinates.angles.formats import _check_hour_range

def workload():
    _check_hour_range(15)

runtimes = timeit.repeat(workload, number=10, repeat=2000)

print("Mean:", statistics.mean(runtimes[-1000:]))
print("Std Dev:", statistics.stdev(runtimes[-1000:]))