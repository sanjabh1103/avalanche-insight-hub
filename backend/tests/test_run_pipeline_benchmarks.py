from __future__ import annotations

import unittest

from backend.scripts.run_pipeline_benchmarks import build_pipeline_benchmark_report


class RunPipelineBenchmarksTests(unittest.TestCase):
    def test_build_pipeline_benchmark_report_uses_existing_artifact_summaries(self) -> None:
        report = build_pipeline_benchmark_report(
            training_metrics={
                'latest_benchmark_summary': {
                    'benchmark_kind': 'training',
                    'status': 'ok',
                    'total_seconds': 18.2,
                },
            },
            training_stage_metrics=None,
            inference_manifest={
                'latest_benchmark_summary': {
                    'benchmark_kind': 'inference_publication',
                    'status': 'ok',
                    'total_seconds': 9.4,
                },
            },
            release_gate={
                'status': 'ok',
                'decision': 'promote',
                'evaluation_report': {
                    'beats_baseline': True,
                    'duration_seconds': 44.1,
                },
            },
        )

        self.assertEqual(report['training']['total_seconds'], 18.2)
        self.assertEqual(report['inference_publication']['benchmark_kind'], 'inference_publication')
        self.assertEqual(report['release_verification']['decision'], 'promote')
        self.assertEqual(report['available_sections'], ['training', 'inference_publication', 'release_verification'])

    def test_build_pipeline_benchmark_report_builds_training_summary_from_stage_metrics(self) -> None:
        report = build_pipeline_benchmark_report(
            training_metrics=None,
            training_stage_metrics={
                'dataset_snapshot_id': 'snapshot-1',
                'training_row_count': 120,
                'positive_count': 22,
                'region_count': 4,
                'phase_breakdown_seconds': {
                    'dataset_load_seconds': 3.0,
                    'fit_model_seconds': 7.5,
                },
            },
            inference_manifest=None,
            release_gate=None,
        )

        self.assertEqual(report['training']['benchmark_kind'], 'training')
        self.assertEqual(report['training']['total_seconds'], 10.5)
        self.assertEqual(report['training']['input_context']['positive_count'], 22)

    def test_build_pipeline_benchmark_report_ignores_empty_training_summary_dict(self) -> None:
        report = build_pipeline_benchmark_report(
            training_metrics={
                'latest_benchmark_summary': {},
            },
            training_stage_metrics={
                'dataset_snapshot_id': 'snapshot-2',
                'training_row_count': 64,
                'positive_count': 12,
                'region_count': 3,
                'phase_breakdown_seconds': {
                    'dataset_load_seconds': 1.5,
                    'fit_model_seconds': 4.5,
                },
            },
            inference_manifest=None,
            release_gate=None,
        )

        self.assertEqual(report['training']['benchmark_kind'], 'training')
        self.assertEqual(report['training']['total_seconds'], 6.0)
        self.assertEqual(report['available_sections'], ['training'])

    def test_build_pipeline_benchmark_report_ignores_empty_inference_summary_dict(self) -> None:
        report = build_pipeline_benchmark_report(
            training_metrics=None,
            training_stage_metrics=None,
            inference_manifest={
                'latest_benchmark_summary': {},
                'stage_metrics_summary': {
                    'region_count': 2,
                    'lifeboat_mode': False,
                    'lifeboat_profile': 'full',
                    'artifact_resolution_seconds': 0.5,
                    'publication_seconds_total': 7.25,
                },
            },
            release_gate=None,
        )

        self.assertEqual(report['inference_publication']['benchmark_kind'], 'inference_publication')
        self.assertEqual(report['inference_publication']['total_seconds'], 7.75)
        self.assertEqual(report['available_sections'], ['inference_publication'])


if __name__ == '__main__':
    unittest.main()
