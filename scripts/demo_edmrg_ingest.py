#!/usr/bin/env python3
"""Demo: eDMRG adapter ingesting synthetic manned + AWS telemetry.

Generates synthetic eDMRG CSV data for both manned (3h) and AWS (1h) cadences,
parses with field mapping, verifies records, and converts to weather sample
dicts compatible with the inference pipeline.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

from backend.common.edmrg_adapter import (
    EdmrgRecord,
    load_field_mapping,
    parse_edmrg_csv,
    parse_edmrg_json,
    edmrg_to_weather_samples,
)


def make_manned_csv() -> str:
    """Generate synthetic manned 3-hour observatory CSV."""
    rows = []
    base_time = datetime(2026, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
    for i in range(8):  # 24 hours, 3h cadence
        ts = base_time + timedelta(hours=i * 3)
        rows.append(
            f'STN001,{ts.strftime("%Y-%m-%d %H:%M:%S")},'
            f'{-5.0 + i * 0.5:.1f},'   # air_temp
            f'{120 + i * 2:.0f},'       # snow_depth
            f'{5 + i:.0f},'             # new_snow_24h
            f'{8.5:.1f},'               # wind_speed
            f'{270:.0f},'               # wind_dir
            f'{2.3:.1f}'                # precip_24h
        )
    header = 'station_id,obs_time,air_temp,snow_depth,new_snow_24h,wind_speed,wind_dir,precip_24h'
    return header + '\n' + '\n'.join(rows)


def make_aws_json() -> list[dict]:
    """Generate synthetic AWS 1-hour JSON data."""
    base_time = datetime(2026, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
    records = []
    for i in range(24):  # 24 hours, 1h cadence
        ts = base_time + timedelta(hours=i)
        records.append({
            'station_id': 'AWS002',
            'timestamp': ts.strftime('%Y-%m-%dT%H:%M:%S+00:00'),
            'temp_2m': -8.0 + i * 0.3,
            'snow_depth': 85 + i,
            'wind_speed_10m': 12.0 + (i % 3),
            'wind_dir_10m': 180 + (i * 10) % 360,
            'precip_1h': 0.5 + (i % 4) * 0.3,
        })
    return records


def main() -> int:
    print('=== eDMRG Adapter Demo ===\n')

    # Load field mapping
    mapping = load_field_mapping()
    print(f'Loaded field mapping: {list(mapping.keys())}')

    # Parse manned 3h CSV
    print('\n--- Manned Observatory (3h cadence) ---\n')
    csv_data = make_manned_csv()
    manned_records = parse_edmrg_csv(csv_data, mapping['manned_3h'], 'manned_3h')
    print(f'Parsed {len(manned_records)} manned records')
    if len(manned_records) != 8:
        print(f'FAIL: Expected 8 records, got {len(manned_records)}')
        return 1
    print('PASS: 8 manned records parsed')

    r0 = manned_records[0]
    print(f'\nFirst record:')
    print(f'  station_id: {r0.station_id}')
    print(f'  timestamp: {r0.timestamp}')
    print(f'  cadence: {r0.cadence}')
    print(f'  fields: {r0.fields}')

    # Verify field mapping worked
    if 'temperature_c' not in r0.fields:
        print('FAIL: temperature_c not found in mapped fields')
        return 1
    print(f'  temperature_c: {r0.fields["temperature_c"]} (mapped from air_temp)')
    print('PASS: Field mapping verified')

    # Parse AWS 1h JSON
    print('\n--- Automatic Weather Station (1h cadence) ---\n')
    aws_data = make_aws_json()
    aws_records = parse_edmrg_json(aws_data, mapping['aws_1h'], 'aws_1h')
    print(f'Parsed {len(aws_records)} AWS records')
    if len(aws_records) != 24:
        print(f'FAIL: Expected 24 records, got {len(aws_records)}')
        return 1
    print('PASS: 24 AWS records parsed')

    a0 = aws_records[0]
    print(f'\nFirst AWS record:')
    print(f'  station_id: {a0.station_id}')
    print(f'  timestamp: {a0.timestamp}')
    print(f'  cadence: {a0.cadence}')
    print(f'  fields: {a0.fields}')

    # Convert to weather samples
    print('\n--- Weather Sample Conversion ---\n')
    all_records = manned_records + aws_records
    samples = edmrg_to_weather_samples(all_records)
    print(f'Converted {len(all_records)} records to {len(samples)} weather samples')
    if len(samples) != 32:
        print(f'FAIL: Expected 32 samples, got {len(samples)}')
        return 1
    print('PASS: All records converted to weather samples')

    s0 = samples[0]
    print(f'\nFirst weather sample:')
    print(f'  station_id: {s0.get("station_id")}')
    print(f'  timestamp: {s0.get("timestamp")}')
    print(f'  temperature_c: {s0.get("temperature_c")}')
    print(f'  snow_depth_cm: {s0.get("snow_depth_cm")}')
    print(f'  wind_speed_ms: {s0.get("wind_speed_ms")}')

    # Adversarial: empty data
    print('\n=== Adversarial Check: Empty Data ===\n')
    empty_records = parse_edmrg_csv('', mapping['manned_3h'], 'manned_3h')
    print(f'Empty CSV parsed: {len(empty_records)} records')
    if empty_records:
        print('FAIL: Empty CSV should produce 0 records')
        return 1
    print('PASS: Empty CSV produces 0 records')

    # Adversarial: malformed timestamp
    print('\n=== Adversarial Check: Malformed Timestamp ===\n')
    bad_csv = 'station_id,obs_time,air_temp,snow_depth\nSTN001,NOT_A_DATE,-5.0,120'
    bad_records = parse_edmrg_csv(bad_csv, mapping['manned_3h'], 'manned_3h')
    print(f'Malformed timestamp CSV parsed: {len(bad_records)} records')
    if bad_records:
        print('FAIL: Malformed timestamp should produce 0 records')
        return 1
    print('PASS: Malformed timestamp row skipped')

    print('\n=== Demo Complete ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
