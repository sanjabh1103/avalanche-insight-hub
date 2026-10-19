"""Tests for native SNOWPACK binary resolution and output gating."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from backend.common.meteoio_openmeteo import (
    NativeExecutionEvidence,
    parse_snowpack_pro,
    run_snowpack_native,
    snowpack_binary_available,
    write_snow_free_smet_profile,
)


_MINIMAL_SMET_WITH_COORDINATES = (
    'SMET 1.1 ASCII\n'
    '[HEADER]\n'
    'station_id = input\n'
    'latitude = 33.5\n'
    'longitude = 74.0\n'
    'altitude = 3500\n'
    '[DATA]\n'
)


class TestNativeBinaryResolution(unittest.TestCase):
    def test_snow_free_profile_is_revision_compatible_zero_layer_smet(self) -> None:
        """SNOWPACK 3.7 needs an explicit zero-layer SMET seed for snow-free starts."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'pir-panjal-middle-candidate.sno'
            write_snow_free_smet_profile(
                output_path=path,
                station_id='pir-panjal-middle-candidate',
                latitude=34.002778,
                longitude=74.247222,
                elevation=3359.0,
                profile_date='2023-10-01T00:00:00Z',
                slope_angle=31.8,
                aspect=6.2,
            )
            content = path.read_text(encoding='utf-8')
            self.assertIn('nSoilLayerData = 0', content)
            self.assertIn('nSnowLayerData = 0', content)
            self.assertIn('ProfileDate = 2023-10-01T00:00:00Z', content)
            self.assertIn('fields = timestamp Layer_Thick T Vol_Frac_I Vol_Frac_W Vol_Frac_V Vol_Frac_S Rho_S Conduc_S HeatCapac_S rg rb dd sp mk mass_hoar ne CDot metamo', content)

    def test_official_cli_contract_uses_config_and_end_date(self) -> None:
        """The native bridge must use SNOWPACK's official -c/-e interface."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            args_log = root / 'args.log'
            fake_binary = bin_dir / 'snowpack'
            fake_binary.write_text(
                '#!/bin/sh\n'
                'if [ "$1" = "--version" ]; then printf "SNOWPACK 3.7.0\\n"; exit 0; fi\n'
                'printf "%s\\n" "$@" > "$SNOWPACK_ARGS_LOG"\n'
                'config=""\n'
                'previous=""\n'
                'for arg in "$@"; do\n'
                '  if [ "$previous" = "-c" ]; then config="$arg"; fi\n'
                '  if [ "$arg" = "-i" ] || [ "$arg" = "-o" ]; then exit 12; fi\n'
                '  previous="$arg"\n'
                'done\n'
                'if [ -z "$config" ]; then exit 13; fi\n'
                'output_dir=$(dirname "$config")\n'
                'printf "native profile\\n" > "$output_dir/input_poc.pro"\n'
                'exit 0\n',
                encoding='utf-8',
            )
            fake_binary.chmod(fake_binary.stat().st_mode | stat.S_IXUSR)
            toolchain_manifest = {
                'schema_version': 'snowpack_toolchain_manifest_v1',
                'toolchain_id': 'test-toolchain',
                'meteoio_commit': 'a' * 40,
                'snowpack_commit': 'b' * 40,
                'binary_path': str(fake_binary),
                'binary_sha256': hashlib.sha256(fake_binary.read_bytes()).hexdigest(),
                'binary_version': 'SNOWPACK 3.7.0',
                'image_id': 'sha256:' + 'c' * 64,
                'image_archive_sha256': 'd' * 64,
                'image_repository_digest': '',
                'image_identity_source': 'local_id_and_archive',
            }
            (root / 'toolchain-manifest.json').write_text(
                json.dumps(toolchain_manifest), encoding='utf-8'
            )
            smet = root / 'input.smet'
            smet.write_text(_MINIMAL_SMET_WITH_COORDINATES, encoding='utf-8')
            output_dir = root / 'output'
            output_dir.mkdir()
            config_path = output_dir / 'snowpack.ini'
            config_path.write_text(
                '[Input]\nMETEOPATH = /input\nSTATION1 = input\n'
                '[Output]\nMETEOPATH = /output\nEXPERIMENT = poc\n',
                encoding='utf-8',
            )
            old_path = os.environ.get('PATH', '')
            old_args_log = os.environ.get('SNOWPACK_ARGS_LOG')
            old_image_id = os.environ.get('SNOWPACK_IMAGE_ID')
            old_image_archive_sha256 = os.environ.get('SNOWPACK_IMAGE_ARCHIVE_SHA256')
            os.environ['SNOWPACK_ARGS_LOG'] = str(args_log)
            os.environ['SNOWPACK_IMAGE_ID'] = 'sha256:' + 'c' * 64
            os.environ['SNOWPACK_IMAGE_ARCHIVE_SHA256'] = 'd' * 64
            os.environ['PATH'] = f'{bin_dir}{os.pathsep}{old_path}'
            try:
                result = run_snowpack_native(
                    smet_path=smet,
                    output_dir=output_dir,
                    config_path=config_path,
                    begin_date='2023-10-01T00:00',
                    end_date='2026-01-15T00:00',
                )
            finally:
                os.environ['PATH'] = old_path
                if old_args_log is None:
                    os.environ.pop('SNOWPACK_ARGS_LOG', None)
                else:
                    os.environ['SNOWPACK_ARGS_LOG'] = old_args_log
                if old_image_id is None:
                    os.environ.pop('SNOWPACK_IMAGE_ID', None)
                else:
                    os.environ['SNOWPACK_IMAGE_ID'] = old_image_id
                if old_image_archive_sha256 is None:
                    os.environ.pop('SNOWPACK_IMAGE_ARCHIVE_SHA256', None)
                else:
                    os.environ['SNOWPACK_IMAGE_ARCHIVE_SHA256'] = old_image_archive_sha256

            self.assertIsNotNone(result)
            self.assertTrue(result.success)
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(Path(result.pro_path).name, 'input_poc.pro')
            args = args_log.read_text(encoding='utf-8').splitlines()
            self.assertIn('-c', args)
            self.assertIn(str(config_path.resolve()), args)
            self.assertIn('-b', args)
            self.assertIn('2023-10-01T00:00', args)
            self.assertIn('-e', args)
            self.assertIn('2026-01-15T00:00', args)
            self.assertNotIn('-i', args)
            self.assertNotIn('-o', args)

    def test_version_attestation_preserves_merged_stream_order(self) -> None:
        """Runtime attestation must match the Dockerfile's ``2>&1`` probe."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_binary = root / 'snowpack'
            fake_binary.write_text(
                '#!/bin/sh\n'
                'if [ "$1" = "--version" ]; then '
                'printf "stderr-version\\n" >&2; '
                'printf "stdout-version\\n"; exit 0; fi\n'
                'config=""\n'
                'previous=""\n'
                'for arg in "$@"; do\n'
                '  if [ "$previous" = "-c" ]; then config="$arg"; fi\n'
                '  previous="$arg"\n'
                'done\n'
                'printf "native profile\\n" > "$(dirname "$config")/input.pro"\n',
                encoding='utf-8',
            )
            fake_binary.chmod(fake_binary.stat().st_mode | stat.S_IXUSR)
            toolchain_manifest = {
                'schema_version': 'snowpack_toolchain_manifest_v1',
                'toolchain_id': 'test-toolchain',
                'meteoio_commit': 'a' * 40,
                'snowpack_commit': 'b' * 40,
                'binary_path': str(fake_binary),
                'binary_sha256': hashlib.sha256(fake_binary.read_bytes()).hexdigest(),
                'binary_version': 'stderr-version stdout-version',
                'image_id': 'sha256:' + 'c' * 64,
                'image_archive_sha256': 'd' * 64,
                'image_repository_digest': '',
                'image_identity_source': 'local_id_and_archive',
            }
            (root / 'toolchain-manifest.json').write_text(
                json.dumps(toolchain_manifest), encoding='utf-8'
            )
            smet = root / 'input.smet'
            smet.write_text(_MINIMAL_SMET_WITH_COORDINATES, encoding='utf-8')
            old_path = os.environ.get('PATH', '')
            old_image_id = os.environ.get('SNOWPACK_IMAGE_ID')
            old_image_archive_sha256 = os.environ.get('SNOWPACK_IMAGE_ARCHIVE_SHA256')
            os.environ['SNOWPACK_IMAGE_ID'] = 'sha256:' + 'c' * 64
            os.environ['SNOWPACK_IMAGE_ARCHIVE_SHA256'] = 'd' * 64
            os.environ['PATH'] = f'{root}{os.pathsep}{old_path}'
            try:
                result = run_snowpack_native(
                    smet_path=smet,
                    output_dir=root / 'output',
                )
            finally:
                os.environ['PATH'] = old_path
                if old_image_id is None:
                    os.environ.pop('SNOWPACK_IMAGE_ID', None)
                else:
                    os.environ['SNOWPACK_IMAGE_ID'] = old_image_id
                if old_image_archive_sha256 is None:
                    os.environ.pop('SNOWPACK_IMAGE_ARCHIVE_SHA256', None)
                else:
                    os.environ['SNOWPACK_IMAGE_ARCHIVE_SHA256'] = old_image_archive_sha256

            self.assertIsNotNone(result)
            self.assertTrue(result.success)
            self.assertEqual(result.binary_version, 'stderr-version stdout-version')
            self.assertTrue(result.toolchain_manifest_verified)

    def test_path_resolved_binary_is_used_for_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            fake_binary = bin_dir / 'snowpack'
            fake_binary.write_text(
                '#!/bin/sh\n'
                'if [ "$1" = "--version" ]; then printf "SNOWPACK 3.7.0\\n"; exit 0; fi\n'
                'config=""\n'
                'previous=""\n'
                'for arg in "$@"; do\n'
                '  if [ "$previous" = "-c" ]; then config="$arg"; fi\n'
                '  previous="$arg"\n'
                'done\n'
                'printf "native profile\\n" > "$(dirname "$config")/input.pro"\n',
                encoding='utf-8',
            )
            fake_binary.chmod(fake_binary.stat().st_mode | stat.S_IXUSR)
            toolchain_manifest = {
                'schema_version': 'snowpack_toolchain_manifest_v1',
                'toolchain_id': 'test-toolchain',
                'meteoio_commit': 'a' * 40,
                'snowpack_commit': 'b' * 40,
                'binary_path': str(fake_binary),
                'binary_sha256': hashlib.sha256(fake_binary.read_bytes()).hexdigest(),
                'binary_version': 'SNOWPACK 3.7.0',
                'image_id': 'sha256:' + 'c' * 64,
                'image_archive_sha256': 'd' * 64,
                'image_repository_digest': '',
                'image_identity_source': 'local_id_and_archive',
            }
            (root / 'toolchain-manifest.json').write_text(
                json.dumps(toolchain_manifest), encoding='utf-8'
            )
            smet = root / 'input.smet'
            smet.write_text(_MINIMAL_SMET_WITH_COORDINATES, encoding='utf-8')
            output_dir = root / 'output'
            old_path = os.environ.get('PATH', '')
            old_image_id = os.environ.get('SNOWPACK_IMAGE_ID')
            old_image_archive_sha256 = os.environ.get('SNOWPACK_IMAGE_ARCHIVE_SHA256')
            os.environ['SNOWPACK_IMAGE_ID'] = 'sha256:' + 'c' * 64
            os.environ['SNOWPACK_IMAGE_ARCHIVE_SHA256'] = 'd' * 64
            os.environ['PATH'] = f'{bin_dir}{os.pathsep}{old_path}'
            try:
                self.assertTrue(snowpack_binary_available())
                result = run_snowpack_native(
                    smet_path=smet,
                    output_dir=output_dir,
                )
            finally:
                os.environ['PATH'] = old_path
                if old_image_id is None:
                    os.environ.pop('SNOWPACK_IMAGE_ID', None)
                else:
                    os.environ['SNOWPACK_IMAGE_ID'] = old_image_id
                if old_image_archive_sha256 is None:
                    os.environ.pop('SNOWPACK_IMAGE_ARCHIVE_SHA256', None)
                else:
                    os.environ['SNOWPACK_IMAGE_ARCHIVE_SHA256'] = old_image_archive_sha256

            self.assertIsNotNone(result)
            # C0-S5: run_snowpack_native now returns NativeExecutionEvidence
            self.assertTrue(result.success)
            self.assertEqual(result.exit_code, 0)
            pro_path = Path(result.pro_path)
            self.assertEqual(pro_path.name, 'input.pro')
            self.assertGreater(pro_path.stat().st_size, 0)
            self.assertTrue((output_dir / 'input.log').is_file())

    def test_failed_version_is_not_execution_success(self) -> None:
        """C0.14: A normal run cannot be successful if --version fails."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_binary = root / 'snowpack'
            fake_binary.write_text(
                '#!/bin/sh\n'
                'if [ "$1" = "--version" ]; then exit 7; fi\n'
                'config=""\n'
                'prev=""\n'
                'for arg in "$@"; do\n'
                '  if [ "$prev" = "-c" ]; then config="$arg"; fi\n'
                '  prev="$arg"\n'
                'done\n'
                'printf "native profile\\n" > "$(dirname "$config")/input.pro"\n'
                'exit 0\n',
                encoding='utf-8',
            )
            fake_binary.chmod(fake_binary.stat().st_mode | stat.S_IXUSR)
            toolchain_manifest = {
                'schema_version': 'snowpack_toolchain_manifest_v1',
                'toolchain_id': 'test-toolchain',
                'meteoio_commit': 'a' * 40,
                'snowpack_commit': 'b' * 40,
                'binary_path': str(fake_binary),
                'binary_sha256': hashlib.sha256(fake_binary.read_bytes()).hexdigest(),
                'binary_version': 'SNOWPACK 3.7.0',
                'image_id': 'sha256:' + 'c' * 64,
                'image_archive_sha256': 'd' * 64,
                'image_repository_digest': '',
                'image_identity_source': 'local_id_and_archive',
            }
            (root / 'toolchain-manifest.json').write_text(
                json.dumps(toolchain_manifest), encoding='utf-8'
            )
            smet = root / 'input.smet'
            smet.write_text(_MINIMAL_SMET_WITH_COORDINATES, encoding='utf-8')
            old_path = os.environ.get('PATH', '')
            old_image_id = os.environ.get('SNOWPACK_IMAGE_ID')
            old_image_archive_sha256 = os.environ.get('SNOWPACK_IMAGE_ARCHIVE_SHA256')
            os.environ['SNOWPACK_IMAGE_ID'] = 'sha256:' + 'c' * 64
            os.environ['SNOWPACK_IMAGE_ARCHIVE_SHA256'] = 'd' * 64
            os.environ['PATH'] = f'{root}{os.pathsep}{old_path}'
            try:
                result = run_snowpack_native(
                    smet_path=smet,
                    output_dir=root / 'output',
                )
            finally:
                os.environ['PATH'] = old_path
                if old_image_id is None:
                    os.environ.pop('SNOWPACK_IMAGE_ID', None)
                else:
                    os.environ['SNOWPACK_IMAGE_ID'] = old_image_id
                if old_image_archive_sha256 is None:
                    os.environ.pop('SNOWPACK_IMAGE_ARCHIVE_SHA256', None)
                else:
                    os.environ['SNOWPACK_IMAGE_ARCHIVE_SHA256'] = old_image_archive_sha256

            self.assertIsNotNone(result)
            self.assertFalse(result.success)

    def test_native_execution_evidence_writes_subprocess_log(self) -> None:
        """The captured native stdout/stderr must become a hashable log artifact."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_binary = root / 'snowpack'
            fake_binary.write_text(
                '#!/bin/sh\n'
                'if [ "$1" = "--version" ]; then printf "SNOWPACK 3.7.0\\n"; exit 0; fi\n'
                'config=""\n'
                'prev=""\n'
                'for arg in "$@"; do\n'
                '  if [ "$prev" = "-c" ]; then config="$arg"; fi\n'
                '  prev="$arg"\n'
                'done\n'
                'printf "native stdout\\n"\n'
                'printf "native profile\\n" > "$(dirname "$config")/input.pro"\n',
                encoding='utf-8',
            )
            fake_binary.chmod(fake_binary.stat().st_mode | stat.S_IXUSR)
            toolchain_manifest = {
                'schema_version': 'snowpack_toolchain_manifest_v1',
                'toolchain_id': 'test-toolchain',
                'meteoio_commit': 'a' * 40,
                'snowpack_commit': 'b' * 40,
                'binary_path': str(fake_binary),
                'binary_sha256': hashlib.sha256(fake_binary.read_bytes()).hexdigest(),
                'binary_version': 'SNOWPACK 3.7.0',
                'image_id': 'sha256:' + 'c' * 64,
                'image_archive_sha256': 'd' * 64,
                'image_repository_digest': '',
                'image_identity_source': 'local_id_and_archive',
            }
            (root / 'toolchain-manifest.json').write_text(
                json.dumps(toolchain_manifest), encoding='utf-8'
            )
            smet = root / 'input.smet'
            smet.write_text(_MINIMAL_SMET_WITH_COORDINATES, encoding='utf-8')
            output_dir = root / 'output'
            old_path = os.environ.get('PATH', '')
            old_image_id = os.environ.get('SNOWPACK_IMAGE_ID')
            old_image_archive_sha256 = os.environ.get('SNOWPACK_IMAGE_ARCHIVE_SHA256')
            os.environ['SNOWPACK_IMAGE_ID'] = 'sha256:' + 'c' * 64
            os.environ['SNOWPACK_IMAGE_ARCHIVE_SHA256'] = 'd' * 64
            os.environ['PATH'] = f'{root}{os.pathsep}{old_path}'
            try:
                result = run_snowpack_native(smet_path=smet, output_dir=output_dir)
            finally:
                os.environ['PATH'] = old_path
                if old_image_id is None:
                    os.environ.pop('SNOWPACK_IMAGE_ID', None)
                else:
                    os.environ['SNOWPACK_IMAGE_ID'] = old_image_id
                if old_image_archive_sha256 is None:
                    os.environ.pop('SNOWPACK_IMAGE_ARCHIVE_SHA256', None)
                else:
                    os.environ['SNOWPACK_IMAGE_ARCHIVE_SHA256'] = old_image_archive_sha256

            self.assertIsNotNone(result)
            log_path = output_dir / 'input.log'
            self.assertEqual(result.success, True)
            self.assertIn('native stdout', log_path.read_text(encoding='utf-8'))
            self.assertTrue(result.version_verified)
            self.assertEqual(result.version_exit_code, 0)

    def test_execution_evidence_preserves_legacy_profile_parser_compatibility(self) -> None:
        """The old physics caller can consume successful evidence without false green."""
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / 'input.pro'
            profile.write_text(
                '#Date HS rho T grain_type\n'
                '2026-01-15T00:00:00 0.5 300 263.15 8\n',
                encoding='utf-8',
            )
            evidence = NativeExecutionEvidence(pro_path=str(profile), success=True)
            parsed = parse_snowpack_pro(evidence)
            self.assertEqual(parsed['layer_count'], 1)
            failed = NativeExecutionEvidence(pro_path=str(profile), success=False)
            with self.assertRaises(FileNotFoundError):
                parse_snowpack_pro(failed)

    def test_real_snowpack_37_pro_record_format_is_parsed(self) -> None:
        """SNOWPACK 3.7 emits coded 0500/0501 records, not a tabular Date header."""
        real_pro = (
            '[HEADER]\n'
            '0500,Date\n'
            '0501,nElems,height [> 0: top, < 0: bottom of elem.] (cm)\n'
            '0502,nElems,element density (kg m-3)\n'
            '0503,nElems,element temperature (degC)\n'
            '0506,nElems,liquid water content by volume (%)\n'
            '0513,nElems+1,grain type (Swiss Code F1F2F3)\n'
            '0520,nElems,temperature gradient (K m-1)\n'
            '0530,8,position (cm) and minimum stability indices\n'
            '0601,nElems,snow shear strength (kPa)\n'
            '[DATA]\n'
            '0500,01.10.2023 00:00:00\n'
            '0501,2,1.0,10.0\n'
            '0502,2,300.0,250.0\n'
            '0503,2,-2.0,-3.0\n'
            '0506,2,0.0,2.0\n'
            '0513,3,441,772,0\n'
            '0520,2,5.0,7.0\n'
            '0530,8,-1,3,2.0,0.30,4.0,0.80,5.0,0.60\n'
            '0601,2,2.0,1.5\n'
            '0500,02.10.2023 00:00:00\n'
            '0501,2,2.0,20.0\n'
            '0502,2,400.0,200.0\n'
            '0503,2,-1.0,-4.0\n'
            '0506,2,1.0,3.0\n'
            '0513,3,441,772,0\n'
            '0520,2,6.0,8.0\n'
            '0530,8,-1,3,2.0,0.25,4.0,0.70,5.0,0.50\n'
            '0601,2,2.5,1.0\n'
        )
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / 'native.pro'
            profile.write_text(real_pro, encoding='utf-8')
            parsed = parse_snowpack_pro(profile)

        self.assertEqual(parsed['native_format'], 'pro_0500_records')
        self.assertEqual(parsed['profile_date'], '02.10.2023 00:00:00')
        self.assertEqual(parsed['layer_count'], 2)
        self.assertAlmostEqual(parsed['snow_height_m'], 0.2, places=3)
        self.assertAlmostEqual(parsed['layers'][0]['temperature_c'], -1.0, places=3)
        self.assertAlmostEqual(parsed['layers'][1]['temperature_c'], -4.0, places=3)
        self.assertEqual(parsed['layers'][1]['grain_type_code'], 772)
        self.assertEqual(parsed['weak_layer_grain_type'], 'melt_freeze_crust')
        self.assertAlmostEqual(parsed['liquid_water_content_pct'], 2.0, places=3)
        self.assertAlmostEqual(parsed['snowpack_stability_index'], 0.25, places=3)

    def test_missing_output_is_not_execution_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_binary = root / 'snowpack'
            fake_binary.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
            fake_binary.chmod(fake_binary.stat().st_mode | stat.S_IXUSR)
            toolchain_manifest = {
                'schema_version': 'snowpack_toolchain_manifest_v1',
                'toolchain_id': 'test-toolchain',
                'meteoio_commit': 'a' * 40,
                'snowpack_commit': 'b' * 40,
                'binary_path': str(fake_binary),
                'binary_sha256': hashlib.sha256(fake_binary.read_bytes()).hexdigest(),
                'binary_version': 'SNOWPACK 3.7.0',
                'image_id': 'sha256:' + 'c' * 64,
                'image_archive_sha256': 'd' * 64,
                'image_repository_digest': '',
                'image_identity_source': 'local_id_and_archive',
            }
            (root / 'toolchain-manifest.json').write_text(
                json.dumps(toolchain_manifest), encoding='utf-8'
            )
            smet = root / 'input.smet'
            smet.write_text(_MINIMAL_SMET_WITH_COORDINATES, encoding='utf-8')
            old_path = os.environ.get('PATH', '')
            old_image_id = os.environ.get('SNOWPACK_IMAGE_ID')
            old_image_archive_sha256 = os.environ.get('SNOWPACK_IMAGE_ARCHIVE_SHA256')
            os.environ['SNOWPACK_IMAGE_ID'] = 'sha256:' + 'c' * 64
            os.environ['SNOWPACK_IMAGE_ARCHIVE_SHA256'] = 'd' * 64
            os.environ['PATH'] = f'{root}{os.pathsep}{old_path}'
            try:
                result = run_snowpack_native(
                    smet_path=smet,
                    output_dir=root / 'output',
                )
            finally:
                os.environ['PATH'] = old_path
                if old_image_id is None:
                    os.environ.pop('SNOWPACK_IMAGE_ID', None)
                else:
                    os.environ['SNOWPACK_IMAGE_ID'] = old_image_id
                if old_image_archive_sha256 is None:
                    os.environ.pop('SNOWPACK_IMAGE_ARCHIVE_SHA256', None)
                else:
                    os.environ['SNOWPACK_IMAGE_ARCHIVE_SHA256'] = old_image_archive_sha256

            # C0-S5: evidence is returned but success=False (no .pro output)
            self.assertIsNotNone(result)
            self.assertFalse(result.success)


if __name__ == '__main__':
    unittest.main()
