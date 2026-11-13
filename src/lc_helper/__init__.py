import os

# numpy's OpenBLAS commits a buffer per CPU thread when imported: ~495 MB of private memory on a 16-thread machine,
# for matrix work lc-helper never does (its numpy use is element-wise; einsum runs without BLAS). One thread keeps
# the window at ~40 MB before OCR loads. Measured 2026-11-13 with GetProcessMemoryInfo.PrivateUsage.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
