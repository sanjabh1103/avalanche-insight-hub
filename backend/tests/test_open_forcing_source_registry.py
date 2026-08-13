from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.open_forcing.contracts import OpenForcingContractError, SourceSnapshot
from backend.open_forcing.source_registry import (
    ForcingSnapshotManifest,
    SourceRegistry,
)


def _snapshot(source_id: str = "era5_land") -> SourceSnapshot:
    instant = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return SourceSnapshot(
        source_id=source_id,
        product="test-product",
        issue_time=instant,
        valid_time=instant,
        retrieved_at=instant,
        source_as_of=instant,
        native_resolution_m=9000.0,
        content_sha256="a" * 64,
        license_id="test-review-required",
        provider="ECMWF/Copernicus via Open-Meteo archive",
        model_id="era5_land",
        run_id="archive:2026-01-01:2026-01-02",
        assimilation_disclosure="public reanalysis may assimilate observations",
    )


class OpenForcingSourceRegistryTests(unittest.TestCase):
    def test_default_registry_has_quantitative_and_context_only_sources(self) -> None:
        registry = SourceRegistry()
        self.assertIn("era5_land", registry.ids())
        registry.assert_quantitative_allowed("mod10a1")
        with self.assertRaises(OpenForcingContractError):
            registry.assert_quantitative_allowed("gibs_visualization")

    def test_manifest_is_deterministic_and_records_resolution_semantics(self) -> None:
        manifest = ForcingSnapshotManifest(
            snapshots=(_snapshot(),),
            target_crs="EPSG:32643",
            target_resolution_m=500.0,
            effective_resolution_m=9000.0,
            grid_manifest_hash="b" * 64,
        )
        manifest.validate(SourceRegistry())
        self.assertEqual(len(manifest.manifest_hash), 64)
        self.assertEqual(manifest.manifest_hash, manifest.manifest_hash)

    def test_manifest_hash_includes_source_provenance_metadata(self) -> None:
        original = _snapshot()
        changed = SourceSnapshot(
            source_id=original.source_id,
            product=original.product,
            issue_time=original.issue_time,
            valid_time=original.valid_time,
            retrieved_at=original.retrieved_at,
            source_as_of=original.source_as_of,
            native_resolution_m=original.native_resolution_m,
            content_sha256=original.content_sha256,
            license_id="different-review-record",
            provider=original.provider,
            model_id=original.model_id,
            run_id=original.run_id,
            assimilation_disclosure=original.assimilation_disclosure,
            license_review_status=original.license_review_status,
        )
        first = ForcingSnapshotManifest(
            snapshots=(original,),
            target_crs="EPSG:32643",
            target_resolution_m=500.0,
            effective_resolution_m=9000.0,
            grid_manifest_hash="b" * 64,
        )
        second = ForcingSnapshotManifest(
            snapshots=(changed,),
            target_crs="EPSG:32643",
            target_resolution_m=500.0,
            effective_resolution_m=9000.0,
            grid_manifest_hash="b" * 64,
        )
        self.assertNotEqual(first.manifest_hash, second.manifest_hash)

    def test_manifest_hash_rejects_unregistered_or_context_only_sources(self) -> None:
        unknown = ForcingSnapshotManifest(
            snapshots=(_snapshot("unregistered"),),
            target_crs="EPSG:4326",
            target_resolution_m=500.0,
            effective_resolution_m=500.0,
            grid_manifest_hash="b" * 64,
        )
        with self.assertRaises(OpenForcingContractError):
            _ = unknown.manifest_hash

    def test_effective_resolution_cannot_be_finer_than_target(self) -> None:
        manifest = ForcingSnapshotManifest(
            snapshots=(_snapshot(),),
            target_crs="EPSG:32643",
            target_resolution_m=9000.0,
            effective_resolution_m=500.0,
            grid_manifest_hash="b" * 64,
        )
        with self.assertRaises(OpenForcingContractError):
            manifest.validate(SourceRegistry())

    def test_gibs_snapshot_is_rejected_from_quantitative_manifest(self) -> None:
        manifest = ForcingSnapshotManifest(
            snapshots=(_snapshot("gibs_visualization"),),
            target_crs="EPSG:4326",
            target_resolution_m=500.0,
            effective_resolution_m=500.0,
            grid_manifest_hash="b" * 64,
        )
        with self.assertRaises(OpenForcingContractError):
            manifest.validate(SourceRegistry())

    def test_snapshot_requires_exact_provenance_and_research_disclosure(self) -> None:
        snapshot = _snapshot()
        with self.assertRaisesRegex(OpenForcingContractError, "exact model_id and run_id"):
            SourceSnapshot(
                source_id=snapshot.source_id,
                product=snapshot.product,
                issue_time=snapshot.issue_time,
                valid_time=snapshot.valid_time,
                retrieved_at=snapshot.retrieved_at,
                source_as_of=snapshot.source_as_of,
                native_resolution_m=snapshot.native_resolution_m,
                content_sha256=snapshot.content_sha256,
                license_id=snapshot.license_id,
                provider=snapshot.provider,
                model_id="best_match",
                run_id=snapshot.run_id,
                assimilation_disclosure=snapshot.assimilation_disclosure,
            ).validate()

    def test_manifest_can_require_license_approval_without_changing_default_research_validation(self) -> None:
        manifest = ForcingSnapshotManifest(
            snapshots=(_snapshot(),),
            target_crs="EPSG:32643",
            target_resolution_m=500.0,
            effective_resolution_m=9000.0,
            grid_manifest_hash="b" * 64,
        )
        manifest.validate(SourceRegistry())
        with self.assertRaisesRegex(OpenForcingContractError, "license-approved"):
            manifest.validate(SourceRegistry(), require_approved_license=True)


if __name__ == "__main__":
    unittest.main()
