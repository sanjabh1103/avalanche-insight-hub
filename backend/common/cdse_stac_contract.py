"""Deterministic, metadata-only contract for direct CDSE STAC discovery.

This module builds a bounded Copernicus Data Space STAC search request.  It
does not authenticate, make a network request, download an asset, infer an
avalanche event, or authorize training.  The resulting bundle is intended to
make a future GEE-independent Sentinel-1 provenance/feature route
reproducible while keeping its label semantics explicit.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


CDSE_STAC_CONTRACT_VERSION = "mvp4_cdse_stac_metadata_request_v1"
CDSE_STAC_BASE_URL = "https://stac.dataspace.copernicus.eu/v1"
CDSE_STAC_SEARCH_URL = f"{CDSE_STAC_BASE_URL}/search"
CDSE_STAC_COLLECTION = "sentinel-1-grd"
CDSE_STAC_DOCUMENTATION_URL = "https://documentation.dataspace.copernicus.eu/APIs/STAC.html"
CDSE_SENTINEL_LICENSE_URL = (
    "https://sentinel.esa.int/documents/247904/690755/Sentinel_Data_Legal_Notice"
)
DEFAULT_ITEM_LIMIT = 100
MAX_ITEM_LIMIT = 1000


class CdseStacContractError(ValueError):
    """Raised when a direct-CDSE request cannot be made bounded and explicit."""


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _parse_utc(value: Any, *, field: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise CdseStacContractError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CdseStacContractError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CdseStacContractError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_stac_bbox(region_bbox: Sequence[float]) -> list[float]:
    """Convert the repo's (min_lat,min_lng,max_lat,max_lng) to STAC order."""
    if len(region_bbox) != 4:
        raise CdseStacContractError("region bbox must contain four values")
    try:
        min_lat, min_lng, max_lat, max_lng = (float(value) for value in region_bbox)
    except (TypeError, ValueError) as exc:
        raise CdseStacContractError("region bbox values must be finite numbers") from exc
    values = (min_lat, min_lng, max_lat, max_lng)
    if not all(math.isfinite(value) for value in values):
        raise CdseStacContractError("region bbox values must be finite numbers")
    if not -90 <= min_lat < max_lat <= 90:
        raise CdseStacContractError("latitude bounds must satisfy -90 <= min < max <= 90")
    if not -180 <= min_lng < max_lng <= 180:
        raise CdseStacContractError("longitude bounds must satisfy -180 <= min < max <= 180")
    return [min_lng, min_lat, max_lng, max_lat]


def build_stac_search_request(
    *,
    region_key: str,
    region_bbox: Sequence[float],
    start: Any,
    end: Any,
    limit: int = DEFAULT_ITEM_LIMIT,
) -> dict[str, Any]:
    """Build a bounded POST body for CDSE's STAC ``/search`` endpoint."""
    normalized_region = str(region_key or "").strip()
    if not normalized_region:
        raise CdseStacContractError("region_key is required")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_ITEM_LIMIT:
        raise CdseStacContractError(f"limit must be an integer between 1 and {MAX_ITEM_LIMIT}")
    start_dt = _parse_utc(start, field="start")
    end_dt = _parse_utc(end, field="end")
    if end_dt <= start_dt:
        raise CdseStacContractError("end must be after start")
    return {
        "collections": [CDSE_STAC_COLLECTION],
        "bbox": normalize_stac_bbox(region_bbox),
        "datetime": f"{_iso(start_dt)}/{_iso(end_dt)}",
        "limit": limit,
        "fields": {
            "include": [
                "id",
                "type",
                "geometry",
                "bbox",
                "properties.datetime",
                "properties.sar:instrument_mode",
                "properties.product:type",
                "assets",
            ]
        },
        "sortby": [{"field": "properties.datetime", "direction": "asc"}],
        "_mvp4_context": {
            "region_key": normalized_region,
            "label_semantics": "not_an_avalanche_event_label",
            "use_role": "scene_metadata_and_feature_provenance_only",
        },
    }


def build_request_manifest(
    *,
    region_key: str,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind a request to the official endpoint and non-promoting role."""
    request_body = dict(request)
    request_bytes = _canonical_bytes(request_body)
    manifest: dict[str, Any] = {
        "schema_version": CDSE_STAC_CONTRACT_VERSION,
        "endpoint": CDSE_STAC_SEARCH_URL,
        "documentation_url": CDSE_STAC_DOCUMENTATION_URL,
        "collection": CDSE_STAC_COLLECTION,
        "region_key": str(region_key).strip(),
        "request": request_body,
        "request_sha256": _sha256(request_bytes),
        "source_reference": "Copernicus Sentinel-1 GRD via direct CDSE STAC",
        "source_role": "scene_metadata_and_feature_provenance_only",
        "label_semantics": "not_an_avalanche_event_label",
        "license_status": "pending_rights_review",
        "license_terms_url": CDSE_SENTINEL_LICENSE_URL,
        "required_next_action": (
            "Review account/use scope, query results, asset rights, and detection semantics before any feature or label use."
        ),
        "network_fetch_performed": False,
        "training_eligible": False,
        "core_training_eligible": False,
        "production_scoring_eligible": False,
        "remote_pilot_allowed": False,
    }
    manifest["manifest_hash"] = _sha256(_canonical_bytes(manifest))
    return manifest


def write_request_bundle(
    output_dir: Path,
    *,
    region_key: str,
    region_bbox: Sequence[float],
    start: Any,
    end: Any,
    limit: int = DEFAULT_ITEM_LIMIT,
) -> dict[str, Any]:
    """Write a request/manifest bundle without contacting CDSE."""
    request = build_stac_search_request(
        region_key=region_key,
        region_bbox=region_bbox,
        start=start,
        end=end,
        limit=limit,
    )
    manifest = build_request_manifest(region_key=region_key, request=request)
    output_dir.mkdir(parents=True, exist_ok=True)
    request_path = output_dir / "request.json"
    manifest_path = output_dir / "snapshot_manifest.json"
    request_path.write_bytes(_canonical_bytes(request))
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest
