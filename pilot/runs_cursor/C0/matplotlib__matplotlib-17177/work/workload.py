import timeit
import statistics
import io
import numpy as np
import matplotlib

matplotlib.use("PS")

import matplotlib.pyplot as plt
IMG = np.random.randint(0, 255, (1024, 1024, 3), dtype=np.uint8)

def workload():
    fig, ax = plt.subplots(figsize=(6, 6), dpi=100)
    ax.axis("off")
    ax.imshow(IMG)
    buf = io.BytesIO()
    fig.savefig(buf, format="ps")      # triggers the hex-string wrapping
    plt.close(fig)

runtimes = timeit.repeat(workload, number=1, repeat=25)

print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))