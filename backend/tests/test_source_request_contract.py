from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.scripts.audit_training_dataset import build_training_preflight


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / 'schemas/source_manifest.schema.json'
TEMPLATE_PATH = ROOT / 'schemas/source_manifest_request.template.json'
REGISTRY_PATH = ROOT / 'docs/MVP4/03_ml_evidence/source_manifest_registry.json'


class SourceRequestContractTests(unittest.TestCase):
    def _assert_required_shape(self, value: object, schema: dict, path: str = '$') -> None:
        if schema.get('type') == 'object':
            self.assertIsInstance(value, dict, path)
            object_value = value
            for field in schema.get('required', []):
                self.assertIn(field, object_value, f'{path}.{field}')
            for field, child_schema in schema.get('properties', {}).items():
                if field in object_value:
                    self._assert_required_shape(object_value[field], child_schema, f'{path}.{field}')
        elif schema.get('type') == 'array':
            self.assertIsInstance(value, list, path)
            for index, item in enumerate(value):
                self._assert_required_shape(item, schema.get('items', {}), f'{path}[{index}]')

    def test_schema_and_template_declare_fail_closed_core_guard(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))
        template = json.loads(TEMPLATE_PATH.read_text(encoding='utf-8'))
        required = set(schema['required'])

        self.assertEqual(schema['properties']['schema_version']['const'], 'mvp4_source_request_manifest_v1')
        self.assertTrue(required.issubset(template))
        self.assertEqual(template['source_role'], 'requested_core')
        self.assertFalse(template['training_eligible'])
        self.assertFalse(template['production_scoring_eligible'])

        core_guard = schema['allOf'][0]
        self.assertEqual(core_guard['then']['properties']['review_status']['const'], 'approved')
        self.assertEqual(core_guard['then']['properties']['training_eligible']['const'], True)
        self.assertEqual(
            core_guard['then']['properties']['time_semantics']['properties']['precision']['const'],
            'exact',
        )

    def test_core_guard_requires_reviewed_multiseason_source_evidence(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))
        core_guard = schema['allOf'][0]['then']

        self.assertIn('evidence_refs', core_guard['required'])
        self.assertIn('event_rows_sha256', core_guard['required'])
        self.assertEqual(
            core_guard['properties']['evidence_refs']['minItems'],
            1,
        )
        self.assertEqual(
            core_guard['properties']['coverage']['properties']['positive_seasons']['minItems'],
            3,
        )
        self.assertEqual(
            core_guard['properties']['coverage']['properties']['exact_time_positive_seasons']['minItems'],
            3,
        )
        self.assertEqual(
            core_guard['properties']['provenance']['properties']['source_hash']['pattern'],
            '^[0-9a-fA-F]{64}$',
        )
        self.assertEqual(
            core_guard['properties']['provenance']['properties']['source_hash_algorithm']['const'],
            'sha256',
        )
        self.assertEqual(
            core_guard['properties']['provenance']['properties']['retrieved_at']['type'],
            'string',
        )

    def test_registry_entries_are_evidence_only_and_shadow_safe(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))
        registry = json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))
        sources = registry['sources']

        self.assertGreaterEqual(len(sources), 5)
        self.assertEqual(registry['registry_status'], 'evidence_only_not_training_authority')
        for source in sources:
            self._assert_required_shape(source, schema, f'$.sources[{source["source_id"]}]')
            self.assertEqual(source['schema_version'], 'mvp4_source_request_manifest_v1')
            self.assertIn(source['source_role'], {'requested_core', 'shadow', 'benchmark', 'context'})
            self.assertFalse(source['training_eligible'], source['source_id'])
            self.assertFalse(source['production_scoring_eligible'], source['source_id'])
            self.assertFalse(source['time_semantics']['release_time_proven'], source['source_id'])
            self.assertFalse(
                source['time_semantics']['source_time_is_avalanche_occurrence_time'],
                source['source_id'],
            )
            self.assertEqual(source['coverage']['minimum_positive_seasons_gate'], 3)
            self.assertTrue(source['required_next_action'])

    def test_shadow_registry_does_not_bypass_real_preflight(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            events = root / 'events.jsonl'
            events.write_text(json.dumps({
                'source_event_id': 'shadow:1',
                'event_group_id': 'shadow:1',
                'origin_source_family': 'shadow_family',
                'source_key': 'hiaval_hma',
                'region_key': 'himalayas_nepal',
                'event_time_start': '2025-11-01T00:00:00Z',
                'event_time_end': '2025-11-02T00:00:00Z',
                'timestamp_precision': 'day',
                'label': 1,
            }) + '\n', encoding='utf-8')
            manifest = root / 'snapshot_manifest.json'
            manifest.write_text(json.dumps({
                'snapshot_schema_version': 'mvp4_hiaval_snapshot_v1',
                'source_key': 'hiaval_hma',
                'label_time_contract': 'interval_censored_core_v1',
                'license_status': 'permissive_shadow_reviewed',
                'license_review_id': 'shadow-review',
                'training_eligible': False,
                'production_scoring_eligible': False,
                'events_path': events.name,
                'positive_season_ids': ['2025-2026'],
                'required_independent_positive_sources': ['hiaval_hma', 'second_exact_time_source'],
                'target_regions': {'himalayas_nepal': {'season_start_month': 11}},
                'source_overlap_report': 'overlap.json',
            }), encoding='utf-8')
            (root / 'overlap.json').write_text(json.dumps({'status': 'pending'}), encoding='utf-8')

            report = build_training_preflight(root, snapshot_manifest=manifest, selected_region_keys=['himalayas_nepal'])

        errors = report['snapshot_gate']['errors']
        self.assertFalse(report['snapshot_gate']['passed'])
        self.assertTrue(any('not marked training_eligible' in error for error in errors))
        self.assertTrue(any('does not match the requested contract' in error for error in errors))
        self.assertTrue(any('needs at least 30' in error for error in errors))
        self.assertTrue(any('at least 3 positive seasons' in error for error in errors))


if __name__ == '__main__':
    unittest.main()
