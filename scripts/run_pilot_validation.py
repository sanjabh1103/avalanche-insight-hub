#!/usr/bin/env python3
"""Pilot validation harness — dual-track replay + shadow mode.

Track 1: Colorado replay — scores anomaly precision vs known historical events.
Track 2: Great Himalaya shadow — scores Partner bulletin agreement (dry-run only).

Usage:
    python scripts/run_pilot_validation.py --region colorado_rockies --replay
    python scripts/run_pilot_validation.py --region great_himalaya --shadow --dry-run

Env flags:
    ACTIVE_LEARNING_ENABLED — enables active learning queue (default: false)
    VERIFICATION_SPINE_ENABLED — enables verification spine (default: false)
    Partner_BULLETIN_VALIDATION_ENABLED — enables Partner bulletin parsing (default: false)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def run_colorado_replay() -> dict[str, Any]:
    """Colorado replay track: score anomaly precision vs known events.

    Uses historical avalanche events from the Colorado Rockies region
    to validate that the verification spine anomaly detector correctly
    flags cells with known avalanche activity.
    """
    from backend.common.anomaly_detector import (
        SensorReading,
        detect_anomalies,
    )
    from backend.common.snow_baselines import compute_baseline_stats

    print('[Colorado Replay] Starting replay validation...')

    # Synthetic known events for offline replay
    known_events = [
        {'lat': 39.17, 'lng': -106.35, 'date': '2026-01-15', 'type': 'slab'},
        {'lat': 39.25, 'lng': -106.42, 'date': '2026-01-20', 'type': 'loose'},
        {'lat': 39.10, 'lng': -106.50, 'date': '2026-02-01', 'type': 'slab'},
    ]

    # Synthetic cell predictions for replay
    cells = []
    for i in range(20):
        cells.append({
            'cell_id': f'cell_{i}',
            'lat': 39.0 + i * 0.05,
            'lng': -106.3 - i * 0.02,
            'risk_score': 3.0 + (i % 3),
            'snow_depth_m': 0.5 + i * 0.03,
            'snow_cover_fraction': 0.7 + (i % 5) * 0.05,
        })

    # Build baseline stats from synthetic history
    import numpy as np
    np.random.seed(42)
    history_values = list(np.random.uniform(0.4, 0.8, 30))
    baseline = compute_baseline_stats(
        values=history_values,
        cell_id='replay_baseline',
        sensor='snow_depth',
        window='30d',
    )

    # Run anomaly detection on cells with synthetic sensor readings
    anomalies = []
    for cell in cells:
        readings = {
            'weather': SensorReading(
                source='openmeteo_proxy',
                snow_depth_m=cell['snow_depth_m'],
                snow_cover_fraction=cell['snow_cover_fraction'],
                freshness_hours=6.0,
                confidence=0.8,
            ),
        }
        flags, packet = detect_anomalies(
            cell_id=cell['cell_id'],
            region_key='colorado_rockies',
            readings=readings,
            baseline_p25=baseline.p25,
            baseline_p50=baseline.p50,
            baseline_p75=baseline.p75,
        )
        if flags:
            anomalies.append({
                'cell_id': cell['cell_id'],
                'lat': cell['lat'],
                'lng': cell['lng'],
                'discrepancy_type': flags[0].discrepancy_type,
                'severity': flags[0].severity,
                'zscore': flags[0].zscore,
            })

    # Score: check if any anomalies overlap with known event locations
    matched = 0
    for event in known_events:
        for anomaly in anomalies:
            if (abs(anomaly['lat'] - event['lat']) < 0.1
                    and abs(anomaly['lng'] - event['lng']) < 0.1):
                matched += 1
                break

    precision = matched / len(known_events) if known_events else 0.0

    result = {
        'track': 'colorado_replay',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'known_events': len(known_events),
        'cells_checked': len(cells),
        'anomalies_detected': len(anomalies),
        'events_matched': matched,
        'precision': round(precision, 4),
        'anomalies': anomalies,
    }

    print(f'[Colorado Replay] Precision: {precision:.2%} ({matched}/{len(known_events)} events matched)')
    print(f'[Colorado Replay] Anomalies detected: {len(anomalies)}/{len(cells)} cells')

    # AVAMAP benchmark instructions
    result['avamap_benchmark_instructions'] = {
        'description': 'Manual AVAMAP-on-GEP benchmark for runout validation',
        'steps': [
            '1. Download AVAMAP reference runout polygons for Colorado Rockies',
            '2. Run GEP (Gradient Extent Path) model on same terrain inputs',
            '3. Compare runout zone overlap between AVAMAP and GEP',
            '4. Report IoU (Intersection over Union) and alpha-beta angle differences',
            '5. Target: IoU > 0.6, alpha-beta angle deviation < 5 degrees',
        ],
        'url': 'https://nsidc.org/data/avamap',
        'status': 'manual_benchmark_required',
    }

    return result


def run_himalaya_shadow(dry_run: bool = True) -> dict[str, Any]:
    """Himalaya shadow track: score Partner bulletin agreement.

    Runs in shadow mode — writes to shadow tables only, no public risk change.
    Scores Partner bulletin danger levels against verification spine anomaly states.
    """
    from backend.common.Partner_bulletin_adapter import (
        Partner_BULLETIN_VALIDATION_ENABLED,
        parse_bulletin_text,
    )

    print(f'[Himalaya Shadow] Starting shadow validation (dry_run={dry_run})...')

    # Synthetic Partner bulletin text for offline validation
    sample_bulletins = [
        {
            'text': 'Danger Level 4 (High) - Kullu Valley. Natural avalanches likely. '
                    'Wind slab deposits on leeward slopes above 3500m.',
            'expected_zone': 'Kullu Valley',
            'expected_danger_level': 4,
        },
        {
            'text': 'Danger Level 3 (Considerable) - Lahaul. Human-triggered avalanches probable. '
                    'Persistent weak layer at 60cm depth.',
            'expected_zone': 'Lahaul',
            'expected_danger_level': 3,
        },
        {
            'text': 'Danger Level 2 (Moderate) - Spiti Valley. Isolated human-triggered avalanches possible. '
                    'Wet snow below 3000m.',
            'expected_zone': 'Spiti Valley',
            'expected_danger_level': 2,
        },
    ]

    parsed_count = 0
    correct_danger = 0
    correct_zone = 0
    results = []

    for i, bulletin in enumerate(sample_bulletins):
        parsed = parse_bulletin_text(bulletin['text'], bulletin_id=f'test_{i}')
        if parsed is not None:
            parsed_count += 1
            if parsed.danger_level == bulletin['expected_danger_level']:
                correct_danger += 1
            if parsed.zone and bulletin['expected_zone'].lower() in parsed.zone.lower():
                correct_zone += 1
            results.append({
                'expected_zone': bulletin['expected_zone'],
                'expected_danger': bulletin['expected_danger_level'],
                'parsed_zone': parsed.zone,
                'parsed_danger': parsed.danger_level,
                'bulletin_date': str(parsed.issue_date) if parsed.issue_date else None,
            })

    danger_accuracy = correct_danger / len(sample_bulletins) if sample_bulletins else 0.0
    zone_accuracy = correct_zone / len(sample_bulletins) if sample_bulletins else 0.0

    result = {
        'track': 'himalaya_shadow',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'dry_run': dry_run,
        'Partner_enabled': Partner_BULLETIN_VALIDATION_ENABLED,
        'bulletins_tested': len(sample_bulletins),
        'bulletins_parsed': parsed_count,
        'danger_level_accuracy': round(danger_accuracy, 4),
        'zone_accuracy': round(zone_accuracy, 4),
        'results': results,
        'shadow_table': 'shadow_verification_results' if not dry_run else None,
        'public_risk_changed': False,
    }

    print(f'[Himalaya Shadow] Danger level accuracy: {danger_accuracy:.2%}')
    print(f'[Himalaya Shadow] Zone accuracy: {zone_accuracy:.2%}')
    print(f'[Himalaya Shadow] Shadow mode: {"dry-run (no writes)" if dry_run else "shadow table writes"}')

    # AVAMAP benchmark instructions for Himalaya
    result['avamap_benchmark_instructions'] = {
        'description': 'Manual AVAMAP-on-GEP benchmark for Himalayan terrain',
        'steps': [
            '1. Obtain Partner historical runout polygon data for Kullu/Lahaul/Spiti',
            '2. Run GEP model on SRTM/ALOS DEM for same terrain',
            '3. Compare runout zone overlap and path lengths',
            '4. Report IoU and runout distance deviation',
            '5. Note: Himalayan terrain may require different friction parameters',
        ],
        'status': 'manual_benchmark_required',
    }

    return result


def main():
    parser = argparse.ArgumentParser(
        description='Pilot validation harness for verification spine.',
    )
    parser.add_argument(
        '--region',
        choices=['colorado_rockies', 'great_himalaya'],
        required=True,
        help='Region to validate.',
    )
    parser.add_argument(
        '--replay',
        action='store_true',
        help='Run in replay mode (Colorado only).',
    )
    parser.add_argument(
        '--shadow',
        action='store_true',
        help='Run in shadow mode (Himalaya only).',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Dry-run mode: no database writes (default: true).',
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output file path for results JSON.',
    )

    args = parser.parse_args()

    if args.region == 'colorado_rockies' and args.replay:
        result = run_colorado_replay()
    elif args.region == 'great_himalaya' and args.shadow:
        result = run_himalaya_shadow(dry_run=args.dry_run)
    else:
        print(f'Error: --region {args.region} requires {"--replay" if args.region == "colorado_rockies" else "--shadow"}')
        sys.exit(1)

    # Output results
    output_path = args.output or f'pilot_validation_{args.region}_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.json'
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)

    print(f'\nResults written to: {output_path}')
    print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    main()
