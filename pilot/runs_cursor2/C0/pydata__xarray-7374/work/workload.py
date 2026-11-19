
import timeit
import statistics

import xarray as xr
import numpy as np
from dataclasses import dataclass
import os

@dataclass
class PerformanceBackendArray(xr.backends.BackendArray):
    filename_or_obj: str | os.PathLike | None
    shape: tuple[int, ...]
    dtype: np.dtype
    lock: xr.backends.locks.SerializableLock

    def __getitem__(self, key: tuple):
        return xr.core.indexing.explicit_indexing_adapter(
            key,
            self.shape,
            xr.core.indexing.IndexingSupport.BASIC,
            self._raw_indexing_method,
        )

    def _raw_indexing_method(self, key: tuple):
        raise NotImplementedError

@dataclass
class PerformanceStore(xr.backends.common.AbstractWritableDataStore):
    manager: xr.backends.CachingFileManager
    mode: str | None = None
    lock: xr.backends.locks.SerializableLock | None = None
    autoclose: bool = False

    def __post_init__(self):
        self.filename = self.manager._args[0]

    @classmethod
    def open(
        cls,
        filename: str | os.PathLike | None,
        mode: str = "r",
        lock: xr.backends.locks.SerializableLock | None = None,
        autoclose: bool = False,
    ):
        if lock is None:
            if mode == "r":
                locker = xr.backends.locks.SerializableLock()
            else:
                locker = xr.backends.locks.SerializableLock()
        else:
            locker = lock

        manager = xr.backends.CachingFileManager(
            xr.backends.DummyFileManager,
            filename,
            mode=mode,
        )
        return cls(manager, mode=mode, lock=locker, autoclose=autoclose)

    def load(self) -> tuple:
        """
        Load a bunch of test data quickly.

        Normally this method would've opened a file and parsed it.
        """
        n_variables = 2000

        # Important to have a shape and dtype for lazy loading.
        shape = (1,)
        dtype = np.dtype(int)
        variables = {
            f"long_variable_name_{v}": xr.Variable(
                data=PerformanceBackendArray(
                    self.filename, shape, dtype, self.lock
                ),
                dims=("time",),
                fastpath=True,
            )
            for v in range(0, n_variables)
        }
        attributes = {}

        return variables, attributes

class PerformanceBackend(xr.backends.BackendEntrypoint):
    def open_dataset(
        self,
        filename_or_obj: str | os.PathLike | None,
        drop_variables: tuple[str] = None,
        *,
        mask_and_scale=True,
        decode_times=True,
        concat_characters=True,
        decode_coords=True,
        use_cftime=None,
        decode_timedelta=None,
        lock=None,
        **kwargs,
    ) -> xr.Dataset:
        filename_or_obj = xr.backends.common._normalize_path(filename_or_obj)
        store = PerformanceStore.open(filename_or_obj, lock=lock)

        store_entrypoint = xr.backends.store.StoreBackendEntrypoint()

        ds = store_entrypoint.open_dataset(
            store,
            mask_and_scale=mask_and_scale,
            decode_times=decode_times,
            concat_characters=concat_characters,
            decode_coords=decode_coords,
            drop_variables=drop_variables,
            use_cftime=use_cftime,
            decode_timedelta=decode_timedelta,
        )
        return ds

engine = PerformanceBackend

def workload():
    global ds
    xr.open_dataset(None, engine=engine, chunks=None)
    
runtimes = timeit.repeat(workload, number=1, repeat=100)

print("Mean:", statistics.mean(runtimes))
print("Std Dev:", statistics.stdev(runtimes))
