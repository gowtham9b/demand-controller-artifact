import timeit
import statistics

from scipy.spatial import SphericalVoronoi
import numpy as np

num_points = 10000
ndim = 2

def generate_circle_points(num_points):
    angles = np.linspace(0, 1.9999 * np.pi, num_points)
    points = np.empty(shape=(num_points, 2))
    points[..., 0] = np.cos(angles)
    points[..., 1] = np.sin(angles)
    return points

center = np.zeros(2)
points = generate_circle_points(num_points)

def setup():
    global sv
    sv = SphericalVoronoi(points, radius=1,
                          center=center)
    
def workload():
    global sv
    sv.calculate_areas()

runtimes = timeit.repeat(workload, number=1, repeat=1000, setup=setup)

print("Mean:", statistics.mean(runtimes[-1000:]))
print("Std Dev:", statistics.stdev(runtimes[-1000:]))
