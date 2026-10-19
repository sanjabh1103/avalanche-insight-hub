"""Tests for native SNOWPACK output artifact manifest (Phase 5-prep)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.common.snowpack_artifact_manifest import (
    ArtifactEntry,
    ArtifactManifest,
    build_manifest_from_directory,
    compute_file_hash,
    manifest_to_json,
    CRITICAL_OUTPUT_EXTENSIONS,
    SNOWPACK_OUTPUT_EXTENSIONS,
)


class TestArtifactManifest(unittest.TestCase):
    """Test artifact manifest validation."""

    def _valid_manifest(self, **overrides) -> ArtifactManifest:
        defaults = dict(
            run_id='run_001',
            region_key='himalayas_nepal',
            elevation_band='lower',
            aspect_class='N',
            binary_version='snowpack-3.7.0',
            artifacts=(
                ArtifactEntry(
                    file_path='/output/run_001.pro',
                    file_type='.pro',
                    size_bytes=1024,
                    sha256='a' * 64,
                    is_critical=True,
                    role='profile_pro',
                ),
                ArtifactEntry(
                    file_path='/output/run_001.sno',
                    file_type='.sno',
                    size_bytes=512,
                    sha256='b' * 64,
                    is_critical=True,
                    role='snow_profile_sno',
                ),
                ArtifactEntry(
                    file_path='/output/run_001.haz',
                    file_type='.haz',
                    size_bytes=256,
                    sha256='c' * 64,
                    is_critical=True,
                    role='hazard_haz',
                ),
                ArtifactEntry(
                    file_path='/output/run_001.smet',
                    file_type='.smet',
                    size_bytes=128,
                    sha256='d' * 64,
                    is_critical=True,
                    role='forcing_smet',
                ),
            ),
            is_native_execution=True,
            native_binary_invoked=True,
            created_at='2026-01-15T00:00:00+00:00',
        )
        defaults.update(overrides)
        return ArtifactManifest(**defaults)

    def test_valid_manifest_accepted(self) -> None:
        errors = self._valid_manifest().validate()
        self.assertEqual(errors, [])

    def test_dry_run_manifest_rejected(self) -> None:
        """Dry-run paths must not produce an ArtifactManifest."""
        errors = self._valid_manifest(is_native_execution=False).validate()
        self.assertTrue(any('is_native_execution' in e for e in errors))

    def test_empty_artifacts_rejected(self) -> None:
        errors = self._valid_manifest(artifacts=()).validate()
        self.assertTrue(any('at least one artifact' in e for e in errors))

    def test_empty_file_rejected(self) -> None:
        """No missing critical output is silently accepted."""
        empty_art = ArtifactEntry(
            file_path='/output/empty.pro', file_type='.pro',
            size_bytes=0, sha256='a' * 64, is_critical=True,
        )
        errors = self._valid_manifest(artifacts=(empty_art,)).validate()
        self.assertTrue(any('empty' in e.lower() for e in errors))

    def test_missing_critical_outputs_rejected(self) -> None:
        """Native execution must produce .pro and .sno files."""
        non_critical = ArtifactEntry(
            file_path='/output/run.log', file_type='.log',
            size_bytes=100, sha256='c' * 64, is_critical=False,
        )
        errors = self._valid_manifest(artifacts=(non_critical,)).validate()
        self.assertTrue(any('missing critical' in e for e in errors))

    def test_missing_hash_rejected(self) -> None:
        """Outputs must be hash-linked."""
        no_hash = ArtifactEntry(
            file_path='/output/run.pro', file_type='.pro',
            size_bytes=100, sha256='', is_critical=True,
        )
        errors = self._valid_manifest(artifacts=(no_hash,)).validate()
        self.assertTrue(any('hash' in e.lower() for e in errors))

    def test_unexpected_file_type_rejected(self) -> None:
        bad_type = ArtifactEntry(
            file_path='/output/run.txt', file_type='.txt',
            size_bytes=100, sha256='d' * 64, is_critical=False,
        )
        errors = self._valid_manifest(artifacts=(bad_type,)).validate()
        self.assertTrue(any('unexpected file type' in e for e in errors))


class TestBuildManifestFromDirectory(unittest.TestCase):
    """Test building a manifest from a directory of outputs."""

    def test_build_manifest_with_valid_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / 'run.smet').write_text('forcing data')
            (tmp_path / 'processed-meteo.smet').write_text('processed meteo data')
            (tmp_path / 'run.pro').write_text('profile data')
            (tmp_path / 'run.sno').write_text('snow data')
            (tmp_path / 'run.haz').write_text('hazard data')
            (tmp_path / 'run.log').write_text('log data')

            manifest = build_manifest_from_directory(
                run_id='run_001',
                region_key='himalayas_nepal',
                elevation_band='lower',
                aspect_class='N',
                binary_version='snowpack-3.7.0',
                output_dir=tmp_path,
                created_at='2026-01-15T00:00:00+00:00',
                native_binary_invoked=True,
            )

            errors = manifest.validate()
            self.assertEqual(errors, [])
            self.assertEqual(len(manifest.artifacts), 6)
            self.assertTrue(manifest.is_native_execution)

    def test_build_manifest_with_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = build_manifest_from_directory(
                run_id='run_001',
                region_key='himalayas_nepal',
                elevation_band='lower',
                aspect_class='N',
                binary_version='snowpack-3.7.0',
                output_dir=Path(tmp),
                created_at='2026-01-15T00:00:00+00:00',
            )
            errors = manifest.validate()
            self.assertTrue(any('at least one artifact' in e for e in errors))

    def test_explicit_native_smet_roles_preserve_all_outputs(self) -> None:
        """Pinned SNOWPACK SMET outputs must not collapse into one role."""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp).resolve()
            files = {
                'station.smet': 'input forcing',
                'station_native_forcing.smet': 'processed forcing',
                'station_native.smet': 'model time series',
            }
            for name, content in files.items():
                (output_dir / name).write_text(content, encoding='utf-8')
            manifest = build_manifest_from_directory(
                run_id='run_001',
                region_key='himalayas_nepal',
                elevation_band='lower',
                aspect_class='N',
                binary_version='snowpack-3.7.0',
                output_dir=output_dir,
                created_at='2026-01-15T00:00:00+00:00',
                native_binary_invoked=True,
                artifact_roles={
                    str(output_dir / 'station.smet'): 'forcing_smet',
                    str(output_dir / 'station_native_forcing.smet'): 'processed_meteo',
                    str(output_dir / 'station_native.smet'): 'model_timeseries_smet',
                },
            )
            self.assertEqual(
                {artifact.role for artifact in manifest.artifacts},
                {'forcing_smet', 'processed_meteo', 'model_timeseries_smet'},
            )


class TestComputeFileHash(unittest.TestCase):
    """Test file hash computation."""

    def test_hash_is_deterministic(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b'test content')
            f.flush()
            h1 = compute_file_hash(Path(f.name))
            h2 = compute_file_hash(Path(f.name))
            self.assertEqual(h1, h2)
            self.assertEqual(len(h1), 64)


class TestManifestToJson(unittest.TestCase):
    """Test manifest JSON serialization."""

    def test_json_serialization(self) -> None:
        manifest = self._valid_manifest() if hasattr(self, '_valid_manifest') else None
        if manifest is None:
            manifest = ArtifactManifest(
                run_id='run_001', region_key='himalayas_nepal',
                elevation_band='lower', aspect_class='N',
                binary_version='snowpack-3.7.0',
                artifacts=(ArtifactEntry(
                    file_path='/output/run.pro', file_type='.pro',
                    size_bytes=100, sha256='a' * 64, is_critical=True,
                ),),
                is_native_execution=True,
                native_binary_invoked=True,
                created_at='2026-01-15T00:00:00+00:00',
            )
        json_str = manifest_to_json(manifest)
        self.assertIn('run_001', json_str)
        self.assertIn('himalayas_nepal', json_str)


if __name__ == '__main__':
    unittest.main()
