from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.scripts.build_avalcd_benchmark_from_first_gate import build_avalcd_benchmark_from_first_gate
from backend.scripts.build_fresh_final_holdout_plan import build_fresh_final_holdout_plan
from backend.scripts.build_snowslide_mask_dtype_requalification_requests import (
    build_snowslide_mask_dtype_requalification_requests,
)
from backend.scripts.build_snowslide_v6_qualification_requests import build_snowslide_v6_qualification_requests


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def _staged_manifest(root: Path) -> Path:
    records = root / 'records.jsonl'
    rows = [
        {
            'event_id': 'livigno_20250318',
            'source_key': 'avalcd_zenodo_v1',
            'region_key': 'italian_alps',
            'event_time': '2025-03-18',
            'assets': {'stack_ref': 'stack-a', 'truth_mask_ref': 'truth-a'},
            'training_eligible': True,
            'production_eligible': False,
        },
        {
            'event_id': 'nuuk_20210411',
            'source_key': 'avalcd_zenodo_v1',
            'region_key': 'greenland_nuuk',
            'event_time': '2021-04-11',
            'assets': {'stack_ref': 'stack-b', 'truth_mask_ref': 'truth-b'},
            'training_eligible': True,
            'production_eligible': False,
        },
    ]
    records.write_text('\n'.join(json.dumps(row) for row in rows) + '\n', encoding='utf-8')
    return _write_json(root / 'staged_manifest.json', {
        'source_key': 'avalcd_zenodo_v1',
        'source': {'source_key': 'avalcd_zenodo_v1', 'data_lane': 'sar_masks', 'label': 'AvalCD'},
        'requested_role': 'shadow_training',
        'license_review_id': 'license-review-test',
        'records_jsonl': str(records),
    })


def _first_gate(root: Path) -> Path:
    return _write_json(root / 'first_gate.json', {
        'status': 'passed_avalcd_first_gate',
        'precision_floor': 0.6,
        'recall_floor': 0.5,
        'metrics': {
            'threshold': 0.9980000257492065,
            'postprocess_min_component_area_px': 0,
            'postprocess_opening_size_px': 0,
            'precision': 0.649,
            'recall': 0.535,
        },
    })


def _evaluation_request(root: Path) -> Path:
    return _write_json(root / 'eval_request.json', {
        'source_key': 'avalcd_zenodo_v1',
        'license_review_id': 'license-review-test',
        'model_family': 'swinunet_tiny_diff',
        'candidate_model_version': 'candidate-v6',
    })


def _evaluation_result(root: Path) -> Path:
    return _write_json(root / 'eval_result.json', {
        'status': 'ok',
        'evaluation_mode': 'scene_blended',
        'quality_gate_passed': True,
        'candidate_model_version': 'candidate-v6',
        'model_family': 'swinunet_tiny_diff',
        'dataset_version': 'dataset-v1',
        'validation_auprc': 0.1,
        'train_events': ['train-1'],
        'val_events': ['livigno_20250318', 'nuuk_20210411'],
        'validation_metrics': {
            'threshold': 0.9980000257492065,
            'precision': 0.649,
            'recall': 0.535,
            'f1': 0.586,
            'false_positive_rate': 0.001,
            'tp': 10,
            'fp': 5,
            'fn': 8,
            'tn': 100,
            'postprocess_min_component_area_px': 0,
            'postprocess_opening_size_px': 0,
        },
    })


def _v5_templates(root: Path) -> Path:
    template_root = root / 'v5'
    for index in range(7):
        scene_id = f'scene_{index}'
        _write_json(template_root / scene_id / 'sar_segment_request.json', {
            'reference_set_key': 'snowslide-heldout-v1',
            'prediction_model_version': 'v5',
            'model_path': '/artifacts/v5/sar_model.pt',
            'threshold': 0.996,
            'compact_response': True,
            'dry_run': True,
            'shadow_mode': True,
            'scenes': [{
                'scene_id': scene_id,
                'prediction_mask': f'sar-masks/heldout/snowslide/validation/{scene_id}/predictions/v5/prediction_mask.tif',
                'truth_mask': f'truth/{scene_id}.tif',
                'stack_ref': f'stack/{scene_id}.json',
            }],
        })
    return template_root


class Phase5Phase6SnowSlideQualificationTests(unittest.TestCase):
    def test_avalcd_bridge_builds_guard_compatible_benchmark(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = build_avalcd_benchmark_from_first_gate(
                first_gate_plan=_first_gate(root),
                evaluation_result=_evaluation_result(root),
                evaluation_request=_evaluation_request(root),
                staged_manifest=_staged_manifest(root),
                output_root=root / 'out',
            )

        report = result['benchmark_report']
        sar = report['source_reports'][0]['sar_prediction_metrics']
        self.assertFalse(report['production_scoring_allowed'])
        self.assertEqual(report['promotion_gate_report']['decision'], 'blocked_shadow_only')
        self.assertEqual(sar['evaluation_mode'], 'scene_blended')
        self.assertTrue(sar['quality_gate']['passed'])
        self.assertTrue(sar['quality_gate']['precision_floor_met'])
        self.assertTrue(sar['quality_gate']['recall_floor_met'])

    def test_v6_request_builder_preserves_selected_rule_and_shadow_guards(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            bridge = build_avalcd_benchmark_from_first_gate(
                first_gate_plan=_first_gate(root),
                evaluation_result=_evaluation_result(root),
                evaluation_request=_evaluation_request(root),
                staged_manifest=_staged_manifest(root),
                output_root=root / 'bench',
            )
            manifest = build_snowslide_v6_qualification_requests(
                avalcd_benchmark_report=Path(bridge['benchmark_report_path']),
                first_gate_plan=_first_gate(root),
                v5_by_scene_request_root=_v5_templates(root),
                materialization_output_root=root / 'materialize',
                dry_run_output_root=root / 'dry-run',
                model_path='/artifacts/v6/sar_model.pt',
                model_version='candidate-v6-scene-blended',
            )
            first_request = json.loads(Path(manifest['scene_request_paths'][0]).read_text(encoding='utf-8'))
            eval_request = json.loads((root / 'dry-run' / 'evaluate_release_request.json').read_text(encoding='utf-8'))

        self.assertEqual(manifest['scene_count'], 7)
        self.assertEqual(first_request['model_path'], '/artifacts/v6/sar_model.pt')
        self.assertEqual(first_request['threshold'], 0.9980000257492065)
        self.assertEqual(first_request['postprocess_min_component_area_px'], 0)
        self.assertTrue(first_request['compact_response'])
        self.assertFalse(first_request['persist_events'])
        self.assertIn('/predictions/candidate-v6-scene-blended/prediction_mask.tif', first_request['scenes'][0]['prediction_mask'])
        self.assertEqual(eval_request['prediction_threshold'], 0.9980000257492065)
        self.assertEqual(eval_request['reference_set_key'], 'snowslide-heldout-v1')

    def test_mask_dtype_requalification_builder_rewrites_refs_and_preserves_guards(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = _v5_templates(root)
            source_eval = _write_json(root / 'source-eval.json', {
                'reference_set_key': 'snowslide-heldout-v1',
                'prediction_model_version': 'candidate-v7',
                'prediction_threshold': 0.9980000257492065,
                'postprocess_min_component_area_px': 96,
                'postprocess_opening_size_px': 0,
                'dry_run': True,
            })
            manifest = build_snowslide_mask_dtype_requalification_requests(
                source_materialization_root=source_root,
                source_evaluate_request=source_eval,
                prediction_model_version='candidate-v7-float32',
                prediction_mask_dtype='float32',
                materialization_output_root=root / 'materialize-float32',
                dry_run_output_root=root / 'dry-run-float32',
            )
            first_request = json.loads(Path(manifest['scene_request_paths'][0]).read_text(encoding='utf-8'))
            eval_request = json.loads((root / 'dry-run-float32' / 'evaluate_release_request.json').read_text(encoding='utf-8'))

        self.assertEqual(manifest['scene_count'], 7)
        self.assertEqual(manifest['prediction_mask_dtype'], 'float32')
        self.assertFalse(manifest['production_scoring_allowed'])
        self.assertFalse(manifest['next_gpu_run_authorized'])
        self.assertEqual(first_request['prediction_mask_dtype'], 'float32')
        self.assertFalse(first_request['persist_events'])
        self.assertTrue(first_request['shadow_mode'])
        self.assertTrue(first_request['compact_response'])
        self.assertIn('/predictions/candidate-v7-float32/prediction_mask.tif', first_request['scenes'][0]['prediction_mask'])
        self.assertEqual(eval_request['prediction_model_version'], 'candidate-v7-float32')
        self.assertEqual(eval_request['prediction_threshold'], 0.9980000257492065)

    def test_fresh_final_holdout_blocks_without_independent_reference_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            acceptance = _write_json(root / 'acceptance.json', {'decision': 'requires_fresh_final_holdout'})
            report = build_fresh_final_holdout_plan(snowslide_acceptance_report=acceptance, output_root=root / 'out')

        self.assertEqual(report['status'], 'blocked_pending_fresh_reference_set')
        self.assertFalse(report['production_scoring_allowed'])
        self.assertFalse(report['promotion_allowed'])

    def test_fresh_final_holdout_refuses_reusing_snowslide_qualification_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            acceptance = _write_json(root / 'acceptance.json', {'decision': 'requires_fresh_final_holdout'})
            report = build_fresh_final_holdout_plan(
                snowslide_acceptance_report=acceptance,
                fresh_final_reference_set_key='snowslide-heldout-v1',
                output_root=root / 'out',
            )

        self.assertEqual(report['status'], 'blocked_reuses_snow_slide_qualification_set')
        self.assertFalse(report['promotion_allowed'])

    def test_fresh_final_holdout_blocks_when_snowslide_acceptance_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            acceptance = _write_json(root / 'acceptance.json', {'decision': 'blocked_research_grade'})
            report = build_fresh_final_holdout_plan(
                snowslide_acceptance_report=acceptance,
                fresh_final_reference_set_key='fresh-final-v1',
                output_root=root / 'out',
            )

        self.assertEqual(report['status'], 'blocked_pending_snowslide_research_grade')
        self.assertFalse(report['phase7_promotion_ready'])


if __name__ == '__main__':
    unittest.main()
