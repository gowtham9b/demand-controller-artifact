

import timeit
import statistics

import xarray
import subprocess

import zipfile
import os
import glob

# Download the dataset from: 
dataset_url = "https://github.com/pydata/xarray/files/15213429/software_timestamp.zip"

# Download to /tmp/software_timestamp.zip
subprocess.run(['wget', dataset_url, '-O', '/tmp/software_timestamp.zip'])

# Unzip the dataset
with zipfile.ZipFile('/tmp/software_timestamp.zip', 'r') as zip_ref:
    zip_ref.extractall('/tmp')

def setup():
    global software_timestamp, N_frames

    dataset = xarray.open_dataset('/tmp/software_timestamp.nc', engine='h5netcdf')
    software_timestamp = dataset['software_timestamp'].compute()
    N_frames = dataset.sizes['frame_number']
    dataset.close()

def workload():
    global software_timestamp, N_frames
    for i in range(1000):
        software_timestamp.isel(frame_number=i % N_frames)

runtimes = timeit.repeat(workload, number=1, repeat=10, setup=setup)

for filepath in glob.glob('/tmp/software_timestamp*'):
    os.remove(filepath)

print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))