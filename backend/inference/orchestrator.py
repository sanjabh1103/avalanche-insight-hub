"""Main orchestration entry point — extracted from backend/daily_inference.py.

Contains the CLI and high-level orchestration loop.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd

from backend.inference import require_canonical_runtime
from backend.common.artifacts import dump_json, load_joblib, resolve_artifact_dir
from backend.common.ravafcast_runtime_gate import check_pipeline_status, emit_gate_metadata
from backend.common.audit_metadata import (
    build_decision_provenance,
    build_feature_completeness_row,
    build_latest_benchmark_summary,
    build_source_health_summary,
)
from backend.common.cap_alert import (
    CAP_ENABLED,
    generate_multi_language_cap,
    should_trigger_alert,
    validate_cap_xml,
)
from backend.common.config import load_settings
from backend.common.continuous_learning import (
    CONTINUOUS_LEARNING_ENABLED,
    process_detections_for_learning,
)
from backend.common.features import FEATURE_COLUMNS
from backend.common.forecast_bulletins import (
    build_daypart_forecast_bulletin,
    build_forecast_bulletin,
)
from backend.common.forecast_publication import (
    attach_compatibility_forecast_grid,
    publish_forecast_run,
    promote_forecast_run,
)
from backend.common.model_status_state import (
    build_autonomous_evidence_summary,
    build_drift_mode_state,
    build_dynamic_model_candidate,
    resolve_active_candidate_artifact_dir,
    resolve_active_model_state,
)
from backend.common.regions import load_regions
from backend.common.sachet_push import (
    SACHET_ENABLED,
    SACHET_RSS_ENABLED,
    SachetConfig,
    build_multi_language_alerts,
    push_sachet_alert,
)
from backend.common.sachet_rss import (
    SachetRssConfig,
    get_sachet_alert_summary,
    ingest_sachet_alerts,
)
from backend.common.schema_drift import detect_drift, feature_columns_hash
from backend.common.seismic_integrator import (
    HIMALAYAN_BBOX,
    SEISMIC_MIN_MAGNITUDE,
    fetch_recent_earthquakes,
)
from backend.common.sensor_ingestion import (
    SENSOR_ENABLED,
    fetch_sensor_events_rest,
)
from backend.common.aavds_adapter import (
    AAVDS_ENABLED,
    AAVDSAdapter,
)
from backend.common.citizen_science import (
    CITIZEN_SCIENCE_ENABLED,
    CitizenReport,
)
from backend.common.route_planner import (
    SafeRoute,
    assess_route_safety,
    compute_safe_route,
)
from backend.common.multi_hazard import (
    MULTI_HAZARD_ENABLED,
    assess_multi_hazard,
)
from backend.inference.grid import (
    build_cells,
    build_hourly_grids,
)
from backend.inference.options import ProofModeOptions
from backend.inference.persistence import upsert_forecast_grid
from backend.inference.utils import (
    _default_inference_backend,
    _fetch_current_model_status,
    _is_truthy_env,
)




def main(argv: list[str] | None = None) -> int:
    require_canonical_runtime('backend.inference.orchestrator')
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(description='Generate forecast grids for Avalanche Insight Hub')
    parser.add_argument('--artifact-root', type=Path, default=load_settings().artifact_root)
    parser.add_argument('--artifact-dir', type=Path)
    parser.add_argument('--forecast-hours', type=int, default=load_settings().forecast_horizon_hours)
    parser.add_argument('--grid-size', type=int, default=load_settings().grid_size)
    parser.add_argument('--dry-run', action='store_true', default=load_settings().dry_run)
    parser.add_argument('--region-key', action='append', default=[])
    parser.add_argument('--lifeboat-mode', action='store_true')
    parser.add_argument('--lifeboat-profile', choices=('proof72', 'smoke24'), default='proof72')
    parser.add_argument('--skip-tree-shap', action='store_true')
    parser.add_argument('--skip-shap-cache', action='store_true')
    parser.add_argument('--skip-runout-generation', action='store_true')
    parser.add_argument('--skip-compatibility-write', action='store_true')
    parser.add_argument('--emit-stage-metrics', action='store_true')
    parser.add_argument(
        '--snowpack-proxy-mode',
        choices=('cell', 'regional', 'synthetic'),
        default=os.getenv('SNOWPACK_PROXY_MODE', 'cell'),
        help='Snowpack proxy source. Use synthetic only for bounded technical publication proofs.',
    )
    parser.add_argument(
        '--require-same-day-publication',
        action='store_true',
        help='Fail unless every generated region has same-day published forecast_run proof.',
    )
    parser.add_argument(
        '--require-full-grid-publication',
        action='store_true',
        help='Fail unless every generated region has same-day full-grid proof plus structured bulletin content.',
    )
    args = parser.parse_args(raw_argv)

    def _flag_was_explicit(flag: str) -> bool:
        return any(item == flag or item.startswith(f'{flag}=') for item in raw_argv)

    if args.lifeboat_mode:
        if args.require_full_grid_publication:
            raise RuntimeError('lifeboat_mode cannot satisfy --require-full-grid-publication')
        if not _flag_was_explicit('--forecast-hours'):
            args.forecast_hours = 24 if args.lifeboat_profile == 'smoke24' else 72
        if not _flag_was_explicit('--grid-size'):
            args.grid_size = 5
        args.skip_tree_shap = True
        args.skip_shap_cache = True
        args.skip_runout_generation = True
        args.skip_compatibility_write = True
        args.emit_stage_metrics = True

    proof_options = ProofModeOptions(
        enabled=bool(args.lifeboat_mode),
        profile=str(args.lifeboat_profile if args.lifeboat_mode else 'standard'),
        skip_tree_shap=bool(args.skip_tree_shap),
        skip_shap_cache=bool(args.skip_shap_cache),
        skip_runout_generation=bool(args.skip_runout_generation),
        skip_compatibility_write=bool(args.skip_compatibility_write),
        emit_stage_metrics=bool(args.emit_stage_metrics),
    )

    current_model_status = _fetch_current_model_status()
    requested_artifact_dir = args.artifact_dir
    if requested_artifact_dir is None and current_model_status is not None:
        requested_artifact_dir = resolve_active_candidate_artifact_dir(args.artifact_root, current_model_status)
    artifact_resolution_started_at = perf_counter()
    try:
        artifact_dir = resolve_artifact_dir(
            args.artifact_root,
            requested_artifact_dir,
            require_model=True,
        )
        bundle = load_joblib(artifact_dir / 'model.joblib')
        try:
            from backend.common.schema_drift import detect_drift, feature_columns_hash
            current_hash = feature_columns_hash(FEATURE_COLUMNS)
            stored_hash = bundle.get('feature_columns_hash') if isinstance(bundle, dict) else None
            drift_report = detect_drift(
                stored_feature_hash=stored_hash if isinstance(stored_hash, str) else None,
                current_feature_hash=current_hash,
                stored_label_hash=None,
                current_label_hash='',
            )
            if drift_report['requires_retrain']:
                print(
                    f"::warning title=Schema drift detected::"
                    f"feature_columns_hash mismatch (stored={stored_hash!s}, current={current_hash!s}). "
                    f"Retrain required.",
                    file=sys.stderr,
                )
        except Exception as drift_exc:  # pragma: no cover - drift check is advisory
            print(f"[daily_inference] drift check skipped: {drift_exc}", file=sys.stderr)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    except FileNotFoundError:
        raise RuntimeError(
            (
                f'No usable trained model artifact is available at {args.artifact_dir}.'
                if args.artifact_dir
                else 'No trained model artifact is available. Run backend.train_model first; '
                'daily inference no longer bootstraps a synthetic fallback model.'
            )
        )
    artifact_resolution_seconds = round(perf_counter() - artifact_resolution_started_at, 3)

    forecast_start_env = str(os.getenv('FORECAST_START_DATE') or '').strip()
    if forecast_start_env:
        try:
            forecast_date = pd.Timestamp(forecast_start_env).tz_localize('UTC')
        except Exception:
            forecast_date = pd.Timestamp(datetime.now(timezone.utc))
        print(f'[daily_inference] Hindcast mode: forecast_date={forecast_date.isoformat()}', file=sys.stderr)
    else:
        forecast_date = pd.Timestamp(datetime.now(timezone.utc))
    regions = load_regions()

    # F1: Seismic Cascade Integrator — fetch recent earthquakes for Himalayan bbox
    seismic_events: list[Any] = []
    try:
        seismic_events = fetch_recent_earthquakes(HIMALAYAN_BBOX)
        if seismic_events:
            print(f'[seismic] Found {len(seismic_events)} recent earthquakes (M>={SEISMIC_MIN_MAGNITUDE})')
    except Exception as exc:
        print(f'[seismic] Warning: could not fetch seismic data: {exc}', file=sys.stderr)

    requested_region_keys = [
        str(region_key).strip()
        for region_key in args.region_key
        if str(region_key).strip()
    ]
    if proof_options.enabled and not requested_region_keys:
        raise RuntimeError('lifeboat_mode requires at least one --region-key')
    if requested_region_keys:
        region_map = {region.key: region for region in regions}
        missing_region_keys = [
            region_key for region_key in requested_region_keys
            if region_key not in region_map
        ]
        if missing_region_keys:
            raise RuntimeError(f'Unknown region_key(s): {", ".join(missing_region_keys)}')
        seen_region_keys: set[str] = set()
        regions = [
            region_map[region_key]
            for region_key in requested_region_keys
            if not (region_key in seen_region_keys or seen_region_keys.add(region_key))
        ]
    candidate_summary = build_dynamic_model_candidate(
        bundle,
        artifact_dir=artifact_dir,
        model_status_version=f'forecast-{artifact_dir.name}',
    )
    evidence_summary = build_autonomous_evidence_summary(
        bundle.get('dataset_manifest') if isinstance(bundle.get('dataset_manifest'), dict) else {},
        sar_volume_stats=candidate_summary.get('sar_volume_stats') if isinstance(candidate_summary, dict) else None,
    )
    active_model_state = resolve_active_model_state(current_model_status, candidate_summary, bundle, publication_gates_passed=False)

    outputs = []
    stage_metrics_payload: dict[str, Any] = {
        'artifact_dir': str(artifact_dir),
        'artifact_resolution_seconds': artifact_resolution_seconds,
        'proof_mode': proof_options.as_metadata(),
        'regions': [],
    }

    # F16: SACHET RSS feed ingestion — fetch national NDMA alerts once before the
    # per-region loop. The SACHET feed is national (all India), not region-specific,
    # so calling it per region was redundant and added ~3 min × 11 regions = ~33 min
    # of unnecessary network calls per CI run.
    global_sachet_rss_summary: dict[str, Any] | None = None
    if SACHET_RSS_ENABLED:
        try:
            rss_cfg = SachetRssConfig()
            rss_alerts, rss_error = ingest_sachet_alerts(rss_cfg)
            global_sachet_rss_summary = get_sachet_alert_summary(
                rss_alerts, fetch_error=rss_error, config=rss_cfg,
            )
            rss_count = len(rss_alerts)
            print(f'[daily_inference] F16: SACHET RSS feed ingested once (national) — {rss_count} current alerts', file=sys.stderr)
        except Exception as rss_exc:
            global_sachet_rss_summary = {'enabled': True, 'ingested': False, 'error': str(rss_exc)}
            print(f'[daily_inference] F16: SACHET RSS feed ingestion failed: {rss_exc}', file=sys.stderr)

    for region in regions:
        region_stage_metrics: dict[str, Any] = {
            'region_key': region.key,
            'compute_started_at': datetime.now(timezone.utc).isoformat(),
        }
        try:
            hourly_grid_started_at = perf_counter()
            hourly_grids, ensemble_profile = build_hourly_grids(
                region,
                bundle,
                grid_size=args.grid_size,
                forecast_date=forecast_date,
                horizon_hours=args.forecast_hours,
                artifact_dir=artifact_dir,
                use_dynamic_inference=bool(active_model_state.get('use_dynamic_inference')),
                proof_options=proof_options,
                snowpack_proxy_mode=str(args.snowpack_proxy_mode),
                stage_metrics=region_stage_metrics,
                seismic_events=seismic_events,
            )
            region_stage_metrics['hourly_grid_build_seconds'] = round(perf_counter() - hourly_grid_started_at, 3)
            rows = hourly_grids[0] if hourly_grids else []
            payload = upsert_forecast_grid(
                region,
                bundle,
                forecast_date,
                rows,
                len(hourly_grids) or args.forecast_hours,
                hourly_grids=hourly_grids,
                artifact_dir=artifact_dir,
                grid_size=args.grid_size,
                dry_run=bool(args.dry_run),
                active_model_state=active_model_state,
                candidate_summary=candidate_summary,
                evidence_summary=evidence_summary,
                proof_options=proof_options,
                stage_metrics=region_stage_metrics,
                ensemble_profile=ensemble_profile,
                seismic_events=seismic_events,
            )
            region_stage_metrics['forecast_run_id'] = (payload.get('model_metadata') or {}).get('forecast_run_id')
            region_stage_metrics['status'] = payload.get('status')
            region_stage_metrics['ready_cell_count'] = int(payload.get('ready_cell_count') or 0)
            region_stage_metrics['stale_cell_count'] = int(payload.get('stale_cell_count') or 0)

            # F22: CAP 1.2 Alert Generation
            max_risk = max(
                (cell.get('risk_score', 0) for cell in (payload.get('grid_geojson') or [])),
                default=0,
            )
            cap_alert_generated = False
            cap_alert_danger_level = 0
            if CAP_ENABLED and should_trigger_alert(max_risk):
                cap_alert_danger_level = int(max_risk)
                try:
                    cap_xml = generate_multi_language_cap(
                        identifier=f'avhub-{region.key}-{forecast_date.strftime("%Y%m%d")}',
                        sender='avalanche-insight-hub@system',
                        region_name=region.name,
                        region_key=region.key,
                        bbox=list(region.bbox),
                        forecast_date=forecast_date.strftime('%Y-%m-%d'),
                        horizon_hours=len(hourly_grids) or args.forecast_hours,
                        max_danger_level=cap_alert_danger_level,
                    )
                    valid, err = validate_cap_xml(cap_xml)
                    if valid:
                        cap_path = artifact_dir / f'cap_alert_{region.key}.xml'
                        cap_path.write_text(cap_xml, encoding='utf-8')
                        cap_alert_generated = True
                        print(f'[daily_inference] F22: CAP alert generated for {region.key} (danger level {cap_alert_danger_level})', file=sys.stderr)
                    else:
                        print(f'[daily_inference] F22: CAP XML validation failed: {err}', file=sys.stderr)
                except Exception as cap_exc:
                    print(f'[daily_inference] F22: CAP alert generation failed: {cap_exc}', file=sys.stderr)
            payload.setdefault('model_metadata', {})['cap_alert_generated'] = cap_alert_generated
            payload['model_metadata']['cap_alert_danger_level'] = cap_alert_danger_level

            # F16: SACHET Push — disseminate alert via NDMA Sachet RSS feed
            sachet_metadata: dict[str, Any] = {
                'enabled': False,
                'pushed': False,
                'alerts_sent': 0,
                'results': [],
                'error': None,
                'rss_ingest': None,
            }
            if (SACHET_ENABLED or SACHET_RSS_ENABLED) and cap_alert_generated:
                try:
                    sachet_alerts = build_multi_language_alerts(
                        region_name=region.name,
                        danger_level=cap_alert_danger_level,
                        bbox=list(region.bbox),
                    )
                    sachet_cfg = SachetConfig()
                    push_results = []
                    for sa_alert in sachet_alerts:
                        result = push_sachet_alert(sa_alert, config=sachet_cfg)
                        push_results.append({
                            'language': sa_alert.language,
                            'success': result.success,
                            'message_id': result.message_id,
                            'error': result.error,
                            'channel': result.channel,
                        })
                    sachet_metadata = {
                        'enabled': True,
                        'pushed': any(r['success'] for r in push_results),
                        'alerts_sent': sum(1 for r in push_results if r['success']),
                        'results': push_results,
                        'error': None,
                        'rss_ingest': None,
                    }
                    sent_count = sachet_metadata['alerts_sent']
                    print(f'[daily_inference] F16: SACHET push completed — {sent_count}/{len(sachet_alerts)} alerts sent', file=sys.stderr)
                except Exception as sachet_exc:
                    sachet_metadata['error'] = str(sachet_exc)
                    print(f'[daily_inference] F16: SACHET push failed: {sachet_exc}', file=sys.stderr)

            # F16: SACHET RSS feed ingestion — use pre-fetched national summary
            if global_sachet_rss_summary is not None:
                sachet_metadata['rss_ingest'] = global_sachet_rss_summary

            payload['model_metadata']['sachet_push'] = sachet_metadata

            # F15: AAVDS — fetch victim detection events from feed
            aavds_metadata: dict[str, Any] = {
                'enabled': False,
                'events': [],
                'event_count': 0,
                'error': None,
            }
            if AAVDS_ENABLED:
                try:
                    adapter = AAVDSAdapter()
                    adapter.ingest_rest()
                    bbox = region.bbox
                    region_events = adapter.get_events_in_bounds(
                        min_lat=float(bbox[1]),
                        max_lat=float(bbox[3]),
                        min_lng=float(bbox[0]),
                        max_lng=float(bbox[2]),
                    )
                    aavds_metadata = {
                        'enabled': True,
                        'events': [
                            {
                                'event_id': e.event_id,
                                'timestamp': e.timestamp.isoformat(),
                                'lat': e.lat,
                                'lng': e.lng,
                                'detection_confidence': e.detection_confidence,
                                'signal_type': e.signal_type,
                                'victim_id': e.victim_id,
                                'burial_depth_m': e.burial_depth_m,
                                'signal_strength_db': e.signal_strength_db,
                                'source': e.source,
                            }
                            for e in region_events
                        ],
                        'event_count': len(region_events),
                        'error': None,
                    }
                    print(f'[daily_inference] F15: AAVDS fetched {len(region_events)} events for {region.key}', file=sys.stderr)
                except Exception as aavds_exc:
                    aavds_metadata['error'] = str(aavds_exc)
                    print(f'[daily_inference] F15: AAVDS fetch failed: {aavds_exc}', file=sys.stderr)
            payload['model_metadata']['aavds'] = aavds_metadata

            # F18: Citizen Science — fetch recent community reports
            citizen_metadata: dict[str, Any] = {
                'enabled': False,
                'reports': [],
                'report_count': 0,
                'error': None,
            }
            if CITIZEN_SCIENCE_ENABLED and has_supabase_credentials() and not args.dry_run:
                try:
                    from backend.common.supabase_utils import rest_get
                    reports_data = rest_get(
                        'field_reports',
                        params={
                            'region_key': 'eq.' + region.key,
                            'order': 'created_at.desc',
                            'limit': '20',
                        },
                    )
                    citizen_reports = []
                    for row in (reports_data or []):
                        photo_url = row.get('photo_url')
                        citizen_reports.append({
                            'report_id': str(row.get('report_id', row.get('id', ''))),
                            'lat': float(row.get('lat', 0.0)),
                            'lng': float(row.get('lng', 0.0)),
                            'timestamp': str(row.get('created_at', row.get('timestamp', ''))),
                            'description': str(row.get('description', '')),
                            'status': str(row.get('review_status', row.get('status', 'pending'))),
                            'hazard_type': str(row.get('hazard_type', 'avalanche')),
                            'estimated_size': row.get('estimated_size'),
                            'confidence': float(row.get('confidence', 0.3)),
                            'has_photo': bool(photo_url),
                            'photo_url': photo_url,
                        })
                    citizen_metadata = {
                        'enabled': True,
                        'reports': citizen_reports,
                        'report_count': len(citizen_reports),
                        'error': None,
                    }
                    print(f'[daily_inference] F18: Fetched {len(citizen_reports)} citizen reports for {region.key}', file=sys.stderr)
                except Exception as citizen_exc:
                    citizen_metadata['error'] = str(citizen_exc)
                    print(f'[daily_inference] F18: Citizen science fetch failed: {citizen_exc}', file=sys.stderr)
            payload['model_metadata']['citizen_science'] = citizen_metadata

            # F7: Sensor Ingestion — fetch ground radar events from REST feed
            sensor_metadata: dict[str, Any] = {
                'enabled': False,
                'events': [],
                'event_count': 0,
                'error': None,
            }
            if SENSOR_ENABLED:
                try:
                    sensor_events = fetch_sensor_events_rest()
                    bbox = region.bbox
                    region_sensor_events = [
                        e for e in sensor_events
                        if float(bbox[1]) <= e.lat <= float(bbox[3])
                        and float(bbox[0]) <= e.lng <= float(bbox[2])
                    ]
                    sensor_metadata = {
                        'enabled': True,
                        'events': [e.to_dict() for e in region_sensor_events],
                        'event_count': len(region_sensor_events),
                        'error': None,
                    }
                    print(f'[daily_inference] F7: Fetched {len(region_sensor_events)} sensor events for {region.key}', file=sys.stderr)
                except Exception as sensor_exc:
                    sensor_metadata['error'] = str(sensor_exc)
                    print(f'[daily_inference] F7: Sensor fetch failed: {sensor_exc}', file=sys.stderr)
            payload['model_metadata']['sensor_events'] = sensor_metadata

            # Post-publication metadata update — persist new metadata to forecast_runs
            post_pub_metadata = {
                'sachet_push': sachet_metadata,
                'aavds': aavds_metadata,
                'citizen_science': citizen_metadata,
                'sensor_events': sensor_metadata,
            }
            if has_supabase_credentials() and not args.dry_run:
                try:
                    import requests as _req
                    from backend.common.supabase_io import _base_url, _headers
                    _run_id = (payload.get('model_metadata') or {}).get('forecast_run_id')
                    if _run_id and _run_id != 'uq_blocked':
                        updated_metadata = {**(payload.get('model_metadata') or {}), **post_pub_metadata}
                        _req.patch(
                            f'{_base_url()}/rest/v1/forecast_runs?id=eq.{_run_id}',
                            headers={**_headers(), 'Content-Type': 'application/json', 'Prefer': 'return=minimal'},
                            json={'model_metadata': updated_metadata},
                            timeout=30,
                        )
                except Exception as patch_exc:
                    print(f'[daily_inference] Post-publication metadata PATCH failed: {patch_exc}', file=sys.stderr)

            outputs.append(payload)
        except Exception as region_exc:
            tb_str = traceback.format_exc()
            print(
                f'[daily_inference] Region {region.key} FAILED: {region_exc}\n{tb_str}',
                file=sys.stderr,
            )
            print(
                f'::error::Region {region.key} inference failed: {region_exc}. '
                f'Check logs for full traceback. Continuing to next region.',
                file=sys.stderr,
            )
            region_stage_metrics['status'] = 'failed'
            region_stage_metrics['error'] = str(region_exc)
            region_stage_metrics['traceback'] = tb_str
            outputs.append({
                'hazard_type': 'avalanche',
                'region_key': region.key,
                'region_name': region.name,
                'status': 'failed',
                'model_metadata': {'region_key': region.key, 'error': str(region_exc)},
                'grid_geojson': [],
                'ready_cell_count': 0,
                'stale_cell_count': 0,
            })
        stage_metrics_payload['regions'].append(region_stage_metrics)

    # F19: Continuous Learning Loop — auto-label new detections
    auto_label_count = 0
    if CONTINUOUS_LEARNING_ENABLED:
        for payload in outputs:
            region_key = (payload.get('model_metadata') or {}).get('region_key', 'unknown')
            sar_dets = payload.get('sar_detections') or []
            seismic_events_list = payload.get('seismic_events') or []
            field_reports_list = payload.get('field_reports') or []
            if sar_dets or seismic_events_list or field_reports_list:
                cl_result = process_detections_for_learning(
                    sar_detections=sar_dets,
                    seismic_events=seismic_events_list,
                    field_reports=field_reports_list,
                    region_key=region_key,
                )
                auto_label_count += cl_result.labels_created
        if auto_label_count > 0:
            print(f'[daily_inference] F19: Auto-labeled {auto_label_count} new training labels', file=sys.stderr)
    stage_metrics_payload['auto_labels_created'] = auto_label_count

    # RAvaFcast candidate pipeline gate — metadata only, does not alter active path
    _ravafcast_gate_status = check_pipeline_status()
    stage_metrics_payload['ravafcast_gate'] = emit_gate_metadata(_ravafcast_gate_status)

    dump_json(artifact_dir / 'forecast_grids.json', outputs)
    dump_json(artifact_dir / 'inference_stage_metrics.json', stage_metrics_payload)

    inference_manifest = {
        'artifact_dir': str(artifact_dir),
        'compute_job_id': str(os.getenv('COMPUTE_JOB_ID') or os.getenv('JOB_ID') or '').strip() or None,
        'modal_call_id': str(os.getenv('MODAL_CALL_ID') or '').strip() or None,
        'regions_written': len(outputs),
        'total_cells_written': sum(len(payload.get('grid_geojson') or []) for payload in outputs),
        'partial_regions': sum(1 for payload in outputs if payload.get('status') == 'partial'),
        'stale_regions': sum(1 for payload in outputs if payload.get('status') == 'stale'),
        'ready_cells': sum(int(payload.get('ready_cell_count') or 0) for payload in outputs),
        'stale_cells': sum(
            1
            for payload in outputs
            for cell in (payload.get('grid_geojson') or [])
            if cell.get('status') != 'ready'
        ),
        'unavailable_terrain_cells': sum(int(payload.get('unavailable_terrain_cell_count') or 0) for payload in outputs),
        'unavailable_weather_cells': sum(int(payload.get('unavailable_weather_cell_count') or 0) for payload in outputs),
        'dry_run': bool(args.dry_run),
        'stage_metrics_summary': {
            'artifact_resolution_seconds': artifact_resolution_seconds,
            'lifeboat_mode': proof_options.enabled,
            'lifeboat_profile': proof_options.profile if proof_options.enabled else None,
            'region_count': len(stage_metrics_payload['regions']),
            'snowpack_fetch_seconds_total': round(
                sum(float(region_metric.get('snowpack_fetch_seconds') or 0.0) for region_metric in stage_metrics_payload['regions']),
                3,
            ),
            'runout_generation_seconds_total': round(
                sum(float(region_metric.get('runout_generation_seconds') or 0.0) for region_metric in stage_metrics_payload['regions']),
                3,
            ),
            'hourly_grid_build_seconds_total': round(
                sum(float(region_metric.get('hourly_grid_build_seconds') or 0.0) for region_metric in stage_metrics_payload['regions']),
                3,
            ),
            'publication_seconds_total': round(
                sum(float(region_metric.get('publication_seconds') or 0.0) for region_metric in stage_metrics_payload['regions']),
                3,
            ),
            'compatibility_seconds_total': round(
                sum(float(region_metric.get('compatibility_seconds') or 0.0) for region_metric in stage_metrics_payload['regions']),
                3,
            ),
            'promotion_seconds_total': round(
                sum(float(region_metric.get('promotion_seconds') or 0.0) for region_metric in stage_metrics_payload['regions']),
                3,
            ),
        },
        'forecast_run_id': next(
            (
                (payload.get('model_metadata') or {}).get('forecast_run_id')
                for payload in outputs
                if isinstance(payload.get('model_metadata'), dict) and (payload.get('model_metadata') or {}).get('forecast_run_id')
            ),
            None,
        ),
        'forecast_run_ids': [
            str((payload.get('model_metadata') or {}).get('forecast_run_id'))
            for payload in outputs
            if isinstance(payload.get('model_metadata'), dict) and (payload.get('model_metadata') or {}).get('forecast_run_id')
        ],
        'forecast_run_ids_by_region': {
            str(payload.get('region_key')): str((payload.get('model_metadata') or {}).get('forecast_run_id'))
            for payload in outputs
            if isinstance(payload.get('model_metadata'), dict) and payload.get('region_key') and (payload.get('model_metadata') or {}).get('forecast_run_id')
        },
        'regions': [
            {
                'region_key': payload.get('region_key'),
                'region_name': payload.get('region_name'),
                'forecast_run_id': (payload.get('model_metadata') or {}).get('forecast_run_id'),
                'forecast_date': payload.get('forecast_date'),
                'horizon_hours': payload.get('horizon_hours'),
                'status': payload.get('status'),
                'cell_count': len(payload.get('grid_geojson') or []),
                'ready_cell_count': int(payload.get('ready_cell_count') or 0),
                'stale_cell_count': int(payload.get('stale_cell_count') or 0),
                'unavailable_terrain_cell_count': int(payload.get('unavailable_terrain_cell_count') or 0),
                'unavailable_weather_cell_count': int(payload.get('unavailable_weather_cell_count') or 0),
                'runout_method_sample': (payload.get('model_metadata') or {}).get('runout_method_sample'),
                'runout_method_counts': (payload.get('model_metadata') or {}).get('runout_method_counts'),
                'snowpack_proxy_mode': str(args.snowpack_proxy_mode),
                'training_dataset_version': (payload.get('model_metadata') or {}).get('training_dataset_version'),
                'lifeboat_mode': (payload.get('model_metadata') or {}).get('lifeboat_mode'),
                'lifeboat_profile': (payload.get('model_metadata') or {}).get('lifeboat_profile'),
            }
            for payload in outputs
        ],
        'active_model_type': active_model_state.get('active_model_type'),
        'active_model_version': active_model_state.get('active_model_version'),
        'dynamic_model_candidate': candidate_summary,
        'autonomous_evidence_summary': evidence_summary,
        'completed_at': datetime.now(timezone.utc).isoformat(),
    }
    latest_benchmark_summary = build_latest_benchmark_summary(
        benchmark_kind='inference_publication',
        phase_breakdown_seconds={
            'artifact_resolution_seconds': artifact_resolution_seconds,
            'snowpack_fetch_seconds_total': float(inference_manifest['stage_metrics_summary']['snowpack_fetch_seconds_total']),
            'runout_generation_seconds_total': float(inference_manifest['stage_metrics_summary']['runout_generation_seconds_total']),
            'hourly_grid_build_seconds_total': float(inference_manifest['stage_metrics_summary']['hourly_grid_build_seconds_total']),
            'publication_seconds_total': float(inference_manifest['stage_metrics_summary']['publication_seconds_total']),
            'compatibility_seconds_total': float(inference_manifest['stage_metrics_summary']['compatibility_seconds_total']),
            'promotion_seconds_total': float(inference_manifest['stage_metrics_summary']['promotion_seconds_total']),
        },
        input_context={
            'forecast_hours': int(args.forecast_hours),
            'grid_size': int(args.grid_size),
            'snowpack_proxy_mode': str(args.snowpack_proxy_mode),
            'region_count': len(outputs),
            'dry_run': bool(args.dry_run),
            'lifeboat_mode': bool(proof_options.enabled),
        },
        status='ok',
        artifact_ref=str(artifact_dir / 'inference_stage_metrics.json'),
    )
    inference_manifest['latest_benchmark_summary'] = latest_benchmark_summary
    dump_json(artifact_dir / 'inference_manifest.json', inference_manifest)
    publication_proof_generated_at = datetime.now(timezone.utc)
    publication_proof = build_publication_proof(
        outputs=outputs,
        generated_at=publication_proof_generated_at,
        dry_run=bool(args.dry_run),
        supabase_enabled=has_supabase_credentials(),
        expected_forecast_date=forecast_date.date().isoformat(),
        artifact_dir=artifact_dir,
        expected_grid_size=int(args.grid_size),
        require_full_grid=bool(args.require_full_grid_publication),
    )
    dump_json(artifact_dir / 'publication_proof.json', publication_proof)
    required_proof_status = publication_proof.get('proof_status')
    if (
        bool(args.dry_run)
        and args.require_full_grid_publication
        and not args.require_same_day_publication
    ):
        required_proof_status = publication_proof.get('compute_proof_status')
    if (args.require_same_day_publication or args.require_full_grid_publication) and required_proof_status != 'passed':
        failures = publication_proof.get('failures')
        raise RuntimeError(
            'publication proof failed for region(s): '
            + ', '.join(str(item) for item in failures if item)
        )

    if has_supabase_credentials() and not args.dry_run:
        next_run = (datetime.now(timezone.utc) + pd.Timedelta(hours=24)).isoformat()
        bundle_metrics = bundle.get('metrics') if isinstance(bundle.get('metrics'), dict) else {}
        patch_latest_model_status_row({
            'version': f"forecast-{artifact_dir.name}",
            'last_inference': datetime.now(timezone.utc).isoformat(),
            'capability_summary': 'batch-only forecast_grids',
            'inference_backend': 'batch_async',
            'capabilities': {
                'serving_mode': 'batch_only',
                'serving_summary': 'batch-only forecast_grids',
                'runtime_mode': 'batch_async',
                'runtime_summary': 'batch async precompute via forecast_grids',
            },
            'feature_version': str(bundle.get('dynamic_model_type') or 'surrogate_rf_v1'),
            'calibration_profile_version': str(bundle.get('dynamic_model_version') or bundle.get('created_at')),
            'threshold_profile_version': 'chebyshev_ipa_v2',
            'pss_reported': bundle_metrics.get('pss_reported'),
            'pss_gate_passed': bundle_metrics.get('pss_gate_passed'),
            'promotion_gate_passed': active_model_state.get('promotion_gate_passed'),
            'shadow_mode_active': active_model_state.get('shadow_mode_active'),
            'active_model_type': active_model_state.get('active_model_type'),
            'active_model_version': active_model_state.get('active_model_version'),
            'dynamic_model_candidate': candidate_summary,
            'autonomous_evidence_summary': evidence_summary,
            'stability_summary': bundle.get('stability_summary') if isinstance(bundle.get('stability_summary'), dict) else {},
            'drift_mode_state': build_drift_mode_state(candidate_summary if isinstance(candidate_summary, dict) else {}),
            'latest_benchmark_summary': latest_benchmark_summary,
            'next_run': next_run,
        })

    print(json.dumps(inference_manifest, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
