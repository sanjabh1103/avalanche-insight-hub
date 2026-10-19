from __future__ import annotations

import json
import unittest

from backend.open_forcing.contracts import OpenForcingContractError
from backend.open_forcing.open_meteo_source import (
    OpenMeteoRunRequest,
    parse_open_meteo_single_run,
)


def _request() -> OpenMeteoRunRequest:
    return OpenMeteoRunRequest(
        latitudes=(34.0, 34.1),
        longitudes=(75.0, 75.1),
        model_id="ecmwf_ifs025",
        run_id="2026-07-31T00:00",
        forecast_hours=3,
        hourly_variables=("temperature_2m", "precipitation"),
    )


def _response() -> list[dict[str, object]]:
    return [
        {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": {
                "time": ["2026-07-31T00:00", "2026-07-31T01:00", "2026-07-31T02:00"],
                "temperature_2m": [-5.0, -4.5, -4.0],
                "precipitation": [0.0, None, 0.2],
            },
        }
        for latitude, longitude in ((34.0, 75.0), (34.1, 75.1))
    ]


class OpenMeteoSourceTests(unittest.TestCase):
    def test_url_is_explicit_and_deterministic(self) -> None:
        request = _request()
        self.assertEqual(request.url, _request().url)
        self.assertIn("models=ecmwf_ifs025", request.url)
        self.assertIn("run=2026-07-31T00%3A00", request.url)
        self.assertIn("hourly=precipitation%2Ctemperature_2m", request.url)
        self.assertNotIn("best_match", request.url)

    def test_multi_point_payload_preserves_missing_values_and_is_research_only(self) -> None:
        raw = json.dumps(_response(), separators=(",", ":")).encode()
        payload = parse_open_meteo_single_run(_response(), _request(), raw_payload=raw)
        self.assertEqual(payload.point_count, 2)
        self.assertIsNone(payload.points[0].records[1]["precipitation"])
        self.assertFalse(payload.publication_eligible)
        self.assertFalse(payload.training_eligible)
        self.assertEqual(len(payload.raw_payload_sha256), 64)

    def test_single_object_is_supported_for_one_requested_point(self) -> None:
        request = OpenMeteoRunRequest(
            latitudes=(34.0,),
            longitudes=(75.0,),
            model_id="ecmwf_ifs025",
            run_id="2026-07-31T00:00",
            forecast_hours=3,
            hourly_variables=("temperature_2m", "precipitation"),
        )
        payload = parse_open_meteo_single_run(_response()[0], request)
        self.assertEqual(payload.point_count, 1)

    def test_coordinate_order_mismatch_fails_closed(self) -> None:
        response = _response()
        response[1]["longitude"] = 75.2
        with self.assertRaisesRegex(OpenForcingContractError, "longitude/order"):
            parse_open_meteo_single_run(response, _request())

    def test_duplicate_request_coordinates_fail_closed(self) -> None:
        request = OpenMeteoRunRequest(
            latitudes=(34.0, 34.0),
            longitudes=(75.0, 75.0),
            model_id="ecmwf_ifs025",
            run_id="2026-07-31T00:00",
            forecast_hours=1,
            hourly_variables=("temperature_2m",),
        )
        with self.assertRaisesRegex(OpenForcingContractError, "coordinates must be unique"):
            request.url

    def test_points_must_share_one_hourly_timeline(self) -> None:
        response = _response()
        response[1]["hourly"]["time"] = [  # type: ignore[index]
            "2026-07-31T01:00",
            "2026-07-31T02:00",
            "2026-07-31T03:00",
        ]
        with self.assertRaisesRegex(OpenForcingContractError, "same hourly timeline"):
            parse_open_meteo_single_run(response, _request())

    def test_missing_variable_fails_closed(self) -> None:
        response = _response()
        del response[0]["hourly"]["precipitation"]  # type: ignore[index]
        with self.assertRaisesRegex(OpenForcingContractError, "missing required variable"):
            parse_open_meteo_single_run(response, _request())

    def test_timestamp_gap_and_non_hourly_response_fail_closed(self) -> None:
        response = _response()
        response[0]["hourly"]["time"][1] = "2026-07-31T03:00"  # type: ignore[index]
        with self.assertRaisesRegex(OpenForcingContractError, "contiguous hourly"):
            parse_open_meteo_single_run(response, _request())

    def test_missing_or_best_match_run_is_rejected(self) -> None:
        with self.assertRaises(OpenForcingContractError):
            OpenMeteoRunRequest(
                latitudes=(34.0,),
                longitudes=(75.0,),
                model_id="best_match",
                run_id="2026-07-31T00:00",
                forecast_hours=1,
                hourly_variables=("temperature_2m",),
            ).url
        with self.assertRaises(OpenForcingContractError):
            OpenMeteoRunRequest(
                latitudes=(34.0,),
                longitudes=(75.0,),
                model_id="ecmwf_ifs025",
                run_id="",
                forecast_hours=1,
                hourly_variables=("temperature_2m",),
            ).url

    def test_non_utc_explicit_offset_is_rejected_by_utc_contract(self) -> None:
        response = _response()
        response[0]["hourly"]["time"][0] = "2026-07-31T00:00+05:30"  # type: ignore[index]
        with self.assertRaisesRegex(OpenForcingContractError, "timezone-aware UTC"):
            parse_open_meteo_single_run(response, _request())

    def test_run_id_requires_a_cycle_hour_not_a_cycle_minute(self) -> None:
        request = _request()
        invalid = OpenMeteoRunRequest(
            latitudes=request.latitudes,
            longitudes=request.longitudes,
            model_id=request.model_id,
            run_id="2026-07-31T01:00",
            forecast_hours=request.forecast_hours,
            hourly_variables=request.hourly_variables,
        )
        with self.assertRaisesRegex(OpenForcingContractError, "cycle hour"):
            invalid.url


if __name__ == "__main__":
    unittest.main()
