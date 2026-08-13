from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.scripts.build_interval_training_shadow_frame import _prepare_label_rows, main as build_shadow_main
from backend.scripts.build_open_meteo_interval_feature_snapshot import _feature_join_key


class IntervalTrainingShadowFrameAdapterTests(unittest.TestCase):
    def test_derives_join_key_without_mutating_source_row(self) -> None:
        source = {
            "source_event_id": "gee-event-1",
            "region_key": "himalayas_nepal",
            "lat": 28.0,
            "lng": 86.0,
        }

        prepared, diagnostics = _prepare_label_rows([source])

        self.assertNotIn("feature_join_key", source)
        self.assertEqual(prepared[0]["feature_join_key"], "himalayas_nepal:621:1685")
        self.assertEqual(
            prepared[0]["feature_join_key_derivation"],
            "spatial_feature_join_key_v1",
        )
        self.assertEqual(diagnostics["derived_count"], 1)

    def test_preserves_existing_join_key(self) -> None:
        source = {
            "source_event_id": "event-1",
            "region_key": "himalayas_nepal",
            "feature_join_key": "himalayas_nepal:1:2",
        }

        prepared, diagnostics = _prepare_label_rows([source])

        self.assertEqual(prepared[0]["feature_join_key"], "himalayas_nepal:1:2")
        self.assertNotIn("feature_join_key_derivation", prepared[0])
        self.assertEqual(diagnostics["derived_count"], 0)

    def test_feature_snapshot_selector_resolves_coordinate_key_before_group_cap(self) -> None:
        row = {
            "region_key": "himalayas_nepal",
            "lat": 28.0,
            "lng": 86.0,
        }

        self.assertEqual(
            _feature_join_key(row, spatial_bin_km=5.0),
            "himalayas_nepal:621:1685",
        )

    def test_binds_reviewed_overlap_and_license_without_mutating_source_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_manifest = root / "hiaval_manifest.json"
            source_manifest.write_text(json.dumps({
                "license_review_id": "license-review-1",
            }), encoding="utf-8")
            overlap_report = root / "source_overlap_report.json"
            overlap_report.write_text(json.dumps({
                "status": "reviewed",
                "independent_positive_source_count": 2,
            }), encoding="utf-8")
            source = {
                "source_event_id": "hiaval-1",
                "source_key": "hiaval_hma",
                "origin_source_family": "hiaval_literature_database",
                "region_key": "himalayas_nepal",
                "lat": 28.0,
                "lng": 86.0,
            }
            manifest = {
                "source_overlap_report": "source_overlap_report.json",
                "source_manifests": {
                    "hiaval_hma": {"snapshot_manifest": "hiaval_manifest.json"},
                },
            }

            prepared, diagnostics = _prepare_label_rows(
                [source],
                label_manifest=manifest,
                label_manifest_path=root / "catalog_manifest.json",
            )

            self.assertNotIn("source_overlap_review_status", source)
            self.assertEqual(prepared[0]["source_overlap_review_status"], "reviewed")
            self.assertEqual(prepared[0]["license_review_id"], "license-review-1")
            self.assertTrue(diagnostics["governance_bindings"]["source_snapshot_bytes_unchanged"])

    def test_bounded_selection_is_explicit_and_records_exclusions(self) -> None:
        root = Path(__file__).resolve().parents[2]
        label_manifest = root / "backend/data/open_source_labels/mvp4_reviewed_hma_catalog/snapshot_manifest.json"
        feature_manifest = root / "backend/data/open_source_labels/mvp4_interval_nepal_pilot_era5_20260803/snapshot_manifest.json"
        if not label_manifest.is_file() or not feature_manifest.is_file():
            self.skipTest(
                "optional open-source interval evidence fixtures are not present in this checkout"
            )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            rc = build_shadow_main([
                "--label-manifest",
                str(label_manifest),
                "--feature-manifest",
                str(feature_manifest),
                "--output-dir",
                str(output),
                "--region-key",
                "himalayas_nepal",
                "--select-covered-labels",
            ])
            report = json.loads((output / "join_report.json").read_text(encoding="utf-8"))

            self.assertEqual(rc, 0)
            self.assertEqual(report["status"], "shadow_frame_written")
            self.assertEqual(report["bounded_selection"]["selected_label_count"], 21)
            self.assertEqual(report["bounded_selection"]["excluded_label_count"], 5096)
            self.assertEqual(report["coverage"]["joined_label_coverage"], 1.0)
            self.assertFalse(report["training_eligible"])
            self.assertFalse(report["production_scoring_eligible"])


if __name__ == "__main__":
    unittest.main()
