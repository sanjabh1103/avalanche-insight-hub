from __future__ import annotations

import inspect
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

import numpy as np

from backend.open_forcing.contracts import OpenForcingContractError, OpenForcingPolicy
from backend.open_forcing.cosipy_adapter import (
    CosipyApi,
    CosipyForcingSeries,
    build_cosipy_dataset,
    load_cosipy_api,
    run_cosipy_coupled_reference,
    run_cosipy_reference,
)

try:
    import xarray  # noqa: F401
    _HAS_XARRAY = True
except ImportError:
    _HAS_XARRAY = False

try:
    import cosipy  # noqa: F401
    _HAS_COSIPY = True
except ImportError:
    _HAS_COSIPY = False


def _records(count: int = 3) -> list[dict[str, object]]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        {
            "time": start + timedelta(hours=index),
            "temperature_2m": -5.0 + index,
            "relative_humidity_2m": 70.0,
            "windspeed_10m": 2.0,
            "surface_pressure": 700.0,
            "shortwave_radiation": 20.0,
            "precipitation": 1.0,
            "cloud_cover": 50.0,
            "terrestrial_radiation": 1367.7,
            "snowfall": 0.5,
        }
        for index in range(count)
    ]


class _FakeCosipy:
    def __init__(self) -> None:
        self.received = None

    def init_snowpack(self, DATA):
        return DATA

    def cosipy_core(self, DATA, indY, indX, GRID_RESTART=None, stake_names=None, stake_data=None):
        self.received = (DATA, indY, indX)
        values = [None] * 45
        values[14] = np.asarray([0.25, 0.3, 0.35])
        values[15] = np.asarray([0.25, 0.3, 0.35])
        values[16] = np.asarray([268.0, 269.0, 270.0])
        values[18] = np.asarray([2, 2, 3])
        return tuple(values)


class OpenForcingCosipyAdapterTests(unittest.TestCase):
    @unittest.skipUnless(_HAS_XARRAY, "xarray not installed; run in COSIPY smoke environment")
    def test_open_meteo_units_are_converted_and_dataset_uses_cosipy_names(self) -> None:
        forcing = CosipyForcingSeries.from_open_meteo_records(
            _records(), latitude=34.0, longitude=75.0, elevation_m=3000.0
        )
        dataset = build_cosipy_dataset(forcing)
        self.assertEqual(tuple(dataset.dims), ("time",))
        self.assertAlmostEqual(float(dataset.T2.values[0]), 268.15)
        self.assertAlmostEqual(float(dataset.SNOWFALL.values[0]), 0.005)
        self.assertAlmostEqual(float(dataset.HGT.values), 3000.0)
        self.assertEqual(dataset.attrs["production_eligible"], "false")
        self.assertNotIn("LWin", dataset.data_vars)

    def test_top_of_atmosphere_terrestrial_radiation_is_not_promoted_to_longwave(self) -> None:
        forcing = CosipyForcingSeries.from_open_meteo_records(
            _records(), latitude=34.0, longitude=75.0, elevation_m=3000.0
        )
        self.assertEqual(forcing.longwave_wm2, (None, None, None))

    @unittest.skipUnless(_HAS_XARRAY, "xarray not installed; run in COSIPY smoke environment")
    def test_adapter_calls_cosipy_core_with_dataset_and_indices(self) -> None:
        forcing = CosipyForcingSeries.from_open_meteo_records(
            _records(), latitude=34.0, longitude=75.0, elevation_m=3000.0
        )
        fake = _FakeCosipy()
        api = CosipyApi(fake.init_snowpack, fake.cosipy_core, "test")
        result = run_cosipy_reference(forcing, api=api)
        self.assertIsNotNone(fake.received)
        self.assertEqual(fake.received[1:], (0, 0))
        self.assertEqual(result.native_fields["layer_count"], 3)
        self.assertIsNone(result.snow_water_equivalent_m)
        self.assertFalse(result.production_eligible)
        self.assertFalse(result.stratigraphy_native)

    def test_policy_rejects_production_or_training(self) -> None:
        with self.assertRaises(OpenForcingContractError):
            OpenForcingPolicy(enabled=True, production_eligible=True).validate()

    @unittest.skipUnless(
        sys.version_info[:2] != (3, 12),
        "unsupported-runtime guard is exercised on the host Python 3.14 lane",
    )
    def test_real_engine_is_fail_closed_on_unsupported_runtime(self) -> None:
        forcing = CosipyForcingSeries.from_open_meteo_records(
            _records(), latitude=34.0, longitude=75.0, elevation_m=3000.0
        )
        with self.assertRaisesRegex(OpenForcingContractError, "requires Python 3.12"):
            run_cosipy_coupled_reference(forcing)

    def test_numba_disabled_is_rejected_by_runtime_gate(self) -> None:
        from unittest.mock import patch
        from backend.open_forcing import cosipy_adapter

        with patch.object(cosipy_adapter.sys, "version_info", (3, 12, 0)), patch.dict(
            os.environ, {"NUMBA_DISABLE_JIT": "1"}
        ):
            with self.assertRaisesRegex(OpenForcingContractError, "NUMBA_DISABLE_JIT"):
                cosipy_adapter._assert_supported_real_runtime()

    @unittest.skipUnless(_HAS_XARRAY, "xarray not installed; run in COSIPY smoke environment")
    def test_coupled_dataset_contains_scalar_runtime_contract(self) -> None:
        forcing = CosipyForcingSeries.from_open_meteo_records(
            _records(), latitude=34.0, longitude=75.0, elevation_m=3000.0
        )
        from backend.open_forcing.cosipy_adapter import _build_cosipy_dataset

        dataset = _build_cosipy_dataset(forcing, coupled=True)
        self.assertEqual(int(dataset.DT.values), 3600)
        self.assertEqual(int(dataset.max_layers.values), 200)
        self.assertAlmostEqual(float(dataset.ZLVL.values), 2.0)

    @unittest.skipUnless(_HAS_COSIPY, "cosipy package not installed; run in COSIPY smoke environment")
    def test_installed_cosipy_signature_is_checked_without_running_numba_core(self) -> None:
        api = load_cosipy_api()
        self.assertEqual(list(inspect.signature(api.init_snowpack).parameters), ["DATA"])
        self.assertEqual(list(inspect.signature(api.cosipy_core).parameters)[:3], ["DATA", "indY", "indX"])


if __name__ == "__main__":
    unittest.main()
