from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.common.label_time_contract import (
    LABEL_TIME_CONTRACT_EXACT_V1,
    LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1,
)
from backend.common.station_free_feature_snapshot import (
    build_station_free_feature_snapshot,
    write_station_free_feature_snapshot,
)
from backend.scripts.audit_training_dataset import build_dataset_audit, build_training_preflight


class TrainingDatasetAuditTests(unittest.TestCase):
    def _write_reviewed_snapshot(
        self,
        root: Path,
        *,
        overlap_status: str = 'reviewed',
        gee_time_reviewed: bool = True,
    ) -> Path:
        rows = []
        for index in range(30):
            source = 'hiaval_hma' if index % 2 == 0 else 'gee_sar'
            origin_family = 'hiaval_literature' if source == 'hiaval_hma' else 'gee_sar_scene'
            year = 2023 + (index // 10)
            row = {
                'source_event_id': f'{source}:{index}',
                'event_group_id': f'group:{index}',
                'origin_source_family': origin_family,
                'source_key': source,
                'region_key': 'himalayas_nepal',
                'timestamp': f'{year}-12-{(index % 10) + 1:02d}T00:00:00Z',
                'timestamp_precision': 'timestamp',
                'label': 1,
            }
            if source != 'gee_sar' or gee_time_reviewed:
                row.update({
                    'event_time_semantics': 'independent_observed_occurrence_time',
                    'source_time_review_status': 'approved_occurrence_time',
                    'source_time_review_id': 'fixture-time-review-1',
                })
            rows.append(row)
        events = ''.join(json.dumps(row, sort_keys=True) + '\n' for row in rows).encode('utf-8')
        events_path = root / 'events.jsonl'
        events_path.write_bytes(events)
        overlap_path = root / 'source_overlap_report.json'
        overlap_path.write_text(json.dumps({
            'status': overlap_status,
            'source_a': 'gee_sar',
            'source_b': 'hiaval_hma',
            'source_a_sha256': 'a' * 64,
            'source_b_sha256': 'b' * 64,
            'source_a_record_count': 15,
            'source_b_record_count': 15,
            'source_a_non_overlap_count': 15,
            'source_b_non_overlap_count': 15,
            'independent_positive_source_count': 2,
            'same_event_must_not_count_as_independent': True,
        }), encoding='utf-8')
        manifest = {
            'snapshot_schema_version': 'mvp4_hiaval_snapshot_v1',
            'source_key': 'mvp4-reviewed-fixture',
            'license_status': 'permissive_core_reviewed',
            'license_review_id': 'fixture-license-review-1',
            'training_eligible': True,
            'production_scoring_eligible': False,
            'events_path': events_path.name,
            'event_rows_sha256': hashlib.sha256(events).hexdigest(),
            'positive_season_ids': ['2023-2024', '2024-2025', '2025-2026'],
            'required_independent_positive_sources': ['gee_sar', 'hiaval_hma'],
            'target_regions': {'himalayas_nepal': {'season_start_month': 11}},
            'source_overlap_report': overlap_path.name,
        }
        manifest_path = root / 'snapshot_manifest.json'
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        return manifest_path

    def _write_artifact_bundle(self, root: Path) -> None:
        manifest = {
            'training_dataset_version': 'real_event_join_v1',
            'positive_count': 8,
            'negative_count': 24,
            'training_row_count': 32,
            'oldest_timestamp': '2026-06-24T00:00:00+00:00',
            'newest_timestamp': '2026-06-26T00:00:00+00:00',
            'event_source_counts': {'gee_sar': 8},
            'source_region_counts': {'gee_sar': 2},
            'region_keys': ['himalayas_nepal', 'pir_panjal_nw_himalaya'],
            'debug_stats': {
                'raw_rows': 10,
                'assembled_ok': 8,
                'terrain_failed': 2,
                'terrain_clamped': 1,
                'weather_failed': 0,
            },
        }
        (root / 'training_metrics.json').write_text(
            json.dumps({
                'dataset_snapshot_id': 'real_event_join_v1:2026-06-26T00:00:00+00:00',
                'dataset_manifest': manifest,
                'feature_columns_hash': 'feature-hash',
                'label_schema_hash': 'label-hash',
                'metrics': {
                    'pss_reported': 0.86,
                    'brier_score': 0.11,
                    'pss_timeseries_folds': [0.35, 0.75],
                    'pss_spatial_folds': [0.28, 0.70],
                },
            }),
            encoding='utf-8',
        )
        (root / 'training_stage_metrics.json').write_text(
            json.dumps({
                'dataset_snapshot_id': 'real_event_join_v1:2026-06-26T00:00:00+00:00',
                'phase_breakdown_seconds': {
                    'dataset_load_seconds': 120.0,
                    'fit_model_seconds': 10.0,
                },
            }),
            encoding='utf-8',
        )
        (root / 'autonomous_evidence_summary.json').write_text(
            json.dumps({
                'manual_positive_count': 0,
                'autonomous_positive_count': 8,
                'positive_source_counts': {'gee_sar': 8},
            }),
            encoding='utf-8',
        )
        (root / 'hindcast_run.json').write_text(
            json.dumps({'summary_metrics': {'shadow_quality_gate_passed': False}}),
            encoding='utf-8',
        )

    def _write_interval_snapshot(self, root: Path, *, training_eligible: bool = True) -> Path:
        rows = []
        for index in range(30):
            source = 'hiaval_hma' if index % 2 == 0 else 'bipad_nepal_avalanche_candidate'
            origin_family = 'hiaval_literature' if source == 'hiaval_hma' else 'bipad_drr_api'
            year = 2023 + (index // 10)
            start = f'{year}-12-{(index % 10) + 1:02d}T00:00:00Z'
            end = f'{year}-12-{(index % 10) + 2:02d}T00:00:00Z'
            rows.append({
                'source_event_id': f'{source}:{index}',
                'event_group_id': f'group:{index}',
                'origin_source_family': origin_family,
                'source_key': source,
                'region_key': 'himalayas_nepal',
                'event_time_start': start,
                'event_time_end': end,
                'timestamp_precision': 'day',
                'feature_cutoff_at': f'{year}-11-30T00:00:00Z',
                'label': 1,
            })
        events = ''.join(json.dumps(row, sort_keys=True) + '\n' for row in rows).encode('utf-8')
        events_path = root / 'interval-events.jsonl'
        events_path.write_bytes(events)
        overlap_path = root / 'interval-source-overlap.json'
        overlap_path.write_text(json.dumps({
            'status': 'reviewed',
            'source_a': 'bipad_nepal_avalanche_candidate',
            'source_b': 'hiaval_hma',
            'source_a_sha256': 'a' * 64,
            'source_b_sha256': 'b' * 64,
            'source_a_record_count': 15,
            'source_b_record_count': 15,
            'source_a_non_overlap_count': 15,
            'source_b_non_overlap_count': 15,
            'independent_positive_source_count': 2,
            'same_event_must_not_count_as_independent': True,
        }), encoding='utf-8')
        manifest = {
            'snapshot_schema_version': 'mvp4_hiaval_snapshot_v1',
            'source_key': 'mvp4-interval-fixture',
            'label_time_contract': LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1,
            'license_status': 'permissive_core_reviewed',
            'license_review_id': 'fixture-license-review-interval-1',
            'training_eligible': training_eligible,
            'production_scoring_eligible': False,
            'events_path': events_path.name,
            'event_rows_sha256': hashlib.sha256(events).hexdigest(),
            'positive_season_ids': ['2023-2024', '2024-2025', '2025-2026'],
            'required_independent_positive_sources': [
                'bipad_nepal_avalanche_candidate',
                'hiaval_hma',
            ],
            'target_regions': {'himalayas_nepal': {'season_start_month': 11}},
            'region_season_start_months': {'himalayas_nepal': 11},
            'source_overlap_report': overlap_path.name,
        }
        manifest_path = root / 'interval-snapshot-manifest.json'
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        return manifest_path

    def test_audit_surfaces_runtime_and_scientific_risks(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_artifact_bundle(root)

            audit = build_dataset_audit(root)

        self.assertEqual(audit['dataset']['training_row_count'], 32)
        self.assertAlmostEqual(audit['dataset']['positive_fraction'], 0.25)
        self.assertEqual(audit['coverage']['region_count'], 2)
        self.assertEqual(audit['coverage']['temporal_span_days'], 2.0)
        self.assertAlmostEqual(audit['runtime']['dataset_load_fraction'], 120 / 130, places=6)
        finding_ids = {finding['id'] for finding in audit['findings']}
        self.assertIn('temporal_coverage_concentrated', finding_ids)
        self.assertIn('label_source_concentrated', finding_ids)
        self.assertIn('dataset_load_bottleneck', finding_ids)
        self.assertIn('cv_fold_robustness_breach', finding_ids)
        self.assertIn('shadow_quality_gate_failed', finding_ids)
        self.assertEqual(audit['decision'], 'blocked_pending_snapshot_evidence')

    def test_audit_records_missing_artifact_evidence_without_crashing(self) -> None:
        with TemporaryDirectory() as tmpdir:
            audit = build_dataset_audit(Path(tmpdir))

        self.assertEqual(audit['decision'], 'blocked_missing_dataset_manifest')
        self.assertTrue(audit['integrity']['dataset_manifest_present'] is False)
        self.assertTrue(any(item['id'] == 'missing_dataset_manifest' for item in audit['findings']))

    def test_metadata_preflight_blocks_a_fresh_artifact_root_without_snapshot(self) -> None:
        with TemporaryDirectory() as tmpdir:
            report = build_training_preflight(Path(tmpdir))

        self.assertEqual(report['status'], 'no_prior_artifact')
        self.assertEqual(report['decision'], 'blocked_pending_snapshot_evidence')
        self.assertFalse(report['snapshot_gate']['passed'])

    def test_metadata_preflight_blocks_pending_source_overlap(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snapshot_manifest = self._write_reviewed_snapshot(root, overlap_status='pending_gee_sar_snapshot')

            report = build_training_preflight(root, snapshot_manifest=snapshot_manifest)

        self.assertEqual(report['status'], 'no_prior_artifact')
        self.assertEqual(report['decision'], 'blocked_pending_snapshot_evidence')
        self.assertFalse(report['snapshot_gate']['passed'])
        self.assertTrue(any('not reviewed' in error for error in report['snapshot_gate']['errors']))

    def test_metadata_preflight_allows_first_candidate_only_after_reviewed_snapshot(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snapshot_manifest = self._write_reviewed_snapshot(root)

            report = build_training_preflight(root, snapshot_manifest=snapshot_manifest)

        self.assertEqual(report['status'], 'no_prior_artifact')
        self.assertEqual(report['decision'], 'ready_for_first_training')
        self.assertTrue(report['snapshot_gate']['passed'])

    def test_metadata_preflight_blocks_pending_source_request_package(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snapshot_manifest = self._write_reviewed_snapshot(root)
            request_manifest = root / 'mvp4_source_request_manifest.json'
            template = Path(__file__).resolve().parents[2] / 'schemas/source_manifest_request.template.json'
            request_manifest.write_text(template.read_text(encoding='utf-8'), encoding='utf-8')
            payload = root / 'source-payload.bin'
            payload.write_bytes(b'pending source-owner payload')

            report = build_training_preflight(
                root,
                snapshot_manifest=snapshot_manifest,
                source_request_manifest=request_manifest,
                source_request_payload=payload,
            )

        self.assertEqual(report['status'], 'no_prior_artifact')
        self.assertEqual(report['decision'], 'blocked_pending_source_manifest_intake')
        self.assertTrue(report['snapshot_gate']['passed'])
        self.assertFalse(report['source_request_gate']['passed'])
        self.assertEqual(
            report['source_request_gate']['decision'],
            'blocked_source_request_pending',
        )

    def test_metadata_preflight_rejects_source_request_payload_without_manifest(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snapshot_manifest = self._write_reviewed_snapshot(root)
            payload = root / 'source-payload.bin'
            payload.write_bytes(b'orphaned source-owner payload')

            report = build_training_preflight(
                root,
                snapshot_manifest=snapshot_manifest,
                source_request_payload=payload,
            )

        self.assertEqual(report['decision'], 'blocked_pending_source_manifest_intake')
        self.assertFalse(report['source_request_gate']['passed'])
        self.assertTrue(any('manifest is required' in error for error in report['source_request_gate']['errors']))

    def test_metadata_preflight_accepts_a_valid_source_request_fixture(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snapshot_manifest = self._write_reviewed_snapshot(root)
            payload_bytes = b'event_id,release_time\nindependent-event-1,2023-12-04T05:30:00Z\n'
            payload = root / 'source-payload.csv'
            payload.write_bytes(payload_bytes)
            events = root / 'source-events.jsonl'
            events.write_text(json.dumps({
                'source_event_id': 'independent-event-1',
                'event_group_id': 'independent-event-1',
                'origin_source_family': 'independent_release_catalog',
                'source_key': 'independent_hma_source',
                'label_source': 'independent_hma_source',
                'region_key': 'himalayas_nepal',
                'event_time': '2023-12-04T05:30:00Z',
                'timestamp_precision': 'exact',
                'lat': 28.2,
                'lng': 86.8,
                'label': 1,
                'source_reference': 'source-row-1',
            }, sort_keys=True) + '\n', encoding='utf-8')
            source_manifest = root / 'mvp4_source_request_manifest.json'
            source_manifest.write_text(json.dumps({
                'schema_version': 'mvp4_source_request_manifest_v1',
                'source_id': 'independent_hma_source',
                'source_name': 'Independent HMA avalanche release catalog',
                'source_owner': 'Reviewed data owner',
                'source_url': 'https://example.invalid/source',
                'source_reference': 'release-2026-08',
                'source_role': 'core',
                'review_status': 'approved',
                'license_review_id': 'license-review-2026-08',
                'license': {
                    'status': 'permissive_core_reviewed',
                    'reuse_scope': 'model training and approved internal review',
                    'attribution_required': True,
                },
                'coverage': {
                    'regions': ['himalayas_nepal'],
                    'positive_seasons': ['2021-2022', '2022-2023', '2023-2024'],
                    'exact_time_positive_seasons': ['2021-2022', '2022-2023', '2023-2024'],
                    'coverage_note': 'Three reviewed Nepal snow seasons.',
                },
                'time_semantics': {
                    'event_time_field': 'release_time',
                    'event_time_kind': 'source_reported_avalanche_occurrence_time',
                    'timezone': 'UTC',
                    'precision': 'exact',
                    'release_time_proven': True,
                    'source_time_is_avalanche_occurrence_time': True,
                },
                'spatial_semantics': {
                    'geometry_type': 'point',
                    'coordinate_reference': 'EPSG:4326',
                    'coordinate_precision': 'exact_event_point',
                    'has_exact_coordinates': True,
                },
                'event_id_field': 'event_id',
                'event_rows_sha256': hashlib.sha256(events.read_bytes()).hexdigest(),
                'provenance': {
                    'source_hash': hashlib.sha256(payload_bytes).hexdigest(),
                    'source_hash_algorithm': 'sha256',
                    'retrieved_at': '2026-08-03T12:00:00+00:00',
                    'version_or_commit': 'release-2026-08',
                },
                'independence': {
                    'origin_source_family': 'independent_release_catalog',
                    'independent_of_source_ids': ['hiaval_hma', 'gee_sar_scene_aware'],
                    'independence_status': 'independent_after_overlap_review',
                    'overlap_review_status': 'clean',
                },
                'evidence_refs': ['evidence/source-review.json'],
                'training_eligible': True,
                'production_scoring_eligible': False,
                'required_next_action': 'Build the reviewed multi-source snapshot.',
            }, sort_keys=True), encoding='utf-8')

            report = build_training_preflight(
                root,
                snapshot_manifest=snapshot_manifest,
                source_request_manifest=source_manifest,
                source_request_payload=payload,
                source_request_events=events,
            )

        self.assertEqual(report['status'], 'no_prior_artifact')
        self.assertEqual(report['decision'], 'ready_for_first_training')
        self.assertTrue(report['source_request_gate']['passed'])
        self.assertEqual(
            report['source_request_gate']['decision'],
            'source_manifest_accepted_for_normalization',
        )
        self.assertTrue(report['source_request_gate']['checks']['event_rows']['passed'])

    def test_metadata_preflight_checks_selected_region_seasons_and_sources(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snapshot_manifest = self._write_reviewed_snapshot(root)

            report = build_training_preflight(
                root,
                snapshot_manifest=snapshot_manifest,
                selected_region_keys=['pir_panjal_nw_himalaya'],
            )

        self.assertFalse(report['snapshot_gate']['passed'])
        self.assertTrue(any('does not cover selected training region' in error for error in report['snapshot_gate']['errors']))

    def test_metadata_preflight_explains_bounded_source_exclusion(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            events = (
                b'{"source_key":"hiaval_hma","event_time":"2023-12-01T00:00:00Z","region_key":"himalayas_nepal","label":1}\n'
                b'{"source_key":"everest_sentinel1","event_time_start":"2024-12-01T00:00:00Z","event_time_end":"2024-12-12T00:00:00Z","timestamp_precision":"bounded_12_day_detection_interval","region_key":"himalayas_nepal","label":1}\n'
                b'{"source_key":"hiaval_hma","event_time":"2025-12-01T00:00:00Z","region_key":"himalayas_nepal","label":1}\n'
            )
            events_path = root / 'events.jsonl'
            events_path.write_bytes(events)
            overlap_path = root / 'source_overlap_report.json'
            overlap_path.write_text(json.dumps({
                'status': 'reviewed',
                'source_a': 'everest_sentinel1',
                'source_b': 'hiaval_hma',
                'source_a_sha256': 'a' * 64,
                'source_b_sha256': 'b' * 64,
                'source_a_record_count': 1,
                'source_b_record_count': 2,
                'source_a_non_overlap_count': 1,
                'source_b_non_overlap_count': 2,
                'independent_positive_source_count': 2,
                'same_event_must_not_count_as_independent': True,
            }), encoding='utf-8')
            manifest = {
                'snapshot_schema_version': 'mvp4_hiaval_snapshot_v1',
                'source_key': 'mvp4-bounded-fixture',
                'license_status': 'permissive_core_reviewed',
                'license_review_id': 'fixture-license-review-interval-1',
                'training_eligible': True,
                'production_scoring_eligible': False,
                'events_path': events_path.name,
                'event_rows_sha256': hashlib.sha256(events).hexdigest(),
                'positive_season_ids': ['2023-2024', '2024-2025', '2025-2026'],
                'required_independent_positive_sources': ['everest_sentinel1', 'hiaval_hma'],
                'target_regions': {'himalayas_nepal': {'season_start_month': 11}},
                'region_season_start_months': {'himalayas_nepal': 11},
                'source_overlap_report': overlap_path.name,
            }
            manifest_path = root / 'snapshot_manifest.json'
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

            report = build_training_preflight(
                root,
                snapshot_manifest=manifest_path,
                selected_region_keys=['himalayas_nepal'],
            )

        self.assertFalse(report['snapshot_gate']['passed'])
        self.assertTrue(any('bounded interval sources are not eligible' in error for error in report['snapshot_gate']['errors']))
        region = report['snapshot_gate']['region_checks']['himalayas_nepal']
        self.assertEqual(region['exact_positive_source_ids'], [])
        self.assertEqual(region['bounded_positive_source_ids'], ['everest_sentinel1'])
        self.assertEqual(region['bounded_positive_row_count'], 1)

    def test_metadata_preflight_blocks_unreviewed_gee_exact_timestamp(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snapshot_manifest = self._write_reviewed_snapshot(root, gee_time_reviewed=False)

            report = build_training_preflight(
                root,
                snapshot_manifest=snapshot_manifest,
                selected_region_keys=['himalayas_nepal'],
            )

        self.assertFalse(report['snapshot_gate']['passed'])
        self.assertTrue(
            any(
                'gee_sar exact timestamp' in error
                and 'occurrence-time review' in error
                for error in report['snapshot_gate']['errors']
            )
        )

    def test_metadata_preflight_blocks_unreviewed_non_gee_exact_timestamp(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snapshot_manifest = self._write_reviewed_snapshot(root)
            manifest = json.loads(snapshot_manifest.read_text(encoding='utf-8'))
            events_path = snapshot_manifest.parent / manifest['events_path']
            rows = [json.loads(line) for line in events_path.read_text(encoding='utf-8').splitlines() if line.strip()]
            for row in rows:
                if row['source_key'] == 'hiaval_hma':
                    row.pop('event_time_semantics', None)
                    row.pop('source_time_review_status', None)
                    row.pop('source_time_review_id', None)
            payload = ''.join(json.dumps(row, sort_keys=True) + '\n' for row in rows).encode('utf-8')
            events_path.write_bytes(payload)
            manifest['event_rows_sha256'] = hashlib.sha256(payload).hexdigest()
            snapshot_manifest.write_text(json.dumps(manifest), encoding='utf-8')

            report = build_training_preflight(
                root,
                snapshot_manifest=snapshot_manifest,
            )

        self.assertFalse(report['snapshot_gate']['passed'])
        self.assertTrue(any(
            'exact timestamp rows lack explicit occurrence-time review' in error
            for error in report['snapshot_gate']['errors']
        ))
        self.assertEqual(
            report['snapshot_gate']['exact_time_review']['unreviewed_exact_row_count'],
            15,
        )

    def test_interval_preflight_accepts_day_rows_only_with_explicit_contract(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snapshot_manifest = self._write_interval_snapshot(root)

            report = build_training_preflight(
                root,
                snapshot_manifest=snapshot_manifest,
                selected_region_keys=['himalayas_nepal'],
                label_time_contract=LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1,
            )

        self.assertEqual(report['decision'], 'blocked_pending_interval_training_support')
        self.assertTrue(report['snapshot_gate']['passed'])
        self.assertTrue(report['structural_contract_passed'])
        self.assertEqual(report['interval_training_path_status'], 'implemented_shadow_only')
        self.assertEqual(
            report['snapshot_gate']['label_time_validation']['precision_counts'],
            {'day': 30},
        )
        self.assertEqual(
            report['snapshot_gate']['region_checks']['himalayas_nepal']['positive_source_ids'],
            ['bipad_nepal_avalanche_candidate', 'hiaval_hma'],
        )

    def test_interval_preflight_consumes_shadow_evidence_but_blocks_pending_approval(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            label_manifest_path = self._write_interval_snapshot(root)
            label_manifest = json.loads(label_manifest_path.read_text(encoding='utf-8'))
            feature_rows, feature_manifest = build_station_free_feature_snapshot(
                [{
                    'feature_id': 'era5:nepal:1995-11-12',
                    'region_key': 'himalayas_nepal',
                    'feature_join_key': 'himalayas_nepal:0:0',
                    'feature_valid_from': '1995-11-12T00:00:00Z',
                    'feature_valid_until': '1995-11-13T00:00:00Z',
                    'feature_cutoff_at': '1995-11-11T00:00:00Z',
                    'features': {
                        'temperature_2m': -10.0,
                        'snowfall': 1.0,
                        'precipitation': 2.0,
                        'relative_humidity_2m': 55.0,
                        'windspeed_10m': 4.0,
                    },
                }],
                region_keys=['himalayas_nepal'],
                source_manifest={
                    'source_key': 'era5',
                    'source_family': 'open_weather_reanalysis',
                    'source_snapshot_id': 'fixture-era5-1995',
                    'source_manifest_sha256': 'a' * 64,
                    'source_content_sha256': 'b' * 64,
                    'license': 'Open-Meteo/ERA5 fixture',
                    'license_status': 'pending',
                    'license_review_id': 'fixture-era5-license-pending',
                    'station_data_used': False,
                    'cutoff_policy': 'valid_time_shadow',
                    'cutoff_policy_review_status': 'pending_scientist_approval',
                },
            )
            feature_dir = root / 'feature-snapshot'
            write_station_free_feature_snapshot(feature_dir, feature_rows, feature_manifest)
            feature_manifest_path = feature_dir / 'snapshot_manifest.json'
            join_report_path = root / 'join_report.json'
            join_report_path.write_text(json.dumps({
                'status': 'shadow_frame_written',
                'label_manifest': str(label_manifest_path),
                'label_event_rows_sha256': label_manifest['event_rows_sha256'],
                'feature_manifest': str(feature_manifest_path),
                'feature_manifest_hash': feature_manifest['manifest_hash'],
                'training_eligible': False,
                'production_scoring_eligible': False,
                'shadow_only': True,
                'join': {'summary': {'joined_count': 30}},
                'evidence': {
                    'validation': {'passed': True},
                    'shadow_only': True,
                    'core_training_eligible': False,
                    'production_scoring_eligible': False,
                    'snapshot_provenance': {
                        'feature_manifest_hash': feature_manifest['manifest_hash'],
                    },
                },
            }), encoding='utf-8')

            report = build_training_preflight(
                root,
                snapshot_manifest=label_manifest_path,
                feature_snapshot_manifest=feature_manifest_path,
                interval_evidence_manifest=join_report_path,
                selected_region_keys=['himalayas_nepal'],
                label_time_contract=LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1,
            )

        self.assertEqual(report['decision'], 'blocked_pending_interval_feature_approval')
        self.assertTrue(report['interval_feature_gate']['structural_passed'])
        self.assertFalse(report['interval_feature_gate']['training_ready'])
        self.assertTrue(any('license' in error for error in report['interval_feature_gate']['training_errors']))
        self.assertTrue(any('cutoff' in error for error in report['interval_feature_gate']['training_errors']))

    def test_interval_preflight_blocks_unapproved_source_even_when_time_shape_is_valid(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snapshot_manifest = self._write_interval_snapshot(root, training_eligible=False)

            report = build_training_preflight(
                root,
                snapshot_manifest=snapshot_manifest,
                selected_region_keys=['himalayas_nepal'],
                label_time_contract=LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1,
            )

        self.assertFalse(report['snapshot_gate']['passed'])
        self.assertTrue(any('training_eligible' in error for error in report['snapshot_gate']['errors']))

    def test_interval_preflight_requires_snapshot_contract_declaration(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snapshot_manifest = self._write_interval_snapshot(root)
            payload = json.loads(snapshot_manifest.read_text(encoding='utf-8'))
            payload.pop('label_time_contract')
            snapshot_manifest.write_text(json.dumps(payload), encoding='utf-8')

            report = build_training_preflight(
                root,
                snapshot_manifest=snapshot_manifest,
                selected_region_keys=['himalayas_nepal'],
                label_time_contract=LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1,
            )

        self.assertFalse(report['snapshot_gate']['passed'])
        self.assertTrue(any('label_time_contract' in error for error in report['snapshot_gate']['errors']))

    def test_interval_staging_schema_is_recognised_but_blocks_before_feature_join(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            events = b''.join(
                (
                    json.dumps({
                        'source_event_id': f'source-{index}',
                        'event_group_id': f'group-{index}',
                        'origin_source_family': 'family-a' if index % 2 == 0 else 'family-b',
                        'source_key': 'hiaval_hma' if index % 2 == 0 else 'everest_sentinel1',
                        'region_key': 'himalayas_nepal',
                        'interval_start': f'{2023 + index}-12-01T00:00:00Z',
                        'interval_end': f'{2023 + index}-12-02T00:00:00Z',
                        'timestamp_precision': 'day',
                        'feature_cutoff_at': None,
                        'label': 1,
                    }, sort_keys=True) + '\n'
                ).encode()
                for index in range(3)
            )
            events_path = root / 'events.jsonl'
            events_path.write_bytes(events)
            overlap_path = root / 'source_overlap_report.json'
            overlap_path.write_text(json.dumps({
                'status': 'reviewed',
                'source_a': 'hiaval_hma',
                'source_b': 'everest_sentinel1',
                'source_a_sha256': 'a' * 64,
                'source_b_sha256': 'b' * 64,
                'source_a_record_count': 2,
                'source_b_record_count': 1,
                'source_a_non_overlap_count': 2,
                'source_b_non_overlap_count': 1,
                'independent_positive_source_count': 2,
                'same_event_must_not_count_as_independent': True,
            }), encoding='utf-8')
            source_manifests = {
                key: {
                    'event_rows_sha256': 'a' * 64 if key == 'hiaval_hma' else 'b' * 64,
                    'license_status': 'permissive_core_reviewed' if key == 'hiaval_hma' else 'permissive_shadow_reviewed',
                    'license_review_id': f'review-{key}',
                }
                for key in ('hiaval_hma', 'everest_sentinel1')
            }
            manifest = {
                'snapshot_schema_version': 'mvp4_interval_label_staging_v1',
                'source_key': 'mvp4_interval_label_staging',
                'label_time_contract': LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1,
                'source_manifests': source_manifests,
                'source_overlap_report': overlap_path.name,
                'source_overlap_report_sha256': hashlib.sha256(overlap_path.read_bytes()).hexdigest(),
                'required_independent_positive_sources': ['everest_sentinel1', 'hiaval_hma'],
                'positive_season_ids': ['2023-2024', '2024-2025', '2025-2026'],
                'positive_seasons_by_region': {'himalayas_nepal': ['2023-2024', '2024-2025', '2025-2026']},
                'target_regions': {'himalayas_nepal': {'season_start_month': 11}},
                'region_season_start_months': {'himalayas_nepal': 11},
                'training_eligible': False,
                'interval_training_ready': False,
                'staging_only': True,
                'production_scoring_eligible': False,
                'review_status': 'reviewed_interval_staging',
                'events_path': events_path.name,
                'event_rows_sha256': hashlib.sha256(events).hexdigest(),
            }
            manifest_path = root / 'snapshot_manifest.json'
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

            report = build_training_preflight(
                root,
                snapshot_manifest=manifest_path,
                selected_region_keys=['himalayas_nepal'],
                label_time_contract=LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1,
            )

        self.assertFalse(report['snapshot_gate']['passed'])
        self.assertFalse(any('unsupported reviewed snapshot schema' in error for error in report['snapshot_gate']['errors']))
        self.assertTrue(any('feature snapshot is not ready' in error for error in report['snapshot_gate']['errors']))

    def test_gee_scene_aware_shadow_schema_is_recognised_without_core_promotion(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rows = [
                {
                    'source_key': 'gee_sar_scene_aware',
                    'origin_source_family': 'gee_sar_sentinel1_scene_detection',
                    'source_event_id': f'gee:{index}',
                    'event_group_id': f'gee-group:{index}',
                    'region_key': 'himalayas_nepal',
                    'event_time_start': f'{2021 + index}-12-01T00:00:00Z',
                    'event_time_end': f'{2021 + index}-12-12T00:00:00Z',
                    'timestamp_precision': 'interval',
                    'label_time_contract': LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1,
                    'label': 1,
                }
                for index in range(3)
            ]
            events = ''.join(json.dumps(row, sort_keys=True) + '\n' for row in rows).encode('utf-8')
            events_path = root / 'events.jsonl'
            events_path.write_bytes(events)
            scenes_path = root / 'source_scenes.jsonl'
            scenes_path.write_text('{"scene_id":"S1"}\n', encoding='utf-8')
            manifest_path = root / 'snapshot_manifest.json'
            manifest_path.write_text(json.dumps({
                'snapshot_schema_version': 'mvp4_gee_scene_aware_interval_snapshot_v1',
                'source_key': 'gee_sar_scene_aware',
                'origin_source_family': 'gee_sar_sentinel1_scene_detection',
                'source_role': 'independent_sar_derived_interval_shadow',
                'label_time_contract': LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1,
                'license_status': 'pending_review',
                'license_review_id': 'fixture-gee-license-pending',
                'review_status': 'scene_provenance_captured_pending_time_rights_overlap_review',
                'shadow_only': True,
                'core_training_eligible': False,
                'training_eligible': False,
                'production_scoring_eligible': False,
                'events_path': events_path.name,
                'event_rows_sha256': hashlib.sha256(events).hexdigest(),
                'source_scenes_path': scenes_path.name,
                'scene_manifest_sha256': hashlib.sha256(scenes_path.read_bytes()).hexdigest(),
                'positive_season_ids': ['2021-2022', '2022-2023', '2023-2024'],
                'positive_seasons_by_region': {
                    'himalayas_nepal': ['2021-2022', '2022-2023', '2023-2024'],
                },
                'bounded_interval_record_count': 3,
                'exact_timestamp_record_count': 0,
                'required_independent_positive_sources': ['gee_sar_scene_aware'],
            }), encoding='utf-8')

            report = build_training_preflight(
                root,
                snapshot_manifest=manifest_path,
                selected_region_keys=['himalayas_nepal'],
            )

        errors = report['snapshot_gate']['errors']
        self.assertFalse(report['snapshot_gate']['passed'])
        self.assertFalse(any('unsupported reviewed snapshot schema' in error for error in errors))
        self.assertTrue(any('interval-only' in error for error in errors))
        self.assertTrue(any('license is not reviewed' in error for error in errors))
        self.assertTrue(any('training_eligible' in error for error in errors))

    def test_interval_rows_hard_block_when_exact_contract_is_requested(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snapshot_manifest = self._write_interval_snapshot(root)

            report = build_training_preflight(
                root,
                snapshot_manifest=snapshot_manifest,
                selected_region_keys=['himalayas_nepal'],
                label_time_contract=LABEL_TIME_CONTRACT_EXACT_V1,
            )

        self.assertEqual(report['decision'], 'blocked_pending_snapshot_evidence')
        self.assertFalse(report['snapshot_gate']['passed'])
        self.assertTrue(any('does not match' in error for error in report['snapshot_gate']['errors']))

    def test_metadata_preflight_blocks_exact_catalog_below_event_group_floor(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            events = (
                b'{"source_key":"hiaval_hma","event_time":"2023-12-01T00:00:00Z","region_key":"himalayas_nepal","label":1}\n'
                b'{"source_key":"gee_sar","event_time":"2024-12-12T00:00:00Z","region_key":"himalayas_nepal","label":1}\n'
                b'{"source_key":"hiaval_hma","event_time":"2025-12-01T00:00:00Z","region_key":"himalayas_nepal","label":1}\n'
            )
            events_path = root / 'events.jsonl'
            events_path.write_bytes(events)
            overlap_path = root / 'source_overlap_report.json'
            overlap_path.write_text(json.dumps({
                'status': 'reviewed',
                'source_a': 'gee_sar',
                'source_b': 'hiaval_hma',
                'source_a_sha256': 'a' * 64,
                'source_b_sha256': 'b' * 64,
                'source_a_record_count': 1,
                'source_b_record_count': 2,
                'source_a_non_overlap_count': 1,
                'source_b_non_overlap_count': 2,
                'independent_positive_source_count': 2,
                'same_event_must_not_count_as_independent': True,
            }), encoding='utf-8')
            source_manifests = {}
            source_rows = {
                'gee_sar': [events.splitlines()[1]],
                'hiaval_hma': [events.splitlines()[0], events.splitlines()[2]],
            }
            for source_key, rows in source_rows.items():
                source_dir = root / source_key
                source_dir.mkdir()
                source_events = b'\n'.join(rows) + b'\n'
                source_events_path = source_dir / 'events.jsonl'
                source_events_path.write_bytes(source_events)
                nested_manifest = {
                    'snapshot_schema_version': 'fixture_source_v1',
                    'source_key': source_key,
                    'events_path': 'events.jsonl',
                    'event_rows_sha256': hashlib.sha256(source_events).hexdigest(),
                }
                nested_manifest_path = source_dir / 'snapshot_manifest.json'
                nested_manifest_path.write_text(json.dumps(nested_manifest), encoding='utf-8')
                source_manifests[source_key] = {
                    'snapshot_manifest': str(nested_manifest_path.relative_to(root)),
                    'event_rows_sha256': nested_manifest['event_rows_sha256'],
                    'license_status': 'permissive_core_reviewed',
                    'training_eligible': True,
                }
            manifest = {
                'snapshot_schema_version': 'mvp4_reviewed_hma_catalog_v1',
                'source_key': 'mvp4_reviewed_hma_catalog',
                'source_keys': ['gee_sar', 'hiaval_hma'],
                'source_role': 'reviewed_multi_source_core_catalog',
                'source_manifests': source_manifests,
                'source_overlap_report': overlap_path.name,
                'source_overlap_report_sha256': hashlib.sha256(overlap_path.read_bytes()).hexdigest(),
                'required_independent_positive_sources': ['gee_sar', 'hiaval_hma'],
                'independent_positive_source_count': 2,
                'same_event_must_not_count_as_independent': True,
                'events_path': events_path.name,
                'event_rows_sha256': hashlib.sha256(events).hexdigest(),
                'positive_season_ids': ['2023-2024', '2024-2025', '2025-2026'],
                'positive_seasons_by_region': {
                    'himalayas_nepal': ['2023-2024', '2024-2025', '2025-2026'],
                },
                'region_season_start_months': {'himalayas_nepal': 11},
                'training_eligible': True,
                'production_scoring_eligible': False,
                'review_status': 'reviewed_local_source_catalog',
            }
            manifest_path = root / 'snapshot_manifest.json'
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

            report = build_training_preflight(
                root,
                snapshot_manifest=manifest_path,
                selected_region_keys=['himalayas_nepal'],
            )

        self.assertEqual(report['decision'], 'blocked_pending_snapshot_evidence')
        self.assertFalse(report['snapshot_gate']['passed'])
        self.assertTrue(any('event groups' in error for error in report['snapshot_gate']['errors']))
        self.assertEqual(
            report['snapshot_gate']['region_checks']['himalayas_nepal']['exact_positive_source_ids'],
            [],
        )

    def test_metadata_preflight_blocks_missing_event_groups_and_origin_families(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            events = b'{"source_key":"hiaval_hma","region_key":"himalayas_nepal","timestamp":"2023-12-01T00:00:00Z","label":1}\n'
            events_path = root / 'events.jsonl'
            events_path.write_bytes(events)
            overlap_path = root / 'source_overlap_report.json'
            overlap_path.write_text(json.dumps({
                'status': 'reviewed',
                'source_a': 'gee_sar',
                'source_b': 'hiaval_hma',
                'source_a_sha256': 'a' * 64,
                'source_b_sha256': 'b' * 64,
                'source_a_record_count': 1,
                'source_b_record_count': 1,
                'source_a_non_overlap_count': 1,
                'source_b_non_overlap_count': 1,
                'independent_positive_source_count': 2,
                'same_event_must_not_count_as_independent': True,
            }), encoding='utf-8')
            manifest_path = root / 'snapshot_manifest.json'
            manifest_path.write_text(json.dumps({
                'snapshot_schema_version': 'mvp4_hiaval_snapshot_v1',
                'source_key': 'fixture-incomplete-groups',
                'license_status': 'permissive_core_reviewed',
                'license_review_id': 'fixture-license-review-groups',
                'training_eligible': True,
                'production_scoring_eligible': False,
                'events_path': events_path.name,
                'event_rows_sha256': hashlib.sha256(events).hexdigest(),
                'positive_season_ids': ['2023-2024', '2024-2025', '2025-2026'],
                'required_independent_positive_sources': ['gee_sar', 'hiaval_hma'],
                'target_regions': {'himalayas_nepal': {'season_start_month': 11}},
                'source_overlap_report': overlap_path.name,
            }), encoding='utf-8')

            report = build_training_preflight(root, snapshot_manifest=manifest_path)

        self.assertFalse(report['snapshot_gate']['passed'])
        self.assertTrue(any('event groups' in error for error in report['snapshot_gate']['errors']))
        self.assertTrue(any('origin source families' in error for error in report['snapshot_gate']['errors']))

    def test_metadata_preflight_audits_the_latest_timestamped_artifact(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact = root / '20260705T110420Z'
            artifact.mkdir()
            self._write_artifact_bundle(artifact)
            # Recovery and cache directories must not be mistaken for the
            # latest training candidate.
            recovery = root / 'recovery'
            recovery.mkdir()
            (recovery / 'training_metrics.json').write_text('{}', encoding='utf-8')

            report = build_training_preflight(root)

        self.assertEqual(report['status'], 'prior_artifact_audited')
        self.assertEqual(report['artifact_dir'], str(artifact))
        self.assertEqual(report['decision'], 'blocked_pending_snapshot_evidence')
        self.assertIn('audit', report)

    def test_audit_validates_snapshot_bytes_and_nested_runtime_manifest(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snapshot = b'{"event_group_id":"event:1","label":1}\n'
            (root / 'event_rows.jsonl').write_bytes(snapshot)
            snapshot_hash = hashlib.sha256(snapshot).hexdigest()
            split_boundaries = {
                'train': {'event_group_ids': ['event:1']},
                'calibration': {'event_group_ids': ['event:2']},
                'test': {'event_group_ids': ['event:3']},
            }
            manifest = {
                'training_dataset_version': 'real_event_join_v1',
                'positive_count': 2,
                'negative_count': 6,
                'training_row_count': 8,
                'oldest_timestamp': '2024-01-01T00:00:00+00:00',
                'newest_timestamp': '2024-03-15T00:00:00+00:00',
                'event_source_counts': {'gee_sar': 1, 'french_epa': 1},
                'positive_source_ids': ['french_epa', 'gee_sar'],
                'positive_season_ids': ['2023-2024', '2024-2025', '2025-2026'],
                'region_keys': ['himalayas_nepal'],
                'row_snapshot_sha256': snapshot_hash,
                'row_snapshot_ref': 'event_rows.jsonl',
                'split_boundaries': split_boundaries,
                'runtime_manifest': {'code_sha': 'abc123', 'dependency_lock_hash': 'lock123'},
                'debug_stats': {
                    'raw_rows': 2,
                    'assembled_ok': 2,
                    'terrain_loss_report': {
                        'terrain_loss_rate': 0.0,
                        'terrain_loss_count': 0,
                        'candidate_rows': 2,
                        'failure_reasons': {},
                        'by_region': {},
                    },
                },
            }
            (root / 'training_metrics.json').write_text(
                json.dumps({
                    'dataset_snapshot_id': 'real_event_join_v1:2024-03-15T00:00:00+00:00',
                    'dataset_manifest': manifest,
                    'feature_columns_hash': 'feature-hash',
                    'label_schema_hash': 'label-hash',
                    'metrics': {
                        'pss_timeseries_folds': [0.7, 0.8],
                        'pss_spatial_folds': [0.7, 0.8],
                    },
                }),
                encoding='utf-8',
            )
            (root / 'reproducibility_manifest.json').write_text(
                json.dumps({
                    'snapshot_hash': snapshot_hash,
                    'split_boundaries': split_boundaries,
                    'runtime': {'code_sha': 'abc123', 'dependency_lock_hash': 'lock123'},
                }),
                encoding='utf-8',
            )
            (root / 'split_manifest.json').write_text(json.dumps(split_boundaries), encoding='utf-8')
            (root / 'autonomous_evidence_summary.json').write_text(
                json.dumps({'manual_positive_count': 1}),
                encoding='utf-8',
            )

            snapshot_manifest = self._write_reviewed_snapshot(root)
            audit = build_dataset_audit(root, snapshot_manifest=snapshot_manifest)

        self.assertTrue(audit['integrity']['row_level_snapshot_present'])
        self.assertTrue(audit['integrity']['row_snapshot_hash_valid'])
        self.assertTrue(audit['integrity']['split_boundaries_present'])
        self.assertTrue(audit['integrity']['code_sha_present'])
        self.assertTrue(audit['integrity']['environment_manifest_present'])
        self.assertTrue(audit['evaluation']['fold_metrics_present'])
        self.assertEqual(audit['decision'], 'reviewable')

    def test_audit_blocks_artifact_without_temporal_or_spatial_fold_metrics(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_artifact_bundle(root)
            metrics_path = root / 'training_metrics.json'
            payload = json.loads(metrics_path.read_text(encoding='utf-8'))
            payload['metrics'] = {'pss_reported': 0.86}
            metrics_path.write_text(json.dumps(payload), encoding='utf-8')

            audit = build_dataset_audit(root)

        self.assertFalse(audit['evaluation']['fold_metrics_present'])
        self.assertIn('fold_metrics_missing', {finding['id'] for finding in audit['findings']})
        self.assertEqual(audit['decision'], 'blocked_pending_snapshot_evidence')


if __name__ == '__main__':
    unittest.main()
