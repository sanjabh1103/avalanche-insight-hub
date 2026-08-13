from __future__ import annotations

import math
import os
import sys
import time as _time
from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.common.features import FEATURE_COLUMNS, build_region_grid, generate_training_frame
from backend.common.label_governance import GOVERNANCE_VERSION, derive_label_governance
from backend.common.real_features import (
    build_real_feature_row,
    extract_cell_terrain,
    fetch_historical_weather_profile,
    select_hourly_weather_sample,
)
from backend.common.regions import Region, load_regions, repo_root
from backend.common.snowpack_proxy import SnowpackProxy, compute_region_snowpack_proxy
from backend.common.supabase_io import has_supabase_credentials, rest_get
from backend.common.terrain_diagnostics import build_terrain_loss_report, classify_terrain_failure
from backend.common.open_source_label_lane import (
    build_open_source_label_manifest,
    load_open_source_label_events,
)


NEGATIVES_PER_POSITIVE = 3
NEGATIVE_TRAINING_WEIGHT = NEGATIVES_PER_POSITIVE / (NEGATIVES_PER_POSITIVE + 1)
NEGATIVE_DISTANCE_M = 5000.0
NEGATIVE_TIME_WINDOW_HOURS = 24.0
NEGATIVE_SLOPE_MIN = 20.0
NEGATIVE_SLOPE_MAX = 65.0
GEE_SAR_CORE_PROVENANCE_STATUS = 'approved_core'

DEFAULT_DEM_DIR = repo_root() / 'backend' / 'data' / 'dem'


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6_371_000.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _parse_ewkb_hex(value: str) -> tuple[float, float] | None:
    """Parse PostGIS EWKB hex format (e.g., '0101000020E6100000...')."""
    try:
        import struct
        # Hex decode
        data = bytes.fromhex(value)
        # Minimum size: 1 byte order + 4 bytes type + 4 bytes SRID + 16 bytes coords = 25
        if len(data) < 25:
            return None
        # Byte order: 01 = little endian, 00 = big endian
        little_endian = data[0] == 1
        endian = '<' if little_endian else '>'
        # Geometry type at offset 1 (4 bytes)
        geom_type = struct.unpack(endian + 'I', data[1:5])[0]
        # SRID flag check (0x20000000 bit indicates SRID present)
        has_srid = (geom_type & 0x20000000) != 0
        # Mask out flags (Z, M, SRID) to get base geometry type
        base_type = geom_type & 0xFFFFFF
        if base_type != 1:  # 1 = Point
            return None
        offset = 5
        if has_srid:
            offset += 4  # Skip SRID
        # Coordinates: 2 doubles (16 bytes)
        if len(data) < offset + 16:
            return None
        lng, lat = struct.unpack(endian + 'dd', data[offset:offset + 16])
        return float(lat), float(lng)
    except Exception:
        return None


def parse_point_wkt(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, str):
        return None
    # Try WKT format first
    if 'POINT(' in value:
        inner = value[value.index('POINT(') + 6:].rstrip(')')
        parts = inner.split()
        if len(parts) == 2:
            try:
                lng = float(parts[0])
                lat = float(parts[1])
                return lat, lng
            except ValueError:
                pass
    # Try EWKB hex format (starts with '01' and is long hex string)
    if len(value) >= 50 and all(c in '0123456789abcdefABCDEF' for c in value[:10]):
        return _parse_ewkb_hex(value)
    return None


def match_region(lat: float, lng: float, regions: list[Region]) -> Region | None:
    for region in regions:
        lat_min, lng_min, lat_max, lng_max = region.bbox
        if lat_min <= lat <= lat_max and lng_min <= lng <= lng_max:
            return region
    return None


def _dem_root() -> Path:
    raw = str(os.getenv('DEM_ROOT') or os.getenv('DEM_DIR') or '').strip()
    if not raw:
        return DEFAULT_DEM_DIR
    return Path(raw).expanduser()


def _dem_path(region_key: str) -> Path:
    return _dem_root() / f'{region_key}.tif'


@lru_cache(maxsize=4096)
def _cached_historical_weather_profile(lat_round: float, lng_round: float, timestamp_iso: str) -> dict[str, Any]:
    return fetch_historical_weather_profile(
        lat=lat_round,
        lng=lng_round,
        timestamp=datetime.fromisoformat(timestamp_iso.replace('Z', '+00:00')),
    )


@lru_cache(maxsize=2048)
def _cached_region_day_weather_profile(
    region_key: str,
    region_center_lat: float,
    region_center_lng: float,
    day_iso: str,
) -> dict[str, Any]:
    day = datetime.fromisoformat(day_iso).replace(tzinfo=timezone.utc)
    midday = day.replace(hour=12, minute=0, second=0, microsecond=0)
    return _cached_historical_weather_profile(region_center_lat, region_center_lng, midday.isoformat())


def _event_timestamp(value: Any) -> datetime:
    """Parse an event timestamp as an aware UTC datetime.

    Supabase rows normally arrive with a ``Z`` suffix, but older/backfilled
    rows can be timezone-naive. Keeping both positive and negative rows on the
    same UTC-aware representation prevents cold-start concatenation failures.
    """
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _training_season_id(timestamp: datetime, region: Region) -> str:
    """Return a region-aware season identifier for terrain diagnostics."""

    try:
        season_start_month = int(str(region.season_start or '07-01').split('-', 1)[0])
    except (TypeError, ValueError):
        season_start_month = 7
    season_year = timestamp.year if timestamp.month >= season_start_month else timestamp.year - 1
    return f'{season_year}-{season_year + 1}'


def _training_snowpack_proxy_mode() -> str:
    mode = str(os.getenv('TRAINING_SNOWPACK_PROXY_MODE', 'regional_day') or 'regional_day').strip().lower()
    if mode not in {'cell', 'regional_day'}:
        raise ValueError(
            f'Unsupported TRAINING_SNOWPACK_PROXY_MODE={mode!r}; '
            "expected 'cell' or 'regional_day'"
        )
    return mode


def _gee_sar_core_provenance_eligible(row: dict[str, Any]) -> bool:
    """Keep unproven internal SAR rows out of the core database lane."""
    if str(row.get('source') or '').strip().lower() != 'gee_sar':
        return True
    scene_ids = row.get('source_scene_ids')
    features = row.get('features') if isinstance(row.get('features'), dict) else {}
    if not isinstance(scene_ids, list) or not any(str(value).strip() for value in scene_ids):
        for key in ('source_scene_ids', 'sar_scene_ids', 'scene_ids'):
            candidate = features.get(key)
            if isinstance(candidate, list) and any(str(value).strip() for value in candidate):
                scene_ids = candidate
                break
    if not isinstance(scene_ids, list) or not any(str(value).strip() for value in scene_ids):
        return False
    provenance_status = str(
        row.get('source_provenance_review_status')
        or features.get('source_provenance_review_status')
        or ''
    ).strip().lower()
    return provenance_status == GEE_SAR_CORE_PROVENANCE_STATUS


def _prewarm_training_snowpack_proxies(
    region_day_pairs: set[tuple[str, str]],
    regions: list[Region],
) -> tuple[dict[tuple[str, str], SnowpackProxy], dict[str, Any]]:
    """Resolve bounded snowpack proxies for training without per-row I/O.

    The regional-day mode intentionally reuses one seasonal proxy for all
    cells from the same region and event day. It preserves the event-time
    boundary while matching the existing regional inference strategy. The
    cell mode remains available for high-fidelity local runs, but is not the
    safe default because it performs one seasonal request per feature row.
    """
    mode = _training_snowpack_proxy_mode()
    stats: dict[str, Any] = {
        'mode': mode,
        'requested_pairs': len(region_day_pairs),
        'proxy_calls': 0,
        'remote_fetches': 0,
        'fallbacks': 0,
        'skipped_pairs': 0,
    }
    if mode == 'cell' or not region_day_pairs:
        return {}, stats

    region_by_key = {region.key: region for region in regions}
    proxy_map: dict[tuple[str, str], SnowpackProxy] = {}
    started_at = _time.perf_counter()
    print(
        f'[training_dataset] Pre-warming regional snowpack proxies for '
        f'{len(region_day_pairs)} unique (region, day) pairs',
        file=sys.stderr,
    )
    for region_key, day_iso in sorted(region_day_pairs):
        region = region_by_key.get(region_key)
        if region is None:
            stats['skipped_pairs'] += 1
            continue
        try:
            as_of = datetime.fromisoformat(day_iso).replace(
                hour=12,
                minute=0,
                second=0,
                microsecond=0,
                tzinfo=timezone.utc,
            )
            stats['proxy_calls'] += 1
            proxy = compute_region_snowpack_proxy(
                center_lat=float(region.center[0]),
                center_lng=float(region.center[1]),
                as_of=as_of,
                cells=[],
            )
        except Exception as exc:
            # Keep training bounded and deterministic even if a future proxy
            # implementation raises before reaching its normal fallback.
            print(
                f'[training_dataset] Regional snowpack pre-warm failed for '
                f'({region_key}, {day_iso}): {exc}; using deterministic fallback',
                file=sys.stderr,
            )
            proxy = SnowpackProxy(
                estimated_shear_strength=3.0,
                snow_settlement_index=0.3,
                season_start=day_iso,
                method='synthetic_fallback_empty',
            )
        if proxy.method.startswith('synthetic_fallback'):
            stats['fallbacks'] += 1
        else:
            stats['remote_fetches'] += 1
        proxy_map[(region_key, day_iso)] = proxy

    stats['elapsed_seconds'] = round(_time.perf_counter() - started_at, 3)
    print(
        f'[training_dataset] Regional snowpack pre-warm done in '
        f"{stats['elapsed_seconds']:.1f}s; calls={stats['proxy_calls']}, "
        f"remote_fetches={stats['remote_fetches']}, "
        f"fallbacks={stats['fallbacks']}",
        file=sys.stderr,
    )
    return proxy_map, stats


def fetch_training_events(
    hazard_type: str = 'avalanche',
    region_keys: list[str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if has_supabase_credentials():
        # Query relaxed: backfilled events may lack verification_status/label_role.
        # Post-query filtering handles exclusion logic for rows that have these fields.
        database_rows = rest_get(
            'avalanche_events_decayed',
            params={
                'select': 'id,location,timestamp,severity,source,fusion_source,training_eligible,training_eligible_reason,label_role,verification_status,elevation_m,topo_profile,features,confidence,label_confidence,training_weight,source_model,source_scene_ids,geometry_type,mask_asset_ref,confidence_decayed,governance_version,governed_at,label_source,review_basis,nowcast_ref,observer_ref,regime,timing',
                'hazard_type': f'eq.{hazard_type}',
                'training_eligible': 'eq.true',
                'order': 'timestamp.asc',
            },
        ) or []
        rows.extend(row for row in database_rows if _gee_sar_core_provenance_eligible(row))

    # The open-source lane is opt-in and local-snapshot based.  It remains
    # inert for normal jobs, and staging records cannot enter this training
    # frame unless shadow_training plus a license review was explicitly set.
    open_snapshot = os.getenv('OPEN_SOURCE_LABEL_SNAPSHOT', '').strip()
    if open_snapshot:
        open_source_rows = load_open_source_label_events(
            open_snapshot,
            source_key=os.getenv('OPEN_SOURCE_LABEL_SOURCE_KEY', '').strip() or None,
            requested_role=os.getenv('OPEN_SOURCE_LABEL_ROLE', 'staging').strip() or 'staging',
            license_review_id=os.getenv('OPEN_SOURCE_LABEL_LICENSE_REVIEW_ID', '').strip() or None,
        )
        rows.extend(row for row in open_source_rows if row.get('training_eligible') is True)

    # Post-filter: include if verification_status is missing/null OR in allowed list
    # Note: 'unverified' covers backfilled SAR events; 'weak'/'verified'/'expert_verified' cover human-verified events
    allowed_status = {'unverified', 'weak', 'verified', 'expert_verified', None}
    filtered = [
        r for r in rows
        if r.get('verification_status') in allowed_status
        and r.get('label_role') != 'excluded'
    ]
    # Region filtering: if region_keys is provided, only keep events that fall
    # within the bounding box of one of the specified regions.
    if region_keys:
        regions = load_regions()
        selected_regions = [r for r in regions if r.key in region_keys]
        unknown = set(region_keys) - {r.key for r in selected_regions}
        if unknown:
            raise ValueError(
                f'Unknown region key(s): {sorted(unknown)}. '
                f'Available: {sorted(r.key for r in regions)}'
            )
        filtered = [
            r for r in filtered
            if (point := parse_point_wkt(r.get('location'))) is not None
            and match_region(point[0], point[1], selected_regions) is not None
        ]
    return filtered


def _sample_negatives_for_event(
    event: dict[str, Any],
    *,
    region: Region,
    positives: list[dict[str, Any]],
    rng: np.random.Generator,
    grid_size: int,
) -> list[dict[str, Any]]:
    event_timestamp = _event_timestamp(event['timestamp'])
    cells = build_region_grid(region, grid_size=grid_size)
    rng.shuffle(cells)
    negatives: list[dict[str, Any]] = []

    for cell in cells:
        if len(negatives) >= NEGATIVES_PER_POSITIVE:
            break
        lat = float(cell['lat'] + (cell['lat_end'] - cell['lat']) / 2)
        lng = float(cell['lng'] + (cell['lng_end'] - cell['lng']) / 2)

        if any(
            haversine_distance(lat, lng, positive['lat'], positive['lng']) <= NEGATIVE_DISTANCE_M
            and abs((event_timestamp - positive['timestamp']).total_seconds()) <= NEGATIVE_TIME_WINDOW_HOURS * 3600
            for positive in positives
            if positive['region_key'] == region.key
        ):
            continue

        dem_path = _dem_path(region.key)
        try:
            terrain = extract_cell_terrain(str(dem_path), lat=lat, lng=lng)
        except Exception:
            continue

        slope = float(terrain['slope_angle_deg'])
        if slope < NEGATIVE_SLOPE_MIN or slope > NEGATIVE_SLOPE_MAX:
            continue

        negatives.append({
            'lat': lat,
            'lng': lng,
            'timestamp': event_timestamp,
            'terrain': terrain,
            'region_key': region.key,
            'source_event_id': event['id'],
        })

    return negatives


def build_real_training_frame(
    *,
    seed: int,
    grid_size: int,
    hazard_type: str = 'avalanche',
    region_keys: list[str] | None = None,
    samples_per_region: int | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    import sys
    dataset_started_at = _time.perf_counter()
    rows = fetch_training_events(hazard_type=hazard_type, region_keys=region_keys)
    regions = load_regions()
    rng = np.random.default_rng(seed)

    # Cap positive events per region if samples_per_region is set.
    # This bounds the training corpus before weather pre-warming and negative
    # sampling, which are the dominant time costs for large event counts.
    raw_event_count = len(rows)
    capped_event_count = raw_event_count
    selected_region_keys: list[str] = []
    unique_weather_pair_count: int | None = None
    weather_prewarm_seconds = 0.0
    if samples_per_region is not None and samples_per_region > 0 and rows:
        # Group events by region for deterministic per-region capping
        events_by_region: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            point = parse_point_wkt(row.get('location'))
            if point is None:
                continue
            region = match_region(point[0], point[1], regions)
            if region is None:
                continue
            events_by_region.setdefault(region.key, []).append(row)
        capped_rows: list[dict[str, Any]] = []
        for r_key in sorted(events_by_region.keys()):
            region_events = events_by_region[r_key]
            if len(region_events) > samples_per_region:
                # Deterministic shuffle using the same seed, then take first N
                indices = rng.permutation(len(region_events))
                region_events = [region_events[i] for i in indices[:samples_per_region]]
            capped_rows.extend(region_events)
            selected_region_keys.append(r_key)
        rows = capped_rows
        capped_event_count = len(rows)
        print(
            f'[training_dataset] Region cap: {raw_event_count} raw events → '
            f'{capped_event_count} capped (samples_per_region={samples_per_region}, '
            f'regions={selected_region_keys})',
            file=sys.stderr,
        )
    elif rows:
        selected_region_keys = sorted({
            r_key for row in rows
            if (point := parse_point_wkt(row.get('location'))) is not None
            and (region := match_region(point[0], point[1], regions)) is not None
            for r_key in [region.key]
        })

    # Pre-warm weather cache: collect unique (region_key, day_iso) pairs
    # and fetch them concurrently to avoid sequential API calls.
    _warmup_pairs: set[tuple[str, str]] = set()
    for row in rows:
        ts_raw = row.get('timestamp')
        if not ts_raw:
            continue
        point = parse_point_wkt(row.get('location'))
        if point is None:
            continue
        lat, lng = point
        region = match_region(lat, lng, regions)
        if region is None:
            continue
        try:
            day_iso = _event_timestamp(ts_raw).date().isoformat()
        except (TypeError, ValueError):
            continue
        _warmup_pairs.add((region.key, day_iso))
    if _warmup_pairs:
        import concurrent.futures
        print(f'[training_dataset] Pre-warming weather cache for {len(_warmup_pairs)} unique (region, day) pairs', file=sys.stderr)
        _warmup_start = _time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = {}
            for r_key, day_iso in _warmup_pairs:
                region = next((r for r in regions if r.key == r_key), None)
                if region is None:
                    continue
                futures[executor.submit(
                    _cached_region_day_weather_profile,
                    r_key,
                    float(region.center[0]),
                    float(region.center[1]),
                    day_iso,
                )] = (r_key, day_iso)
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    r_key, day_iso = futures[future]
                    print(f'[training_dataset] Weather pre-warm failed for ({r_key}, {day_iso}): {exc}', file=sys.stderr)
        weather_prewarm_seconds = _time.perf_counter() - _warmup_start
        print(f'[training_dataset] Weather pre-warm done in {weather_prewarm_seconds:.1f}s', file=sys.stderr)
    unique_weather_pair_count = len(_warmup_pairs)
    training_proxy_mode = _training_snowpack_proxy_mode()
    training_snowpack_proxy_map, snowpack_proxy_stats = _prewarm_training_snowpack_proxies(
        _warmup_pairs,
        regions,
    )
    missing_proxy_pairs = sorted(_warmup_pairs.difference(training_snowpack_proxy_map))
    snowpack_proxy_stats['missing_pairs'] = len(missing_proxy_pairs)
    if training_proxy_mode == 'regional_day' and missing_proxy_pairs:
        raise RuntimeError(
            'Regional-day snowpack prewarm is incomplete; refusing to fall back '
            f'to per-cell archive calls for {missing_proxy_pairs[:5]}'
        )
    fallback_count = int(snowpack_proxy_stats.get('fallbacks', 0) or 0)
    if training_proxy_mode == 'regional_day' and fallback_count:
        raise RuntimeError(
            'Regional-day snowpack prewarm returned deterministic fallback values; '
            f'refusing source-incomplete training (fallbacks={fallback_count})'
        )

    positives: list[dict[str, Any]] = []
    dataset_rows: list[dict[str, Any]] = []
    event_source_counts: Counter[str] = Counter()
    source_training_weight_sums: dict[str, float] = {}
    source_region_keys: dict[str, set[str]] = {}
    newest_timestamp_by_source: dict[str, str] = {}

    # Debug diagnostics
    debug_stats = {
        'raw_rows': len(rows),
        'no_point': 0,
        'no_timestamp': 0,
        'no_region': 0,
        'no_dem': 0,
        'terrain_failed': 0,
        'terrain_clamped': 0,
        'weather_failed': 0,
        # Terrain counters are deliberately scoped to valid positive-event
        # candidates. Negative sampling has a separate acceptance policy and
        # must not hide the positive-label terrain loss rate.
        'terrain_success': 0,
        'terrain_failure_reasons': {},
        'terrain_failure_reasons_by_region': {},
        'terrain_failure_reasons_by_source': {},
        'terrain_failure_reasons_by_season': {},
        'terrain_candidates_by_region': {},
        'terrain_candidates_by_source': {},
        'terrain_candidates_by_season': {},
        'terrain_missing_dem_by_region': {},
        'terrain_missing_dem_by_source': {},
        'terrain_missing_dem_by_season': {},
        'terrain_failed_by_region': {},
        'terrain_failed_by_source': {},
        'terrain_failed_by_season': {},
        'terrain_success_by_region': {},
        'terrain_success_by_source': {},
        'terrain_success_by_season': {},
        'assembled_ok': 0,
    }
    print(f'[training_dataset] Starting with {len(rows)} raw events', file=sys.stderr)
    _loop_start = _time.perf_counter()

    for idx, row in enumerate(rows):
        if (idx + 1) % 50 == 0:
            elapsed = _time.perf_counter() - _loop_start
            print(f'[training_dataset] Processed {idx + 1}/{len(rows)} events in {elapsed:.1f}s', file=sys.stderr)
        point = parse_point_wkt(row.get('location'))
        if point is None:
            debug_stats['no_point'] += 1
            continue
        lat, lng = point
        timestamp_raw = row.get('timestamp')
        if not timestamp_raw:
            debug_stats['no_timestamp'] += 1
            continue
        timestamp = _event_timestamp(timestamp_raw)
        region = match_region(lat, lng, regions)
        if region is None:
            debug_stats['no_region'] += 1
            continue
        source_name = str(row.get('source') or 'unknown')
        season_id = _training_season_id(timestamp, region)
        debug_stats['terrain_candidates_by_region'][region.key] = (
            debug_stats['terrain_candidates_by_region'].get(region.key, 0) + 1
        )
        debug_stats['terrain_candidates_by_source'][source_name] = (
            debug_stats['terrain_candidates_by_source'].get(source_name, 0) + 1
        )
        debug_stats['terrain_candidates_by_season'][season_id] = (
            debug_stats['terrain_candidates_by_season'].get(season_id, 0) + 1
        )

        dem_path = _dem_path(region.key)
        if not dem_path.exists():
            debug_stats['no_dem'] += 1
            debug_stats['terrain_failure_reasons']['missing_dem'] = (
                debug_stats['terrain_failure_reasons'].get('missing_dem', 0) + 1
            )
            for dimension, key in (
                ('terrain_failure_reasons_by_region', region.key),
                ('terrain_failure_reasons_by_source', source_name),
                ('terrain_failure_reasons_by_season', season_id),
            ):
                counts = debug_stats[dimension].setdefault(key, {})
                counts['missing_dem'] = counts.get('missing_dem', 0) + 1
            debug_stats['terrain_missing_dem_by_region'][region.key] = (
                debug_stats['terrain_missing_dem_by_region'].get(region.key, 0) + 1
            )
            debug_stats['terrain_missing_dem_by_source'][source_name] = (
                debug_stats['terrain_missing_dem_by_source'].get(source_name, 0) + 1
            )
            debug_stats['terrain_missing_dem_by_season'][season_id] = (
                debug_stats['terrain_missing_dem_by_season'].get(season_id, 0) + 1
            )
            continue
        try:
            terrain = extract_cell_terrain(str(dem_path), lat=lat, lng=lng)
        except Exception as exc:
            debug_stats['terrain_failed'] += 1
            reason = classify_terrain_failure(exc)
            debug_stats['terrain_failure_reasons'][reason] = (
                debug_stats['terrain_failure_reasons'].get(reason, 0) + 1
            )
            for dimension, key in (
                ('terrain_failure_reasons_by_region', region.key),
                ('terrain_failure_reasons_by_source', source_name),
                ('terrain_failure_reasons_by_season', season_id),
            ):
                counts = debug_stats[dimension].setdefault(key, {})
                counts[reason] = counts.get(reason, 0) + 1
            debug_stats['terrain_failed_by_region'][region.key] = (
                debug_stats['terrain_failed_by_region'].get(region.key, 0) + 1
            )
            debug_stats['terrain_failed_by_source'][source_name] = (
                debug_stats['terrain_failed_by_source'].get(source_name, 0) + 1
            )
            debug_stats['terrain_failed_by_season'][season_id] = (
                debug_stats['terrain_failed_by_season'].get(season_id, 0) + 1
            )
            continue
        debug_stats['terrain_success'] += 1
        debug_stats['terrain_success_by_region'][region.key] = (
            debug_stats['terrain_success_by_region'].get(region.key, 0) + 1
        )
        debug_stats['terrain_success_by_source'][source_name] = (
            debug_stats['terrain_success_by_source'].get(source_name, 0) + 1
        )
        debug_stats['terrain_success_by_season'][season_id] = (
            debug_stats['terrain_success_by_season'].get(season_id, 0) + 1
        )
        if float(terrain.get('clamped_to_bounds', 0.0) or 0.0) > 0:
            debug_stats['terrain_clamped'] += 1
        try:
            weather_profile = _cached_region_day_weather_profile(
                region.key,
                float(region.center[0]),
                float(region.center[1]),
                timestamp.date().isoformat(),
            )
            weather_sample = select_hourly_weather_sample(weather_profile, timestamp)
        except Exception as e:
            debug_stats['weather_failed'] += 1
            continue
        if not weather_sample:
            debug_stats['weather_failed'] += 1
            continue
        assembled = build_real_feature_row(
            weather_sample=weather_sample,
            terrain=terrain,
            timestamp=timestamp,
            lat=lat,
            lng=lng,
            snowpack_proxy_override=training_snowpack_proxy_map.get(
                (region.key, timestamp.date().isoformat())
            ),
        )
        topo_profile = row.get('topo_profile') if isinstance(row.get('topo_profile'), dict) else {}
        governance = derive_label_governance({
            **row,
            'metadata': topo_profile.get('metadata'),
        })
        if not governance.training_eligible:
            continue
        debug_stats['assembled_ok'] += 1
        positives.append({'lat': lat, 'lng': lng, 'timestamp': timestamp, 'region_key': region.key, 'id': row['id']})
        event_source_counts[source_name] += 1
        source_training_weight_sums[source_name] = (
            source_training_weight_sums.get(source_name, 0.0) + float(governance.training_weight)
        )
        source_region_keys.setdefault(source_name, set()).add(region.key)
        previous_latest = newest_timestamp_by_source.get(source_name)
        timestamp_iso = timestamp.isoformat()
        if previous_latest is None or timestamp_iso > previous_latest:
            newest_timestamp_by_source[source_name] = timestamp_iso
        dataset_rows.append({
            'event_id': row['id'],
            'source_event_id': row['id'],
            'event_group_id': f"event:{row['id']}",
            'sample_id': f"event:{row['id']}:positive",
            'timestamp': pd.Timestamp(timestamp),
            'region_key': region.key,
            'region_name': region.name,
            'lat': lat,
            'lng': lng,
            'label': 1,
            'severity': row.get('severity'),
            'confidence': float(row.get('confidence') or 0.0),
            'label_confidence': governance.label_confidence,
            'training_weight': governance.training_weight,
            'training_eligible_reason': row.get('training_eligible_reason'),
            'source_weight': governance.source_weight,
            'corroboration_weight': governance.corroboration_weight,
            'recency_decay': governance.recency_decay,
            'confidence_decayed': governance.confidence_decayed,
            'governance_version': str(row.get('governance_version') or GOVERNANCE_VERSION),
            'governed_at': str(row.get('governed_at') or datetime.now(timezone.utc).isoformat()),
            'label_source': str(row.get('label_source') or row.get('source') or 'unknown'),
            'review_basis': str(row.get('review_basis') or 'unverified'),
            'nowcast_ref': row.get('nowcast_ref'),
            'observer_ref': row.get('observer_ref'),
            'regime': row.get('regime'),
            'timing': row.get('timing'),
            'elevation_m_raw': float(terrain['elevation_m']),
            'slope_angle_deg_raw': float(terrain['slope_angle_deg']),
            'aspect_deg_raw': float(terrain['aspect_deg']),
            'terrain_roughness_raw': float(terrain['terrain_roughness']),
            'curvature_proxy_raw': float(terrain['curvature_proxy']),
            'temperature_2m': assembled['raw_inputs']['temperature_2m'],
            'windspeed_10m': assembled['raw_inputs']['windspeed_10m'],
            **assembled['feature_row'],
        })

    positive_build_seconds = _time.perf_counter() - _loop_start
    _neg_start = _time.perf_counter()
    for neg_idx, event in enumerate(rows):
        if (neg_idx + 1) % 50 == 0:
            elapsed = _time.perf_counter() - _neg_start
            print(f'[training_dataset] Negative sampling {neg_idx + 1}/{len(rows)} events in {elapsed:.1f}s', file=sys.stderr)
        point = parse_point_wkt(event.get('location'))
        if point is None:
            continue
        lat, lng = point
        region = match_region(lat, lng, regions)
        if region is None:
            continue
        negatives = _sample_negatives_for_event(
            event,
            region=region,
            positives=positives,
            rng=rng,
            grid_size=grid_size,
        )
        for negative in negatives:
            weather_profile = _cached_region_day_weather_profile(
                region.key,
                float(region.center[0]),
                float(region.center[1]),
                negative['timestamp'].date().isoformat(),
            )
            weather_sample = select_hourly_weather_sample(weather_profile, negative['timestamp'])
            assembled = build_real_feature_row(
                weather_sample=weather_sample,
                terrain=negative['terrain'],
                timestamp=negative['timestamp'],
                lat=negative['lat'],
                lng=negative['lng'],
                snowpack_proxy_override=training_snowpack_proxy_map.get(
                    (region.key, negative['timestamp'].date().isoformat())
                ),
            )
            dataset_rows.append({
                'event_id': None,
                'source_event_id': negative['source_event_id'],
                'event_group_id': f"event:{negative['source_event_id']}",
                'sample_id': (
                    f"event:{negative['source_event_id']}:negative:"
                    f"{negative['lat']:.8f}:{negative['lng']:.8f}:"
                    f"{negative['timestamp'].isoformat()}"
                ),
                'timestamp': pd.Timestamp(negative['timestamp']),
                'region_key': region.key,
                'region_name': region.name,
                'lat': negative['lat'],
                'lng': negative['lng'],
                'label': 0,
                'severity': None,
                'confidence': 0.0,
                'label_confidence': 1.0,
                'training_weight': NEGATIVE_TRAINING_WEIGHT,
                'training_eligible_reason': None,
                'source_weight': 1.0,
                'corroboration_weight': 1.0,
                'recency_decay': 1.0,
                'confidence_decayed': 0.0,
                'governance_version': GOVERNANCE_VERSION,
                'governed_at': datetime.now(timezone.utc).isoformat(),
                'label_source': 'synthetic_negative',
                'review_basis': 'terrain_sampling',
                'nowcast_ref': None,
                'observer_ref': None,
                'regime': None,
                'timing': None,
                'elevation_m_raw': float(negative['terrain']['elevation_m']),
                'slope_angle_deg_raw': float(negative['terrain']['slope_angle_deg']),
                'aspect_deg_raw': float(negative['terrain']['aspect_deg']),
                'terrain_roughness_raw': float(negative['terrain']['terrain_roughness']),
                'curvature_proxy_raw': float(negative['terrain']['curvature_proxy']),
                'temperature_2m': assembled['raw_inputs']['temperature_2m'],
                'windspeed_10m': assembled['raw_inputs']['windspeed_10m'],
                **assembled['feature_row'],
            })

    negative_build_seconds = _time.perf_counter() - _neg_start
    frame = pd.DataFrame(dataset_rows)
    if not frame.empty:
        frame = frame.sort_values('timestamp').reset_index(drop=True)
        frame = frame[[
            'timestamp',
            'event_id',
            'source_event_id',
            'event_group_id',
            'sample_id',
            'region_key',
            'region_name',
            'lat',
            'lng',
            'label',
            'severity',
            'confidence',
            'label_confidence',
            'training_weight',
            'training_eligible_reason',
            'source_weight',
            'corroboration_weight',
            'recency_decay',
            'confidence_decayed',
            'governance_version',
            'governed_at',
            'label_source',
            'review_basis',
            'nowcast_ref',
            'observer_ref',
            'regime',
            'timing',
            'elevation_m_raw',
            'slope_angle_deg_raw',
            'aspect_deg_raw',
            'terrain_roughness_raw',
            'curvature_proxy_raw',
            'temperature_2m',
            'windspeed_10m',
            *FEATURE_COLUMNS,
        ]]

    positives_count = int((frame['label'] == 1).sum()) if not frame.empty else 0
    negatives_count = int((frame['label'] == 0).sum()) if not frame.empty else 0
    debug_stats['final_positives'] = positives_count
    debug_stats['final_negatives'] = negatives_count
    debug_stats['final_total'] = len(frame)
    debug_stats['terrain_loss_report'] = build_terrain_loss_report(debug_stats)
    print(f'[training_dataset] Debug stats: {debug_stats}', file=sys.stderr)

    open_source_label_manifest = None
    open_snapshot = os.getenv('OPEN_SOURCE_LABEL_SNAPSHOT', '').strip()
    if open_snapshot:
        open_source_label_manifest = build_open_source_label_manifest(
            open_snapshot,
            source_key=os.getenv('OPEN_SOURCE_LABEL_SOURCE_KEY', '').strip() or None,
            requested_role=os.getenv('OPEN_SOURCE_LABEL_ROLE', 'staging').strip() or 'staging',
            license_review_id=os.getenv('OPEN_SOURCE_LABEL_LICENSE_REVIEW_ID', '').strip() or None,
        )

    manifest = {
        'training_dataset_version': 'real_event_join_v1',
        'positive_count': positives_count,
        'negative_count': negatives_count,
        'training_row_count': len(frame),
        'selected_region_keys': selected_region_keys,
        'raw_event_count': raw_event_count,
        'capped_event_count': capped_event_count,
        'samples_per_region_applied': samples_per_region,
        'unique_weather_pairs': unique_weather_pair_count,
        'snowpack_proxy_mode': snowpack_proxy_stats['mode'],
        'snowpack_proxy_stats': snowpack_proxy_stats,
        'timing_seconds': {
            'weather_prewarm': round(weather_prewarm_seconds, 3),
            'snowpack_prewarm': round(float(snowpack_proxy_stats.get('elapsed_seconds', 0.0) or 0.0), 3),
            'positive_build': round(positive_build_seconds, 3),
            'negative_build': round(negative_build_seconds, 3),
            'total': round(_time.perf_counter() - dataset_started_at, 3),
        },
        'is_synthetic': False,
        'filters': {
            'hazard_type': hazard_type,
            'training_eligible': True,
            'label_role_excluded': True,
            'verification_status': ['unverified', 'weak', 'verified', 'expert_verified'],
            'negative_ratio': NEGATIVES_PER_POSITIVE,
            'negative_distance_m': NEGATIVE_DISTANCE_M,
            'negative_time_window_hours': NEGATIVE_TIME_WINDOW_HOURS,
            'negative_slope_band_deg': [NEGATIVE_SLOPE_MIN, NEGATIVE_SLOPE_MAX],
            'region_keys_filter': region_keys,
        },
        'oldest_timestamp': frame['timestamp'].min().isoformat() if not frame.empty else None,
        'newest_timestamp': frame['timestamp'].max().isoformat() if not frame.empty else None,
        'event_source_counts': dict(event_source_counts),
        'source_training_weight_sums': {
            key: round(value, 6)
            for key, value in source_training_weight_sums.items()
        },
        'source_region_counts': {
            key: len(value)
            for key, value in source_region_keys.items()
        },
        'newest_timestamp_by_source': newest_timestamp_by_source,
        'region_keys': sorted({positive['region_key'] for positive in positives}),
        'mean_training_weight': float(frame['training_weight'].mean()) if not frame.empty else None,
        'promoted_sar_volume': {
            'sar_unet_promoted_count': int(event_source_counts.get('sar_unet', 0)),
        },
        'debug_stats': debug_stats,
        'open_source_label_manifest': open_source_label_manifest,
    }
    return frame, manifest


def load_training_frame(
    *,
    seed: int,
    samples_per_region: int,
    grid_size: int,
    allow_synthetic_bootstrap: bool,
    region_keys: list[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame, manifest = build_real_training_frame(
        seed=seed,
        grid_size=grid_size,
        region_keys=region_keys,
        samples_per_region=samples_per_region,
    )
    if not frame.empty and int((frame['label'] == 1).sum()) > 0 and int((frame['label'] == 0).sum()) > 0:
        return frame, manifest

    if not allow_synthetic_bootstrap:
        raise RuntimeError('Real training dataset is empty or class-degenerate and synthetic bootstrap is disabled.')

    # P2.3: Loudly annotate any synthetic bootstrap run so it shows up as a
    # warning in GitHub Actions and the resulting artifact is tagged
    # is_synthetic=True. train_model.py refuses to publish to Supabase when
    # this flag is set, so a cold-start synthetic run can build a local
    # artifact but will never overwrite the live model_status.
    import sys as _sys
    print(
        "::warning title=Synthetic training bootstrap::"
        "Real training frame is empty or class-degenerate; falling back to "
        "generate_training_frame. This artifact will NOT be published to Supabase.",
        file=_sys.stderr,
    )
    synthetic = generate_training_frame(load_regions(), samples_per_region=samples_per_region, seed=seed)
    synthetic['severity'] = None
    synthetic['confidence'] = synthetic['label'].astype(float)
    synthetic['label_confidence'] = np.where(synthetic['label'] == 1, 0.55, 1.0)
    synthetic['training_weight'] = np.where(synthetic['label'] == 1, 0.55, 1.0)
    synthetic['source_weight'] = 1.0
    synthetic['corroboration_weight'] = 1.0
    synthetic['recency_decay'] = 1.0
    synthetic['confidence_decayed'] = synthetic['label_confidence']
    synthetic['governance_version'] = GOVERNANCE_VERSION
    synthetic['governed_at'] = datetime.now(timezone.utc).isoformat()
    synthetic['label_source'] = 'synthetic_bootstrap'
    synthetic['review_basis'] = 'synthetic'
    synthetic['nowcast_ref'] = None
    synthetic['observer_ref'] = None
    synthetic['regime'] = None
    synthetic['timing'] = None
    synthetic['elevation_m_raw'] = synthetic['elevation'] * 5000.0
    synthetic['slope_angle_deg_raw'] = synthetic['slope'] * 60.0
    synthetic['aspect_deg_raw'] = 180.0
    synthetic['terrain_roughness_raw'] = synthetic['terrain_roughness'] * 150.0
    synthetic['curvature_proxy_raw'] = synthetic['curvature_proxy'] * 50.0
    synthetic['temperature_2m'] = synthetic['temp_gradient'] * 20 - 10
    synthetic['windspeed_10m'] = synthetic['wind_loading'] * 55
    return synthetic, {
        'training_dataset_version': 'synthetic_bootstrap_v1',
        'is_synthetic': True,
        'positive_count': int((synthetic['label'] == 1).sum()),
        'negative_count': int((synthetic['label'] == 0).sum()),
        'filters': {'allow_synthetic_bootstrap': True},
        'oldest_timestamp': synthetic['timestamp'].min().isoformat(),
        'newest_timestamp': synthetic['timestamp'].max().isoformat(),
    }
