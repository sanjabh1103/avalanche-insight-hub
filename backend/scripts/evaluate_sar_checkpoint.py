from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from backend.sar_unet_training import (
    DEFAULT_POSTPROCESS_RECALL_FLOOR,
    DEFAULT_PRECISION_FLOOR,
    build_sar_validation_error_diagnostics,
    evaluate_sar_checkpoint,
    evaluate_sar_checkpoint_scene_blended,
)


def _parse_float_list(value: str) -> list[float]:
    values = [
        float(item.strip())
        for item in value.split(',')
        if item.strip()
    ]
    if not values:
        raise ValueError('threshold grid must include at least one value')
    return values


def build_request(args: argparse.Namespace) -> dict[str, Any]:
    request: dict[str, Any] = {
        'training_manifest_path': str(args.training_manifest.expanduser().resolve()),
        'checkpoint_path': str(args.checkpoint_path.expanduser().resolve()),
        'source_key': args.source_key,
        'license_review_id': args.license_review,
        'candidate_model_version': args.candidate_model_version,
        'model_family': args.model_family,
        'patch_size': args.patch_size,
        'stride': args.stride,
        'batch_size': args.batch_size,
        'loss': args.loss,
        'f_beta': args.f_beta,
        'precision_floor': args.precision_floor,
        'threshold_grid': _parse_float_list(args.threshold_grid),
        'postprocess_min_component_area_px': args.postprocess_min_component_area_px,
        'postprocess_opening_size_px': args.postprocess_opening_size_px,
        'postprocess_recall_floor': args.postprocess_recall_floor,
        'postprocess_apply_to_threshold_selection': True,
        'export_validation_prediction_artifact': True,
    }
    if args.materialized_dataset_root:
        request['materialized_dataset_root'] = str(args.materialized_dataset_root.expanduser().resolve())
    if args.threshold is not None:
        request['threshold'] = float(args.threshold)
        request['best_threshold'] = float(args.threshold)
    return request


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Evaluate a trained SAR checkpoint on a SAR training manifest without additional training.',
    )
    parser.add_argument('--training-manifest', type=Path, required=True)
    parser.add_argument('--checkpoint-path', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--materialized-dataset-root', type=Path)
    parser.add_argument('--source-key', default='avalcd_zenodo_v1')
    parser.add_argument('--license-review', required=True)
    parser.add_argument('--candidate-model-version', required=True)
    parser.add_argument('--model-family', default='swinunet_tiny_diff')
    parser.add_argument('--patch-size', type=int, default=128)
    parser.add_argument('--stride', type=int, default=64)
    parser.add_argument('--batch-size', type=int, default=8)
    parser.add_argument('--loss', default='focal_tversky')
    parser.add_argument('--f-beta', type=float, default=0.75)
    parser.add_argument('--precision-floor', type=float, default=DEFAULT_PRECISION_FLOOR)
    parser.add_argument('--postprocess-recall-floor', type=float, default=DEFAULT_POSTPROCESS_RECALL_FLOOR)
    parser.add_argument('--postprocess-min-component-area-px', type=int, default=32)
    parser.add_argument('--postprocess-opening-size-px', type=int, default=0)
    parser.add_argument('--threshold-grid', default='0.990,0.991,0.992,0.993,0.994,0.995,0.996,0.997')
    parser.add_argument('--threshold', type=float, help='Threshold for error diagnostics; defaults to selected threshold when omitted')
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--diagnostics', action='store_true')
    parser.add_argument('--scene-blended', action='store_true')
    parser.add_argument('--max-components', type=int, default=10)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    request = build_request(args)
    if args.diagnostics:
        result = build_sar_validation_error_diagnostics(
            request,
            artifact_root=args.output_root,
            device=args.device,
            max_components=args.max_components,
        )
    elif args.scene_blended:
        request['evaluation_mode'] = 'scene_blended'
        result = evaluate_sar_checkpoint_scene_blended(
            request,
            artifact_root=args.output_root,
            device=args.device,
        )
    else:
        result = evaluate_sar_checkpoint(
            request,
            artifact_root=args.output_root,
            device=args.device,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get('status') in {'ok', 'completed_with_validation_gate_failure'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
