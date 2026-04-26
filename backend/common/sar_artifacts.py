from __future__ import annotations

from typing import Any

from backend.common.supabase_io import has_supabase_credentials, rest_insert


def _feature_record(event: dict[str, Any]) -> dict[str, Any]:
    features = event.get('features')
    return features if isinstance(features, dict) else {}


def build_sar_artifact_records(
    inserted_events: list[dict[str, Any]],
    source_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for inserted, source in zip(inserted_events, source_events):
        event_id = inserted.get('id')
        if not event_id:
            continue
        features = _feature_record(source)
        scene_ids = source.get('source_scene_ids') or features.get('sar_scene_ids') or []
        if not isinstance(scene_ids, list):
            scene_ids = []
        centroid = features.get('sar_centroid')
        if not isinstance(centroid, dict):
            centroid = {}
        geometry = features.get('sar_geometry')
        if not isinstance(geometry, dict):
            geometry = {}
        artifacts.append({
            'avalanche_event_id': event_id,
            'region_key': str(features.get('region_key') or 'unknown'),
            'scene_time': features.get('sar_scene_time'),
            'source_scene_ids': [str(scene_id) for scene_id in scene_ids if scene_id],
            'detection_geometry': geometry,
            'centroid_summary': centroid,
            'model_version': str(source.get('source_model') or 'unknown'),
            'confidence_score': float(
                source.get('label_confidence')
                or source.get('confidence')
                or 0.0
            ),
            'provenance': {
                'source': source.get('source'),
                'fusion_source': source.get('fusion_source'),
                'mask_asset_ref': source.get('mask_asset_ref'),
                'geometry_type': source.get('geometry_type'),
                'training_eligible': source.get('training_eligible'),
                'training_eligible_reason': source.get('training_eligible_reason'),
                'features': {
                    'sar_coverage_state': features.get('sar_coverage_state'),
                    'shadow_mask_applied': features.get('shadow_mask_applied'),
                    'fusion_method': features.get('fusion_method'),
                },
            },
            'mask_asset_ref': source.get('mask_asset_ref'),
            'geometry_type': str(source.get('geometry_type') or 'polygon'),
        })
    return artifacts


def persist_sar_artifacts(
    inserted_events: list[dict[str, Any]],
    source_events: list[dict[str, Any]],
) -> int:
    artifacts = build_sar_artifact_records(inserted_events, source_events)
    if not artifacts or not has_supabase_credentials():
        return 0
    rest_insert('sar_detection_artifacts', artifacts)
    return len(artifacts)
