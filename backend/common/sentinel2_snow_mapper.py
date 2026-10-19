"""Sentinel-2 optical snow mapper via Google Earth Engine.

Extracts NDSI snow cover, NDVI vegetation chronology, and EVI from
COPERNICUS/S2_SR_HARMONIZED, cloud-masked and co-registered to the
region grid. Credential-gated like gee_extractor.py.

Env flags:
  S2_SNOW_ENABLED — master switch (default: false)
  GEE_SERVICE_ACCOUNT_JSON / GEE_SERVICE_ACCOUNT_EMAIL — GEE credentials
"""
from __future__ import annotations

import os
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

S2_SNOW_ENABLED = os.getenv('S2_SNOW_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}

S2_COLLECTION = 'COPERNICUS/S2_SR_HARMONIZED'
S2_CLOUDY_PIXEL_PERCENTAGE_MAX = 30.0
S2_NDSI_SNOW_THRESHOLD = 0.4
S2_SCALE_M = 20  # native S2 SR resolution
S2_MAX_CELLS = int(os.getenv('S2_MAX_CELLS', '50'))

GEE_SERVICE_ACCOUNT_JSON = os.getenv('GEE_SERVICE_ACCOUNT_JSON')
GEE_SERVICE_ACCOUNT_EMAIL = os.getenv('GEE_SERVICE_ACCOUNT_EMAIL')

_GEE_INITIALIZED = False


def _scene_lineage_sha256(scene_id: str | None, acquisition_time: str | None) -> str | None:
    """Hash the immutable scene identity/time pair, never display pixels."""
    if not scene_id or not acquisition_time:
        return None
    payload = json.dumps(
        {
            'collection': S2_COLLECTION,
            'scene_id': str(scene_id),
            'acquisition_time': str(acquisition_time),
        },
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


@dataclass
class S2SnowResult:
    """Per-cell S2 snow mapping result."""

    cell_id: str
    ndsi: float | None = None
    snow_cover_fraction: float | None = None
    ndvi: float | None = None
    evi: float | None = None
    cloud_cover: float | None = None
    scene_id: str | None = None
    acquisition_time: str | None = None
    source: str = 'sentinel2_sr'
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'cell_id': self.cell_id,
            'ndsi': self.ndsi,
            'snow_cover_fraction': self.snow_cover_fraction,
            'ndvi': self.ndvi,
            'evi': self.evi,
            'cloud_cover': self.cloud_cover,
            'scene_id': self.scene_id,
            'acquisition_time': self.acquisition_time,
            'source': self.source,
            'metadata': self.metadata,
        }


def _has_credentials() -> bool:
    """Check if GEE credentials are available."""
    has_json = bool(GEE_SERVICE_ACCOUNT_JSON and GEE_SERVICE_ACCOUNT_EMAIL)
    key_file = os.getenv('GEE_KEY_FILE', 'config/earth-engine-key.json')
    has_file = bool(key_file and os.path.exists(key_file))
    return has_json or has_file


def _get_gee_session(gee_session: Any | None = None) -> Any | None:
    """Return one initialized EE module/session for the current process."""
    global _GEE_INITIALIZED
    if gee_session is not None:
        return gee_session
    try:
        import ee
    except ImportError:
        return None

    if _GEE_INITIALIZED:
        return ee
    try:
        from google.oauth2 import service_account as _sa_creds
        _GEE_SCOPE = 'https://www.googleapis.com/auth/earthengine'
        if GEE_SERVICE_ACCOUNT_JSON and GEE_SERVICE_ACCOUNT_EMAIL:
            import json as _json
            credentials = _sa_creds.Credentials.from_service_account_info(
                _json.loads(GEE_SERVICE_ACCOUNT_JSON), scopes=[_GEE_SCOPE]
            )
            ee.Initialize(credentials)
        else:
            key_file = os.getenv('GEE_KEY_FILE', 'config/earth-engine-key.json')
            if os.path.exists(key_file):
                credentials = _sa_creds.Credentials.from_service_account_file(
                    key_file, scopes=[_GEE_SCOPE]
                )
                ee.Initialize(credentials)
            else:
                ee.Initialize()
    except Exception:
        return None
    _GEE_INITIALIZED = True
    return ee


def compute_ndsi(green: float, swir1: float) -> float | None:
    """Compute Normalized Difference Snow Index.

    NDSI = (Green - SWIR1) / (Green + SWIR1)
    Snow when NDSI > 0.4.

    Args:
        green: Green band reflectance (B3).
        swir1: SWIR1 band reflectance (B11).

    Returns:
        NDSI value, or None if inputs are invalid.
    """
    if green is None or swir1 is None:
        return None
    denom = green + swir1
    if abs(denom) < 1e-9:
        return None
    return (green - swir1) / denom


def compute_ndvi(nir: float, red: float) -> float | None:
    """Compute Normalized Difference Vegetation Index.

    NDVI = (NIR - Red) / (NIR + Red)

    Args:
        nir: NIR band reflectance (B8).
        red: Red band reflectance (B4).
    """
    if nir is None or red is None:
        return None
    denom = nir + red
    if abs(denom) < 1e-9:
        return None
    return (nir - red) / denom


def compute_evi(nir: float, red: float, blue: float) -> float | None:
    """Compute Enhanced Vegetation Index.

    EVI = 2.5 * (NIR - Red) / (NIR + 6*Red - 7.5*Blue + 1)

    Args:
        nir: NIR band reflectance (B8).
        red: Red band reflectance (B4).
        blue: Blue band reflectance (B2).
    """
    if nir is None or red is None or blue is None:
        return None
    denom = nir + 6.0 * red - 7.5 * blue + 1.0
    if abs(denom) < 1e-9:
        return None
    return 2.5 * (nir - red) / denom


def is_snow(ndsi: float | None, threshold: float = S2_NDSI_SNOW_THRESHOLD) -> bool:
    """Check if NDSI indicates snow cover."""
    return ndsi is not None and ndsi > threshold


def _mask_scl(ee: Any, img: Any) -> Any:
    """Apply the SCL fallback mask when cloud-probability join is absent."""
    image = ee.Image(img)
    scl = image.select('SCL')
    scl_mask = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10))
    return image.updateMask(scl_mask).addBands(
        ee.Image.constant(0).rename('cloud_prob')
    )


def _mask_cloud_probability(ee: Any, joined_image: Any) -> Any:
    """Apply official S2 Cloud Probability plus SCL masking."""
    image = ee.Image(joined_image)
    cloud_prob = ee.Image(image.get('cloud_mask')).select('probability').rename('cloud_prob')
    scl = image.select('SCL')
    scl_mask = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10))
    return image.addBands(cloud_prob).updateMask(cloud_prob.lt(40).And(scl_mask))


def map_s2_snow_for_cell(
    *,
    cell_id: str,
    lat: float,
    lng: float,
    target_date: datetime,
    gee_session: Any | None = None,
) -> S2SnowResult | None:
    """Map S2 snow cover for a single grid cell.

    When GEE credentials are absent, returns None (graceful no-op).
    When S2_SNOW_ENABLED is false, returns None.

    Args:
        cell_id: Cell identifier.
        lat: Cell center latitude.
        lng: Cell center longitude.
        target_date: Date to query.
        gee_session: Optional shared GEE session.

    Returns:
        S2SnowResult or None if unavailable.
    """
    if not S2_SNOW_ENABLED or not _has_credentials():
        return None

    ee = _get_gee_session(gee_session)
    if ee is None:
        return None

    # Date range: ±3 days around target
    end_date = target_date
    start_date = end_date - timedelta(days=3)
    date_str_start = start_date.strftime('%Y-%m-%d')
    date_str_end = end_date.strftime('%Y-%m-%d')

    # Cell centroid point
    cell_point = ee.Geometry.Point([lng, lat])

    # Filter S2 SR Harmonized collection by date and location
    s2_col = (
        ee.ImageCollection(S2_COLLECTION)
        .filterDate(date_str_start, date_str_end)
        .filterBounds(cell_point)
        .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', S2_CLOUDY_PIXEL_PERCENTAGE_MAX))
    )

    # Join with S2 Cloud Probability for s2cloudless-style masking
    s2_clouds = (
        ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY')
        .filterDate(date_str_start, date_str_end)
        .filterBounds(cell_point)
    )

    # Save the official S2 Cloud Probability image under a property. The
    # source band is ``probability`` (0-100); it is not ``cloud_probability``.
    s2_with_clouds = ee.Join.saveFirst('cloud_mask').apply(
        primary=s2_col,
        secondary=s2_clouds,
        condition=ee.Filter.equals(leftField='system:index', rightField='system:index'),
    )
    s2_with_clouds = ee.ImageCollection(s2_with_clouds).filter(
        ee.Filter.notNull(['cloud_mask'])
    )

    joined_count = s2_with_clouds.size().getInfo()

    # Map cloud masking over collection
    if joined_count:
        masked_col = ee.ImageCollection(
            s2_with_clouds.map(lambda image: _mask_cloud_probability(ee, image))
        )
    elif s2_col.size().getInfo():
        masked_col = ee.ImageCollection(
            s2_col.map(lambda image: _mask_scl(ee, image))
        )
    else:
        return None

    # Take the least cloudy image
    sorted_col = masked_col.sort('CLOUDY_PIXEL_PERCENTAGE')
    best_image = ee.Image(sorted_col.first())

    # Compute NDSI = (B3 - B11) / (B3 + B11)
    green = best_image.select('B3')
    swir1 = best_image.select('B11')
    ndsi = green.subtract(swir1).divide(green.add(swir1)).rename('ndsi')

    # Snow cover fraction: fraction of pixels with NDSI > threshold
    snow_fraction = ndsi.gt(S2_NDSI_SNOW_THRESHOLD).rename('snow_fraction').reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=cell_point.buffer(500),  # 1km buffer around cell centroid
        scale=S2_SCALE_M,
        maxPixels=1024,
    )

    # Cloud cover fraction for the cell area
    cloud_cover_val = best_image.select('cloud_prob').gt(40).rename('cloud_fraction').reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=cell_point.buffer(500),
        scale=S2_SCALE_M,
        maxPixels=1024,
    )

    # NDSI mean for the cell
    ndsi_mean = ndsi.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=cell_point.buffer(500),
        scale=S2_SCALE_M,
        maxPixels=1024,
    )

    # Get scene ID and acquisition time
    scene_id = best_image.get('system:index')
    acq_time_ms = best_image.get('system:time_start')

    # Pull values to client
    try:
        snow_val = snow_fraction.getInfo()
        cloud_val = cloud_cover_val.getInfo()
        ndsi_val = ndsi_mean.getInfo()
        scene_id_val = scene_id.getInfo() if scene_id else None
        acq_time_val = acq_time_ms.getInfo() if acq_time_ms else None
    except Exception:
        return None

    snow_cover = None
    if snow_val and 'snow_fraction' in snow_val:
        snow_cover = float(snow_val['snow_fraction']) if snow_val['snow_fraction'] is not None else None

    cloud_cover = None
    if cloud_val and 'cloud_fraction' in cloud_val:
        cloud_cover = float(cloud_val['cloud_fraction']) if cloud_val['cloud_fraction'] is not None else None

    ndsi_mean_val = None
    if ndsi_val and 'ndsi' in ndsi_val:
        ndsi_mean_val = float(ndsi_val['ndsi']) if ndsi_val['ndsi'] is not None else None

    acq_time_str = None
    if acq_time_val is not None:
        try:
            acq_time_str = datetime.fromtimestamp(
                int(acq_time_val) / 1000.0, tz=timezone.utc
            ).isoformat()
        except (ValueError, TypeError):
            pass

    return S2SnowResult(
        cell_id=cell_id,
        ndsi=ndsi_mean_val,
        snow_cover_fraction=snow_cover,
        cloud_cover=cloud_cover,
        scene_id=str(scene_id_val) if scene_id_val else None,
        acquisition_time=acq_time_str,
        metadata={
            'cloud_mask_collection': 'COPERNICUS/S2_CLOUD_PROBABILITY',
            'cloud_mask_band': 'probability',
            'cloud_mask_threshold': 40,
            'cloud_mask_fallback': not bool(joined_count),
            'snow_fraction_band': 'snow_fraction',
            'scale_m': S2_SCALE_M,
            'lineage_ref': f'sentinel2:{scene_id_val}' if scene_id_val else None,
            'lineage_sha256': _scene_lineage_sha256(
                str(scene_id_val) if scene_id_val else None,
                acq_time_str,
            ),
            'lineage_complete': bool(scene_id_val and acq_time_str),
        },
    )


def map_s2_snow_batch(
    *,
    cells: list[dict[str, Any]],
    target_date: datetime,
    gee_session: Any | None = None,
) -> dict[str, S2SnowResult]:
    """Map S2 snow cover for a batch of grid cells.

    Args:
        cells: List of cell dicts with 'cell_id', 'lat', 'lng'.
        target_date: Date to query.
        gee_session: Optional shared GEE session.

    Returns:
        Dict mapping cell_id to S2SnowResult. Empty when disabled.
    """
    if not S2_SNOW_ENABLED or not _has_credentials():
        return {}

    session = _get_gee_session(gee_session)
    if session is None:
        return {}

    results: dict[str, S2SnowResult] = {}
    bounded_cells: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    max_cells = max(0, S2_MAX_CELLS)
    if max_cells == 0:
        return results
    for cell in cells:
        cell_id = str(cell.get('cell_id', '')).strip()
        if not cell_id or cell_id in seen_ids:
            continue
        seen_ids.add(cell_id)
        bounded_cells.append(cell)
        if len(bounded_cells) >= max_cells:
            break

    for cell in bounded_cells:
        cell_id = cell.get('cell_id', '')
        lat = float(cell.get('lat', 0))
        lng = float(cell.get('lng', 0))
        result = map_s2_snow_for_cell(
            cell_id=cell_id,
            lat=lat,
            lng=lng,
            target_date=target_date,
            gee_session=session,
        )
        if result is not None:
            results[cell_id] = result

    return results
