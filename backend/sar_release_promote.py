from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.common.sar_acceptance_policy import assert_sar_acceptance_for_promotion
from backend.common.config import load_settings
from backend.common.supabase_io import has_supabase_credentials, rest_get
from backend.sar_unet_worker import SAR_UNET_SEGMENTATION_THRESHOLD, flip_to_training_eligible, run_segmentation


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def _assert_positive_evaluation(
    report: dict[str, Any],
    *,
    acceptance_report: dict[str, Any] | None,
) -> None:
    if str(report.get('status')) != 'ok':
        raise ValueError('evaluation report must have status=ok before promotion')
    if not bool(report.get('beats_baseline')):
        raise ValueError('evaluation report must have beats_baseline=true before promotion')
    assert_sar_acceptance_for_promotion(acceptance_report)


def _query_recent_shadow_event_ids(days_back: int, *, hazard_type: str = 'avalanche') -> list[str]:
    if not has_supabase_credentials():
        return []
    cutoff = (_utc_now() - timedelta(days=max(1, days_back))).isoformat()
    rows = rest_get('avalanche_events', params={
        'select': 'id',
        'source': 'eq.sar_unet',
        'hazard_type': f'eq.{hazard_type}',
        'training_eligible': 'eq.false',
        'timestamp': f'gte.{cutoff}',
        'order': 'timestamp.desc',
        'limit': '1000',
    })
    return [str(row.get('id')) for row in rows if row.get('id')]


def promote_from_report(
    report: dict[str, Any],
    *,
    acceptance_report: dict[str, Any] | None = None,
    scenes_manifest: dict[str, Any] | None = None,
    model_path: Path | None = None,
    artifact_root: Path,
    threshold: float = SAR_UNET_SEGMENTATION_THRESHOLD,
    device: str = 'cpu',
    hazard_type: str = 'avalanche',
    dry_run: bool = False,
    recent_shadow_event_ids: list[str] | None = None,
    recent_days_back: int | None = None,
) -> dict[str, Any]:
    _assert_positive_evaluation(report, acceptance_report=acceptance_report)

    if scenes_manifest and isinstance(scenes_manifest.get('scenes'), list) and scenes_manifest['scenes']:
        if model_path is None or not str(model_path):
            raise ValueError('model_path is required when promoting via rerun segmentation')
        rerun_manifest = dict(scenes_manifest)
        rerun_manifest['shadow_mode'] = False
        result = run_segmentation(
            scenes=rerun_manifest['scenes'],
            model_path=model_path,
            artifact_root=artifact_root,
            threshold=threshold,
            device=device,
            hazard_type=hazard_type,
            persist_events=not dry_run,
            promoted=True,
        )
        result['promotion_mode'] = 'rerun_segmentation'
        return result

    shadow_ids = list(recent_shadow_event_ids or [])
    if not shadow_ids and recent_days_back is not None:
        shadow_ids = _query_recent_shadow_event_ids(recent_days_back, hazard_type=hazard_type)

    flipped = len(shadow_ids) if dry_run else flip_to_training_eligible(shadow_ids)
    return {
        'status': 'ok',
        'promotion_mode': 'flip_existing',
        'requested_event_ids': len(shadow_ids),
        'promoted_event_ids': flipped,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    settings = load_settings()
    parser = argparse.ArgumentParser(description='Promote SAR release results after a successful held-out evaluation')
    parser.add_argument('--evaluation-report', type=Path, required=True, help='Path to sar_evaluation_report.json')
    parser.add_argument('--acceptance-report', type=Path, required=True, help='SnowSlide research-grade acceptance report JSON')
    parser.add_argument('--scenes-manifest', type=Path, help='Optional scenes manifest to rerun sar-segment in promoted mode')
    model_path_raw = os.environ.get('SAR_UNET_MODEL_PATH')
    parser.add_argument('--model-path', type=Path, default=Path(model_path_raw) if model_path_raw else None)
    parser.add_argument('--artifact-root', type=Path, default=settings.artifact_root)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--threshold', type=float, default=SAR_UNET_SEGMENTATION_THRESHOLD)
    parser.add_argument('--hazard-type', default=settings.hazard_type)
    parser.add_argument('--days-back', type=int, help='Fallback: flip existing recent shadow rows when no scenes manifest is supplied')
    parser.add_argument('--event-ids-file', type=Path, help='Fallback: newline-delimited event ids to flip')
    parser.add_argument('--dry-run', action='store_true')
    return parser.parse_args(argv)


def _load_event_ids(path: Path | None) -> list[str]:
    if path is None:
        return []
    return [line.strip() for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = _load_json(args.evaluation_report)
    acceptance_report = _load_json(args.acceptance_report)
    scenes_manifest = _load_json(args.scenes_manifest) if args.scenes_manifest else None
    event_ids = _load_event_ids(args.event_ids_file)
    result = promote_from_report(
        report,
        acceptance_report=acceptance_report,
        scenes_manifest=scenes_manifest,
        model_path=args.model_path if args.scenes_manifest else None,
        artifact_root=args.artifact_root,
        threshold=args.threshold,
        device=args.device,
        hazard_type=args.hazard_type,
        dry_run=args.dry_run,
        recent_shadow_event_ids=event_ids,
        recent_days_back=args.days_back,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
