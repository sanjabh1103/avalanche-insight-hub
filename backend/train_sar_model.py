from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.common.config import load_settings
from backend.sar_unet_training import build_cli_request, train_sar_unet


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    settings = load_settings()
    parser = argparse.ArgumentParser(description='Train a SAR Swin U-Net candidate on a SAR training manifest')
    parser.add_argument('--training-manifest', type=Path, required=True)
    parser.add_argument('--artifact-root', type=Path, default=settings.artifact_root)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--model-family', default='swinunet_tiny_diff')
    parser.add_argument('--patch-size', type=int, default=128)
    parser.add_argument('--stride', type=int, default=64)
    parser.add_argument('--epochs', type=int, default=8)
    parser.add_argument('--batch-size', type=int, default=8)
    parser.add_argument('--learning-rate', type=float, default=1e-4)
    parser.add_argument('--patience', type=int, default=4)
    parser.add_argument('--loss', default='focal_tversky')
    parser.add_argument('--candidate-model-version')
    parser.add_argument('--initial-checkpoint-path', type=Path)
    parser.add_argument('--materialized-dataset-root', type=Path)
    parser.add_argument('--source-key')
    parser.add_argument('--license-review-id')
    parser.add_argument('--export-validation-prediction-artifact', action='store_true')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--f-beta', type=float, default=1.5)
    parser.add_argument('--precision-floor', type=float, default=0.05)
    parser.add_argument('--focal-tversky-alpha', type=float)
    parser.add_argument('--focal-tversky-beta', type=float)
    parser.add_argument('--focal-tversky-gamma', type=float)
    parser.add_argument('--postprocess-min-component-area-px', type=int)
    parser.add_argument('--postprocess-opening-size-px', type=int)
    parser.add_argument('--postprocess-recall-floor', type=float, default=0.50)
    parser.add_argument('--postprocess-apply-to-threshold-selection', action='store_true')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    request = build_cli_request(args)
    result = train_sar_unet(
        request,
        artifact_root=args.artifact_root,
        device=args.device,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
