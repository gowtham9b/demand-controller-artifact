import timeit
import statistics

from matplotlib.backends.backend_pdf import Name

def workload():
    Name("foo\xff\x01")

runtimes = timeit.repeat(workload, number=1, repeat=1000)

# Print runtime mean and std deviation.
print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))
