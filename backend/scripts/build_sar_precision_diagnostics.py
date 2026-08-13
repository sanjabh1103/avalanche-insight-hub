from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from backend.common.sar_precision_diagnostics import build_sar_precision_diagnostics


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build precision diagnostics from SAR training metrics.')
    parser.add_argument('--metrics', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--precision-floor', type=float, default=0.60)
    parser.add_argument('--recall-floor', type=float, default=0.50)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    metrics_payload = json.loads(args.metrics.read_text(encoding='utf-8'))
    diagnostics = build_sar_precision_diagnostics(
        metrics_payload,
        source_path=args.metrics,
        precision_floor=args.precision_floor,
        recall_floor=args.recall_floor,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(diagnostics, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(diagnostics, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
