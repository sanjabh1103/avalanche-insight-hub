from __future__ import annotations

import unittest

from backend.common.interval_negative_sampling import (
    IntervalNegativeSamplingError,
    IntervalNegativeSamplingPolicy,
    filter_interval_negative_candidates,
)


def _positive(**overrides):
    row = {
        "source_event_id": "positive-1",
        "region_key": "himalayas_nepal",
        "lat": 28.0,
        "lng": 86.0,
        "interval_start": "2024-01-10T00:00:00Z",
        "interval_end": "2024-01-11T00:00:00Z",
        "timestamp_precision": "day",
        "label": 1,
    }
    row.update(overrides)
    return row


def _candidate(**overrides):
    row = {
        "candidate_id": "candidate-1",
        "region_key": "himalayas_nepal",
        "lat": 28.0,
        "lng": 86.0,
        "interval_start": "2024-01-12T00:00:00Z",
        "interval_end": "2024-01-13T00:00:00Z",
        "timestamp_precision": "interval",
        "label": 0,
    }
    row.update(overrides)
    return row


class IntervalNegativeSamplingTests(unittest.TestCase):
    def test_excludes_spatiotemporal_candidates_and_preserves_end_exclusive_boundary(self) -> None:
        candidates = [
            _candidate(candidate_id="near", interval_start="2024-01-11T12:00:00Z"),
            _candidate(candidate_id="boundary", interval_start="2024-01-12T00:00:00Z"),
        ]

        accepted, report = filter_interval_negative_candidates(candidates, [_positive()])

        self.assertEqual([row["candidate_id"] for row in accepted], ["boundary"])
        self.assertEqual(report["excluded_reason_counts"], {"near_positive_interval": 1})
        self.assertFalse(report["point_time_synthesis"])

    def test_region_isolation_and_custom_buffer_are_explicit(self) -> None:
        policy = IntervalNegativeSamplingPolicy(
            spatial_exclusion_m=1000.0,
            temporal_buffer_before_hours=0.0,
            temporal_buffer_after_hours=0.0,
        )
        accepted, report = filter_interval_negative_candidates(
            [
                _candidate(candidate_id="other-region", region_key="pir_panjal_nw_himalaya"),
                _candidate(candidate_id="same-region", interval_start="2024-01-10T12:00:00Z"),
            ],
            [_positive()],
            policy=policy,
        )

        self.assertEqual([row["candidate_id"] for row in accepted], ["other-region"])
        self.assertEqual(report["accepted_count"], 1)

    def test_rejects_point_time_and_positive_candidates(self) -> None:
        with self.assertRaisesRegex(IntervalNegativeSamplingError, "point-time"):
            filter_interval_negative_candidates(
                [_candidate(timestamp="2024-01-12T00:00:00Z")],
                [_positive()],
            )

        with self.assertRaisesRegex(IntervalNegativeSamplingError, "label must be zero"):
            filter_interval_negative_candidates(
                [_candidate(label=1)],
                [_positive()],
            )


if __name__ == "__main__":
    unittest.main()
