from __future__ import annotations

import copy
import unittest

from backend.common.interval_shadow_join import (
    IntervalShadowJoinError,
    build_interval_shadow_join,
)


def _label(**overrides):
    row = {
        "source_event_id": "everest-event-001",
        "source_key": "everest_sentinel1",
        "origin_source_family": "everest_sentinel1_satellite_detection",
        "region_key": "himalayas_nepal",
        "feature_join_key": "nepal-cell-001",
        "event_time_start": "2020-01-01T00:00:00Z",
        "event_time_end": "2020-01-02T00:00:00Z",
        "timestamp_precision": "bounded_12_day_detection_interval",
        "source_overlap_review_status": "reviewed",
        "training_eligible": False,
        "production_scoring_eligible": False,
    }
    row.update(overrides)
    return row


def _feature(**overrides):
    row = {
        "feature_id": "weather-feature-001",
        "source_key": "open_meteo",
        "source_family": "open_weather_nwp",
        "region_key": "himalayas_nepal",
        "feature_join_key": "nepal-cell-001",
        "feature_valid_from": "2019-12-31T00:00:00Z",
        "feature_valid_until": "2020-01-03T00:00:00Z",
        "feature_cutoff_at": "2019-12-31T23:00:00Z",
        "features": {"snowfall_24h": 12.5, "wind_speed": 8.0},
        "production_eligible": False,
    }
    row.update(overrides)
    return row


class IntervalShadowJoinTests(unittest.TestCase):
    def test_golden_join_preserves_interval_and_forces_shadow_flags(self):
        result = build_interval_shadow_join([_label()], [_feature()])

        self.assertEqual(result["version"], "interval_shadow_join_v1")
        self.assertEqual(result["summary"]["joined_count"], 1)
        self.assertEqual(result["summary"]["issue_count"], 0)
        row = result["rows"][0]
        self.assertEqual(row["interval_start"], "2020-01-01T00:00:00Z")
        self.assertEqual(row["interval_end"], "2020-01-02T00:00:00Z")
        self.assertEqual(row["feature_cutoff_at"], "2019-12-31T23:00:00Z")
        self.assertEqual(row["features"]["snowfall_24h"], 12.5)
        self.assertTrue(row["shadow_only"])
        self.assertFalse(row["core_training_eligible"])
        self.assertFalse(row["production_scoring_eligible"])
        self.assertNotIn("event_time", row)
        self.assertNotIn("timestamp", row)

    def test_exact_boundary_containment_is_valid_under_end_exclusive_policy(self):
        feature = _feature(
            feature_valid_from="2020-01-01T00:00:00Z",
            feature_valid_until="2020-01-02T00:00:00Z",
            feature_cutoff_at="2020-01-01T00:00:00Z",
        )

        result = build_interval_shadow_join([_label()], [feature])

        self.assertEqual(result["summary"]["joined_count"], 1)

    def test_cutoff_violation_is_dropped_and_never_joined(self):
        feature = _feature(feature_cutoff_at="2020-01-01T00:00:01Z")

        result = build_interval_shadow_join([_label()], [feature])

        self.assertEqual(result["summary"]["joined_count"], 0)
        reasons = {issue["reason"] for issue in result["issues"]}
        self.assertIn("feature_cutoff_violation", reasons)
        self.assertIn("no_eligible_feature", reasons)

    def test_partial_feature_validity_is_not_silently_used(self):
        feature = _feature(feature_valid_from="2020-01-01T12:00:00Z")

        result = build_interval_shadow_join([_label()], [feature])

        self.assertEqual(result["summary"]["joined_count"], 0)
        self.assertIn("partial_feature_validity", {issue["reason"] for issue in result["issues"]})

    def test_ambiguous_matches_are_rejected_without_best_match_selection(self):
        first = _feature(feature_id="weather-feature-a")
        second = _feature(feature_id="weather-feature-b")

        result = build_interval_shadow_join([_label()], [first, second])

        self.assertEqual(result["summary"]["joined_count"], 0)
        ambiguous = [issue for issue in result["issues"] if issue["reason"] == "ambiguous_feature_match"]
        self.assertEqual(len(ambiguous), 1)
        self.assertEqual(ambiguous[0]["feature_ids"], ["weather-feature-a", "weather-feature-b"])

    def test_same_source_family_is_rejected_to_reduce_leakage(self):
        feature = _feature(source_family="everest_sentinel1_satellite_detection")

        result = build_interval_shadow_join([_label()], [feature])

        reasons = {issue["reason"] for issue in result["issues"]}
        self.assertIn("source_family_not_distinct", reasons)
        self.assertEqual(result["summary"]["joined_count"], 0)

    def test_missing_feature_cutoff_fails_closed(self):
        feature = _feature()
        del feature["feature_cutoff_at"]

        with self.assertRaisesRegex(IntervalShadowJoinError, "feature_cutoff_at"):
            build_interval_shadow_join([_label()], [feature])

    def test_point_time_fields_are_forbidden_for_interval_labels(self):
        with self.assertRaisesRegex(IntervalShadowJoinError, "point-time field event_time"):
            build_interval_shadow_join([_label(event_time="2020-01-01T12:00:00Z")], [_feature()])

    def test_unreviewed_overlap_status_is_rejected_by_default(self):
        with self.assertRaisesRegex(IntervalShadowJoinError, "source_overlap_review_status"):
            build_interval_shadow_join([_label(source_overlap_review_status="pending")], [_feature()])

    def test_cross_region_or_join_key_rows_cannot_match(self):
        feature = _feature(region_key="pir_panjal_nw_himalaya")

        result = build_interval_shadow_join([_label()], [feature])

        self.assertEqual(result["summary"]["joined_count"], 0)
        self.assertIn("no_eligible_feature", {issue["reason"] for issue in result["issues"]})

    def test_input_promotion_flags_are_rejected(self):
        with self.assertRaisesRegex(IntervalShadowJoinError, "training_eligible"):
            build_interval_shadow_join([_label(training_eligible=True)], [_feature()])

        with self.assertRaisesRegex(IntervalShadowJoinError, "production_eligible"):
            build_interval_shadow_join([_label()], [_feature(production_eligible=True)])

        with self.assertRaisesRegex(IntervalShadowJoinError, "training_eligible"):
            build_interval_shadow_join([_label()], [_feature(training_eligible=True)])

        with self.assertRaisesRegex(IntervalShadowJoinError, "core_training_eligible"):
            build_interval_shadow_join([_label()], [_feature(core_training_eligible=True)])

    def test_result_is_deterministic_for_input_order(self):
        labels = [_label(source_event_id="event-b"), _label(source_event_id="event-a")]
        features = [_feature(feature_id="feature-b"), _feature(feature_id="feature-a")]
        forward = build_interval_shadow_join(labels, features)
        reverse = build_interval_shadow_join(
            list(reversed(copy.deepcopy(labels))),
            list(reversed(copy.deepcopy(features))),
        )

        self.assertEqual(forward, reverse)


if __name__ == "__main__":
    unittest.main()
