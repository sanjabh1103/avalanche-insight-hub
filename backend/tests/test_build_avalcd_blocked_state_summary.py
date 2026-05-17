from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend.scripts.build_avalcd_blocked_state_summary import (
    build_avalcd_blocked_state_summary,
    main,
)


def _benchmark_report(
    *,
    precision: float,
    recall: float,
    f1: float,
    evaluation_mode: str = 'scene_blended',
    precision_floor_met: bool,
    recall_floor_met: bool,
    passed: bool = False,
    production_scoring_allowed: bool = False,
    decision: str = 'blocked_shadow_only',
) -> dict:
    blocked_gate = None
    if not precision_floor_met:
        blocked_gate = 'precision_floor'
    elif not recall_floor_met:
        blocked_gate = 'recall_floor'
    return {
        'production_scoring_allowed': production_scoring_allowed,
        'promotion_gate_report': {'decision': decision},
        'source_reports': [{
            'source_key': 'avalcd_zenodo_v1',
            'sar_prediction_metrics': {
                'model_version': 'unit-model',
                'evaluation_mode': evaluation_mode,
                'threshold': 0.997,
                'metrics': {
                    'precision': precision,
                    'recall': recall,
                    'f1': f1,
                    'iou': 0.36,
                    'false_positive_rate': 0.001,
                },
                'quality_gate': {
                    'passed': passed,
                    'blocked_gate': blocked_gate,
                    'precision_floor_met': precision_floor_met,
                    'recall_floor_met': recall_floor_met,
                },
            },
        }],
    }


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')


class BuildAvalcdBlockedStateSummaryTests(unittest.TestCase):
    def test_summary_reports_current_v3_v4_blocked_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            v3 = root / 'v3.json'
            v4 = root / 'v4.json'
            snow = root / 'snow.json'
            modal = root / 'modal.txt'
            _write_json(v3, _benchmark_report(
                precision=0.6099,
                recall=0.4674,
                f1=0.5292,
                precision_floor_met=True,
                recall_floor_met=False,
            ))
            _write_json(v4, _benchmark_report(
                precision=0.5208,
                recall=0.5509,
                f1=0.5354,
                precision_floor_met=False,
                recall_floor_met=True,
            ))
            _write_json(snow, {
                'status': 'blocked_prediction_materialization',
                'reason': 'quality gate failed',
            })
            modal.write_text('Active Containers in environment: None\n', encoding='utf-8')

            summary = build_avalcd_blocked_state_summary(
                v3_benchmark_report=v3,
                v4_benchmark_report=v4,
                snow_materialization_result=snow,
                modal_container_list_output=modal,
            )

        self.assertEqual(summary['status'], 'ok')
        self.assertEqual(summary['final_decision'], 'blocked_shadow_only')
        self.assertFalse(summary['snow_slide_materialization_allowed'])
        self.assertEqual(summary['candidates'][0]['gate_summary'], 'precision_passed_recall_failed')
        self.assertEqual(summary['candidates'][1]['gate_summary'], 'recall_passed_precision_failed')
        self.assertEqual(summary['modal_containers']['status'], 'empty')

    def test_summary_flags_patch_level_or_production_allowed_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            v3 = root / 'v3.json'
            v4 = root / 'v4.json'
            snow = root / 'snow.json'
            _write_json(v3, _benchmark_report(
                precision=0.61,
                recall=0.46,
                f1=0.52,
                evaluation_mode='patch_level',
                precision_floor_met=True,
                recall_floor_met=False,
            ))
            _write_json(v4, _benchmark_report(
                precision=0.52,
                recall=0.55,
                f1=0.53,
                precision_floor_met=False,
                recall_floor_met=True,
                production_scoring_allowed=True,
            ))
            _write_json(snow, {'status': 'ok'})

            summary = build_avalcd_blocked_state_summary(
                v3_benchmark_report=v3,
                v4_benchmark_report=v4,
                snow_materialization_result=snow,
            )

        self.assertEqual(summary['status'], 'failed')
        self.assertTrue(any('evaluation_mode must be scene_blended' in item for item in summary['violations']))
        self.assertTrue(any('production_scoring_allowed must be false' in item for item in summary['violations']))
        self.assertTrue(any('SnowSlide materialization result must remain blocked' in item for item in summary['violations']))
        self.assertTrue(any('Modal active container check must be provided' in item for item in summary['violations']))

    def test_summary_modal_check_invokes_container_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            v3 = root / 'v3.json'
            v4 = root / 'v4.json'
            snow = root / 'snow.json'
            _write_json(v3, _benchmark_report(
                precision=0.6099,
                recall=0.4674,
                f1=0.5292,
                precision_floor_met=True,
                recall_floor_met=False,
            ))
            _write_json(v4, _benchmark_report(
                precision=0.5208,
                recall=0.5509,
                f1=0.5354,
                precision_floor_met=False,
                recall_floor_met=True,
            ))
            _write_json(snow, {'status': 'blocked_prediction_materialization'})
            completed = Mock(returncode=0, stdout='Active Containers in environment: None\n', stderr='')

            with patch('backend.scripts.build_avalcd_blocked_state_summary.subprocess.run', return_value=completed) as run_mock:
                summary = build_avalcd_blocked_state_summary(
                    v3_benchmark_report=v3,
                    v4_benchmark_report=v4,
                    snow_materialization_result=snow,
                    modal_profile='sanjabh1103_limit30',
                    modal_cli='modal',
                )

        self.assertEqual(summary['status'], 'ok')
        run_mock.assert_called_once()
        self.assertEqual(run_mock.call_args.args[0], ['modal', 'container', 'list'])

    def test_main_writes_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            v3 = root / 'v3.json'
            v4 = root / 'v4.json'
            snow = root / 'snow.json'
            modal = root / 'modal.txt'
            output_json = root / 'summary.json'
            output_markdown = root / 'summary.md'
            _write_json(v3, _benchmark_report(
                precision=0.6099,
                recall=0.4674,
                f1=0.5292,
                precision_floor_met=True,
                recall_floor_met=False,
            ))
            _write_json(v4, _benchmark_report(
                precision=0.5208,
                recall=0.5509,
                f1=0.5354,
                precision_floor_met=False,
                recall_floor_met=True,
            ))
            _write_json(snow, {'status': 'blocked_prediction_materialization'})
            modal.write_text('Active Containers in environment: None\n', encoding='utf-8')

            exit_code = main([
                '--v3-benchmark-report', str(v3),
                '--v4-benchmark-report', str(v4),
                '--snow-materialization-result', str(snow),
                '--modal-container-list-output', str(modal),
                '--output-json', str(output_json),
                '--output-markdown', str(output_markdown),
            ])

            self.assertEqual(exit_code, 0)
            self.assertTrue(output_json.exists())
            self.assertTrue(output_markdown.exists())
            self.assertIn('AvalCD Blocked-State', output_markdown.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
