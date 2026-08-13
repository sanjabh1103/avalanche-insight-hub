"""Provenance-aware SAR backfill with run/chunk tracking and checkpoint/resume.

Track B — Open-source provenance and label evidence.

This script wraps the existing gee._process_region pipeline with:
  - A run record in sar_provenance_backfill_runs (one per execution)
  - Per-chunk records in sar_provenance_backfill_chunks (one per region/window)
  - backfill_run_id stamped on every inserted event
  - Event fingerprints for idempotency (dedup on retry)
  - Checkpoint/resume: re-running with the same run_id skips completed chunks
  - Fail-closed: lineage and artifact failures fail the chunk and run
  - All events are permanently ineligible until Track A contracts land

Usage:
    python backend/scripts/provenance_backfill.py \\
        --run-id nepal_pilot_v1 \\
        --region-key himalayas_nepal \\
        --start 2023-11-01 --end 2023-11-15 \\
        --chunk-days 7

    # Resume an interrupted run:
    python backend/scripts/provenance_backfill.py --run-id nepal_pilot_v1 --resume
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from backend.common.label_governance import materialize_label_governance
from backend.common.regions import Region, load_regions, repo_root
from backend.common.real_features import extract_cell_terrain
from backend.common.sar_artifacts import persist_sar_artifacts
from backend.common.supabase_io import (
    has_supabase_credentials,
    rest_insert,
    rest_get,
    rest_upsert,
    patch_row_by_id,
    _base_url,
    _headers,
)

import backend.gee_extractor as gee


SLOPE_MIN_DEG = float(os.getenv('PHYSICS_SLOPE_MIN_DEG', '25'))
SLOPE_MAX_DEG = float(os.getenv('PHYSICS_SLOPE_MAX_DEG', '65'))
DEM_DIR = repo_root() / 'backend' / 'data' / 'dem'
ALGORITHM_VERSION = 'gee_threshold_baseline_v1'
DEPENDENCY_LOCK_PATH = repo_root() / 'backend' / 'locks' / 'core-py312.txt'
PROVENANCE_EVENT_FINGERPRINT_FIELD = 'provenance_event_fingerprint'

# All provenance backfill events are permanently ineligible until Track A
# contracts (danger-level assignment, threshold calibration, probability maps)
# are completed and a reviewed snapshot preflight passes. This cannot be
# overridden via CLI flags.
ALWAYS_INELIGIBLE = True
ALWAYS_INELIGIBLE_REASON = (
    'provenance_backfill:not_yet_approved_core:track_a_contracts_pending'
)


def _event_fingerprint(event: dict[str, Any]) -> str:
    """Deterministic SHA-256 fingerprint for an event payload.

    Excludes volatile fields (created_at, governed_at) that would change
    on re-insertion, so the fingerprint is stable across retries.
    """
    volatile_keys = {
        'created_at',
        'governed_at',
        'id',
        # The database uniqueness key is derived from this fingerprint. It
        # must not recursively contribute to its own value.
        PROVENANCE_EVENT_FINGERPRINT_FIELD,
    }
    stable = {k: v for k, v in event.items() if k not in volatile_keys}
    canonical = json.dumps(stable, sort_keys=True, default=str).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


def _scene_lineage_hash(scene_ids: list[str]) -> str:
    """SHA-256 hash of sorted scene IDs for deduplication and integrity."""
    canonical = json.dumps(sorted(scene_ids), default=str).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


def _event_group_id(
    run_id: str,
    region_key: str,
    window_start: datetime,
    window_end: datetime,
) -> str:
    """Return a stable group identity for temporal/spatial split controls."""
    canonical = '|'.join((
        run_id,
        region_key,
        window_start.astimezone(timezone.utc).isoformat(),
        window_end.astimezone(timezone.utc).isoformat(),
    )).encode('utf-8')
    return f'backfill:{hashlib.sha256(canonical).hexdigest()}'


def _prepare_events_for_persistence(
    events: list[dict[str, Any]],
    *,
    run_id: str,
    region_key: str,
    window_start: datetime,
    window_end: datetime,
) -> list[dict[str, Any]]:
    """Stamp immutable provenance and idempotency fields before database IO."""
    group_id = _event_group_id(run_id, region_key, window_start, window_end)
    prepared: list[dict[str, Any]] = []
    for event in events:
        features = event.get('features')
        if not isinstance(features, dict):
            features = {}
        features.update({
            'event_group_id': group_id,
            'label_time_contract': 'interval_censored_core_v1',
            # The database timestamp is retained for existing UI contracts,
            # but it is an observation time, not a claimed occurrence time.
            'event_time_semantics': 'sar_observation_time_not_occurrence_time',
            'core_training_eligible': False,
            'shadow_only': True,
        })
        event['features'] = features
        event['training_eligible'] = False
        event['training_eligible_reason'] = ALWAYS_INELIGIBLE_REASON
        event[PROVENANCE_EVENT_FINGERPRINT_FIELD] = _event_fingerprint(event)
        prepared.append(event)
    return prepared


def _dependency_lock_hash() -> str:
    """Hash the release lock, not an arbitrary local Python environment."""
    if not DEPENDENCY_LOCK_PATH.is_file():
        raise RuntimeError(f'Missing dependency lock: {DEPENDENCY_LOCK_PATH}')
    return hashlib.sha256(DEPENDENCY_LOCK_PATH.read_bytes()).hexdigest()


def _enrich_and_gate(region: Region, raw: list[dict], scene_ts: datetime | None) -> list[dict]:
    """Add terrain features and apply physics gate.

    scene_ts is the actual mean scene acquisition time from the extractor.
    If scene_ts is None, the event timestamp is left as-is (the extractor
    sets it to the mean scene time). We do NOT fabricate a midpoint.
    """
    enriched = []
    dem_path = DEM_DIR / f'{region.key}.tif'
    for ev in raw:
        ev['training_eligible'] = False
        ev['training_eligible_reason'] = ALWAYS_INELIGIBLE_REASON
        feats = ev.get('features') or {}
        lat = feats.get('sar_centroid', {}).get('lat')
        lng = feats.get('sar_centroid', {}).get('lng')

        # Set timestamp from scene_ts BEFORE any early-exit branches
        # so we never accidentally keep a stale or fabricated timestamp.
        if scene_ts is not None:
            ev['timestamp'] = scene_ts.isoformat()

        if lat is None or lng is None:
            enriched.append(ev)
            continue
        try:
            if not dem_path.exists():
                enriched.append(ev)
                continue
            topo = extract_cell_terrain(str(dem_path), lat=lat, lng=lng)
        except Exception:
            enriched.append(ev)
            continue
        ev['elevation_m'] = int(round(float(topo.get('elevation_m', 0))))
        ev['slope_angle_deg'] = round(float(topo.get('slope_angle_deg', 0)), 3)
        ev['aspect_deg'] = round(float(topo.get('aspect_deg', 0)), 3)
        ev['topo_source'] = 'srtm_local_rasterio'
        slope = ev['slope_angle_deg']
        if slope is not None:
            source_eligible = bool(ev.get('training_eligible', True))
            physics_eligible = SLOPE_MIN_DEG <= slope <= SLOPE_MAX_DEG
            ev['training_eligible'] = source_eligible and physics_eligible
            if not physics_eligible:
                ev['training_eligible_reason'] = f'slope {slope:.1f} outside [{SLOPE_MIN_DEG}, {SLOPE_MAX_DEG}]'
        governance = materialize_label_governance(ev)
        ev.update({
            'label_confidence': governance['label_confidence'],
            'training_weight': governance['training_weight'],
            'training_eligible': governance['training_eligible'],
            'governance_version': governance['governance_version'],
            'governed_at': governance['governed_at'],
        })
        # Track-B provenance rows cannot become core labels through a later
        # governance refresh or physics branch. Keep the reason stable.
        ev['training_eligible'] = False
        ev['training_eligible_reason'] = ALWAYS_INELIGIBLE_REASON
        enriched.append(ev)
    return enriched


def _parse_remote_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _create_or_upsert_run(run_id: str, start: datetime, end: datetime, chunk_days: int,
                          regions: list[str], code_sha: str, dep_hash: str,
                          algorithm_version: str, resume: bool) -> dict:
    """Create a run or resume the exact same immutable execution contract."""
    algorithm_version = algorithm_version or ALGORITHM_VERSION
    extractor_config = {
        # These values are imported from the extractor so the persisted run
        # cannot silently diverge from the values used by Earth Engine.
        'vv_threshold_db': gee.GEE_VV_THRESHOLD_DB,
        'vh_threshold_db': gee.GEE_VH_THRESHOLD_DB,
        'slope_min': SLOPE_MIN_DEG,
        'slope_max': SLOPE_MAX_DEG,
        'python_version': platform.python_version(),
        'dependency_lock': str(DEPENDENCY_LOCK_PATH.relative_to(repo_root())),
        'dependency_lock_sha256': dep_hash,
    }
    run_record = {
        'run_id': run_id,
        'status': 'running',
        'start_date': start.isoformat(),
        'end_date': end.isoformat(),
        'chunk_days': chunk_days,
        'regions': regions,
        'algorithm_version': algorithm_version,
        'code_sha': code_sha,
        'dependency_hash': dep_hash,
        'extractor_config': extractor_config,
    }
    existing_rows = rest_get('sar_provenance_backfill_runs', params={
        'select': '*',
        'run_id': f'eq.{run_id}',
        'limit': '1',
    }) or []
    existing = existing_rows[0] if existing_rows else None

    if existing is not None and not resume:
        raise RuntimeError(
            f'Run {run_id!r} already exists; use --resume only with the original contract'
        )

    if existing is not None:
        mismatches: list[str] = []
        if _parse_remote_datetime(existing.get('start_date')) != start.astimezone(timezone.utc):
            mismatches.append('start_date')
        if _parse_remote_datetime(existing.get('end_date')) != end.astimezone(timezone.utc):
            mismatches.append('end_date')
        if int(existing.get('chunk_days') or 0) != chunk_days:
            mismatches.append('chunk_days')
        if sorted(existing.get('regions') or []) != sorted(regions):
            mismatches.append('regions')
        if existing.get('algorithm_version') != algorithm_version:
            mismatches.append('algorithm_version')
        existing_config = existing.get('extractor_config') or {}
        for key in ('vv_threshold_db', 'vh_threshold_db', 'slope_min', 'slope_max', 'dependency_lock_sha256'):
            if existing_config.get(key) != extractor_config[key]:
                mismatches.append(f'extractor_config.{key}')
        if mismatches:
            raise RuntimeError(
                f'Cannot resume run {run_id!r}; immutable contract mismatch: {mismatches}'
            )
        response = requests.patch(
            f'{_base_url()}/rest/v1/sar_provenance_backfill_runs?run_id=eq.{run_id}',
            headers={**_headers(), 'Prefer': 'return=representation'},
            json={'status': 'running', 'updated_at': datetime.now(timezone.utc).isoformat()},
            timeout=30,
        )
        if not response.ok:
            raise RuntimeError(
                f'Failed to resume run {run_id!r}: {response.status_code} {response.text}'
            )
        rows = response.json() if response.text.strip() else []
        return rows[0] if rows else {**existing, 'status': 'running'}

    inserted = rest_insert('sar_provenance_backfill_runs', [run_record])
    return inserted[0] if inserted else run_record


def _get_existing_chunks(run_id: str) -> dict[str, dict]:
    """Get completed chunks for resume support. Returns {(region, window_start): chunk_record}."""
    chunks = rest_get('sar_provenance_backfill_chunks', params={
        'select': '*',
        'run_id': f'eq.{run_id}',
        'status': 'eq.completed',
    }) or []
    result: dict[str, dict] = {}
    for chunk in chunks:
        start = _parse_remote_datetime(chunk.get('window_start'))
        if start is None:
            raise RuntimeError(f'Completed chunk {chunk.get("id")} has invalid window_start')
        result[(chunk['region_key'], start.isoformat())] = chunk
    return result


def _create_chunk(run_id: str, region_key: str, window_start: datetime, window_end: datetime) -> dict:
    """Create a chunk record. Uses upsert to handle retry-after-crash idempotency."""
    chunk = {
        'run_id': run_id,
        'region_key': region_key,
        'window_start': window_start.isoformat(),
        'window_end': window_end.isoformat(),
        'status': 'running',
        'started_at': datetime.now(timezone.utc).isoformat(),
    }
    # The unique index is a required migration. Do not fall back to a plain
    # insert: doing so would reintroduce duplicate chunks when the schema is
    # not at the required version.
    upserted = rest_upsert(
        'sar_provenance_backfill_chunks',
        [chunk],
        on_conflict='run_id,region_key,window_start',
    )
    return upserted[0] if upserted else chunk


def _complete_chunk(chunk_id: str, summary: dict) -> None:
    """Mark a chunk as completed with summary data."""
    if not chunk_id:
        raise RuntimeError('Cannot complete a chunk without its control-plane id')
    patch_row_by_id('sar_provenance_backfill_chunks', chunk_id, {
        'status': 'completed',
        'scene_count': summary.get('scene_count', 0),
        'detection_count': summary.get('detection_count', 0),
        'inserted_count': summary.get('inserted_count', 0),
        'eligible_count': summary.get('eligible_count', 0),
        'lineage_persisted': summary.get('lineage_persisted', False),
        'artifacts_persisted': summary.get('artifacts_persisted', False),
        'scene_ids': summary.get('scene_ids', []),
        'scene_lineage_hash': summary.get('scene_lineage_hash'),
        'event_fingerprints': summary.get('event_fingerprints', []),
        'completed_at': datetime.now(timezone.utc).isoformat(),
    })


def _fail_chunk(chunk_id: str, error: str) -> None:
    """Mark a chunk as failed."""
    if not chunk_id:
        return
    patch_row_by_id('sar_provenance_backfill_chunks', chunk_id, {
        'status': 'failed',
        'error': error[:2000],
        'completed_at': datetime.now(timezone.utc).isoformat(),
    })


def _complete_run(run_id: str, summary: dict) -> None:
    """Mark a run as completed, partial_failed, or failed. Patches by run_id.

    Fail-closed: if run-status update fails, this is logged as a FATAL error
    because the run state cannot be trusted.
    """
    failed = summary.get('failed_chunks', 0)
    completed = summary.get('completed_chunks', 0)
    total = summary.get('total_chunks', 0)
    incomplete = total != completed + failed
    if (failed > 0 or incomplete) and completed == 0:
        status = 'failed'
    elif failed > 0 or incomplete:
        status = 'partial_failed'
    else:
        status = 'completed'
    payload = {
        'status': status,
        'completed_chunks': completed,
        'failed_chunks': failed,
        'total_chunks': summary.get('total_chunks', 0),
        'total_detections': summary.get('total_detections', 0),
        'total_inserted': summary.get('total_inserted', 0),
        'total_eligible': summary.get('total_eligible', 0),
        'total_lineage_rows': summary.get('total_lineage_rows', 0),
        'total_artifact_rows': summary.get('total_artifact_rows', 0),
        'lineage_failures': summary.get('lineage_failures', 0),
        'artifact_failures': summary.get('artifact_failures', 0),
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }
    response = requests.patch(
        f'{_base_url()}/rest/v1/sar_provenance_backfill_runs?run_id=eq.{run_id}',
        headers={**_headers(), 'Prefer': 'return=minimal'},
        json=payload,
        timeout=30,
    )
    if not response.ok:
        print(f'[provenance] FATAL: failed to update run status: '
              f'{response.status_code} {response.text}', file=sys.stderr)
        # This is fatal — the run state is now unknown
        raise RuntimeError(f'Run status update failed: {response.status_code} {response.text}')


def _validate_regions(region_keys: list[str], all_regions: list[Region]) -> list[Region]:
    """Validate that all requested region keys exist. Fail fast on unknown keys."""
    if not region_keys:
        return all_regions
    valid_keys = {r.key for r in all_regions}
    unknown = [k for k in region_keys if k not in valid_keys]
    if unknown:
        raise ValueError(f'Unknown region keys: {unknown}. Valid keys: {sorted(valid_keys)}')
    return [r for r in all_regions if r.key in region_keys]


def _compute_total_chunks(regions: list[Region], start: datetime, end: datetime, chunk_days: int) -> int:
    """Compute the expected total number of chunks for validation."""
    total = 0
    for region in regions:
        cursor = start
        while cursor < end:
            total += 1
            cursor = cursor + timedelta(days=chunk_days)
    return total


def run_provenance_backfill(
    run_id: str,
    start: datetime,
    end: datetime,
    chunk_days: int,
    region_keys: list[str],
    code_sha: str = '',
    dep_hash: str = '',
    algorithm_version: str = '',
    resume: bool = False,
) -> dict:
    """Run a provenance-tracked SAR backfill.

    All events are permanently ineligible (ALWAYS_INELIGIBLE=True).
    There is no --eligible flag and no way to override this.

    Args:
        run_id: Unique identifier for this run.
        start/end: Date range to extract.
        chunk_days: Days per chunk (7 recommended for Sentinel-1 revisit).
        region_keys: List of region keys to process.
        code_sha: Git SHA of the code being run.
        dep_hash: Hash of key dependencies.
        algorithm_version: Version string for the extraction algorithm.
        resume: If True, skip chunks already completed in a prior run.
    """
    if end <= start:
        return {'status': 'invalid_window', 'error': 'end must be after start'}
    if chunk_days <= 0:
        return {'status': 'invalid_chunk_days', 'error': 'chunk_days must be positive'}
    # A provenance run that cannot write both its control-plane state and its
    # source lineage is not a dry run; it is an invalid execution.
    if not has_supabase_credentials():
        return {'status': 'skipped_no_supabase_creds'}
    if not gee._has_credentials():
        return {'status': 'skipped_no_gee_creds'}

    try:
        ee = gee._initialize_ee()
    except Exception as exc:
        return {'status': 'ee_init_failed', 'error': str(exc)}

    all_regions = load_regions()
    try:
        selected = _validate_regions(region_keys, all_regions)
    except ValueError as exc:
        return {'status': 'invalid_regions', 'error': str(exc)}

    total_chunks_expected = _compute_total_chunks(selected, start, end, chunk_days)
    if total_chunks_expected == 0:
        return {'status': 'invalid_empty_region_selection'}

    algorithm_version = algorithm_version or ALGORITHM_VERSION
    dep_hash = dep_hash or _dependency_lock_hash()

    # Create or upsert run record
    existing_chunks = _get_existing_chunks(run_id) if resume else {}
    _create_or_upsert_run(
        run_id, start, end, chunk_days, [r.key for r in selected],
        code_sha, dep_hash, algorithm_version, resume,
    )

    summary = {
        'total_chunks': total_chunks_expected,
        'completed_chunks': 0, 'failed_chunks': 0,
        'total_detections': 0, 'total_inserted': 0, 'total_eligible': 0,
        'total_lineage_rows': 0, 'total_artifact_rows': 0,
        'lineage_failures': 0, 'artifact_failures': 0,
    }
    per_region: list[dict] = []

    for region in selected:
        region_detections = 0
        region_inserted = 0
        region_eligible = 0
        cursor = start
        while cursor < end:
            w_end = min(cursor + timedelta(days=chunk_days), end)
            chunk_key = (region.key, cursor.isoformat())

            # Skip if already completed (resume mode)
            if chunk_key in existing_chunks:
                print(f'[provenance] {region.key} {cursor.date()}->{w_end.date()}: '
                      f'SKIPPED (already completed)')
                summary['completed_chunks'] += 1
                cursor = w_end
                continue

            chunk_record = _create_chunk(run_id, region.key, cursor, w_end)
            chunk_id = chunk_record.get('id', '')

            try:
                # Extract with lineage persistence enabled
                raw = gee._process_region(
                    ee, region, start_date=cursor, end_date=w_end,
                    persist_lineage=True,
                )
                scene_ids = sorted({
                    str(scene_id)
                    for event in raw
                    for scene_id in (
                        event.get('source_scene_ids', [])
                        or (event.get('features', {}) or {}).get('sar_scene_ids', [])
                    )
                    if scene_id
                })
                if raw and not scene_ids:
                    raise RuntimeError(
                        'Scene lineage missing for non-empty detection chunk'
                    )

                # Stamp backfill_run_id and force ineligible (ALWAYS)
                for ev in raw:
                    ev['backfill_run_id'] = run_id
                    ev['training_eligible'] = False
                    ev['training_eligible_reason'] = ALWAYS_INELIGIBLE_REASON

                # Use the actual mean scene time from the extractor.
                # Do NOT fabricate a midpoint timestamp.
                scene_ts = None
                if raw and raw[0].get('features', {}).get('sar_scene_time'):
                    try:
                        scene_ts = datetime.fromisoformat(
                            raw[0]['features']['sar_scene_time'].replace('Z', '+00:00')
                        )
                    except Exception:
                        pass
                # No scene time means no safe observation timestamp. The
                # database default must never silently turn that into `now()`.
                if raw and scene_ts is None:
                    raise RuntimeError(
                        'Scene acquisition time missing; refusing to synthesize a label timestamp'
                    )
                enriched = _enrich_and_gate(region, raw, scene_ts)
                enriched = _prepare_events_for_persistence(
                    enriched,
                    run_id=run_id,
                    region_key=region.key,
                    window_start=cursor,
                    window_end=w_end,
                )

                # Insert events
                inserted_count = 0
                artifact_count = 0
                artifact_failure = False
                lineage_failure = False

                if enriched:
                    try:
                        # Requires the forward idempotency migration. A plain
                        # insert here would duplicate events after a crash
                        # between event persistence and chunk completion.
                        inserted_rows = rest_upsert(
                            'avalanche_events',
                            enriched,
                            on_conflict='backfill_run_id,provenance_event_fingerprint',
                        )
                        inserted_count = len(inserted_rows)
                    except Exception as exc:
                        raise RuntimeError(
                            f'Event insertion failed (chunk fails): {exc}'
                        ) from exc

                    # Artifact persistence is fail-closed
                    try:
                        artifact_count = persist_sar_artifacts(inserted_rows, enriched)
                    except Exception as exc:
                        artifact_failure = True
                        summary['artifact_failures'] += 1
                        print(f'[provenance] {region.key} {cursor.date()}: '
                              f'FATAL: artifact persistence FAILED: {exc}',
                              file=sys.stderr)
                        # Fail the chunk — do NOT mark as completed
                        raise RuntimeError(
                            f'Artifact persistence failed (chunk fails): {exc}'
                        ) from exc
                    if artifact_count != inserted_count:
                        summary['artifact_failures'] += 1
                        raise RuntimeError(
                            'Artifact persistence failed (chunk fails): '
                            f'expected {inserted_count}, persisted {artifact_count}'
                        )

                # Verify lineage was actually persisted (not just that scene_ids exist).
                # The extractor now raises on an upsert failure; this read-back
                # also catches partial writes or stale schema/runtime behavior.
                lineage_persisted = False
                if scene_ids:
                    try:
                        lineage_rows = rest_get('remote_sensing_scenes', params={
                            'select': 'scene_id',
                            'region_key': f'eq.{region.key}',
                            'sensor': 'eq.sentinel1_gee',
                            'scene_id': f'in.({",".join(scene_ids)})',
                        }) or []
                        found_scene_ids = {
                            str(row.get('scene_id'))
                            for row in lineage_rows
                            if row.get('scene_id')
                        }
                        missing_scene_ids = sorted(set(scene_ids) - found_scene_ids)
                        lineage_persisted = not missing_scene_ids
                        if not lineage_persisted:
                            lineage_failure = True
                            summary['lineage_failures'] += 1
                            raise RuntimeError(
                                f'Lineage persistence verification failed: '
                                f'missing {len(missing_scene_ids)} of {len(scene_ids)} scenes '
                                'in remote_sensing_scenes'
                            )
                    except RuntimeError:
                        raise
                    except Exception as exc:
                        lineage_failure = True
                        summary['lineage_failures'] += 1
                        raise RuntimeError(
                            f'Lineage persistence verification error: {exc}'
                        ) from exc

                fingerprints = [
                    str(ev[PROVENANCE_EVENT_FINGERPRINT_FIELD])
                    for ev in enriched
                ]
                lineage_hash = _scene_lineage_hash(scene_ids)

                chunk_summary = {
                    'scene_count': len(scene_ids),
                    'detection_count': len(enriched),
                    'inserted_count': inserted_count,
                    'eligible_count': 0,  # Always 0 — permanently ineligible
                    'lineage_persisted': lineage_persisted,
                    'artifacts_persisted': not artifact_failure,
                    'scene_ids': scene_ids,
                    'scene_lineage_hash': lineage_hash,
                    'event_fingerprints': fingerprints,
                }
                _complete_chunk(chunk_id, chunk_summary)

                region_detections += len(enriched)
                region_inserted += inserted_count
                summary['completed_chunks'] += 1
                summary['total_detections'] += len(enriched)
                summary['total_inserted'] += inserted_count
                summary['total_lineage_rows'] += len(scene_ids)
                summary['total_artifact_rows'] += artifact_count

                print(f'[provenance] {region.key} {cursor.date()}->{w_end.date()}: '
                      f'detections={len(enriched)} inserted={inserted_count} '
                      f'scenes={len(scene_ids)} artifacts={artifact_count} '
                      f'lineage_verified={lineage_persisted}')

            except Exception as exc:
                summary['failed_chunks'] += 1
                _fail_chunk(chunk_id, str(exc))
                print(f'[provenance] {region.key} {cursor.date()}->{w_end.date()}: '
                      f'FAILED: {exc}', file=sys.stderr)
                traceback.print_exc()

            cursor = w_end

        per_region.append({
            'region': region.key,
            'detections': region_detections,
            'inserted': region_inserted,
            'eligible': 0,  # Always 0
        })
        print(f'[provenance] {region.key}: '
              f'detections={region_detections} inserted={region_inserted}')

    try:
        _complete_run(run_id, summary)
    except RuntimeError as exc:
        # Run status update failed — this is fatal
        return {
            'status': 'fatal_run_update_failed',
            'run_id': run_id,
            'error': str(exc),
            'summary': summary,
            'per_region': per_region,
        }

    failed = summary['failed_chunks']
    completed = summary['completed_chunks']
    incomplete = summary['total_chunks'] != completed + failed
    if (failed > 0 or incomplete) and completed == 0:
        final_status = 'failed'
    elif failed > 0 or incomplete:
        final_status = 'partial_failed'
    else:
        final_status = 'completed'

    return {
        'status': final_status,
        'run_id': run_id,
        'summary': summary,
        'per_region': per_region,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True, help='Unique run identifier')
    parser.add_argument('--region-key', default='', help='Comma-separated region keys (empty = all)')
    parser.add_argument('--start', default='2023-11-01', help='YYYY-MM-DD')
    parser.add_argument('--end', default='2024-04-30', help='YYYY-MM-DD')
    parser.add_argument('--chunk-days', type=int, default=7, help='Days per chunk')
    parser.add_argument('--resume', action='store_true', help='Skip already-completed chunks')
    # NOTE: --eligible flag has been REMOVED (P0-05).
    # All provenance backfill events are permanently ineligible until Track A
    # contracts land and a reviewed snapshot preflight passes.
    args = parser.parse_args(argv)

    if sys.version_info[:2] != (3, 12):
        print(
            'Python 3.12 is required for provenance backfill; '
            f'found {platform.python_version()}',
            file=sys.stderr,
        )
        return 2

    start = datetime.strptime(args.start, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    end = datetime.strptime(args.end, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    if end <= start:
        print('--end must be after --start', file=sys.stderr)
        return 2

    region_keys = [k.strip() for k in args.region_key.split(',') if k.strip()] if args.region_key else []

    # Get code SHA and dependency hash for reproducibility
    try:
        code_sha = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=repo_root()
        ).decode().strip()
        # Check if worktree is dirty
        dirty = subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=repo_root()
        ).decode().strip()
        if dirty:
            code_sha += '-dirty'
    except Exception:
        code_sha = 'unknown'

    # Hash the committed release lock. A local pip-freeze hash can describe a
    # different interpreter and is not an acceptable release identity.
    try:
        dep_hash = _dependency_lock_hash()
    except (OSError, RuntimeError) as exc:
        print(f'Cannot determine dependency lock hash: {exc}', file=sys.stderr)
        dep_hash = 'unknown'

    result = run_provenance_backfill(
        run_id=args.run_id,
        start=start,
        end=end,
        chunk_days=args.chunk_days,
        region_keys=region_keys,
        code_sha=code_sha,
        dep_hash=dep_hash,
        algorithm_version=ALGORITHM_VERSION,
        resume=args.resume,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get('status') == 'completed' else 2


if __name__ == '__main__':
    sys.exit(main())
