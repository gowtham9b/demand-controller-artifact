import timeit
import statistics

import numpy as np
import dask.array as da


class ArrayLikeObject:
    def __init__(self):
        self._array = np.ones((1, 1, 20, 30), dtype=float)
        self.shape = self._array.shape
        self.ndim = self._array.ndim
        self.dtype = self._array.dtype

    def __getitem__(self, item):
        return self._array[item]


def workload():
    meta = np.zeros((0,), dtype=float)
    chunks = [[[[da.from_array(ArrayLikeObject(), meta=meta)] * 269] * 6] * 4]
    da.block(chunks)
    

runtimes = timeit.repeat(workload, number=1, repeat=100)

# Print runtime mean and std deviation.
print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))
