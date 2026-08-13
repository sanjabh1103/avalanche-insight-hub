# Regional SRTM DEMs

Pre-bundled SRTM 30 m Digital Elevation Models used by `backend/common/runout.py`
(Alpha-Beta WhiteboxTools runout) and `backend/gee_extractor.py` (terrain masks).

Files in this folder are tracked via **Git LFS** (see `.gitattributes`).

## Expected files (one per region key)

| Region key (from `config/regions.json`) | File |
|---|---|
| colorado_rockies | colorado_rockies.tif |
| swiss_alps | swiss_alps.tif |
| french_alps | french_alps.tif |
| himalayas_nepal | himalayas_nepal.tif |
| andes_patagonia | andes_patagonia.tif |
| cascades_wa | cascades_wa.tif |
| scandinavia_norway | scandinavia_norway.tif |
| japanese_alps | japanese_alps.tif |

Each file must be an SRTMGL1 (30 m) GeoTIFF cropped to the region's bbox,
typically 10–25 MB. Cloud-Optimized GeoTIFF (COG) preferred.

## How to regenerate

```bash
# 1. Install once
brew install git-lfs && git lfs install
pip install -r backend/requirements.txt  # rasterio, requests

# 2. Get a free OpenTopography API key: https://portal.opentopography.org/
export OPENTOPOGRAPHY_API_KEY=...

# 3. Download + crop all 8 regions (~120 MB total)
python -m backend.scripts.download_region_dems

# 4. Commit via LFS
git add .gitattributes backend/data/dem/*.tif
git commit -m "data(dem): bundle SRTM 30m per region for Alpha-Beta runout"
git push
```

## Flipping the physics flag

After DEMs are pushed, set the workflow env flag:

```bash
gh workflow run ml_pipeline.yml -f mode=infer -f run_physics_runout=true
```

Or update the default in `.github/workflows/ml_pipeline.yml`.
