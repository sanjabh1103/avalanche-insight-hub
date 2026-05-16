from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from backend.common.european_shadow_sources import (
    SAR_MANIFEST_LANES,
    build_sar_training_manifest_from_staged_records,
    get_european_source,
    normalize_staged_european_record,
)

try:  # pragma: no cover - optional at import time, covered when installed
    import shapefile  # type: ignore
except Exception:  # pragma: no cover
    shapefile = None


EUROPEAN_SHADOW_STAGING_MANIFEST_VERSION = 'european_shadow_staging_manifest_v1'
DEFAULT_SAR_SPLIT = 'val'
SUPPORTED_TEXT_SUFFIXES = {'.csv', '.json', '.jsonl', '.ndjson', '.geojson'}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def compute_raw_checksum_manifest(raw_path: Path) -> dict[str, Any]:
    path = raw_path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f'raw_path not found: {path}')
    if path.is_dir():
        files = []
        total_bytes = 0
        for file_path in sorted(item for item in path.rglob('*') if item.is_file()):
            size = file_path.stat().st_size
            total_bytes += size
            files.append({
                'relative_path': file_path.relative_to(path).as_posix(),
                'size_bytes': size,
                'sha256': sha256_file(file_path),
            })
        return {
            'version': 'raw_checksum_manifest_v1',
            'path': str(path),
            'path_type': 'directory',
            'file_count': len(files),
            'total_bytes': total_bytes,
            'files': files,
        }
    payload: dict[str, Any] = {
        'version': 'raw_checksum_manifest_v1',
        'path': str(path),
        'path_type': 'file',
        'size_bytes': path.stat().st_size,
        'sha256': sha256_file(path),
    }
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            payload['zip_members'] = [
                {
                    'filename': info.filename,
                    'size_bytes': info.file_size,
                    'crc': f'{info.CRC:08x}',
                }
                for info in archive.infolist()
                if not info.is_dir()
            ]
    return payload


def stage_european_source(
    *,
    source_key: str,
    raw_path: Path,
    license_review_id: str,
    output_root: Path,
    snapshot_id: str,
    requested_role: str | None = None,
    sar_split: str = DEFAULT_SAR_SPLIT,
) -> dict[str, Any]:
    source = get_european_source(source_key)
    review_id = _clean_string(license_review_id)
    if source.requires_license_review and not review_id:
        raise ValueError(f'source "{source.source_key}" requires a license_review_id for staging into shadow reports')

    role = _clean_string(requested_role) or source.default_training_role
    checksum_manifest = compute_raw_checksum_manifest(raw_path)
    rows = list(_iter_source_rows(raw_path.expanduser().resolve(), source_key=source.source_key))
    if not rows:
        raise ValueError(f'no parseable records found for source "{source.source_key}" under {raw_path}')

    records = [
        normalize_staged_european_record(
            _build_normalization_payload(
                source_key=source.source_key,
                source_regions=source.region_keys,
                raw=row,
                index=index,
                license_review_id=review_id,
            ),
            requested_role=role,
        )
        for index, row in enumerate(rows, start=1)
    ]

    stage_dir = output_root.expanduser().resolve() / str(snapshot_id) / source.source_key
    stage_dir.mkdir(parents=True, exist_ok=True)
    checksum_path = stage_dir / 'checksum_manifest.json'
    records_path = stage_dir / 'staged_records.jsonl'
    manifest_path = stage_dir / 'staged_manifest.json'
    checksum_path.write_text(json.dumps(checksum_manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    _write_jsonl(records_path, records)

    sar_manifest_path: Path | None = None
    sar_records = [
        record
        for record in records
        if record.get('data_lane') in SAR_MANIFEST_LANES
        and _asset_ref(record, 'stack_ref')
        and _asset_ref(record, 'truth_mask_ref')
        and '#' not in _asset_ref(record, 'stack_ref')
        and '#' not in _asset_ref(record, 'truth_mask_ref')
    ]
    if sar_records:
        sar_manifest = build_sar_training_manifest_from_staged_records(
            sar_records,
            dataset_version=f'{snapshot_id}-{source.source_key}-sar',
            split=sar_split,
        )
        sar_manifest_path = stage_dir / 'sar_training_manifest.json'
        sar_manifest_path.write_text(json.dumps(sar_manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    generated_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        'version': EUROPEAN_SHADOW_STAGING_MANIFEST_VERSION,
        'snapshot_id': str(snapshot_id),
        'generated_at': generated_at,
        'source_key': source.source_key,
        'source': source.as_manifest_dict(),
        'requested_role': role,
        'license_review_id': review_id,
        'production_scoring_allowed': False,
        'raw_checksum_manifest_path': str(checksum_path),
        'records_jsonl': str(records_path),
        'record_count': len(records),
        'sample_records': records[:5],
        'sar_training_manifest_path': str(sar_manifest_path) if sar_manifest_path is not None else None,
        'sar_training_manifest_scene_count': len(sar_records),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return manifest


def load_staged_records(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    records_path = Path(str(manifest.get('records_jsonl') or '')).expanduser()
    if not records_path.exists():
        raise FileNotFoundError(f'staged records JSONL not found: {records_path}')
    records: list[dict[str, Any]] = []
    for line in records_path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        parsed = json.loads(line)
        if not isinstance(parsed, dict):
            raise ValueError(f'staged records JSONL contains a non-object row in {records_path}')
        records.append(parsed)
    return records


def _iter_source_rows(raw_path: Path, *, source_key: str) -> Iterator[dict[str, Any]]:
    if raw_path.is_dir():
        for file_path in sorted(item for item in raw_path.rglob('*') if item.is_file()):
            yield from _iter_file_rows(file_path, source_key=source_key, asset_prefix=str(file_path))
        return
    if zipfile.is_zipfile(raw_path):
        yield from _iter_zip_rows(raw_path, source_key=source_key)
        return
    yield from _iter_file_rows(raw_path, source_key=source_key, asset_prefix=str(raw_path))


def _iter_file_rows(path: Path, *, source_key: str, asset_prefix: str) -> Iterator[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == '.csv':
        yield from _rows_from_csv(path.read_text(encoding='utf-8-sig'), asset_ref=asset_prefix)
    elif suffix in {'.json', '.geojson'}:
        yield from _rows_from_json(json.loads(path.read_text(encoding='utf-8')), asset_ref=asset_prefix)
    elif suffix in {'.jsonl', '.ndjson'}:
        for index, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
            if line.strip():
                row = json.loads(line)
                if isinstance(row, dict):
                    yield {**row, '__asset_ref': f'{asset_prefix}#line-{index}', '__source_format': suffix[1:]}
    elif suffix == '.shp':
        yield from _rows_from_shapefile_path(path, asset_ref=asset_prefix)
    elif source_key == 'avalcd_zenodo_v1':
        yield from _avalcd_archive_records([path.name], asset_ref=str(path))


def _iter_zip_rows(path: Path, *, source_key: str) -> Iterator[dict[str, Any]]:
    emitted = False
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if not name.endswith('/')]
        for name in sorted(names):
            suffix = Path(name).suffix.lower()
            if suffix not in SUPPORTED_TEXT_SUFFIXES:
                continue
            asset_ref = f'{path}#{name}'
            payload = archive.read(name)
            if suffix == '.csv':
                for row in _rows_from_csv(payload.decode('utf-8-sig'), asset_ref=asset_ref):
                    emitted = True
                    yield row
            elif suffix in {'.json', '.geojson'}:
                for row in _rows_from_json(json.loads(payload.decode('utf-8')), asset_ref=asset_ref):
                    emitted = True
                    yield row
            elif suffix in {'.jsonl', '.ndjson'}:
                for index, line in enumerate(payload.decode('utf-8').splitlines(), start=1):
                    if line.strip():
                        row = json.loads(line)
                        if isinstance(row, dict):
                            emitted = True
                            yield {**row, '__asset_ref': f'{asset_ref}#line-{index}', '__source_format': suffix[1:]}
        for row in _rows_from_zipped_shapefiles(archive, path):
            emitted = True
            yield row
        if not emitted and source_key == 'avalcd_zenodo_v1':
            yield from _avalcd_archive_records(names, asset_ref=str(path))


def _rows_from_csv(text: str, *, asset_ref: str) -> Iterator[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    for index, row in enumerate(reader, start=1):
        yield {
            **{str(key): value for key, value in row.items() if key is not None},
            '__asset_ref': f'{asset_ref}#row-{index}',
            '__source_format': 'csv',
        }


def _rows_from_json(payload: Any, *, asset_ref: str) -> Iterator[dict[str, Any]]:
    if isinstance(payload, dict) and payload.get('type') == 'FeatureCollection':
        features = payload.get('features') if isinstance(payload.get('features'), list) else []
        for index, feature in enumerate(features, start=1):
            if not isinstance(feature, dict):
                continue
            props = feature.get('properties') if isinstance(feature.get('properties'), dict) else {}
            yield {
                **props,
                '__geometry': feature.get('geometry'),
                '__asset_ref': f'{asset_ref}#feature-{index}',
                '__source_format': 'geojson',
            }
        return
    if isinstance(payload, dict) and isinstance(payload.get('features'), list):
        yield from _rows_from_json({'type': 'FeatureCollection', 'features': payload['features']}, asset_ref=asset_ref)
        return
    if isinstance(payload, dict):
        for key in ('records', 'scenes', 'detections', 'events', 'bulletins', 'data', 'items'):
            items = payload.get(key)
            if isinstance(items, list):
                for index, item in enumerate(items, start=1):
                    if isinstance(item, dict):
                        yield {**item, '__asset_ref': f'{asset_ref}#{key}-{index}', '__source_format': 'json'}
                return
        yield {**payload, '__asset_ref': asset_ref, '__source_format': 'json'}
        return
    if isinstance(payload, list):
        for index, item in enumerate(payload, start=1):
            if isinstance(item, dict):
                yield {**item, '__asset_ref': f'{asset_ref}#item-{index}', '__source_format': 'json'}


def _rows_from_shapefile_path(path: Path, *, asset_ref: str) -> Iterator[dict[str, Any]]:
    if shapefile is None:
        raise RuntimeError('pyshp is required to parse shapefiles')
    reader = shapefile.Reader(str(path))
    yield from _rows_from_shapefile_reader(reader, asset_ref=asset_ref)


def _rows_from_zipped_shapefiles(archive: zipfile.ZipFile, zip_path: Path) -> Iterator[dict[str, Any]]:
    if shapefile is None:
        return
    names = {name: name for name in archive.namelist() if not name.endswith('/')}
    bases = sorted({str(Path(name).with_suffix('')) for name in names if Path(name).suffix.lower() == '.shp'})
    for base in bases:
        shp_name = f'{base}.shp'
        dbf_name = f'{base}.dbf'
        shx_name = f'{base}.shx'
        if shp_name not in names or dbf_name not in names:
            continue
        reader_kwargs = {
            'shp': io.BytesIO(archive.read(shp_name)),
            'dbf': io.BytesIO(archive.read(dbf_name)),
        }
        if shx_name in names:
            reader_kwargs['shx'] = io.BytesIO(archive.read(shx_name))
        reader = shapefile.Reader(**reader_kwargs)
        yield from _rows_from_shapefile_reader(reader, asset_ref=f'{zip_path}#{base}.shp')


def _rows_from_shapefile_reader(reader: Any, *, asset_ref: str) -> Iterator[dict[str, Any]]:
    fields = [field[0] for field in reader.fields[1:]]
    for index, record in enumerate(reader.iterShapeRecords(), start=1):
        values = {
            str(name): value
            for name, value in zip(fields, list(record.record))
        }
        yield {
            **values,
            '__geometry': record.shape.__geo_interface__,
            '__asset_ref': f'{asset_ref}#shape-{index}',
            '__source_format': 'shapefile',
        }


def _avalcd_archive_records(names: Iterable[str], *, asset_ref: str) -> Iterator[dict[str, Any]]:
    scene_groups: dict[str, dict[str, Any]] = {}
    for name in names:
        lowered = name.lower()
        suffix = Path(name).suffix.lower()
        if suffix not in {'.tif', '.tiff', '.npy', '.npz', '.json', '.gpkg'}:
            continue
        scene_id = _scene_id_from_path(name)
        group = scene_groups.setdefault(scene_id, {'scene_id': scene_id, 'members': []})
        group['members'].append(name)
        ref = f'{asset_ref}#{name}' if zipfile.is_zipfile(Path(asset_ref)) else asset_ref
        if 'stack_manifest.json' in lowered or ('stack' in lowered and suffix in {'.json', '.npy', '.npz', '.tif', '.tiff'}):
            group['stack_ref'] = ref
        if 'mask' in lowered or 'truth' in lowered or 'avalanche' in lowered:
            if suffix in {'.tif', '.tiff', '.npy', '.npz'}:
                group['truth_mask_ref'] = ref
        if suffix == '.gpkg':
            group['geometry_ref'] = ref
    for group in scene_groups.values():
        if group.get('truth_mask_ref') or group.get('stack_ref') or group.get('geometry_ref'):
            yield {
                **group,
                'external_id': group['scene_id'],
                '__asset_ref': asset_ref,
                '__source_format': 'avalcd_archive_scan',
            }


def _scene_id_from_path(value: str) -> str:
    parts = [part for part in Path(value).parts if part not in {'.', ''}]
    if len(parts) >= 2:
        return _slug(parts[-2])
    return _slug(Path(value).stem)


def _build_normalization_payload(
    *,
    source_key: str,
    source_regions: tuple[str, ...],
    raw: dict[str, Any],
    index: int,
    license_review_id: str,
) -> dict[str, Any]:
    external_id = _first_string(
        raw,
        'external_id', 'event_id', 'scene_id', 'id', 'ID', 'objectid', 'OBJECTID',
        'fid', 'FID', 'avalanche_id', 'AvalancheID', 'nr', 'Nr', 'numero',
    ) or f'{source_key}-{index:06d}'
    event_time = _event_time_for_source(source_key, raw)
    geometry = raw.get('__geometry') if isinstance(raw.get('__geometry'), dict) else None
    asset_ref = _clean_string(raw.get('__asset_ref'))
    metadata = _metadata_for_source(source_key, raw, index=index, geometry=geometry)
    payload: dict[str, Any] = {
        'source_key': source_key,
        'external_id': external_id,
        'event_id': _first_string(raw, 'event_id', 'avalanche_id', 'AvalancheID') or external_id,
        'scene_id': _first_string(raw, 'scene_id', 'SceneID', 'scene') or external_id,
        'region_key': _infer_region_key(source_regions, raw),
        'event_time': event_time,
        'license_review_id': license_review_id,
        'metadata': metadata,
    }
    for target, keys in {
        'geometry_ref': ('geometry_ref', 'geometry_path', 'outline_ref', 'polygon_ref'),
        'stack_ref': ('stack_ref', 'stack_path', 'sar_stack', 'bitemporal_stack', 'stack_manifest'),
        'truth_mask_ref': ('truth_mask_ref', 'mask_ref', 'mask_path', 'truth_mask', 'avalanche_mask'),
        'bulletin_ref': ('bulletin_ref', 'bulletin_path', 'caaml_ref'),
        'feature_ref': ('feature_ref', 'feature_path', 'measurement_ref', 'weather_ref'),
    }.items():
        value = _first_string(raw, *keys)
        if value:
            payload[target] = value
    if geometry is not None and not payload.get('geometry_ref'):
        payload['geometry_ref'] = asset_ref
    if source_key in {'slf_data_service_weather_snowpack'} and not payload.get('feature_ref'):
        payload['feature_ref'] = asset_ref
    if source_key in {'slf_bulletin_caaml', 'eaws_bulletin_context'} and not payload.get('bulletin_ref'):
        payload['bulletin_ref'] = asset_ref
    if 'label' in raw:
        payload['label'] = raw.get('label')
    return payload


def _metadata_for_source(
    source_key: str,
    raw: dict[str, Any],
    *,
    index: int,
    geometry: dict[str, Any] | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        'raw_index': index,
        'raw_asset_ref': _clean_string(raw.get('__asset_ref')) or None,
        'source_format': _clean_string(raw.get('__source_format')) or None,
    }
    bbox = _geometry_bbox(geometry)
    if bbox is not None:
        metadata['bbox'] = bbox
    for key in (
        'area_m2', 'area', 'elevation_m', 'aspect', 'slope_angle', 'station_id',
        'site_id', 'path_id', 'municipality', 'canton', 'danger_level',
        'predicted_danger_level', 'danger_problem', 'date_accuracy',
        'location_accuracy_m', 'coordinate_accuracy', 'caught_count',
        'dead_count', 'fatality_count', 'buried_count', 'detection_probability',
        'confidence', 'temporal_uncertainty_hours', 'false_positive_review_status',
        'dataset_kind',
    ):
        if key in raw and raw.get(key) not in (None, ''):
            metadata[key] = _json_safe(raw.get(key))
    if source_key in {'swiss_spot6_2018', 'swiss_spot6_2019'}:
        metadata['extreme_event_split'] = source_key
        metadata['event_type'] = 'extreme_avalanche_period'
    if source_key == 'french_clpa_extent_priors':
        metadata['label_semantics'] = 'terrain_path_prior_not_dated_occurrence'
    if source_key == 'slf_accident_datasets':
        metadata['label_semantics'] = 'accident_event_not_occurrence_frequency'
    if source_key in {'slf_bulletin_caaml', 'eaws_bulletin_context'}:
        metadata['label_semantics'] = 'forecast_context_not_observed_occurrence'
    if source_key == 'norway_sar_activity_monitoring':
        metadata['label_semantics'] = 'automated_detection_requires_false_positive_review'
    if source_key == 'avalcd_zenodo_v1':
        metadata['avalcd_members'] = raw.get('members') if isinstance(raw.get('members'), list) else None
    return {key: value for key, value in metadata.items() if value is not None}


def _event_time_for_source(source_key: str, raw: dict[str, Any]) -> str | None:
    if source_key == 'swiss_spot6_2018':
        return '2018-01-24T00:00:00Z'
    if source_key == 'swiss_spot6_2019':
        return '2019-01-16T00:00:00Z'
    return _first_string(
        raw,
        'event_time', 'event_date', 'date', 'Date', 'DATE', 'timestamp',
        'datetime', 'activeAt', 'valid_from', 'acquisition_date',
    ) or None


def _infer_region_key(source_regions: tuple[str, ...], raw: dict[str, Any]) -> str:
    explicit = _first_string(raw, 'region_key', 'region', 'Region', 'area', 'Area')
    if explicit in source_regions:
        return explicit
    search_blob = ' '.join(
        _clean_string(raw.get(key))
        for key in ('region_key', 'region', 'scene_id', 'external_id', '__asset_ref')
    ).lower()
    aliases = {
        'scandinavia_norway': ('norway', 'tromso', 'tromsø', 'lyngen'),
        'italian_alps': ('livigno', 'italy', 'italian'),
        'greenland_nuuk': ('nuuk', 'greenland'),
        'tajikistan_pamir': ('pish', 'shughnon', 'tajik', 'pamir'),
        'swiss_alps': ('swiss', 'switzerland', 'davos'),
        'french_alps': ('france', 'french', 'alps', 'pyrenees'),
    }
    for region, tokens in aliases.items():
        if region in source_regions and any(token in search_blob for token in tokens):
            return region
    return source_regions[0]


def _asset_ref(record: dict[str, Any], key: str) -> str:
    asset_refs = record.get('asset_refs') if isinstance(record.get('asset_refs'), dict) else {}
    return _clean_string(asset_refs.get(key) or record.get(key))


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open('w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + '\n')


def _first_string(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        cleaned = _clean_string(value)
        if cleaned:
            return cleaned
    return ''


def _clean_string(value: Any) -> str:
    return str(value or '').strip()


def _slug(value: str) -> str:
    slug = ''.join(ch.lower() if ch.isalnum() else '_' for ch in str(value)).strip('_')
    return slug or 'record'


def _geometry_bbox(geometry: dict[str, Any] | None) -> list[float] | None:
    if not isinstance(geometry, dict):
        return None
    coords: list[tuple[float, float]] = []

    def visit(value: Any) -> None:
        if isinstance(value, (list, tuple)) and len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            coords.append((float(value[0]), float(value[1])))
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    visit(geometry.get('coordinates'))
    if not coords:
        return None
    xs = [coord[0] for coord in coords]
    ys = [coord[1] for coord in coords]
    return [min(xs), min(ys), max(xs), max(ys)]


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)
