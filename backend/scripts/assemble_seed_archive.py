from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import numpy as np

from backend.common.avalcd_manifest import (
    AVALCD_SCENE_MANIFEST_FILENAME,
    build_avalcd_scene_manifest,
    encode_patch_payload,
)

try:  # pragma: no cover - optional dependency at runtime
    import rasterio
except Exception:  # pragma: no cover - optional dependency
    rasterio = None


DOCUMENT_SUFFIXES = {'.md', '.pdf', '.txt'}
VECTOR_TRUTH_SUFFIXES = {'.shp', '.geojson', '.json'}
SHAPEFILE_REQUIRED_SUFFIXES = {'.shp', '.shx', '.dbf'}
SHAPEFILE_OPTIONAL_SUFFIXES = {'.prj', '.cpg'}
RASTER_SUFFIXES = {'.tif', '.tiff'}
OPTICAL_SUFFIXES = {'.jpg', '.jpeg', '.png'}


@dataclass(frozen=True)
class TruthScene:
    year: str
    region_key: str
    scene_id: str
    split: str
    truth_path: Path
    shapefile_components: tuple[Path, ...] = ()


@dataclass(frozen=True)
class RasterPair:
    year: str
    vv_path: Path
    vh_path: Path


@dataclass(frozen=True)
class AvalcdScene:
    split: str
    region_key: str
    scene_id: str
    source_stem: str
    truth_path: Path
    pre_vv_path: Path
    pre_vh_path: Path
    post_vv_path: Path
    post_vh_path: Path


AVALCD_ROLE_PATTERNS: dict[str, re.Pattern[str]] = {
    'truth': re.compile(r'(?i)^(?P<stem>.+?)[_-]gt$'),
    'pre_vv': re.compile(r'(?i)^(?P<stem>.+?)[_-]prevv$'),
    'pre_vh': re.compile(r'(?i)^(?P<stem>.+?)[_-]prevh$'),
    'post_vv': re.compile(r'(?i)^(?P<stem>.+?)[_-]postvv$'),
    'post_vh': re.compile(r'(?i)^(?P<stem>.+?)[_-]postvh$'),
}


def _extract_year_token(value: str) -> str | None:
    match = re.search(r'(?<!\d)((?:19|20)\d{2})(?!\d)', value)
    return match.group(1) if match else None


def _slug(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', value.strip().lower()).strip('_')


def _infer_region_key(path: Path) -> str:
    lowered = '/'.join(part.lower() for part in path.parts)
    if 'davos' in lowered or 'davalmap' in path.stem.lower():
        return 'davos'
    for part in reversed(path.parts[:-1]):
        slug = _slug(part)
        if slug and slug not in {'validation', 'val', 'test', 'heldout', 'truth', 'reference', 'references'}:
            return slug
    return 'heldout'


def _infer_split_key(path: Path) -> str:
    for part in path.parts:
        lowered = part.lower()
        if lowered == 'val':
            return 'validation'
        if lowered in {'validation', 'test'}:
            return lowered
    return 'validation'


def _infer_avalcd_region_key(path: Path, *, split: str, source_stem: str) -> str:
    parts = [part for part in path.parts[:-1] if part]
    normalized_split = 'val' if split == 'validation' else split
    for idx, part in enumerate(parts):
        lowered = part.lower()
        if lowered in {split, normalized_split} and idx + 1 < len(parts):
            slug = _slug(parts[idx + 1])
            if slug:
                return slug
    if parts:
        slug = _slug(parts[-1])
        if slug and slug not in {split, normalized_split}:
            return slug
    scene_parts = re.split(r'[_-]+', source_stem.strip())
    if scene_parts:
        slug = _slug(scene_parts[0])
        if slug:
            return slug
    return 'heldout'


def _safe_extract_zip(archive: zipfile.ZipFile, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for info in archive.infolist():
        member_name = info.filename
        parts = [part for part in PurePosixPath(member_name).parts if part not in ('', '.')]
        if any(part == '..' for part in parts):
            raise ValueError(f'archive member "{member_name}" contains parent-directory traversal')
        target = destination.joinpath(*parts) if parts else destination
        resolved = target.resolve()
        if destination.resolve() not in (resolved, *resolved.parents):
            raise ValueError(f'archive member "{member_name}" escapes extraction root')
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, target.open('wb') as handle:
            shutil.copyfileobj(source, handle)


def _extract_truth_archive(truth_zip: Path, destination: Path) -> None:
    with zipfile.ZipFile(truth_zip) as outer_archive:
        member_names = [name for name in outer_archive.namelist() if not outer_archive.getinfo(name).is_dir()]
        zip_members = [name for name in member_names if Path(name).suffix.lower() == '.zip']
        non_zip_members = [name for name in member_names if Path(name).suffix.lower() != '.zip']
        if len(zip_members) == 1 and all(Path(name).suffix.lower() in DOCUMENT_SUFFIXES for name in non_zip_members):
            with zipfile.ZipFile(io.BytesIO(outer_archive.read(zip_members[0]))) as nested_archive:
                _safe_extract_zip(nested_archive, destination)
            return
        _safe_extract_zip(outer_archive, destination)


def _extract_plain_archive(source_zip: Path, destination: Path) -> None:
    with zipfile.ZipFile(source_zip) as archive:
        _safe_extract_zip(archive, destination)


def _iter_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob('*') if path.is_file())


def _avalcd_role_and_stem(path: Path) -> tuple[str, str] | None:
    lowered = path.stem.lower()
    for role, pattern in AVALCD_ROLE_PATTERNS.items():
        match = pattern.match(lowered)
        if match:
            stem = match.group('stem')
            return role, stem
    return None


def _truth_stem_family(path: Path) -> str:
    lowered = path.stem.lower()
    year = _extract_year_token(lowered)
    if year:
        lowered = re.sub(fr'(^|[_-]){year}(?=$|[_-])', '', lowered)
    return re.sub(r'^[_-]+|[_-]+$', '', lowered)


def _is_auxiliary_truth_layer(path: Path) -> bool:
    return _truth_stem_family(path) in {
        'groundtruthcoverage',
        'vali_points',
        'validation_area',
    }


def _is_truth_candidate(path: Path) -> bool:
    lowered = path.stem.lower()
    if path.suffix.lower() not in VECTOR_TRUTH_SUFFIXES:
        return False
    if _is_auxiliary_truth_layer(path):
        return False
    return any(token in lowered for token in ('truth', 'davalmap', 'reference'))


def _discover_truth_scenes(truth_root: Path) -> dict[str, TruthScene]:
    scenes: dict[str, TruthScene] = {}
    for path in _iter_files(truth_root):
        if not _is_truth_candidate(path):
            continue
        year = _extract_year_token(path.stem)
        if not year:
            raise ValueError(f'truth vector "{path.name}" is missing a 4-digit year token')
        suffix = path.suffix.lower()
        region_key = _infer_region_key(path)
        scene_id = f'{region_key}_{year}'
        if year in scenes:
            raise ValueError(f'duplicate truth vector candidates found for year {year}')
        if suffix == '.shp':
            components: list[Path] = []
            for component_suffix in sorted(SHAPEFILE_REQUIRED_SUFFIXES | SHAPEFILE_OPTIONAL_SUFFIXES):
                component_path = path.with_suffix(component_suffix)
                if component_suffix in SHAPEFILE_REQUIRED_SUFFIXES and not component_path.exists():
                    raise ValueError(f'shapefile truth "{path.name}" is missing companion "{component_path.name}"')
                if component_path.exists():
                    components.append(component_path)
            scenes[year] = TruthScene(
                year=year,
                region_key=region_key,
                scene_id=scene_id,
                split='validation',
                truth_path=path,
                shapefile_components=tuple(sorted(components)),
            )
            continue
        scenes[year] = TruthScene(
            year=year,
            region_key=region_key,
            scene_id=scene_id,
            split='validation',
            truth_path=path,
        )
    if not scenes:
        raise ValueError('truth archive does not contain any supported truth vectors (.shp/.geojson/.json)')
    return scenes


def _discover_avalcd_scene_map(
    root: Path,
    *,
    roles: set[str],
) -> dict[tuple[str, str, str], dict[str, Path | str]]:
    scenes: dict[tuple[str, str, str], dict[str, Path | str]] = {}
    for path in _iter_files(root):
        if path.suffix.lower() not in RASTER_SUFFIXES:
            continue
        role_and_stem = _avalcd_role_and_stem(path)
        if role_and_stem is None:
            continue
        role, source_stem = role_and_stem
        if role not in roles:
            continue
        split = _infer_split_key(path.relative_to(root))
        region_key = _infer_avalcd_region_key(
            path.relative_to(root),
            split=split,
            source_stem=source_stem,
        )
        scene_id = _slug(source_stem)
        if not scene_id:
            raise ValueError(f'could not derive scene_id from AvalCD member "{path.name}"')
        key = (split, region_key, scene_id)
        entry = scenes.setdefault(key, {
            'split': split,
            'region_key': region_key,
            'scene_id': scene_id,
            'source_stem': source_stem,
        })
        if role in entry:
            raise ValueError(f'duplicate AvalCD member for role "{role}" in scene "{scene_id}"')
        entry[role] = path
    return scenes


def _discover_avalcd_scenes(truth_root: Path, raster_root: Path) -> list[AvalcdScene]:
    truth_map = _discover_avalcd_scene_map(truth_root, roles={'truth'})
    raster_map = _discover_avalcd_scene_map(raster_root, roles={'pre_vv', 'pre_vh', 'post_vv', 'post_vh'})
    if not truth_map or not raster_map:
        return []

    scenes: list[AvalcdScene] = []
    for key, truth_entry in sorted(truth_map.items()):
        raster_entry = raster_map.get(key)
        if raster_entry is None:
            split, region_key, scene_id = key
            raise ValueError(f'AvalCD scene "{scene_id}" in region "{region_key}" split "{split}" is missing SAR members')
        missing_roles = [
            role for role in ('pre_vv', 'pre_vh', 'post_vv', 'post_vh')
            if role not in raster_entry
        ]
        if missing_roles:
            raise ValueError(
                f'AvalCD scene "{truth_entry["scene_id"]}" is missing required members: {", ".join(missing_roles)}',
            )
        scenes.append(AvalcdScene(
            split=str(truth_entry['split']),
            region_key=str(truth_entry['region_key']),
            scene_id=str(truth_entry['scene_id']),
            source_stem=str(truth_entry['source_stem']),
            truth_path=Path(truth_entry['truth']),
            pre_vv_path=Path(raster_entry['pre_vv']),
            pre_vh_path=Path(raster_entry['pre_vh']),
            post_vv_path=Path(raster_entry['post_vv']),
            post_vh_path=Path(raster_entry['post_vh']),
        ))
    return scenes


def _band_from_name(path: Path) -> str | None:
    lowered = path.stem.lower()
    if re.search(r'(^|[_-])vv([_.-]|$)', lowered):
        return 'vv'
    if re.search(r'(^|[_-])vh([_.-]|$)', lowered):
        return 'vh'
    return None


def _discover_raster_pairs(raster_root: Path) -> dict[str, RasterPair]:
    optical_members = [path for path in _iter_files(raster_root) if path.suffix.lower() in OPTICAL_SUFFIXES]
    pairs: dict[str, dict[str, Path]] = {}
    saw_tiff = False
    for path in _iter_files(raster_root):
        suffix = path.suffix.lower()
        if suffix not in RASTER_SUFFIXES:
            continue
        saw_tiff = True
        band = _band_from_name(path)
        if band is None:
            raise ValueError(f'SAR raster "{path.name}" is missing a VV/VH band token in its filename')
        year = _extract_year_token(path.stem)
        if not year:
            raise ValueError(f'SAR raster "{path.name}" is missing a 4-digit year token')
        entry = pairs.setdefault(year, {})
        if band in entry:
            raise ValueError(f'duplicate {band.upper()} raster candidates found for year {year}')
        entry[band] = path
    if not pairs:
        if optical_members:
            raise ValueError('SAR raster archive contains optical-only imagery; expected paired Sentinel-1 VV/VH GeoTIFFs')
        if saw_tiff:
            raise ValueError('SAR raster archive does not contain any paired VV/VH GeoTIFFs')
        raise ValueError('SAR raster archive does not contain any GeoTIFF members')

    raster_pairs: dict[str, RasterPair] = {}
    for year, entry in sorted(pairs.items()):
        if 'vv' not in entry or 'vh' not in entry:
            raise ValueError(f'SAR raster archive is missing paired VV/VH GeoTIFFs for year {year}')
        raster_pairs[year] = RasterPair(year=year, vv_path=entry['vv'], vh_path=entry['vh'])
    return raster_pairs


def _load_single_band_geotiff(path: Path) -> tuple[np.ndarray, tuple[int, int], object, str, tuple[float, float, float, float]]:
    if rasterio is None:
        raise RuntimeError('rasterio is required to assemble AvalCD GeoTIFF scenes')
    with rasterio.open(path) as dataset:
        data = np.asarray(dataset.read(), dtype=np.float32)
        if data.ndim == 2:
            band = data
        elif data.ndim == 3 and data.shape[0] == 1:
            band = np.asarray(data[0], dtype=np.float32)
        else:
            raise ValueError(f'AvalCD raster "{path.name}" must be a single-band GeoTIFF')
        crs = str(dataset.crs) if dataset.crs is not None else ''
        if not crs:
            raise ValueError(f'AvalCD raster "{path.name}" is missing a CRS')
        bounds = dataset.bounds
        return (
            band,
            (int(dataset.height), int(dataset.width)),
            dataset.transform,
            crs,
            (float(bounds.left), float(bounds.bottom), float(bounds.right), float(bounds.top)),
        )


def _assemble_avalcd_scene(scene: AvalcdScene, destination: Path) -> None:
    truth_band, truth_shape, truth_transform, truth_crs, truth_bbox = _load_single_band_geotiff(scene.truth_path)
    stack_bands: list[np.ndarray] = []
    expected_shape: tuple[int, int] | None = None
    expected_transform = None
    expected_crs: str | None = None
    expected_bbox: tuple[float, float, float, float] | None = None
    for raster_path in (scene.pre_vv_path, scene.pre_vh_path, scene.post_vv_path, scene.post_vh_path):
        band, shape, transform, crs, bbox = _load_single_band_geotiff(raster_path)
        if expected_shape is None:
            expected_shape = shape
            expected_transform = transform
            expected_crs = crs
            expected_bbox = bbox
        elif shape != expected_shape or transform != expected_transform or crs != expected_crs or bbox != expected_bbox:
            raise ValueError(
                f'AvalCD scene "{scene.scene_id}" has non-aligned SAR rasters; pre/post VV/VH members must share one grid/CRS',
            )
        stack_bands.append(band)
    if truth_shape != expected_shape or truth_transform != expected_transform or truth_crs != expected_crs or truth_bbox != expected_bbox:
        raise ValueError(
            f'AvalCD scene "{scene.scene_id}" truth mask grid does not align with its SAR rasters',
        )
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(scene.truth_path, destination / 'truth_mask.tif')
    manifest, patch_entries = build_avalcd_scene_manifest(
        np.stack(stack_bands, axis=0).astype(np.float32),
        bbox=truth_bbox,
    )
    (destination / AVALCD_SCENE_MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    for patch_entry in patch_entries:
        patch_path = destination / str(patch_entry['filename'])
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_bytes(encode_patch_payload(patch_entry['stack']))


def _copy_truth_scene(scene: TruthScene, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if scene.shapefile_components:
        for component in scene.shapefile_components:
            shutil.copy2(component, destination / f'truth_mask{component.suffix.lower()}')
        return
    shutil.copy2(scene.truth_path, destination / f'truth_mask{scene.truth_path.suffix.lower()}')


def assemble_seed_archive(args: argparse.Namespace) -> dict[str, object]:
    truth_zip = Path(args.truth_zip)
    sar_zip = Path(args.sar_zip)
    output_dir = Path(args.output_dir)
    if not truth_zip.exists():
        raise ValueError(f'truth archive "{truth_zip}" does not exist')
    if not sar_zip.exists():
        raise ValueError(f'SAR raster archive "{sar_zip}" does not exist')
    if not zipfile.is_zipfile(truth_zip):
        raise ValueError(f'truth archive "{truth_zip}" is not a ZIP file')
    if not zipfile.is_zipfile(sar_zip):
        raise ValueError(f'SAR raster archive "{sar_zip}" is not a ZIP file')

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_root = Path(tmpdir)
        truth_root = temp_root / 'truth'
        raster_root = temp_root / 'sar'
        _extract_truth_archive(truth_zip, truth_root)
        _extract_plain_archive(sar_zip, raster_root)
        avalcd_scenes = _discover_avalcd_scenes(truth_root, raster_root)
        if avalcd_scenes:
            if output_dir.exists():
                shutil.rmtree(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            assembled_scenes: list[dict[str, str]] = []
            for scene in avalcd_scenes:
                scene_root = output_dir / scene.split / scene.region_key / scene.scene_id
                _assemble_avalcd_scene(scene, scene_root)
                assembled_scenes.append({
                    'split': scene.split,
                    'region_key': scene.region_key,
                    'scene_id': scene.scene_id,
                    'layout': 'avalcd_bitemporal',
                    'source_stem': scene.source_stem,
                })
            return {
                'status': 'ok',
                'output_dir': str(output_dir),
                'scene_count': len(assembled_scenes),
                'scenes': assembled_scenes,
            }
        truth_scenes = _discover_truth_scenes(truth_root)
        raster_pairs = _discover_raster_pairs(raster_root)

        truth_years = set(truth_scenes)
        raster_years = set(raster_pairs)
        missing_rasters = sorted(truth_years - raster_years)
        extra_rasters = sorted(raster_years - truth_years)
        if missing_rasters:
            raise ValueError(f'SAR raster archive is missing truth-matched VV/VH rasters for year(s): {", ".join(missing_rasters)}')
        if extra_rasters:
            raise ValueError(f'SAR raster archive contains unmatched VV/VH rasters for year(s): {", ".join(extra_rasters)}')

        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        assembled_scenes: list[dict[str, str]] = []
        for year, truth_scene in sorted(truth_scenes.items()):
            pair = raster_pairs[year]
            scene_root = output_dir / truth_scene.split / truth_scene.region_key / truth_scene.scene_id
            _copy_truth_scene(truth_scene, scene_root)
            shutil.copy2(pair.vv_path, scene_root / 'vv.tif')
            shutil.copy2(pair.vh_path, scene_root / 'vh.tif')
            assembled_scenes.append({
                'year': year,
                'region_key': truth_scene.region_key,
                'scene_id': truth_scene.scene_id,
            })

    return {
        'status': 'ok',
        'output_dir': str(output_dir),
        'scene_count': len(assembled_scenes),
        'scenes': assembled_scenes,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Assemble truth vectors and SAR rasters into a canonical held-out directory')
    parser.add_argument('--truth-zip', type=Path, required=True, help='Truth/vector ZIP archive path')
    parser.add_argument('--sar-zip', type=Path, required=True, help='SAR raster ZIP archive path')
    parser.add_argument('--output-dir', type=Path, required=True, help='Output directory for the assembled held-out dataset')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = assemble_seed_archive(args)
    except (ValueError, RuntimeError) as exc:
        print(json.dumps({
            'status': 'invalid_archive',
            'reason': str(exc),
        }, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
