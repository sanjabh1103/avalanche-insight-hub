from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from backend.open_forcing.contracts import OpenForcingContractError, SourceSnapshot
from backend.open_forcing.physical_validation import (
    PhysicalObservation,
    compare_continuous_observations,
)
from backend.open_forcing.replay import SourceReplay
from backend.open_forcing.source_registry import ForcingSnapshotManifest


def _replay() -> SourceReplay:
    instant = datetime(2026, 1, 1, tzinfo=timezone.utc)
    snapshot = SourceSnapshot(
        source_id="mod10a1",
        product="MODIS snow cover science product",
        issue_time=instant,
        valid_time=instant,
        retrieved_at=instant,
        source_as_of=instant,
        native_resolution_m=500.0,
        content_sha256="a" * 64,
        license_id="nasa-review",
        provider="NASA/NSIDC",
        model_id="mod10a1",
        run_id="2026-01-01",
        assimilation_disclosure="satellite science product; no station-feed dependency",
    )
    manifest = ForcingSnapshotManifest(
        snapshots=(snapshot,),
        target_crs="EPSG:32643",
        target_resolution_m=500.0,
        effective_resolution_m=500.0,
        grid_manifest_hash="b" * 64,
    )
    return SourceReplay.from_payload(manifest, b"reviewed-science-payload", created_at=instant)


class OpenForcingPhysicalValidationTests(unittest.TestCase):
    def test_continuous_report_computes_only_physical_metrics_and_stays_pending(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        reference = [
            PhysicalObservation("mod10a1", "p1", start, "snow_cover_fraction", 0.5, "1", "a" * 64),
            PhysicalObservation("mod10a1", "p2", start + timedelta(hours=1), "snow_cover_fraction", 0.8, "1", "a" * 64),
        ]
        candidate = [
            PhysicalObservation("open_forcing_candidate", "p1", start, "snow_cover_fraction", 0.6, "1", "b" * 64),
        ]
        report = compare_continuous_observations(
            replay=_replay(),
            reference=reference,
            candidate=candidate,
            reference_source_id="mod10a1",
            candidate_source_id="open_forcing_candidate",
            variable="snow_cover_fraction",
        )
        metrics = dict(report.metrics)
        self.assertEqual(report.sample_count, 2)
        self.assertEqual(report.paired_count, 1)
        self.assertAlmostEqual(metrics["mae"], 0.1)
        self.assertAlmostEqual(metrics["rmse"], 0.1)
        self.assertAlmostEqual(metrics["paired_coverage"], 0.5)
        self.assertEqual(report.decision, "pending")
        self.assertFalse(report.label_eligible)
        self.assertFalse(report.candidate_pipeline_allowed)
        self.assertNotIn("pss", metrics)
        self.assertNotIn("brier", metrics)

    def test_missing_values_are_not_imputed(self) -> None:
        instant = datetime(2026, 1, 1, tzinfo=timezone.utc)
        report = compare_continuous_observations(
            replay=_replay(),
            reference=[PhysicalObservation("mod10a1", "p1", instant, "snow_cover_fraction", 0.5, "1", "a" * 64)],
            candidate=[],
            reference_source_id="mod10a1",
            candidate_source_id="open_forcing_candidate",
            variable="snow_cover_fraction",
        )
        self.assertEqual(report.paired_count, 0)
        self.assertEqual(dict(report.metrics), {"paired_coverage": 0.0})

    def test_synthetic_observations_are_rejected(self) -> None:
        instant = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with self.assertRaises(OpenForcingContractError):
            PhysicalObservation(
                "mod10a1", "p1", instant, "snow_cover_fraction", 0.5, "1", "a" * 64, synthetic=True
            ).validate()


if __name__ == "__main__":
    unittest.main()
