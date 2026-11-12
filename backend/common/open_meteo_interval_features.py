"""Bounded historical Open-Meteo features for interval-label preparation.

The client groups requests by the deterministic spatial join key and fetches
daily public reanalysis fields for the exact label-date envelope.  It never
uses station data, fabricates event times, or claims that a native weather
grid is a 500 m target-grid observation.  The default output is a shadow
snapshot pending license and cutoff-policy review.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from backend.common.spatial_grouping import spatial_feature_join_key


OPEN_METEO_ARCHIVE_SOURCE_KEY = "era5_land"
OPEN_METEO_ARCHIVE_SOURCE_FAMILY = "open_weather_reanalysis"
OPEN_METEO_INTERVAL_FEATURE_VERSION = "mvp4_open_meteo_interval_features_v1"
OPEN_METEO_LICENSE_URL = "https://open-meteo.com/en/licence"
OPEN_METEO_HISTORICAL_API_URL = "https://open-meteo.com/en/docs/historical-weather-api"
OPEN_METEO_DAILY_VARIABLES = (
    "temperature_2m_mean",
    "precipitation_sum",
    "snowfall_sum",
    "relative_humidity_2m_mean",
    "wind_speed_10m_max",
)
NORMALIZED_FEATURE_NAMES = (
    "temperature_2m",
    "precipitation",
    "snowfall",
    "relative_humidity_2m",
    "windspeed_10m",
)

MODEL_METADATA: dict[str, dict[str, Any]] = {
    "era5": {
        "dataset_product": "ERA5",
        "native_resolution_m": 25000.0,
        "effective_information_scale_m": 25000.0,
        "availability_delay_days": 5,
        "underlying_license_url": "https://confluence.ecmwf.int/pages/viewpage.action?pageId=514766993",
    },
    "era5_land": {
        "dataset_product": "ERA5-Land",
        "native_resolution_m": 11000.0,
        "effective_information_scale_m": 11000.0,
        "availability_delay_days": 5,
        "underlying_license_url": "https://confluence.ecmwf.int/pages/viewpage.action?pageId=355336451",
    },
}


class OpenMeteoIntervalFeatureError(ValueError):
    """Raised when a historical feature request or response is unsafe."""


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _parse_utc(value: Any, *, field: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise OpenMeteoIntervalFeatureError(f"missing {field}")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OpenMeteoIntervalFeatureError(f"invalid {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OpenMeteoIntervalFeatureError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _parse_label_bound(
    row: Mapping[str, Any],
    *,
    field: str,
    aliases: tuple[str, ...],
) -> datetime:
    """Read one explicit interval bound without silently resolving conflicts."""

    candidates = [
        (name, row.get(name))
        for name in aliases
        if row.get(name) not in (None, "")
    ]
    if not candidates:
        raise OpenMeteoIntervalFeatureError(f"missing {field}")
    parsed = [
        (name, _parse_utc(value, field=field))
        for name, value in candidates
    ]
    first = parsed[0][1]
    if any(value != first for _, value in parsed[1:]):
        names = ",".join(name for name, _ in parsed)
        raise OpenMeteoIntervalFeatureError(
            f"conflicting {field} aliases: {names}"
        )
    return first


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _date(value: Any, *, field: str) -> date:
    timestamp = _parse_utc(value, field=field)
    if timestamp.time() != datetime.min.time():
        raise OpenMeteoIntervalFeatureError(f"{field} must be at a UTC day boundary for daily features")
    return timestamp.date()


def _date_string(value: date) -> str:
    return value.isoformat()


def _finite_coordinate(value: Any, *, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise OpenMeteoIntervalFeatureError(f"invalid {field}") from exc
    if not math.isfinite(number):
        raise OpenMeteoIntervalFeatureError(f"invalid {field}")
    if field == "lat" and not -90.0 <= number <= 90.0:
        raise OpenMeteoIntervalFeatureError(f"invalid {field}")
    if field == "lng" and not -180.0 <= number <= 180.0:
        raise OpenMeteoIntervalFeatureError(f"invalid {field}")
    return number


def build_archive_url(
    latitude: float,
    longitude: float,
    start_date: date,
    end_date: date,
    *,
    model: str = "era5_land",
) -> str:
    if end_date < start_date:
        raise OpenMeteoIntervalFeatureError("archive end_date must not precede start_date")
    params = {
        "latitude": f"{latitude:.6f}",
        "longitude": f"{longitude:.6f}",
        "start_date": _date_string(start_date),
        "end_date": _date_string(end_date),
        "daily": ",".join(OPEN_METEO_DAILY_VARIABLES),
        "timezone": "UTC",
        "models": model,
    }
    return "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(params)


def _default_fetch(url: str, *, timeout_seconds: float = 90.0) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "avalanche-insight-hub-mvp4-feature-snapshot/1"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


class OpenMeteoArchiveClient:
    """Small injectable client for deterministic archive requests.

    Retries are deliberately bounded and apply only to transient HTTP status
    codes.  The request URL and response hash remain part of the snapshot
    provenance; retries never change interval or label semantics.
    """

    def __init__(
        self,
        fetch: Callable[[str], bytes] | None = None,
        *,
        max_retries: int = 2,
        backoff_seconds: float = 2.0,
        request_timeout_seconds: float = 90.0,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        if backoff_seconds < 0:
            raise ValueError("backoff_seconds must not be negative")
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        self._fetch = fetch or (
            lambda url: _default_fetch(url, timeout_seconds=request_timeout_seconds)
        )
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._sleep = sleep_fn

    def _fetch_with_retry(self, url: str) -> tuple[bytes, int]:
        retryable_statuses = {429, 500, 502, 503, 504}
        attempts = 0
        while True:
            attempts += 1
            try:
                return self._fetch(url), attempts
            except urllib.error.HTTPError as exc:
                if exc.code not in retryable_statuses or attempts > self._max_retries:
                    raise OpenMeteoIntervalFeatureError(
                        f"Open-Meteo archive request failed: HTTP {exc.code} "
                        f"after {attempts} attempt(s): {url}"
                    ) from exc
                retry_after = None
                if exc.headers is not None:
                    raw_retry_after = exc.headers.get("Retry-After")
                    if raw_retry_after:
                        try:
                            retry_after = max(0.0, float(raw_retry_after))
                        except ValueError:
                            retry_after = None
                delay = retry_after if retry_after is not None else self._backoff_seconds * (2 ** (attempts - 1))
                self._sleep(delay)
            except Exception as exc:  # pragma: no cover - transport-specific errors
                raise OpenMeteoIntervalFeatureError(
                    f"Open-Meteo archive request failed after {attempts} attempt(s): {url}"
                ) from exc

    def fetch_daily(
        self,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
        *,
        model: str = "era5_land",
    ) -> dict[str, Any]:
        lat = _finite_coordinate(latitude, field="lat")
        lng = _finite_coordinate(longitude, field="lng")
        url = build_archive_url(lat, lng, start_date, end_date, model=model)
        raw, request_attempts = self._fetch_with_retry(url)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OpenMeteoIntervalFeatureError("Open-Meteo archive response is not valid JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("daily"), Mapping):
            raise OpenMeteoIntervalFeatureError("Open-Meteo archive response has no daily object")
        daily = payload["daily"]
        times = daily.get("time")
        if not isinstance(times, list) or not times:
            raise OpenMeteoIntervalFeatureError("Open-Meteo archive response has no daily times")
        for variable in OPEN_METEO_DAILY_VARIABLES:
            values = daily.get(variable)
            if not isinstance(values, list) or len(values) != len(times):
                raise OpenMeteoIntervalFeatureError(
                    f"Open-Meteo archive daily variable is missing or misaligned: {variable}"
                )
        return {
            "url": url,
            "latitude": payload.get("latitude", lat),
            "longitude": payload.get("longitude", lng),
            "model": model,
            "start_date": _date_string(start_date),
            "end_date": _date_string(end_date),
            "request_attempts": request_attempts,
            "raw_payload_sha256": _sha256(raw),
            "payload": payload,
        }


def _cache_key(url: str) -> str:
    """Deterministic SHA-256 request-addressed cache key from the archive URL.

    The cache is request-addressed (keyed by the URL), not content-addressed.
    Payload integrity is verified separately by recomputing the canonical
    payload hash on load and comparing it with the stored raw_payload_sha256.
    """
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _verify_cached_response(cached: dict[str, Any], url: str) -> bool:
    """Verify a cached response's structural and cryptographic integrity.

    Checks:
    - URL matches the expected request URL
    - model, start_date, end_date are present and non-empty
    - model, start_date, end_date cross-checked against URL query parameters
    - canonical_payload_sha256 is present and is a valid SHA-256 digest
    - recomputed canonical payload hash matches the stored canonical_payload_sha256
    - daily payload has all required variables aligned with the time array

    The canonical_payload_sha256 is computed from the parsed payload using
    _canonical_bytes (deterministic JSON serialization).  This is separate
    from raw_payload_sha256 (the hash of the raw HTTP response bytes),
    which is preserved as-is for provenance but cannot be recomputed from
    the cached parsed payload alone.

    Returns True if all checks pass, False otherwise.  A False result
    causes the caller to silently discard the entry and re-fetch.
    """
    if str(cached.get("url") or "") != url:
        return False
    # Metadata fields must be present and non-empty
    for field in ("model", "start_date", "end_date"):
        if not str(cached.get(field) or "").strip():
            return False
    # Cross-check metadata against URL query parameters
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    url_model = str(query.get("models", [""])[0]).strip().lower()
    url_start = str(query.get("start_date", [""])[0]).strip()
    url_end = str(query.get("end_date", [""])[0]).strip()
    cached_model = str(cached.get("model") or "").strip().lower()
    cached_start = str(cached.get("start_date") or "").strip()
    cached_end = str(cached.get("end_date") or "").strip()
    if url_model and cached_model and url_model != cached_model:
        return False
    if url_start and cached_start and url_start != cached_start:
        return False
    if url_end and cached_end and url_end != cached_end:
        return False
    stored_hash = str(cached.get("canonical_payload_sha256") or "").strip().lower()
    if len(stored_hash) != 64 or any(c not in "0123456789abcdef" for c in stored_hash):
        return False
    payload = cached.get("payload")
    if not isinstance(payload, Mapping) or not isinstance(payload.get("daily"), Mapping):
        return False
    daily = payload["daily"]
    if not isinstance(daily.get("time"), list) or not daily["time"]:
        return False
    for variable in OPEN_METEO_DAILY_VARIABLES:
        values = daily.get(variable)
        if not isinstance(values, list) or len(values) != len(daily["time"]):
            return False
    # Cryptographic integrity: recompute canonical payload hash and compare
    recomputed_hash = _sha256(_canonical_bytes(payload))
    if recomputed_hash != stored_hash:
        return False
    return True


def _load_cached_response(cache_dir: Path | None, url: str) -> dict[str, Any] | None:
    """Load a cached archive response if it exists and passes integrity verification.

    Returns None if the cache is disabled, the entry is missing, or the
    cached payload fails structural or cryptographic validation.  Rejected
    entries are silently ignored so that a resume re-fetches the chunk.
    """
    if cache_dir is None:
        return None
    key = _cache_key(url)
    cache_path = cache_dir / f"{key}.json"
    if not cache_path.is_file():
        return None
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(cached, dict):
        return None
    if not _verify_cached_response(cached, url):
        return None
    return cached


def _store_cached_response(cache_dir: Path | None, response: dict[str, Any]) -> None:
    """Persist a successful archive response to the cache directory.

    Computes and stores a canonical_payload_sha256 alongside the response
    so that subsequent loads can verify payload integrity by recomputing
    the canonical hash from the cached parsed payload.
    """
    if cache_dir is None:
        return
    url = str(response.get("url") or "")
    if not url:
        return
    payload = response.get("payload")
    if not isinstance(payload, Mapping):
        return
    # Add canonical payload hash for integrity verification on load
    response_to_store = dict(response)
    response_to_store["canonical_payload_sha256"] = _sha256(_canonical_bytes(payload))
    key = _cache_key(url)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{key}.json"
    # Write atomically: temp file + rename to avoid partial writes on crash
    tmp_path = cache_path.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(response_to_store, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, cache_path)


def _build_cache_manifest(
    cache_dir: Path | None,
    fetch_records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Build an auditable cache manifest summarising all cached responses.

    Each entry records whether the cache file exists, whether it passed
    integrity verification (payload hash recomputation and URL metadata
    cross-check), and the canonical_payload_sha256 for external audit.
    The manifest itself is hashed so that provenance can reference a
    stable digest.
    """
    if cache_dir is None:
        return None
    entries: list[dict[str, Any]] = []
    for record in fetch_records:
        url = str(record.get("url") or "")
        if not url:
            continue
        key = _cache_key(url)
        cache_path = cache_dir / f"{key}.json"
        cached_exists = cache_path.is_file()
        verified = False
        canonical_hash = None
        if cached_exists:
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(cached, dict):
                    verified = _verify_cached_response(cached, url)
                    if verified:
                        canonical_hash = str(
                            cached.get("canonical_payload_sha256") or ""
                        ).strip().lower() or None
            except (OSError, json.JSONDecodeError):
                verified = False
        entries.append({
            "cache_key": key,
            "url": url,
            "cached": cached_exists,
            "integrity_verified": verified,
            "canonical_payload_sha256": canonical_hash,
            "feature_join_key": record.get("feature_join_key"),
            "chunk_index": record.get("chunk_index"),
            "start_date": record.get("start_date"),
            "end_date": record.get("end_date"),
            "raw_payload_sha256": record.get("raw_payload_sha256"),
        })
    manifest = {
        "cache_type": "request_addressed",
        "cache_dir": str(cache_dir),
        "entry_count": len(entries),
        "cached_count": sum(1 for e in entries if e["cached"]),
        "integrity_verified_count": sum(1 for e in entries if e["integrity_verified"]),
        "entries": entries,
    }
    manifest["cache_manifest_sha256"] = _sha256(_canonical_bytes(entries))
    return manifest


def _merge_archive_responses(responses: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge non-overlapping daily archive chunks into one deterministic payload."""
    if not responses:
        raise OpenMeteoIntervalFeatureError("at least one archive response is required")
    variables = OPEN_METEO_DAILY_VARIABLES
    by_date: dict[str, dict[str, Any]] = {}
    for response in responses:
        payload = response.get("payload")
        daily = payload.get("daily") if isinstance(payload, Mapping) else None
        if not isinstance(daily, Mapping) or not isinstance(daily.get("time"), list):
            raise OpenMeteoIntervalFeatureError("archive chunk has no mergeable daily payload")
        times = [str(value) for value in daily["time"]]
        values = {
            variable: daily.get(variable)
            for variable in variables
        }
        if any(not isinstance(values[variable], list) or len(values[variable]) != len(times) for variable in variables):
            raise OpenMeteoIntervalFeatureError("archive chunk daily variables are misaligned")
        for index, day in enumerate(times):
            row = {variable: values[variable][index] for variable in variables}
            existing = by_date.get(day)
            if existing is not None and existing != row:
                raise OpenMeteoIntervalFeatureError(f"archive chunks disagree for day {day}")
            by_date[day] = row
    ordered_days = sorted(by_date)
    merged_daily = {
        "time": ordered_days,
        **{
            variable: [by_date[day][variable] for day in ordered_days]
            for variable in variables
        },
    }
    merged_payload = {
        "latitude": responses[0].get("latitude"),
        "longitude": responses[0].get("longitude"),
        "daily": merged_daily,
    }
    return {
        "url": responses[0].get("url"),
        "latitude": responses[0].get("latitude"),
        "longitude": responses[0].get("longitude"),
        "model": responses[0].get("model"),
        "start_date": ordered_days[0],
        "end_date": ordered_days[-1],
        "chunk_count": len(responses),
        "request_attempts": sum(int(response.get("request_attempts") or 1) for response in responses),
        "raw_payload_sha256": _sha256(_canonical_bytes(merged_payload)),
        "payload": merged_payload,
    }


def _numeric_values(values: list[Any], *, variable: str) -> list[float]:
    result: list[float] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, bool):
            raise OpenMeteoIntervalFeatureError(f"{variable} contains a boolean")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise OpenMeteoIntervalFeatureError(f"{variable} contains a non-numeric value") from exc
        if not math.isfinite(number):
            raise OpenMeteoIntervalFeatureError(f"{variable} contains a non-finite value")
        result.append(number)
    return result


def aggregate_daily_interval(
    payload: Mapping[str, Any],
    interval_start: Any,
    interval_end: Any,
) -> dict[str, float | None]:
    """Aggregate daily fields over the complete half-open label interval."""

    start = _date(interval_start, field="interval_start")
    end = _date(interval_end, field="interval_end")
    if end <= start:
        raise OpenMeteoIntervalFeatureError("interval_end must be after interval_start")
    daily = payload.get("daily") if isinstance(payload, Mapping) else None
    if not isinstance(daily, Mapping):
        raise OpenMeteoIntervalFeatureError("daily payload is required")
    raw_times = daily.get("time")
    if not isinstance(raw_times, list):
        raise OpenMeteoIntervalFeatureError("daily.time must be a list")
    times = [date.fromisoformat(str(value)) for value in raw_times]
    required_days = [start + timedelta(days=index) for index in range((end - start).days)]
    positions = {value: index for index, value in enumerate(times)}
    missing_days = [value.isoformat() for value in required_days if value not in positions]
    if missing_days:
        raise OpenMeteoIntervalFeatureError(
            f"daily payload does not cover interval days: {','.join(missing_days[:5])}"
        )

    def values(variable: str) -> list[float]:
        raw_values = daily.get(variable)
        if not isinstance(raw_values, list) or len(raw_values) != len(times):
            raise OpenMeteoIntervalFeatureError(f"daily variable is missing or misaligned: {variable}")
        return _numeric_values(
            [raw_values[positions[day]] for day in required_days],
            variable=variable,
        )

    def mean(variable: str) -> float | None:
        selected = values(variable)
        return round(sum(selected) / len(selected), 6) if selected else None

    def total(variable: str) -> float | None:
        selected = values(variable)
        return round(sum(selected), 6) if selected else None

    def maximum(variable: str) -> float | None:
        selected = values(variable)
        return round(max(selected), 6) if selected else None

    return {
        "temperature_2m": mean("temperature_2m_mean"),
        "precipitation": total("precipitation_sum"),
        "snowfall": total("snowfall_sum"),
        "relative_humidity_2m": mean("relative_humidity_2m_mean"),
        "windspeed_10m": maximum("wind_speed_10m_max"),
    }


def _season_id(interval_start: str, region_key: str) -> str:
    timestamp = _parse_utc(interval_start, field="interval_start")
    start_month = 11 if region_key in {"himalayas_nepal", "pir_panjal_nw_himalaya"} else 7
    year = timestamp.year if timestamp.month >= start_month else timestamp.year - 1
    return f"{year}-{year + 1}"


def build_open_meteo_interval_features(
    labels: Iterable[Mapping[str, Any]],
    *,
    client: OpenMeteoArchiveClient,
    source_manifest_sha256: str,
    license_review_id: str,
    model: str = "era5_land",
    cutoff_policy: str = "valid_time_shadow",
    spatial_bin_km: float = 5.0,
    max_request_days: int = 366,
    cache_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """Fetch grouped daily features and return rows, source metadata, and fetch records.

    When *cache_dir* is supplied, successfully fetched archive responses are
    persisted as request-addressed JSON files with payload-integrity verification
    and reused on subsequent calls.
    This enables safe resumption of interrupted acquisitions without re-fetching
    completed chunks.  Corrupted or structurally invalid cache entries are
    silently discarded so that a resume re-fetches only the missing chunks.
    """

    model = str(model or "").strip().lower()
    metadata = MODEL_METADATA.get(model)
    if metadata is None:
        raise OpenMeteoIntervalFeatureError(
            f"unsupported historical reanalysis model: {model or '<empty>'}"
        )
    if cutoff_policy != "valid_time_shadow":
        raise OpenMeteoIntervalFeatureError(
            "unsupported cutoff policy; only the explicitly named valid_time_shadow policy is supported and remains non-promoting"
        )
    source_manifest_sha256 = str(source_manifest_sha256 or "").strip().lower()
    if len(source_manifest_sha256) != 64 or any(
        value not in "0123456789abcdef" for value in source_manifest_sha256
    ):
        raise OpenMeteoIntervalFeatureError("source_manifest_sha256 must be a SHA-256 value")
    if not str(license_review_id or "").strip():
        raise OpenMeteoIntervalFeatureError("license_review_id is required")
    if max_request_days <= 0:
        raise OpenMeteoIntervalFeatureError("max_request_days must be positive")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, raw in enumerate(labels):
        if raw.get("label") not in (1, True):
            continue
        region = str(raw.get("region_key") or "").strip()
        if not region:
            raise OpenMeteoIntervalFeatureError(f"label:{index}: region_key is required")
        start = _parse_label_bound(
            raw,
            field="interval_start",
            aliases=("interval_start", "event_time_start", "timestamp_start"),
        )
        end = _parse_label_bound(
            raw,
            field="interval_end",
            aliases=("interval_end", "event_time_end", "timestamp_end"),
        )
        if end <= start:
            raise OpenMeteoIntervalFeatureError(f"label:{index}: interval_end must be after interval_start")
        join_key = str(raw.get("feature_join_key") or "").strip()
        if not join_key:
            join_key = spatial_feature_join_key(raw.get("lat"), raw.get("lng"), region, bin_km=spatial_bin_km)
        grouped[join_key].append({
            "source_event_id": str(raw.get("source_event_id") or raw.get("event_id") or index),
            "region_key": region,
            "feature_join_key": join_key,
            "lat": _finite_coordinate(raw.get("lat"), field="lat"),
            "lng": _finite_coordinate(raw.get("lng"), field="lng"),
            "interval_start": start,
            "interval_end": end,
        })
    if not grouped:
        raise OpenMeteoIntervalFeatureError("no positive labels were supplied")

    fetched_by_group: dict[str, dict[str, Any]] = {}
    fetch_records: list[dict[str, Any]] = []
    cache_hits = 0
    cache_misses = 0
    for join_key, group in sorted(grouped.items()):
        start_date = min(item["interval_start"].date() for item in group)
        end_date = max(item["interval_end"].date() for item in group) - timedelta(days=1)
        representative = sorted(group, key=lambda item: item["source_event_id"])[0]
        chunks: list[dict[str, Any]] = []
        cursor = start_date
        chunk_index = 0
        while cursor <= end_date:
            chunk_end = min(end_date, cursor + timedelta(days=max_request_days - 1))
            # Build the URL to check the cache before fetching
            archive_url = build_archive_url(
                representative["lat"],
                representative["lng"],
                cursor,
                chunk_end,
                model=model,
            )
            cached = _load_cached_response(cache_dir, archive_url)
            if cached is not None:
                response = cached
                cache_hits += 1
            else:
                response = client.fetch_daily(
                    representative["lat"],
                    representative["lng"],
                    cursor,
                    chunk_end,
                    model=model,
                )
                _store_cached_response(cache_dir, response)
                cache_misses += 1
            chunks.append(response)
            fetch_records.append({
                "feature_join_key": join_key,
                "chunk_index": chunk_index,
                "requested_lat": representative["lat"],
                "requested_lng": representative["lng"],
                "start_date": _date_string(cursor),
                "end_date": _date_string(chunk_end),
                "url": response["url"],
                "raw_payload_sha256": response["raw_payload_sha256"],
                "request_attempts": response.get("request_attempts", 1),
                "model": model,
                "native_resolution_m": metadata["native_resolution_m"],
                "effective_information_scale_m": metadata["effective_information_scale_m"],
                "assignment_method": "representative_coordinate_native_grid_cell",
            })
            chunk_index += 1
            cursor = chunk_end + timedelta(days=1)
        fetched_by_group[join_key] = _merge_archive_responses(chunks)

    aggregate_hash = _sha256(_canonical_bytes(fetch_records))
    source_key = str(model).strip()
    if not source_key:
        raise OpenMeteoIntervalFeatureError("model must be non-empty")
    source_snapshot_id = f"open-meteo-archive-{source_key}-{aggregate_hash[:24]}"
    source_manifest = {
        "source_key": source_key,
        "source_family": OPEN_METEO_ARCHIVE_SOURCE_FAMILY,
        "source_snapshot_id": source_snapshot_id,
        "source_manifest_sha256": source_manifest_sha256,
        "source_content_sha256": aggregate_hash,
        "license": (
            f"Open-Meteo API data (CC BY 4.0); underlying Copernicus {metadata['dataset_product']} "
            "attribution required"
        ),
        "license_status": "pending",
        "license_review_id": license_review_id,
        "station_data_used": False,
        "direct_station_data_used": False,
        "underlying_reanalysis_observations": "included_by_provider",
        "observation_free": False,
        "station_feed_semantics": "no_direct_station_feed",
        "station_feed_clarification": (
            "No direct station records or station feed were used. "
            "The ERA5 reanalysis provider may assimilate observations "
            "from multiple sources, including stations."
        ),
        "data_provider": "Open-Meteo.com",
        "dataset_product": metadata["dataset_product"],
        "source_url": OPEN_METEO_HISTORICAL_API_URL,
        "license_url": OPEN_METEO_LICENSE_URL,
        "underlying_license_url": metadata["underlying_license_url"],
        "attribution_text": (
            "Weather data by Open-Meteo.com; Generated using Copernicus Climate Change "
            "Service Information [year]."
        ),
        "feature_availability_semantics": "retrospective_reanalysis",
        "forecast_ready": False,
        "retrospective_only": True,
        "availability_delay_days": metadata["availability_delay_days"],
        "model": model,
        "cutoff_policy": cutoff_policy,
        "cutoff_policy_review_status": "pending_scientist_approval",
        "native_resolution_m": metadata["native_resolution_m"],
        "effective_information_scale_m": metadata["effective_information_scale_m"],
    }

    rows: list[dict[str, Any]] = []
    seen_feature_ids: set[str] = set()
    for join_key, group in sorted(grouped.items()):
        response = fetched_by_group[join_key]
        for item in sorted(group, key=lambda value: (value["interval_start"], value["source_event_id"])):
            start = item["interval_start"]
            end = item["interval_end"]
            identity = f"{join_key}|{start.isoformat()}|{end.isoformat()}"
            feature_id = f"{source_key}:{_sha256(identity.encode())[:24]}"
            if feature_id in seen_feature_ids:
                continue
            seen_feature_ids.add(feature_id)
            rows.append({
                "feature_id": feature_id,
                "source_key": source_key,
                "source_family": OPEN_METEO_ARCHIVE_SOURCE_FAMILY,
                "source_snapshot_id": source_snapshot_id,
                "source_manifest_sha256": source_manifest_sha256,
                "source_content_sha256": response["raw_payload_sha256"],
                "region_key": item["region_key"],
                "feature_join_key": join_key,
                "feature_valid_from": _iso(start),
                "feature_valid_until": _iso(end),
                "feature_cutoff_at": _iso(start),
                "feature_cutoff_status": "explicit_provisional_valid_time_shadow",
                "features": aggregate_daily_interval(response["payload"], start, end),
                "station_data_used": False,
                "direct_station_data_used": False,
                "underlying_reanalysis_observations": "included_by_provider",
                "observation_free": False,
                "station_feed_semantics": "no_direct_station_feed",
                "station_feed_clarification": (
                    "No direct station records or station feed were used. "
                    "The ERA5 reanalysis provider may assimilate observations "
                    "from multiple sources, including stations."
                ),
                "data_provider": "Open-Meteo.com",
                "dataset_product": metadata["dataset_product"],
                "feature_availability_semantics": "retrospective_reanalysis",
                "forecast_ready": False,
                "retrospective_only": True,
                "availability_delay_days": metadata["availability_delay_days"],
                "training_eligible": False,
                "core_training_eligible": False,
                "production_eligible": False,
                "production_scoring_eligible": False,
                "native_source_lat": response["latitude"],
                "native_source_lng": response["longitude"],
                "native_resolution_m": metadata["native_resolution_m"],
                "effective_information_scale_m": metadata["effective_information_scale_m"],
                "assignment_method": "representative_coordinate_native_grid_cell",
                "positive_season_id": _season_id(_iso(start), item["region_key"]),
            })
    rows.sort(key=lambda row: (row["region_key"], row["feature_join_key"], row["feature_valid_from"], row["feature_id"]))
    cache_manifest = _build_cache_manifest(cache_dir, fetch_records)
    if cache_manifest is not None:
        cache_manifest["cache_hits"] = cache_hits
        cache_manifest["cache_misses"] = cache_misses
        cache_manifest_dir = cache_dir
        if cache_manifest_dir is not None:
            cache_manifest_dir.mkdir(parents=True, exist_ok=True)
            (cache_manifest_dir / "cache_manifest.json").write_text(
                json.dumps(cache_manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        source_manifest["cache_manifest_sha256"] = cache_manifest.get("cache_manifest_sha256")
        source_manifest["cache_integrity_verified_count"] = cache_manifest.get("integrity_verified_count")
    return rows, source_manifest, fetch_records
