#!/usr/bin/env python3
"""Run the evidence-gated anomaly detector on a JSON observation bundle."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.common.anomaly_detector import SensorReading, detect_anomalies
from backend.common.supabase_io import has_supabase_credentials, rest_insert
from backend.common.verification_contracts import SAFETY_DISCLAIMER, VERIFICATION_SPINE_ENABLED


READING_FIELDS = (
    'snow_cover_fraction',
    'snow_depth_m',
    'wet_snow_fraction',
    'loading_rate_24h',
    'freshness_hours',
    'confidence',
)


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [record for record in payload if isinstance(record, dict)]
    if isinstance(payload, dict) and isinstance(payload.get('cells'), list):
        return [record for record in payload['cells'] if isinstance(record, dict)]
    return []


def _run_records(records: list[dict[str, Any]], run_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    packets = []
    anomaly_rows = []
    for record in records:
        cell_id = str(record.get('cell_id') or '').strip()
        region_key = str(record.get('region_key') or 'unknown').strip()
        if not cell_id:
            continue
        raw_readings = record.get('readings') if isinstance(record.get('readings'), dict) else {}
        readings = {}
        for source, raw in raw_readings.items():
            if not isinstance(raw, dict):
                continue
            values = {field: raw.get(field) for field in READING_FIELDS if raw.get(field) is not None}
            readings[str(source)] = SensorReading(source=str(source), **values)
        flags, packet = detect_anomalies(
            cell_id=cell_id,
            region_key=region_key,
            readings=readings,
            baseline_p25=record.get('baseline_p25'),
            baseline_p50=record.get('baseline_p50'),
            baseline_p75=record.get('baseline_p75'),
            weather_snowfall_cm=record.get('weather_snowfall_cm'),
            physics_method=str(record.get('physics_method') or ''),
        )
        packets.append(packet.to_dict())
        for flag in flags:
            flag_row = flag.to_dict()
            attribution = flag_row.get('attribution') if isinstance(flag_row.get('attribution'), dict) else {}
            anomaly_rows.append({
                'region_key': region_key,
                'run_id': run_id,
                'cell_id': cell_id,
                'discrepancy_type': flag_row['discrepancy_type'],
                'severity': flag_row['severity'],
                'zscore': flag_row.get('zscore'),
                'sources': flag_row.get('sources', []),
                'attribution_bucket': attribution.get('bucket', 'unattributed'),
                'attribution_confidence': attribution.get('confidence', 0.0),
                'review_state': 'pending',
            })
    return packets, anomaly_rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Run verification-spine anomaly checks')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--run-id', default=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)

    if args.dry_run or args.input is None:
        print(json.dumps({
            'status': 'dry_run' if args.dry_run else 'input_required',
            'verification_spine_enabled': bool(VERIFICATION_SPINE_ENABLED),
            'expected_input': {'cells': [{'cell_id': 'c1', 'readings': {}}]},
            'disclaimer': SAFETY_DISCLAIMER,
        }, indent=2))
        return 0

    try:
        payload = json.loads(args.input.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        print(f'[run_anomaly_check] input read failed: {exc}', file=sys.stderr)
        return 1
    packets, anomaly_rows = _run_records(_records(payload), args.run_id)
    persisted = False
    if anomaly_rows and has_supabase_credentials():
        try:
            rest_insert('verification_anomalies', anomaly_rows, returning='minimal')
            persisted = True
        except Exception as exc:
            print(f'[run_anomaly_check] anomaly persistence failed: {exc}', file=sys.stderr)
    print(json.dumps({
        'status': 'completed',
        'run_id': args.run_id,
        'packet_count': len(packets),
        'anomaly_count': len(anomaly_rows),
        'packets': packets,
        'persisted': persisted,
        'disclaimer': SAFETY_DISCLAIMER,
    }, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
