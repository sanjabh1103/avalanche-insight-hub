from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.open_forcing.contracts import OpenForcingContractError, SourceSnapshot
from backend.open_forcing.replay import CoverageMask, PhysicalValidationReport, SourceReplay
from backend.open_forcing.source_registry import ForcingSnapshotManifest


def _manifest() -> ForcingSnapshotManifest:
    instant = datetime(2026, 1, 1, tzinfo=timezone.utc)
    snapshot = SourceSnapshot(
        source_id="era5_land",
        product="ERA5-Land hourly reanalysis",
        issue_time=instant,
        valid_time=instant,
        retrieved_at=instant,
        source_as_of=instant,
        native_resolution_m=9000.0,
        content_sha256="a" * 64,
        license_id="copernicus-review",
        provider="ECMWF/Copernicus via Open-Meteo archive",
        model_id="era5_land",
        run_id="archive:2026-01-01:2026-01-02",
        assimilation_disclosure="public reanalysis may assimilate observations",
    )
    return ForcingSnapshotManifest(
        snapshots=(snapshot,),
        target_crs="EPSG:32643",
        target_resolution_m=500.0,
        effective_resolution_m=9000.0,
        grid_manifest_hash="b" * 64,
    )


class OpenForcingReplayTests(unittest.TestCase):
    def test_source_replay_is_deterministic_and_locked(self) -> None:
        created = datetime(2026, 1, 2, tzinfo=timezone.utc)
        first = SourceReplay.from_payload(_manifest(), {"row": [1, 2, 3]}, created_at=created)
        second = SourceReplay.from_payload(_manifest(), {"row": [1, 2, 3]}, created_at=created)
        self.assertEqual(first.replay_id, second.replay_id)
        self.assertFalse(first.synthetic_inputs_present)
        self.assertFalse(first.training_eligible)
        self.assertFalse(first.production_eligible)

    def test_coverage_mask_exposes_missing_pixels_and_hashes_mask(self) -> None:
        mask = CoverageMask(
            grid_manifest_hash="b" * 64,
            source_snapshot_id="c" * 64,
            pixel_ids=("p1", "p2", "p3"),
            available=(True, False, True),
            freshness_hours=(1.0, None, 3.0),
            max_freshness_hours=6.0,
        )
        self.assertAlmostEqual(mask.coverage_fraction, 2 / 3)
        self.assertEqual(mask.missing_pixel_ids, ("p2",))
        self.assertEqual(len(mask.mask_hash), 64)

    def test_coverage_rejects_available_pixel_without_freshness(self) -> None:
        mask = CoverageMask(
            grid_manifest_hash="b" * 64,
            source_snapshot_id="c" * 64,
            pixel_ids=("p1",),
            available=(True,),
            freshness_hours=(None,),
            max_freshness_hours=6.0,
        )
        with self.assertRaises(OpenForcingContractError):
            mask.validate()

    def test_physical_report_stays_pending_without_named_review(self) -> None:
        report = PhysicalValidationReport(
            report_id="d" * 64,
            replay_id="c" * 64,
            reference_source_id="mod10a1",
            candidate_source_id="open_forcing_candidate",
            variables=("snow_cover_fraction",),
            sample_count=10,
            paired_count=8,
            holdout_strategy="forward_time",
            independent_holdout=False,
            provenance_complete=True,
            metrics=(("mae", 0.2),),
        )
        report.validate()
        self.assertFalse(report.candidate_pipeline_allowed)

    def test_select_requires_holdout_and_provenance_and_label_contract(self) -> None:
        with self.assertRaises(OpenForcingContractError):
            PhysicalValidationReport(
                report_id="d" * 64,
                replay_id="c" * 64,
                reference_source_id="mod10a1",
                candidate_source_id="open_forcing_candidate",
                variables=("snow_cover_fraction",),
                sample_count=10,
                paired_count=8,
                holdout_strategy="forward_time",
                independent_holdout=False,
                provenance_complete=True,
                metrics=(("mae", 0.2),),
                reviewer_id="scientist-1",
                decision="select",
            ).validate()

        report = PhysicalValidationReport(
            report_id="d" * 64,
            replay_id="c" * 64,
            reference_source_id="mod10a1",
            candidate_source_id="open_forcing_candidate",
            variables=("snow_cover_fraction",),
            sample_count=10,
            paired_count=8,
            holdout_strategy="forward_time",
            independent_holdout=True,
            provenance_complete=True,
            metrics=(("mae", 0.2),),
            reviewer_id="scientist-1",
            decision="select",
            label_contract_approved=False,
        )
        self.assertFalse(report.candidate_pipeline_allowed)


if __name__ == "__main__":
    unittest.main()
