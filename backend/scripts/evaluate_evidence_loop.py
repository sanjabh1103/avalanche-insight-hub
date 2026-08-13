"""Export a temporal baseline-vs-verification evidence-loop report."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.common.evidence_loop_evaluation import _stable_hash, evaluate_paired


def _load_records(path: Path, key: str) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    value: Any = payload.get(key) if isinstance(payload, dict) else payload
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f'{path} must contain a list of {key} records')
    return [dict(item) for item in value]


def _blocked_report(reason: str, predictions: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        'schema_version': 'evidence-loop-report/v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'blocked_reason': reason,
        'prediction_source_hash': _stable_hash(predictions),
        'event_source_hash': _stable_hash(events),
        'n_predictions': len(predictions),
        'n_events': len(events),
        'evaluation_only': True,
        'can_promote_model': False,
    }


def _validate_inputs(predictions: list[dict[str, Any]], events: list[dict[str, Any]]) -> str | None:
    if not predictions:
        return 'no_predictions'
    if not events:
        return 'insufficient_independent_labels'
    required_prediction_fields = ('forecast_date', 'lat', 'lng', 'probability', 'evidence_available')
    if any(any(field not in prediction for field in required_prediction_fields) for prediction in predictions):
        return 'prediction_schema_incomplete'
    for prediction in predictions:
        if prediction.get('evidence_available') not in (True, False):
            return 'prediction_evidence_flag_invalid'
        if any(not isinstance(prediction.get(field), (int, float)) or not math.isfinite(float(prediction[field]))
               for field in ('lat', 'lng', 'probability')):
            return 'prediction_numeric_field_invalid'
    required_event_fields = ('timestamp', 'location', 'source_identifier', 'source_hash')
    if any(any(field not in event for field in required_event_fields) for event in events):
        return 'independent_event_lineage_incomplete'
    if any(
        not isinstance(event.get('source_hash'), str)
        or re.fullmatch(r'[0-9a-f]{64}', event['source_hash'].lower()) is None
        for event in events
    ):
        return 'independent_event_source_hash_invalid'
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Export an evaluation-only temporal baseline-vs-evidence-gated report.',
    )
    parser.add_argument('--predictions', required=True, help='JSON list or {"predictions": [...]} input.')
    parser.add_argument('--events', required=True, help='JSON list or {"events": [...]} independent labels input.')
    parser.add_argument('--output', required=True, help='Destination JSON report.')
    parser.add_argument('--match-radius-km', type=float, default=15.0)
    parser.add_argument('--n-splits', type=int, default=3)
    parser.add_argument('--threshold', type=float, default=0.5)
    args = parser.parse_args(argv)

    predictions = _load_records(Path(args.predictions), 'predictions')
    events = _load_records(Path(args.events), 'events')
    blocked_reason = _validate_inputs(predictions, events)
    report = (
        _blocked_report(blocked_reason, predictions, events)
        if blocked_reason
        else evaluate_paired(
            predictions,
            events,
            match_radius_km=args.match_radius_km,
            n_splits=args.n_splits,
            threshold=args.threshold,
        )
    )
    report['schema_version'] = 'evidence-loop-report/v1'
    report['can_promote_model'] = False
    report['evaluation_only'] = True
    output = Path(args.output)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({
        'output': str(output),
        'blocked_reason': report.get('blocked_reason'),
        'can_promote_model': report['can_promote_model'],
        'n_predictions': report.get('n_predictions', 0),
        'n_events': report.get('n_events', 0),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
