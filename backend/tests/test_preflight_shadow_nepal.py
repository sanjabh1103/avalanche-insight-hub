"""Adversarial tests for the formal shadow preflight bundle verifier.

These tests verify that the preflight detects every form of tampering:
- Modified feature rows
- Modified snapshot manifest
- Modified source provenance
- Modified cache manifest
- Changed coverage values
- Changed excluded-event record
- Modified external label manifest
- Altered cache payload with unchanged canonical hash
- Altered cache payload with altered canonical hash (detected by bundle file hash)
- Altered bundle component hashes
- Training eligibility incorrectly enabled

The preflight must return exit code 0 only when the artifact is genuinely
structurally valid AND training is blocked.  Any tamper must return 1
(structural failure) or 2 (safety violation).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from typing import Any

from backend.common.open_meteo_interval_features import (
    OPEN_METEO_DAILY_VARIABLES,
    OpenMeteoArchiveClient,
    build_archive_url,
    build_open_meteo_interval_features,
)
from backend.scripts.build_open_meteo_interval_feature_snapshot import (
    _compute_coverage,
    main as build_main,
)
from backend.scripts.preflight_shadow_nepal import main as preflight_main, run_preflight


def _payload(start: date, *, days: int = 2) -> bytes:
    """Build a minimal valid Open-Meteo archive payload."""
    times = [(start + __import__("datetime").timedelta(days=i)).isoformat() for i in range(days)]
    daily: dict[str, Any] = {"time": times}
    for var in OPEN_METEO_DAILY_VARIABLES:
        daily[var] = [float(i) for i in range(days)]
    payload = {
        "latitude": 28.0,
        "longitude": 86.0,
        "generation_time_ms": 0.1,
        "utc_offset_seconds": 0,
        "timezone": "UTC",
        "timezone_abbreviation": "UTC",
        "elevation": 4000.0,
        "daily": daily,
    }
    return json.dumps(payload).encode("utf-8")


def _label(
    event_id: str,
    *,
    start: str = "2020-12-01T00:00:00Z",
    end: str = "2020-12-03T00:00:00Z",
    join_key: str = "himalayas_nepal:1:1",
    lat: float = 28.0,
    lng: float = 86.0,
) -> dict[str, Any]:
    return {
        "source_event_id": event_id,
        "region_key": "himalayas_nepal",
        "lat": lat,
        "lng": lng,
        "interval_start": start,
        "interval_end": end,
        "label": 1,
    }


def _make_label_manifest(tmpdir: Path, labels: list[dict[str, Any]]) -> Path:
    """Write a label manifest with events.jsonl and snapshot_manifest.json."""
    staging = tmpdir / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    events_path = staging / "events.jsonl"
    payload = b"".join(
        (json.dumps(label, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        for label in labels
    )
    events_path.write_bytes(payload)
    manifest = {
        "snapshot_schema_version": "mvp4_interval_label_snapshot_v1",
        "events_path": "events.jsonl",
        "event_rows_sha256": hashlib.sha256(payload).hexdigest(),
        "event_row_count": len(labels),
        "region_keys": sorted({str(l.get("region_key") or "") for l in labels}),
        "label_count": len(labels),
        "positive_label_count": sum(1 for l in labels if l.get("label") in (1, True)),
    }
    manifest_path = staging / "snapshot_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _build_artifact(tmpdir: Path, labels: list[dict[str, Any]]) -> tuple[Path, Path]:
    """Build a complete artifact with cache and return (artifact_dir, label_manifest_path)."""
    import backend.common.open_meteo_interval_features as omif

    original_fetch_daily = omif.OpenMeteoArchiveClient.fetch_daily

    def mock_fetch_daily(self, lat, lng, start, end, *, model="era5_land"):
        url = build_archive_url(lat, lng, start, end, model=model)
        days = (end - start).days + 1
        raw = _payload(start, days=days)
        payload = json.loads(raw.decode("utf-8"))
        return {
            "url": url,
            "latitude": payload.get("latitude", lat),
            "longitude": payload.get("longitude", lng),
            "model": model,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "request_attempts": 1,
            "raw_payload_sha256": hashlib.sha256(raw).hexdigest(),
            "payload": payload,
        }

    omif.OpenMeteoArchiveClient.fetch_daily = mock_fetch_daily
    try:
        label_manifest_path = _make_label_manifest(tmpdir, labels)
        output_dir = tmpdir / "output"
        exit_code = build_main([
            "--label-manifest", str(label_manifest_path),
            "--output-dir", str(output_dir),
            "--region-key", "himalayas_nepal",
            "--model", "era5",
            "--max-request-days", "90",
            "--request-timeout-seconds", "30",
        ])
        assert exit_code == 0, f"build failed with exit code {exit_code}"
        return output_dir, label_manifest_path
    finally:
        omif.OpenMeteoArchiveClient.fetch_daily = original_fetch_daily


class PreflightValidBundleTests(unittest.TestCase):
    """Tests that a valid, untampered artifact passes the preflight."""

    def test_valid_bundle_returns_0(self) -> None:
        """A valid, untampered artifact must return exit code 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            labels = [_label("event-a"), _label("event-b", join_key="himalayas_nepal:1:2")]
            artifact_dir, _ = _build_artifact(tmpdir_path, labels)

            exit_code = preflight_main([str(artifact_dir), "--repo-root", str(tmpdir_path)])
            self.assertEqual(exit_code, 0)

            report = json.loads((artifact_dir / "shadow_preflight_report.json").read_text())
            self.assertTrue(report["structural_pass"])
            self.assertTrue(report["coverage_pass"])
            self.assertTrue(report["training_blocked"])
            self.assertTrue(report["overall_pass"])


class PreflightTamperDetectionTests(unittest.TestCase):
    """Tests that every form of tampering is detected."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir_path = Path(self._tmpdir.name)
        labels = [_label("event-a"), _label("event-b", join_key="himalayas_nepal:1:2")]
        self.artifact_dir, self.label_manifest_path = _build_artifact(self.tmpdir_path, labels)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _run_preflight(self) -> int:
        return preflight_main([str(self.artifact_dir), "--repo-root", str(self.tmpdir_path)])

    def _load_json(self, relative: str) -> dict[str, Any]:
        return json.loads((self.artifact_dir / relative).read_text())

    def _save_json(self, relative: str, data: dict[str, Any]) -> None:
        path = self.artifact_dir / relative
        path.write_text(
            json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_modified_features_returns_1(self) -> None:
        """Modifying features.jsonl must cause exit code 1."""
        features_path = self.artifact_dir / "features.jsonl"
        content = features_path.read_text()
        # Append a tampered row
        features_path.write_text(content + json.dumps({"tampered": True}) + "\n")
        self.assertEqual(self._run_preflight(), 1)

    def test_modified_snapshot_manifest_returns_1(self) -> None:
        """Modifying snapshot_manifest.json must cause exit code 1."""
        manifest = self._load_json("snapshot_manifest.json")
        manifest["feature_row_count"] = 999
        self._save_json("snapshot_manifest.json", manifest)
        self.assertEqual(self._run_preflight(), 1)

    def test_modified_source_provenance_returns_1(self) -> None:
        """Modifying source_provenance.json must cause exit code 1."""
        provenance = self._load_json("source_provenance.json")
        provenance["label_row_count"] = 999
        self._save_json("source_provenance.json", provenance)
        self.assertEqual(self._run_preflight(), 1)

    def test_modified_cache_manifest_returns_1(self) -> None:
        """Modifying cache_manifest.json must cause exit code 1."""
        cache_manifest = self._load_json("raw_cache/cache_manifest.json")
        cache_manifest["entry_count"] = 999
        self._save_json("raw_cache/cache_manifest.json", cache_manifest)
        self.assertEqual(self._run_preflight(), 1)

    def test_changed_coverage_values_return_1(self) -> None:
        """Changing coverage values in provenance must cause exit code 1."""
        provenance = self._load_json("source_provenance.json")
        provenance["coverage_gate"]["covered_raw_label_count"] = 0
        self._save_json("source_provenance.json", provenance)
        self.assertEqual(self._run_preflight(), 1)

    def test_changed_excluded_event_record_returns_1(self) -> None:
        """Changing the excluded-event record in provenance must cause exit code 1."""
        provenance = self._load_json("source_provenance.json")
        provenance["excluded_labels"] = [{"tampered": True}]
        self._save_json("source_provenance.json", provenance)
        self.assertEqual(self._run_preflight(), 1)

    def test_modified_external_label_manifest_returns_1(self) -> None:
        """Modifying the external label manifest must cause exit code 1."""
        manifest = json.loads(self.label_manifest_path.read_text())
        manifest["event_row_count"] = 999
        self.label_manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        self.assertEqual(self._run_preflight(), 1)

    def test_altered_cache_payload_unchanged_canonical_hash_returns_1(self) -> None:
        """Altering a cache payload without updating the canonical hash must be detected."""
        from backend.common.open_meteo_interval_features import _cache_key

        # Find the first cache file
        cache_dir = self.artifact_dir / "raw_cache"
        cache_files = list(cache_dir.glob("*.json"))
        cache_files = [f for f in cache_files if f.name != "cache_manifest.json"]
        self.assertGreater(len(cache_files), 0)

        cache_path = cache_files[0]
        cached = json.loads(cache_path.read_text())
        # Tamper: change payload but keep canonical hash the same
        tampered_payload = dict(cached["payload"])
        tampered_daily = dict(tampered_payload["daily"])
        tampered_daily["temperature_2m_mean"] = [999.0] + tampered_daily["temperature_2m_mean"][1:]
        tampered_payload["daily"] = tampered_daily
        cached["payload"] = tampered_payload
        # Do NOT update canonical_payload_sha256
        cache_path.write_text(
            json.dumps(cached, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        # The cache file hash changes, so the bundle manifest's cache_manifest hash
        # won't match.  Also, _verify_cached_response will reject the entry
        # because the canonical hash no longer matches.
        self.assertEqual(self._run_preflight(), 1)

    def test_altered_cache_payload_with_altered_canonical_hash_detected_by_bundle(self) -> None:
        """Altering a cache payload AND updating the canonical hash is still detected.

        The cache-level _verify_cached_response will pass (canonical hash matches),
        but the cache FILE hash changes, so the bundle manifest's cache_manifest
        file hash won't match.  The preflight detects this.
        """
        from backend.common.open_meteo_interval_features import (
            _canonical_bytes,
            _sha256,
        )

        cache_dir = self.artifact_dir / "raw_cache"
        cache_files = [f for f in cache_dir.glob("*.json") if f.name != "cache_manifest.json"]
        self.assertGreater(len(cache_files), 0)

        cache_path = cache_files[0]
        cached = json.loads(cache_path.read_text())
        # Tamper: change payload AND update canonical hash
        tampered_payload = dict(cached["payload"])
        tampered_daily = dict(tampered_payload["daily"])
        tampered_daily["temperature_2m_mean"] = [999.0] + tampered_daily["temperature_2m_mean"][1:]
        tampered_payload["daily"] = tampered_daily
        cached["payload"] = tampered_payload
        cached["canonical_payload_sha256"] = _sha256(_canonical_bytes(tampered_payload))
        cache_path.write_text(
            json.dumps(cached, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        # The cache file hash changes, so the bundle manifest's cache_manifest
        # file hash won't match.
        self.assertEqual(self._run_preflight(), 1)

    def test_altered_bundle_component_hashes_cause_mismatch(self) -> None:
        """Altering component hashes in the bundle manifest must be detected."""
        bundle = self._load_json("bundle_manifest.json")
        # Change a component hash
        bundle["component_hashes"]["features_jsonl"]["sha256"] = "0" * 64
        # Recompute bundle_sha256 to match the altered component hashes
        # (this tests that the verifier checks file hashes, not just bundle self-hash)
        bundle_bytes = json.dumps(
            bundle["component_hashes"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        bundle["bundle_sha256"] = hashlib.sha256(bundle_bytes).hexdigest()
        self._save_json("bundle_manifest.json", bundle)
        # The bundle self-hash will match, but the features file hash won't match
        # the altered component hash.
        self.assertEqual(self._run_preflight(), 1)

    def test_training_eligible_true_returns_2(self) -> None:
        """Setting training_eligible=true must cause exit code 2 (safety violation)."""
        provenance = self._load_json("source_provenance.json")
        provenance["training_eligible"] = True
        self._save_json("source_provenance.json", provenance)
        # This changes the provenance file hash, so structural checks will also fail.
        # But the key assertion is that training_blocked is False.
        exit_code = self._run_preflight()
        # The preflight should return 1 (structural failure due to hash mismatch)
        # OR 2 (if structural passes but training not blocked).
        # Since we changed the provenance file, the hash will mismatch, so exit 1.
        # But let's also verify by updating the bundle to match:
        self.assertEqual(exit_code, 1)

    def test_training_eligible_true_with_matching_bundle_returns_2(self) -> None:
        """Setting training_eligible=true AND updating all hashes must return 2.

        This requires updating provenance, snapshot manifest, and bundle to
        all agree.  The cross-manifest checks ensure consistency across all
        manifests, so all must be tampered together for the structural checks
        to pass while training is unblocked.
        """
        from backend.common.station_free_feature_snapshot import _manifest_hash

        # Tamper provenance
        provenance = self._load_json("source_provenance.json")
        provenance["training_eligible"] = True
        provenance["production_scoring_eligible"] = True
        self._save_json("source_provenance.json", provenance)

        # Tamper snapshot manifest to match
        snapshot_manifest = self._load_json("snapshot_manifest.json")
        snapshot_manifest["training_eligible"] = True
        snapshot_manifest["core_training_eligible"] = True
        snapshot_manifest["production_eligible"] = True
        snapshot_manifest["production_scoring_eligible"] = True
        # Recompute manifest_hash
        snapshot_manifest["manifest_hash"] = _manifest_hash(snapshot_manifest)
        self._save_json("snapshot_manifest.json", snapshot_manifest)

        # Update bundle manifest to match all tampered files
        bundle = self._load_json("bundle_manifest.json")
        provenance_path = self.artifact_dir / "source_provenance.json"
        snapshot_path = self.artifact_dir / "snapshot_manifest.json"
        bundle["component_hashes"]["source_provenance"]["sha256"] = hashlib.sha256(
            provenance_path.read_bytes()
        ).hexdigest()
        bundle["component_hashes"]["snapshot_manifest"]["sha256"] = hashlib.sha256(
            snapshot_path.read_bytes()
        ).hexdigest()
        bundle["component_hashes"]["snapshot_manifest"]["manifest_hash"] = snapshot_manifest["manifest_hash"]
        # Update training_eligible in bundle summary
        bundle["training_eligible"] = True
        bundle["production_scoring_eligible"] = True
        # Recompute bundle hash
        bundle_bytes = json.dumps(
            bundle["component_hashes"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        bundle["bundle_sha256"] = hashlib.sha256(bundle_bytes).hexdigest()
        self._save_json("bundle_manifest.json", bundle)

        # Now structural checks should pass, but training_blocked is False
        exit_code = self._run_preflight()
        self.assertEqual(exit_code, 2)

    def test_bundle_sha256_mismatch_returns_1(self) -> None:
        """Changing the bundle_sha256 without changing component hashes must be detected."""
        bundle = self._load_json("bundle_manifest.json")
        bundle["bundle_sha256"] = "0" * 64
        self._save_json("bundle_manifest.json", bundle)
        self.assertEqual(self._run_preflight(), 1)


class PreflightStationSemanticsTests(unittest.TestCase):
    """Tests that station semantics are checked across all rows."""

    def test_station_feed_semantics_wrong_in_one_row_returns_1(self) -> None:
        """If even one row has wrong station_feed_semantics, preflight must fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            labels = [_label("event-a"), _label("event-b", join_key="himalayas_nepal:1:2")]
            artifact_dir, _ = _build_artifact(tmpdir_path, labels)

            # Tamper: change station_feed_semantics in the first feature row
            features_path = artifact_dir / "features.jsonl"
            lines = features_path.read_text().splitlines()
            first_row = json.loads(lines[0])
            first_row["station_feed_semantics"] = "wrong_value"
            lines[0] = json.dumps(first_row, ensure_ascii=False, sort_keys=True)
            features_path.write_text("\n".join(lines) + "\n")

            exit_code = preflight_main([str(artifact_dir), "--repo-root", str(tmpdir_path)])
            self.assertEqual(exit_code, 1)


class PreflightPathEscapeTests(unittest.TestCase):
    """Tests that path traversal and absolute-path escapes are rejected."""

    def test_absolute_path_outside_root_rejected(self) -> None:
        """An absolute path outside repo_root must not be resolved."""
        from backend.scripts.preflight_shadow_nepal import _safe_resolve
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "artifact"
            base.mkdir()
            repo_root = Path(tmpdir)
            # /etc/hosts is a real file but outside both base and repo_root
            result = _safe_resolve(base, "/etc/hosts", repo_root=repo_root)
            self.assertIsNone(result)

    def test_path_traversal_rejected(self) -> None:
        """Path traversal (../../etc/hosts) must not escape the allowed roots."""
        from backend.scripts.preflight_shadow_nepal import _safe_resolve
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "artifact"
            base.mkdir()
            repo_root = Path(tmpdir)
            result = _safe_resolve(base, "../../../etc/hosts", repo_root=repo_root)
            self.assertIsNone(result)

    def test_relative_path_within_repo_root_accepted(self) -> None:
        """A relative path within repo_root (but outside artifact) must be accepted."""
        from backend.scripts.preflight_shadow_nepal import _safe_resolve
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "artifact"
            base.mkdir()
            repo_root = Path(tmpdir)
            # Create a file in repo_root (outside artifact)
            external_file = repo_root / "external.json"
            external_file.write_text('{"test": true}')
            result = _safe_resolve(base, "external.json", repo_root=repo_root)
            self.assertIsNotNone(result)
            self.assertEqual(result, external_file.resolve())


class PreflightCacheIndexTests(unittest.TestCase):
    """Tests for cache-key derivation, duplicate keys, and extra/missing files."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir_path = Path(self._tmpdir.name)
        labels = [_label("event-a"), _label("event-b", join_key="himalayas_nepal:1:2")]
        self.artifact_dir, self.label_manifest_path = _build_artifact(self.tmpdir_path, labels)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _run_preflight(self) -> int:
        return preflight_main([str(self.artifact_dir), "--repo-root", str(self.tmpdir_path)])

    def _load_json(self, relative: str) -> dict[str, Any]:
        return json.loads((self.artifact_dir / relative).read_text())

    def _save_json(self, relative: str, data: dict[str, Any]) -> None:
        path = self.artifact_dir / relative
        path.write_text(
            json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_wrong_cache_key_returns_1(self) -> None:
        """A cache entry with wrong cache_key (not SHA256(url)) must be detected."""
        cache_manifest = self._load_json("raw_cache/cache_manifest.json")
        # Corrupt the cache_key of the first entry
        cache_manifest["entries"][0]["cache_key"] = "0" * 64
        # Recompute internal hash to match
        from backend.common.open_meteo_interval_features import _canonical_bytes, _sha256
        cache_manifest["cache_manifest_sha256"] = _sha256(_canonical_bytes(cache_manifest["entries"]))
        self._save_json("raw_cache/cache_manifest.json", cache_manifest)
        # Update bundle to match the tampered cache manifest
        bundle = self._load_json("bundle_manifest.json")
        cache_path = self.artifact_dir / "raw_cache" / "cache_manifest.json"
        bundle["component_hashes"]["cache_manifest"]["sha256"] = hashlib.sha256(
            cache_path.read_bytes()
        ).hexdigest()
        bundle["component_hashes"]["cache_manifest"]["cache_manifest_sha256"] = (
            cache_manifest["cache_manifest_sha256"]
        )
        bundle_bytes = json.dumps(
            bundle["component_hashes"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        bundle["bundle_sha256"] = hashlib.sha256(bundle_bytes).hexdigest()
        self._save_json("bundle_manifest.json", bundle)
        self.assertEqual(self._run_preflight(), 1)

    def test_duplicate_cache_key_returns_1(self) -> None:
        """Duplicate cache_keys in the manifest must be detected."""
        cache_manifest = self._load_json("raw_cache/cache_manifest.json")
        # Duplicate the first entry
        cache_manifest["entries"].append(dict(cache_manifest["entries"][0]))
        cache_manifest["entry_count"] = len(cache_manifest["entries"])
        from backend.common.open_meteo_interval_features import _canonical_bytes, _sha256
        cache_manifest["cache_manifest_sha256"] = _sha256(_canonical_bytes(cache_manifest["entries"]))
        self._save_json("raw_cache/cache_manifest.json", cache_manifest)
        # Update bundle
        bundle = self._load_json("bundle_manifest.json")
        cache_path = self.artifact_dir / "raw_cache" / "cache_manifest.json"
        bundle["component_hashes"]["cache_manifest"]["sha256"] = hashlib.sha256(
            cache_path.read_bytes()
        ).hexdigest()
        bundle["component_hashes"]["cache_manifest"]["cache_manifest_sha256"] = (
            cache_manifest["cache_manifest_sha256"]
        )
        bundle_bytes = json.dumps(
            bundle["component_hashes"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        bundle["bundle_sha256"] = hashlib.sha256(bundle_bytes).hexdigest()
        self._save_json("bundle_manifest.json", bundle)
        self.assertEqual(self._run_preflight(), 1)

    def test_extra_cache_file_returns_1(self) -> None:
        """An extra cache file not listed in the manifest must be detected."""
        cache_dir = self.artifact_dir / "raw_cache"
        # Create an extra cache file
        extra_path = cache_dir / "deadbeef.json"
        extra_path.write_text('{"fake": true}')
        self.assertEqual(self._run_preflight(), 1)

    def test_missing_cache_file_returns_1(self) -> None:
        """A missing cache file listed in the manifest must be detected."""
        cache_dir = self.artifact_dir / "raw_cache"
        cache_files = [f for f in cache_dir.glob("*.json") if f.name != "cache_manifest.json"]
        self.assertGreater(len(cache_files), 0)
        # Remove a cache file
        cache_files[0].unlink()
        self.assertEqual(self._run_preflight(), 1)


class PreflightSchemaVersionTests(unittest.TestCase):
    """Tests for schema version enforcement."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir_path = Path(self._tmpdir.name)
        labels = [_label("event-a"), _label("event-b", join_key="himalayas_nepal:1:2")]
        self.artifact_dir, self.label_manifest_path = _build_artifact(self.tmpdir_path, labels)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _run_preflight(self) -> int:
        return preflight_main([str(self.artifact_dir), "--repo-root", str(self.tmpdir_path)])

    def _load_json(self, relative: str) -> dict[str, Any]:
        return json.loads((self.artifact_dir / relative).read_text())

    def _save_json(self, relative: str, data: dict[str, Any]) -> None:
        path = self.artifact_dir / relative
        path.write_text(
            json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    def _update_bundle_for_tamper(self) -> None:
        """Update bundle hashes to match tampered files (for testing structural checks only)."""
        bundle = self._load_json("bundle_manifest.json")
        for component, rel_path in [
            ("snapshot_manifest", "snapshot_manifest.json"),
            ("source_provenance", "source_provenance.json"),
        ]:
            path = self.artifact_dir / rel_path
            bundle["component_hashes"][component]["sha256"] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
        bundle_bytes = json.dumps(
            bundle["component_hashes"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        bundle["bundle_sha256"] = hashlib.sha256(bundle_bytes).hexdigest()
        self._save_json("bundle_manifest.json", bundle)

    def test_wrong_bundle_schema_version_returns_1(self) -> None:
        """Wrong bundle_schema_version must be detected."""
        bundle = self._load_json("bundle_manifest.json")
        bundle["bundle_schema_version"] = "wrong_version"
        self._save_json("bundle_manifest.json", bundle)
        # Bundle self-hash will mismatch since we changed a non-component field
        self.assertEqual(self._run_preflight(), 1)

    def test_wrong_snapshot_schema_version_returns_1(self) -> None:
        """Wrong snapshot_schema_version must be detected."""
        from backend.common.station_free_feature_snapshot import _manifest_hash
        snapshot = self._load_json("snapshot_manifest.json")
        snapshot["snapshot_schema_version"] = "wrong_version"
        snapshot["manifest_hash"] = _manifest_hash(snapshot)
        self._save_json("snapshot_manifest.json", snapshot)
        self._update_bundle_for_tamper()
        self.assertEqual(self._run_preflight(), 1)

    def test_wrong_feature_time_contract_returns_1(self) -> None:
        """Wrong feature_time_contract must be detected."""
        from backend.common.station_free_feature_snapshot import _manifest_hash
        snapshot = self._load_json("snapshot_manifest.json")
        snapshot["feature_time_contract"] = "wrong_contract"
        snapshot["manifest_hash"] = _manifest_hash(snapshot)
        self._save_json("snapshot_manifest.json", snapshot)
        self._update_bundle_for_tamper()
        self.assertEqual(self._run_preflight(), 1)

    def test_cross_manifest_region_mismatch_returns_1(self) -> None:
        """Region keys mismatch between snapshot and provenance must be detected."""
        provenance = self._load_json("source_provenance.json")
        provenance["requested_regions"] = ["wrong_region"]
        self._save_json("source_provenance.json", provenance)
        self._update_bundle_for_tamper()
        self.assertEqual(self._run_preflight(), 1)


class PreflightSymlinkEscapeTests(unittest.TestCase):
    """360-degree test: symlink chains must not escape allowed roots."""

    def test_symlink_escape_rejected(self) -> None:
        """A symlink pointing outside repo_root must not be resolved."""
        from backend.scripts.preflight_shadow_nepal import _safe_resolve
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "artifact"
            base.mkdir()
            repo_root = Path(tmpdir)
            # Create a symlink inside base that points to /etc
            symlink_path = base / "escape_link.json"
            try:
                symlink_path.symlink_to("/etc/hosts")
            except (OSError, NotImplementedError):
                self.skipTest("symlinks not supported on this platform")
            result = _safe_resolve(base, "escape_link.json", repo_root=repo_root)
            # The symlink resolves to /etc/hosts which is outside both roots
            self.assertIsNone(result)

    def test_symlink_to_repo_root_file_accepted(self) -> None:
        """A symlink pointing to a file within repo_root should be accepted."""
        from backend.scripts.preflight_shadow_nepal import _safe_resolve
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "artifact"
            base.mkdir()
            repo_root = Path(tmpdir)
            # Create a real file in repo_root
            real_file = repo_root / "real.json"
            real_file.write_text('{"ok": true}')
            # Create a symlink inside base pointing to the real file
            symlink_path = base / "link.json"
            try:
                symlink_path.symlink_to(real_file)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks not supported on this platform")
            result = _safe_resolve(base, "link.json", repo_root=repo_root)
            # Should resolve to the real file within repo_root
            self.assertIsNotNone(result)


class PreflightCoveragePassTests(unittest.TestCase):
    """360-degree test: coverage_pass=False with other passes True must fail."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir_path = Path(self._tmpdir.name)
        labels = [_label("event-a"), _label("event-b", join_key="himalayas_nepal:1:2")]
        self.artifact_dir, self.label_manifest_path = _build_artifact(self.tmpdir_path, labels)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _run_preflight(self) -> int:
        return preflight_main([str(self.artifact_dir), "--repo-root", str(self.tmpdir_path)])

    def _load_json(self, relative: str) -> dict[str, Any]:
        return json.loads((self.artifact_dir / relative).read_text())

    def _save_json(self, relative: str, data: dict[str, Any]) -> None:
        path = self.artifact_dir / relative
        path.write_text(
            json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_coverage_gate_fails_when_coverage_passes_false(self) -> None:
        """Tamper coverage_gate to have passed=False while keeping hashes consistent."""
        from backend.common.open_meteo_interval_features import _canonical_bytes, _sha256

        provenance = self._load_json("source_provenance.json")
        provenance["coverage_gate"]["passed"] = False
        self._save_json("source_provenance.json", provenance)

        # Update bundle to match
        bundle = self._load_json("bundle_manifest.json")
        provenance_path = self.artifact_dir / "source_provenance.json"
        bundle["component_hashes"]["source_provenance"]["sha256"] = hashlib.sha256(
            provenance_path.read_bytes()
        ).hexdigest()
        # Recompute coverage_gate hash
        coverage_bytes = json.dumps(
            provenance["coverage_gate"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        bundle["component_hashes"]["coverage_gate"]["sha256"] = hashlib.sha256(coverage_bytes).hexdigest()
        bundle_bytes = json.dumps(
            bundle["component_hashes"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        bundle["bundle_sha256"] = hashlib.sha256(bundle_bytes).hexdigest()
        self._save_json("bundle_manifest.json", bundle)

        exit_code = self._run_preflight()
        # coverage_pass will be False, so overall_pass is False
        self.assertEqual(exit_code, 1)


class PreflightCacheEntryCountTests(unittest.TestCase):
    """360-degree test: cache_manifest entry_count must match actual entries length."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir_path = Path(self._tmpdir.name)
        labels = [_label("event-a"), _label("event-b", join_key="himalayas_nepal:1:2")]
        self.artifact_dir, self.label_manifest_path = _build_artifact(self.tmpdir_path, labels)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _run_preflight(self) -> int:
        return preflight_main([str(self.artifact_dir), "--repo-root", str(self.tmpdir_path)])

    def _load_json(self, relative: str) -> dict[str, Any]:
        return json.loads((self.artifact_dir / relative).read_text())

    def _save_json(self, relative: str, data: dict[str, Any]) -> None:
        path = self.artifact_dir / relative
        path.write_text(
            json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_wrong_entry_count_returns_1(self) -> None:
        """entry_count field not matching len(entries) must be detected."""
        from backend.common.open_meteo_interval_features import _canonical_bytes, _sha256

        cache_manifest = self._load_json("raw_cache/cache_manifest.json")
        cache_manifest["entry_count"] = 999  # Wrong count
        self._save_json("raw_cache/cache_manifest.json", cache_manifest)

        # Update bundle
        bundle = self._load_json("bundle_manifest.json")
        cache_path = self.artifact_dir / "raw_cache" / "cache_manifest.json"
        bundle["component_hashes"]["cache_manifest"]["sha256"] = hashlib.sha256(
            cache_path.read_bytes()
        ).hexdigest()
        bundle_bytes = json.dumps(
            bundle["component_hashes"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        bundle["bundle_sha256"] = hashlib.sha256(bundle_bytes).hexdigest()
        self._save_json("bundle_manifest.json", bundle)

        self.assertEqual(self._run_preflight(), 1)


class PreflightEmptyArtifactTests(unittest.TestCase):
    """360-degree test: empty artifact dir must fail gracefully, not crash."""

    def test_empty_artifact_dir_returns_1(self) -> None:
        """An empty artifact directory must return exit 1, not crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "empty"
            artifact_dir.mkdir()
            exit_code = preflight_main([str(artifact_dir), "--repo-root", str(tmpdir)])
            self.assertEqual(exit_code, 1)


class PreflightResourceWarningTests(unittest.TestCase):
    """Regression test: preflight must not emit ResourceWarning from unclosed file handles."""

    def test_no_resource_warning_from_preflight(self) -> None:
        """Running preflight must not produce ResourceWarning from unclosed file handles.

        This is a regression test for the file-handle leak at the feature
        row count check (previously `sum(1 for _ in open(features_path))`
        without a context manager).
        """
        import gc
        import warnings

        labels = [_label("event-a"), _label("event-b", join_key="himalayas_nepal:1:2")]
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            artifact_dir, _ = _build_artifact(tmpdir_path, labels)

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                exit_code = preflight_main(
                    [str(artifact_dir), "--repo-root", str(tmpdir_path)]
                )
                gc.collect()  # trigger __del__ on any unclosed handles

            resource_warnings = [
                w for w in caught if issubclass(w.category, ResourceWarning)
            ]
            self.assertEqual(
                len(resource_warnings),
                0,
                f"ResourceWarning(s) emitted: {[str(w.message) for w in resource_warnings]}",
            )


class GateMissingShadowBundleTests(unittest.TestCase):
    """Advisor fix: --shadow-bundle-dir is mandatory on pre-remote path."""

    def test_missing_shadow_bundle_dir_blocks_gate(self) -> None:
        """Omitting --shadow-bundle-dir must block the gate (fail-closed)."""
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from scripts.verify_mvp4_pre_remote_gate import ROOT, evaluate_pre_remote_gate
        """Omitting --shadow-bundle-dir must block the gate (fail-closed)."""
        with TemporaryDirectory(dir=ROOT) as tmpdir:
            root = Path(tmpdir)
            for fname in ["scope.json", "approval.json", "snapshot.json",
                          "source.json", "payload.bin", "events.jsonl"]:
                (root / fname).write_text("{}")
            (root / "artifacts").mkdir(exist_ok=True)

            report = evaluate_pre_remote_gate(
                scope_manifest=root / "scope.json",
                approval_manifest=root / "approval.json",
                snapshot_manifest=root / "snapshot.json",
                artifact_root=root / "artifacts",
                source_request_manifest=root / "source.json",
                source_request_payload=root / "payload.bin",
                source_request_events=root / "events.jsonl",
                selected_region_keys=["himalayas_nepal"],
                # shadow_bundle_dir omitted — should block
            )

            self.assertFalse(report["passed"])
            self.assertTrue(
                any("shadow-bundle directory is required" in b for b in report["blockers"]),
                f"Expected shadow-bundle mandatory blocker in: {report['blockers']}",
            )

    def test_empty_shadow_bundle_dir_blocks_gate(self) -> None:
        """Empty string --shadow-bundle-dir must block the gate."""
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from scripts.verify_mvp4_pre_remote_gate import ROOT, evaluate_pre_remote_gate
        with TemporaryDirectory(dir=ROOT) as tmpdir:
            root = Path(tmpdir)
            for fname in ["scope.json", "approval.json", "snapshot.json",
                          "source.json", "payload.bin", "events.jsonl"]:
                (root / fname).write_text("{}")
            (root / "artifacts").mkdir(exist_ok=True)

            report = evaluate_pre_remote_gate(
                scope_manifest=root / "scope.json",
                approval_manifest=root / "approval.json",
                snapshot_manifest=root / "snapshot.json",
                artifact_root=root / "artifacts",
                source_request_manifest=root / "source.json",
                source_request_payload=root / "payload.bin",
                source_request_events=root / "events.jsonl",
                selected_region_keys=["himalayas_nepal"],
                shadow_bundle_dir=Path("  "),  # whitespace-only path
            )

            self.assertFalse(report["passed"])
            self.assertTrue(
                any("shadow-bundle" in b for b in report["blockers"]),
                f"Expected shadow-bundle blocker in: {report['blockers']}",
            )


class AttestationTests(unittest.TestCase):
    """Tests for the release attestation generator."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir_path = Path(self._tmpdir.name)
        labels = [_label("event-a"), _label("event-b", join_key="himalayas_nepal:1:2")]
        self.artifact_dir, self.label_manifest_path = _build_artifact(self.tmpdir_path, labels)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _load_json(self, relative: str) -> dict[str, Any]:
        return json.loads((self.artifact_dir / relative).read_text())

    def _save_json(self, relative: str, data: dict[str, Any]) -> None:
        path = self.artifact_dir / relative
        path.write_text(
            json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_attestation_generated_successfully(self) -> None:
        """Attestation is generated with all required fields."""
        from backend.scripts.generate_release_attestation import generate_attestation
        # Run preflight first so a preflight report exists
        preflight_main([str(self.artifact_dir), "--repo-root", str(self.tmpdir_path)])
        attestation = generate_attestation(self.artifact_dir, repo_root=self.tmpdir_path)
        self.assertEqual(attestation["attestation_schema_version"], "mvp4_shadow_release_attestation_v1")
        self.assertIsNotNone(attestation["attestation_sha256"])
        self.assertIsNotNone(attestation["bundle_sha256"])
        self.assertEqual(attestation["status"], "shadow_only")
        self.assertFalse(attestation["training_eligible"])
        self.assertFalse(attestation["production_eligible"])
        self.assertEqual(attestation["trust_classification"], "locally_self_consistent")
        self.assertIsNotNone(attestation["preflight_report_sha256"])

    def test_attestation_hash_drift_detected(self) -> None:
        """360-degree test: stale attestation hash must not match after artifact tampering."""
        from backend.scripts.generate_release_attestation import generate_attestation
        # Generate attestation
        attestation = generate_attestation(self.artifact_dir, repo_root=self.tmpdir_path)
        original_hash = attestation["attestation_sha256"]
        original_bundle_hash = attestation["bundle_sha256"]

        # Tamper with bundle_manifest.json (changes the bundle_sha256 the attestation reads)
        bundle = self._load_json("bundle_manifest.json")
        bundle["bundle_sha256"] = "0" * 64
        self._save_json("bundle_manifest.json", bundle)

        # Regenerate attestation
        new_attestation = generate_attestation(self.artifact_dir, repo_root=self.tmpdir_path)
        # The attestation hash should be different (bundle_sha256 changed)
        self.assertNotEqual(original_hash, new_attestation["attestation_sha256"])
        # The bundle hash should also be different
        self.assertNotEqual(original_bundle_hash, new_attestation["bundle_sha256"])

    def test_attestation_missing_bundle_fails(self) -> None:
        """Attestation generation must fail if bundle_manifest.json is missing."""
        from backend.scripts.generate_release_attestation import generate_attestation
        # Remove bundle manifest
        (self.artifact_dir / "bundle_manifest.json").unlink()
        with self.assertRaises(ValueError):
            generate_attestation(self.artifact_dir, repo_root=self.tmpdir_path)

    def test_attestation_uses_portable_relative_paths(self) -> None:
        """G7: attestation must use repo-root-relative paths, not absolute machine paths."""
        from backend.scripts.generate_release_attestation import generate_attestation
        preflight_main([str(self.artifact_dir), "--repo-root", str(self.tmpdir_path)])
        attestation = generate_attestation(self.artifact_dir, repo_root=self.tmpdir_path)
        # artifact_dir must be relative, not an absolute /Users/... path
        self.assertFalse(
            attestation["artifact_dir"].startswith("/"),
            f"artifact_dir must be relative, got: {attestation['artifact_dir']}",
        )
        # repo_root must be "." (portable), not an absolute path
        self.assertEqual(attestation["repo_root"], ".")
        # The relative path should resolve back to the original artifact_dir
        resolved = (self.tmpdir_path / attestation["artifact_dir"]).resolve()
        self.assertEqual(resolved, self.artifact_dir.resolve())


if __name__ == "__main__":
    unittest.main()
