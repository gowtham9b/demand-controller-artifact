import timeit
import statistics
import numpy as np
import scipy.ndimage as ndimage

def setup():
    global data, structure
    data  = (np.random.rand(24, 20)+.5).astype(int)
    structure=np.array([[1,1,1]])
    
def workload():
    global data, structure
    ndimage.binary_erosion(data, structure)

runtimes = timeit.repeat(workload, number=1, repeat=2000, setup=setup)

print("Mean:", statistics.mean(runtimes[-1000:]))
print("Std Dev:", statistics.stdev(runtimes[-1000:]))