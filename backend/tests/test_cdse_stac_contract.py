from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.common.cdse_stac_contract import (
    CDSE_STAC_SEARCH_URL,
    CDSE_STAC_COLLECTION,
    CdseStacContractError,
    build_request_manifest,
    build_stac_search_request,
    normalize_stac_bbox,
    write_request_bundle,
)


class CdseStacContractTests(unittest.TestCase):
    def test_repo_bbox_is_converted_to_stac_order(self) -> None:
        self.assertEqual(normalize_stac_bbox((27.0, 85.0, 29.0, 87.5)), [85.0, 27.0, 87.5, 29.0])

    def test_invalid_bbox_and_time_fail_closed(self) -> None:
        with self.assertRaisesRegex(CdseStacContractError, "latitude bounds"):
            normalize_stac_bbox((29.0, 85.0, 27.0, 87.5))
        with self.assertRaisesRegex(CdseStacContractError, "timezone-aware"):
            build_stac_search_request(
                region_key="himalayas_nepal",
                region_bbox=(27.0, 85.0, 29.0, 87.5),
                start="2024-01-01T00:00:00",
                end="2024-01-02T00:00:00Z",
            )

    def test_request_is_bounded_and_not_an_event_label(self) -> None:
        request = build_stac_search_request(
            region_key="himalayas_nepal",
            region_bbox=(27.0, 85.0, 29.0, 87.5),
            start="2024-01-01T00:00:00Z",
            end="2024-02-01T00:00:00Z",
            limit=7,
        )
        self.assertEqual(request["collections"], [CDSE_STAC_COLLECTION])
        self.assertEqual(request["bbox"], [85.0, 27.0, 87.5, 29.0])
        self.assertEqual(request["limit"], 7)
        self.assertIn("2024-01-01T00:00:00Z/2024-02-01T00:00:00Z", request["datetime"])
        self.assertEqual(request["_mvp4_context"]["label_semantics"], "not_an_avalanche_event_label")
        self.assertEqual(request["_mvp4_context"]["use_role"], "scene_metadata_and_feature_provenance_only")

    def test_manifest_binds_request_and_keeps_all_promotion_flags_false(self) -> None:
        request = build_stac_search_request(
            region_key="himalayas_nepal",
            region_bbox=(27.0, 85.0, 29.0, 87.5),
            start="2024-01-01T00:00:00Z",
            end="2024-02-01T00:00:00Z",
        )
        manifest = build_request_manifest(region_key="himalayas_nepal", request=request)
        request_hash = hashlib.sha256(
            (json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n").encode()
        ).hexdigest()
        self.assertEqual(manifest["endpoint"], CDSE_STAC_SEARCH_URL)
        self.assertEqual(manifest["request_sha256"], request_hash)
        self.assertEqual(manifest["label_semantics"], "not_an_avalanche_event_label")
        self.assertFalse(manifest["network_fetch_performed"])
        self.assertFalse(manifest["training_eligible"])
        self.assertFalse(manifest["core_training_eligible"])
        self.assertFalse(manifest["production_scoring_eligible"])
        self.assertFalse(manifest["remote_pilot_allowed"])

    def test_bundle_writes_hash_bound_request_and_manifest(self) -> None:
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "cdse"
            manifest = write_request_bundle(
                output,
                region_key="himalayas_nepal",
                region_bbox=(27.0, 85.0, 29.0, 87.5),
                start="2024-01-01T00:00:00Z",
                end="2024-02-01T00:00:00Z",
            )
            request = json.loads((output / "request.json").read_text())
            stored_manifest = json.loads((output / "snapshot_manifest.json").read_text())
        self.assertEqual(stored_manifest, manifest)
        request_bytes = (json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n").encode()
        self.assertEqual(manifest["request_sha256"], hashlib.sha256(request_bytes).hexdigest())


if __name__ == "__main__":
    unittest.main()
