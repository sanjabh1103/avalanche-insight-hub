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


if __name__ == '__main__':
    unittest.main()
