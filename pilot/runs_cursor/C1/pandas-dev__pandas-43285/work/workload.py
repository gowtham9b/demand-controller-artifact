import timeit
import statistics

import pandas as pd
import numpy as np

cols = 36
rows = 12

def _apply_func(s):
    return [
        "background-color: lightcyan" if s.name == "row_1" else "" for v in s
    ]

def initialize():
    df = pd.DataFrame(
        np.random.randn(rows, cols),
        columns=[f"float_{i+1}" for i in range(cols)],
        index=[f"row_{i+1}" for i in range(rows)],
    )
    st = df.style.apply(_apply_func, axis=1)
    return st

initialize()

def workload():
    st = initialize()
    st._render_html(True, True)

runtimes = timeit.repeat(workload, number=5, repeat=25)

# Print runtime mean and std deviation.
print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))
