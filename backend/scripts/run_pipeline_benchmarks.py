from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.common.audit_metadata import build_latest_benchmark_summary


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _training_summary(
    training_metrics: dict[str, Any] | None,
    training_stage_metrics: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if isinstance(training_metrics, dict):
        existing = training_metrics.get('latest_benchmark_summary')
        if isinstance(existing, dict):
            return existing
    if not isinstance(training_stage_metrics, dict):
        return None
    phase_breakdown = training_stage_metrics.get('phase_breakdown_seconds')
    if not isinstance(phase_breakdown, dict):
        return None
    return build_latest_benchmark_summary(
        benchmark_kind='training',
        phase_breakdown_seconds={
            str(key): float(value)
            for key, value in phase_breakdown.items()
            if isinstance(value, (int, float))
        },
        input_context={
            'dataset_snapshot_id': training_stage_metrics.get('dataset_snapshot_id'),
            'training_row_count': training_stage_metrics.get('training_row_count'),
            'positive_count': training_stage_metrics.get('positive_count'),
            'region_count': training_stage_metrics.get('region_count'),
        },
        status='ok',
        artifact_ref='training_stage_metrics.json',
    )


def _inference_summary(inference_manifest: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(inference_manifest, dict):
        return None
    existing = inference_manifest.get('latest_benchmark_summary')
    if isinstance(existing, dict):
        return existing
    stage_metrics = inference_manifest.get('stage_metrics_summary')
    if not isinstance(stage_metrics, dict):
        return None
    return build_latest_benchmark_summary(
        benchmark_kind='inference_publication',
        phase_breakdown_seconds={
            str(key): float(value)
            for key, value in stage_metrics.items()
            if key.endswith('_seconds') or key.endswith('_seconds_total')
            if isinstance(value, (int, float))
        },
        input_context={
            'region_count': stage_metrics.get('region_count'),
            'lifeboat_mode': stage_metrics.get('lifeboat_mode'),
            'lifeboat_profile': stage_metrics.get('lifeboat_profile'),
        },
        status='ok',
        artifact_ref='inference_manifest.json',
    )


def _release_summary(release_gate: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(release_gate, dict):
        return None
    evaluation = release_gate.get('evaluation_report') if isinstance(release_gate.get('evaluation_report'), dict) else {}
    duration_seconds = evaluation.get('duration_seconds')
    if not isinstance(duration_seconds, (int, float)):
        duration_seconds = release_gate.get('duration_seconds')
    return {
        'summary_version': 'runtime_benchmark_v1',
        'benchmark_kind': 'release_verification',
        'status': str(release_gate.get('status') or 'unknown'),
        'decision': release_gate.get('decision'),
        'beats_baseline': evaluation.get('beats_baseline'),
        'total_seconds': float(duration_seconds) if isinstance(duration_seconds, (int, float)) else None,
        'artifact_ref': 'authoritative_release_gate.json',
    }


def build_pipeline_benchmark_report(
    *,
    training_metrics: dict[str, Any] | None,
    training_stage_metrics: dict[str, Any] | None,
    inference_manifest: dict[str, Any] | None,
    release_gate: dict[str, Any] | None,
) -> dict[str, Any]:
    report = {
        'summary_version': 'pipeline_benchmark_report_v1',
        'training': _training_summary(training_metrics, training_stage_metrics),
        'inference_publication': _inference_summary(inference_manifest),
        'release_verification': _release_summary(release_gate),
    }
    report['available_sections'] = [
        section
        for section in ('training', 'inference_publication', 'release_verification')
        if isinstance(report.get(section), dict)
    ]
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Summarize pipeline benchmark artifacts')
    parser.add_argument('--training-metrics', type=Path)
    parser.add_argument('--training-stage-metrics', type=Path)
    parser.add_argument('--inference-manifest', type=Path)
    parser.add_argument('--release-gate-json', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)

    report = build_pipeline_benchmark_report(
        training_metrics=_load_json(args.training_metrics),
        training_stage_metrics=_load_json(args.training_stage_metrics),
        inference_manifest=_load_json(args.inference_manifest),
        release_gate=_load_json(args.release_gate_json),
    )
    payload = json.dumps(report, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + '\n', encoding='utf-8')
    print(payload)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
