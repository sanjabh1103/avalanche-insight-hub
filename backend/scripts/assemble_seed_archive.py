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


def _is_truth_candidate(path: Path) -> bool:
    lowered = path.stem.lower()
    if path.suffix.lower() not in VECTOR_TRUTH_SUFFIXES:
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
