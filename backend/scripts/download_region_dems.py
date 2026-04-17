"""Download and crop SRTM 30 m DEMs for every region in ``config/regions.json``.

Uses the OpenTopography ``globaldem`` API (free key required). Output files land in
``backend/data/dem/<region_key>.tif`` as Cloud-Optimized GeoTIFFs ready for
Git LFS commit.

Usage
-----
    export OPENTOPOGRAPHY_API_KEY=...
    python -m backend.scripts.download_region_dems            # all regions
    python -m backend.scripts.download_region_dems swiss_alps # single region

Design notes
------------
* Skips any region whose output file already exists unless ``--force`` is passed.
* Validates file size (>1 MB) so a failed/empty download does not silently pass.
* Rewrites as COG (if ``rio-cogeo`` is available) to keep LFS footprint small.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests

from backend.common.regions import load_regions, repo_root

OT_ENDPOINT = 'https://portal.opentopography.org/API/globaldem'
OT_DATASET = 'SRTMGL1'  # 30 m global
DEM_DIR = repo_root() / 'backend' / 'data' / 'dem'
MIN_BYTES = 1_000_000  # 1 MB sanity floor


def fetch_srtm(bbox: tuple[float, float, float, float], dest: Path, api_key: str) -> None:
    """Download SRTMGL1 cropped to ``bbox=(south, west, north, east)``."""
    south, west, north, east = bbox
    params = {
        'demtype': OT_DATASET,
        'south': south,
        'north': north,
        'west': west,
        'east': east,
        'outputFormat': 'GTiff',
        'API_Key': api_key,
    }
    print(f'[dem] GET {OT_ENDPOINT} bbox=({south},{west},{north},{east})')
    with requests.get(OT_ENDPOINT, params=params, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('wb') as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                if chunk:
                    fh.write(chunk)
    size = dest.stat().st_size
    if size < MIN_BYTES:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f'Downloaded DEM too small ({size} bytes) for {dest.name}')
    print(f'[dem] wrote {dest} ({size / 1e6:.1f} MB)')


def maybe_rewrite_cog(path: Path) -> None:
    try:
        from rio_cogeo.cogeo import cog_translate
        from rio_cogeo.profiles import cog_profiles
    except Exception:
        return  # COG conversion is best-effort; raw GeoTIFF still works.
    tmp = path.with_suffix('.cog.tif')
    cog_translate(str(path), str(tmp), cog_profiles.get('deflate'), quiet=True)
    tmp.replace(path)
    print(f'[dem] rewrote {path.name} as COG')


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('region_keys', nargs='*', help='Optional region keys; defaults to all.')
    parser.add_argument('--force', action='store_true', help='Re-download even if file exists.')
    args = parser.parse_args(argv)

    api_key = os.getenv('OPENTOPOGRAPHY_API_KEY')
    if not api_key:
        print('[dem] OPENTOPOGRAPHY_API_KEY not set; get a free key at https://portal.opentopography.org/', file=sys.stderr)
        return 1

    regions = load_regions()
    wanted = set(args.region_keys) if args.region_keys else None
    targets = [r for r in regions if (wanted is None or r.key in wanted)]
    if wanted and not targets:
        print(f'[dem] no regions match {sorted(wanted)}; known: {[r.key for r in regions]}', file=sys.stderr)
        return 2

    failures: list[str] = []
    for region in targets:
        dest = DEM_DIR / f'{region.key}.tif'
        if dest.exists() and not args.force:
            print(f'[dem] skip (exists): {dest.name}')
            continue
        try:
            fetch_srtm(region.bbox, dest, api_key)
            maybe_rewrite_cog(dest)
        except Exception as exc:
            print(f'[dem] FAILED {region.key}: {exc}', file=sys.stderr)
            failures.append(region.key)
            time.sleep(2)
    if failures:
        print(f'[dem] {len(failures)} region(s) failed: {failures}', file=sys.stderr)
        return 3
    print(f'[dem] done ({len(targets)} region(s))')
    return 0


if __name__ == '__main__':
    sys.exit(main())
