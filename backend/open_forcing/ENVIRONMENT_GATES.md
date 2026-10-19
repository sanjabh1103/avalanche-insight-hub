# Open-forcing environment gates

Status: research-only, not a production or warning runtime.

## Required physics environment

- Real COSIPY execution is gated to **Python 3.12** with the pinned
  `cosipymodel==2.0.0`, `numba==0.66.0`, and `llvmlite==0.48.0` runtime.
- The host Python 3.14 environment is contract/test-only. Its adapter imports
  and fake-engine seam are useful checks, but they are not real physics proof;
  the default real-engine adapter call raises before COSIPY is imported.
- `NUMBA_DISABLE_JIT` is never accepted as a successful physics run.
- The complete snowpack lock contains optional GDAL/cartography tooling. The
  dedicated smoke job installs the minimal cpkernel runtime with exact pinned
  versions from the lock set and intentionally excludes those optional tools.

## COSIPY API boundary

COSIPY 2.0.0 exposes `cosipy_core(DATA, indY, indX, ...)`. The adapter emits
one-dimensional `(time,)` forcing series and scalar spatial coordinates for a
single cell. The verified real smoke uses the explicit coupled
`WRF_X_CSPY` branch because the standalone writer path in this COSIPY release
returns one-element arrays during scalar output assignment.

The coupled path is exposed as `run_cosipy_coupled_reference`; it is not wired
to `daily_inference.py`, publication, training, warning delivery, or the
existing RF/TreeSHAP runtime.

## Required smoke command

```bash
OPEN_FORCING_REAL_COSIPY=1 \
NUMBA_CACHE_DIR=/tmp/numba-cache \
PYTHONPATH=. \
python3.12 -m unittest backend.tests.test_open_forcing_cosipy_real -q
```

The test uses a deterministic synthetic **schema fixture only**. Its outputs
prove API/schema execution, not Himalayan accuracy or a partner forecast claim.
