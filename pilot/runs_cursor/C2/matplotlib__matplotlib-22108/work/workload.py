import timeit
import statistics
from matplotlib.transforms import Affine2D
import numpy as np

def setup():
    global mtx, theta, aff
    mtx = np.array([[.1, .2, .3], [.4, .5, .6], [0, 0, 1]])
    theta = np.pi / 4
    aff = Affine2D()
    aff.set_matrix(mtx)

def workload():
    global mtx, theta, aff
    aff.rotate(theta)
    
runtimes = timeit.repeat(workload, number=100, repeat=2000, setup=setup)
print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))