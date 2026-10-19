"""MeteoIO Open-Meteo data bridge for SNOWPACK integration.

Converts Open-Meteo weather data into MeteoIO-compatible SMET files that
SNOWPACK can consume directly. This replaces the need for a custom C++
MeteoIO plugin — instead we generate SMET text files that MeteoIO reads
natively via its built-in SMET plugin.

SMET (Simple Meteorological Data Format) is the standard input format for
SNOWPACK/MeteoIO. Each file contains hourly weather data for one station
(grid cell) with metadata header + data section.

When SNOWPACK C++ is compiled (via scripts/build_snowpack.sh), this module
generates SMET files, invokes SNOWPACK, and parses the .pro profile output.
When SNOWPACK is not available, the pipeline falls back to COSIPY or the
heuristic proxy.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from backend.common.snowpack_paths import UnsafePathError, ensure_safe_directory
from backend.common.snowpack_toolchain_identity import is_real_image_id, is_real_sha256


@dataclass
class NativeExecutionEvidence:
    """C0-S5: Structured execution evidence captured DURING native execution.

    This is NOT reconstructed after the fact. It contains the actual subprocess
    return code, real binary hash, real timestamps, and real command.

    Used to build invocation.json attestation for the release gate.
    """
    binary_path: str = ''
    binary_sha256: str = ''
    binary_version: str = ''
    command: str = ''
    command_sha256: str = ''
    exit_code: int = -1
    started_at: str = ''
    finished_at: str = ''
    toolchain_id: str = ''
    run_id: str = ''
    stdout_sha256: str = ''
    stderr_sha256: str = ''
    version_exit_code: int = -1
    version_verified: bool = False
    toolchain_manifest_path: str = ''
    toolchain_manifest_sha256: str = ''
    toolchain_manifest: dict[str, Any] | None = None
    toolchain_manifest_verified: bool = False
    # R6: keep local image identity, archive integrity, and registry identity
    # separate. A Docker image ID is not a repository digest.
    image_id: str = ''
    image_archive_sha256: str = ''
    image_repository_digest: str = ''
    image_identity_source: str = ''
    pro_path: str = ''
    log_path: str = ''
    success: bool = False

    # Compatibility surface for the pre-C0 physics caller, which passed the
    # native return value directly to parse_snowpack_pro(). New callers should
    # consume ``pro_path`` explicitly; failed evidence deliberately behaves as
    # a missing profile so it cannot be parsed as native success.
    def _profile_path(self) -> Path:
        if not self.success or not self.pro_path:
            raise FileNotFoundError('native execution evidence has no successful profile path')
        return Path(self.pro_path)

    def __fspath__(self) -> str:
        return os.fspath(self._profile_path())

    def exists(self) -> bool:
        return bool(self.success and self.pro_path) and Path(self.pro_path).exists()

    def is_symlink(self) -> bool:
        return Path(self.pro_path).is_symlink() if self.pro_path else False

    def is_file(self) -> bool:
        return self.exists() and Path(self.pro_path).is_file()

    def stat(self):
        return self._profile_path().stat()

    def read_text(self, *args: Any, **kwargs: Any) -> str:
        return self._profile_path().read_text(*args, **kwargs)


# SMET column names mapping to Open-Meteo variables
SMET_COLUMNS = [
    'timestamp',      # ISO 8601
    'TA',             # Air temperature (K) — from temperature_2m + 273.15
    'RH',             # Relative humidity [0,1] — from percent relative_humidity_2m
    'VW',             # Wind speed (m/s) — from windspeed_10m
    'DW',             # Wind direction (deg) — from winddirection_10m
    'ISWR',           # Incoming shortwave radiation (W/m2) — from shortwave_radiation
    'ILWR',           # Incoming longwave radiation (W/m2) — from true longwave or cloud/temp estimate
    'PSUM',           # Precipitation (mm/h) — from precipitation
    'HS',             # Snow height (m) — from snow_depth / 100
    'TSG',            # Ground temperature (K) — estimated from air temp
    'TSS',            # Surface temperature (K) — estimated from air temp + snow
]


def derive_incoming_longwave_wm2(
    *,
    temperature_c: float,
    relative_humidity_fraction: float,
    cloud_cover_percent: float,
) -> float:
    """Estimate incoming longwave radiation from atmospheric inputs.

    Open-Meteo's ``terrestrial_radiation`` is a top-of-atmosphere solar
    quantity. It must not be used as SNOWPACK ILWR. This named engineering
    bridge is used only when a true longwave source field is unavailable.
    """
    temp_c = float(temperature_c)
    rh_fraction = float(np.clip(relative_humidity_fraction, 0.0, 1.0))
    cloud_fraction = float(np.clip(float(cloud_cover_percent) / 100.0, 0.0, 1.0))
    temperature_k = temp_c + 273.15
    e_clear = 1.24 * (
        rh_fraction * np.exp(17.27 * temp_c / (237.3 + temp_c)) / temperature_k
    ) ** (1.0 / 7.0)
    e_clear = float(np.clip(e_clear, 0.2, 1.0))
    e_effective = e_clear * (1.0 - cloud_fraction) + 0.995 * cloud_fraction
    sigma = 5.67e-8
    return max(100.0, float(e_effective * sigma * temperature_k ** 4))


def _open_meteo_to_smet_row(
    sample: dict[str, Any],
    prev_snow_height: float | None = None,
) -> dict[str, float | str]:
    """Convert a single Open-Meteo hourly sample to SMET column values."""
    temp_c = float(sample.get('temperature_2m', 0.0) or 0.0)
    rh_percent = float(sample.get('relative_humidity_2m', 80.0) or 80.0)
    rh_fraction = float(np.clip(rh_percent / 100.0, 0.0, 1.0))
    vw = float(sample.get('windspeed_10m', 0.0) or 0.0)
    dw = float(sample.get('winddirection_10m', 0.0) or 0.0)
    sw = float(sample.get('shortwave_radiation', 0.0) or 0.0)
    psum = float(sample.get('precipitation', 0.0) or 0.0)
    raw_snow_depth = sample.get('snow_depth')
    snow_depth_m = None if raw_snow_depth is None else float(raw_snow_depth)

    # Longwave radiation: use an explicitly named true longwave field, else
    # derive it from cloud cover and temperature. terrestrial_radiation is
    # top-of-atmosphere solar radiation and is deliberately ignored here.
    lw = sample.get('longwave_radiation')
    if lw is not None:
        ilwr = max(100.0, float(lw))
    else:
        cloud_cover = sample.get('cloud_cover')
        if cloud_cover is None:
            raise ValueError(
                'ILWR requires longwave_radiation or cloud_cover; '
                'terrestrial_radiation is not a valid substitute'
            )
        ilwr = derive_incoming_longwave_wm2(
            temperature_c=temp_c,
            relative_humidity_fraction=rh_fraction,
            cloud_cover_percent=float(cloud_cover),
        )

    # Ground temperature: approximate as mean annual ground temp (~0°C for snow-covered)
    tsg = 273.15 + max(-2.0, min(2.0, temp_c * 0.3))

    # Surface temperature: between air temp and snow temp
    if snow_depth_m is not None and snow_depth_m > 0.01:
        tss = 273.15 + max(-30.0, min(0.0, temp_c))
    else:
        tss = 273.15 + temp_c

    return {
        'timestamp': sample.get('time', sample.get('timestamp', '')),
        'TA': round(temp_c + 273.15, 2),
        'RH': round(rh_fraction, 6),
        'VW': round(max(0.0, vw), 2),
        'DW': round(dw, 1),
        'ISWR': round(max(0.0, sw), 1),
        'ILWR': round(ilwr, 1),
        'PSUM': round(max(0.0, psum), 2),
        # HS is optional when PSUM is supplied.  Missing source snow depth is
        # MeteoIO nodata, never a fabricated zero snow height.
        'HS': -999.0 if snow_depth_m is None else round(max(0.0, snow_depth_m), 3),
        'TSG': round(tsg, 2),
        'TSS': round(tss, 2),
    }


def _validate_precipitation_phase(value: Any) -> float:
    """Validate SNOWPACK's PSUM_PH fraction: 0 solid, 1 liquid."""

    try:
        phase = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('PSUM_PH must be numeric') from exc
    if not math.isfinite(phase) or not 0.0 <= phase <= 1.0:
        raise ValueError('PSUM_PH must be a finite fraction between 0 and 1')
    return phase


def validate_smet_samples(
    samples: list[dict[str, Any]],
    *,
    strict: bool = True,
    expected_cadence_hours: float | None = None,
) -> None:
    """Validate source samples before generating an SMET forcing file.

    Strict mode rejects missing critical source values instead of allowing the
    row converter to silently substitute zeros/defaults. Longwave radiation
    may be supplied directly or derived from cloud cover, matching the
    official SNOWPACK/MeteoIO alternative-input model.

    Phase 0.5: also validates time sequence monotonicity and chronology.
    Invalid time sequences (non-monotonic, duplicate timestamps, gaps) are
    rejected in strict mode to prevent silent data corruption.
    """
    if not samples:
        raise ValueError('SNOWPACK forcing requires at least one sample')
    if not strict:
        return

    if expected_cadence_hours is not None and expected_cadence_hours <= 0:
        raise ValueError('expected_cadence_hours must be positive')

    required = ('time', 'temperature_2m', 'relative_humidity_2m', 'windspeed_10m')
    prev_time: datetime | None = None
    inferred_cadence_seconds: float | None = None
    for index, sample in enumerate(samples):
        missing = [key for key in required if key not in sample or sample[key] is None]
        has_shortwave = any(
            key in sample and sample[key] is not None
            for key in ('shortwave_radiation', 'reflected_shortwave_radiation', 'net_shortwave_radiation')
        )
        has_precipitation = any(
            key in sample and sample[key] is not None
            for key in ('precipitation', 'snowfall', 'snow_depth')
        )
        has_longwave_or_generator_inputs = any(
            key in sample and sample[key] is not None
            for key in ('longwave_radiation', 'cloud_cover')
        )
        if not has_shortwave:
            missing.append('ISWR/RSWR/NET_SW')
        if not has_longwave_or_generator_inputs:
            missing.append('ILWR/TSS or cloud_cover-derived ILWR')
        if not has_precipitation:
            missing.append('PSUM/HS')
        if missing:
            raise ValueError(
                f'SNOWPACK forcing sample {index} is incomplete: {sorted(set(missing))}'
            )
        for key, value in sample.items():
            if isinstance(value, (int, float)) and not math.isfinite(float(value)):
                raise ValueError(f'SNOWPACK forcing sample {index} has non-finite {key}')

        # C0.39: Parse timestamps to timezone-aware UTC before comparing.
        raw_time = sample.get('time', sample.get('timestamp', ''))
        if not isinstance(raw_time, str) or not raw_time.strip():
            raise ValueError(f'SNOWPACK forcing sample {index} has no timestamp')
        try:
            normalized_time = raw_time.strip().replace('Z', '+00:00')
            current_time = datetime.fromisoformat(normalized_time)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f'SNOWPACK forcing sample {index} has invalid timestamp: {raw_time!r}'
            ) from exc
        # Existing Open-Meteo hourly responses omit an offset; treat those
        # values as UTC at this bridge boundary, then retain an aware value.
        if current_time.tzinfo is None or current_time.utcoffset() is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        current_time = current_time.astimezone(timezone.utc)
        if prev_time is not None:
            delta_seconds = (current_time - prev_time).total_seconds()
            if delta_seconds <= 0:
                raise ValueError(
                    f'SNOWPACK forcing time sequence is non-monotonic or duplicate '
                    f'at sample {index}: {raw_time!r}'
                )
            expected_seconds = (
                expected_cadence_hours * 3600
                if expected_cadence_hours is not None
                else inferred_cadence_seconds
            )
            if expected_seconds is None:
                inferred_cadence_seconds = delta_seconds
            elif not math.isclose(delta_seconds, expected_seconds, rel_tol=0.0, abs_tol=1.0):
                raise ValueError(
                    f'SNOWPACK forcing cadence/gap mismatch at sample {index}: '
                    f'got {delta_seconds / 3600:g}h, expected {expected_seconds / 3600:g}h'
                )
        prev_time = current_time


def write_smet_file(
    *,
    output_path: Path,
    station_id: str,
    latitude: float,
    longitude: float,
    elevation: float,
    samples: list[dict[str, Any]],
    slope_angle: float = 0.0,
    aspect: float = 0.0,
    strict: bool = True,
    expected_cadence_hours: float | None = None,
    include_precipitation_phase: bool = False,
) -> Path:
    """Write an SMET file from Open-Meteo weather samples.

    Args:
        output_path: Path to write the .smet file
        station_id: Station identifier (e.g., "cell_33.5_76.5")
        latitude: Station latitude
        longitude: Station longitude
        elevation: Station elevation in meters
        samples: List of hourly weather samples from Open-Meteo
        slope_angle: Slope angle in degrees (for SNOWPACK terrain)
        aspect: Slope aspect in degrees

    Returns:
        Path to the written SMET file
    """
    validate_smet_samples(
        samples,
        strict=strict,
        expected_cadence_hours=expected_cadence_hours,
    )
    lines: list[str] = []

    source_times: list[datetime] = []
    if strict:
        for sample in samples:
            raw_time = str(sample.get('time', sample.get('timestamp', ''))).replace('Z', '+00:00')
            parsed_time = datetime.fromisoformat(raw_time)
            if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
                parsed_time = parsed_time.replace(tzinfo=timezone.utc)
            source_times.append(parsed_time.astimezone(timezone.utc))
    source_cadence_hours = ''
    if len(source_times) > 1:
        source_cadence_hours = str(
            round((source_times[1] - source_times[0]).total_seconds() / 3600.0, 6)
        )

    # SMET header
    lines.append('SMET 1.1 ASCII')
    lines.append('[HEADER]')
    lines.append(f'station_id       = {station_id}')
    lines.append(f'station_name     = {station_id}')
    lines.append(f'latitude         = {latitude:.6f}')
    lines.append(f'longitude        = {longitude:.6f}')
    # MeteoIO 2.11 uses ``altitude`` as the mandatory WGS84 height key.
    # Keep the descriptive ``elevation`` alias for downstream readers.
    lines.append(f'altitude         = {elevation:.1f}')
    lines.append(f'elevation        = {elevation:.1f}')
    lines.append(f'slope_angle      = {slope_angle:.1f}')
    lines.append(f'aspect           = {aspect:.1f}')
    columns = list(SMET_COLUMNS)
    if include_precipitation_phase:
        for index, sample in enumerate(samples):
            if 'precipitation_phase' not in sample:
                raise ValueError(
                    f'SMET sample {index} is missing precipitation_phase required for PSUM_PH'
                )
            _validate_precipitation_phase(sample['precipitation_phase'])
        columns.append('PSUM_PH')
    lines.append(f'ncolumns         = {len(columns)}')
    lines.append(f'column_names     = {",".join(columns)}')
    lines.append(f'fields           = {" ".join(columns)}')
    lines.append('nodata            = -999')
    # MeteoIO's SMET parser expects whitespace-delimited unit vectors.  The
    # comma-delimited form is accepted by neither the pinned 2.11 parser nor
    # the SNOWPACK 3.7 bridge used by the POC container.
    lines.append(f'units_offset     = {" ".join("0" for _ in columns)}')
    lines.append(f'units_multiplier = {" ".join("1" for _ in columns)}')
    lines.append('tz               = 0')
    lines.append('timezone         = UTC')
    if source_times:
        lines.append(f'source_time_start = {source_times[0].isoformat()}')
        lines.append(f'source_time_end   = {source_times[-1].isoformat()}')
        if source_cadence_hours:
            lines.append(f'source_cadence_hours = {source_cadence_hours}')
        lines.append('source_time_semantics = timezone-aware UTC')
    lines.append('[DATA]')

    # Data rows
    for sample in samples:
        row = _open_meteo_to_smet_row(sample)
        lines.append(
            f"{row['timestamp']} "
            f"{row['TA']} {row['RH']} {row['VW']} {row['DW']} "
            f"{row['ISWR']} {row['ILWR']} {row['PSUM']} {row['HS']} "
            f"{row['TSG']} {row['TSS']}"
        )
        if include_precipitation_phase:
            lines[-1] += f" {_validate_precipitation_phase(sample['precipitation_phase']):.6f}"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return output_path


def write_snow_free_smet_profile(
    *,
    output_path: Path,
    station_id: str,
    latitude: float,
    longitude: float,
    elevation: float,
    profile_date: str,
    slope_angle: float = 0.0,
    aspect: float = 0.0,
) -> Path:
    """Write an explicit zero-layer SMET initial state for SNOWPACK 3.7.

    The pinned SNOWPACK/MeteoIO source has no ``SNOW = NONE`` input mode. Its
    SMET snow-cover reader instead accepts a profile with zero soil and snow
    layers, which is the revision-compatible representation of a snow-free
    start. This helper creates only that runtime seed; it does not establish
    that the selected site was scientifically snow-free.
    """
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', station_id):
        raise ValueError(f'Invalid SNOWPACK station_id: {station_id!r}')
    for value, field_name in (
        (latitude, 'latitude'),
        (longitude, 'longitude'),
        (elevation, 'elevation'),
        (slope_angle, 'slope_angle'),
        (aspect, 'aspect'),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f'{field_name} must be a finite number')
    if not -90.0 <= float(latitude) <= 90.0:
        raise ValueError('latitude is outside valid bounds')
    if not -180.0 <= float(longitude) <= 180.0:
        raise ValueError('longitude is outside valid bounds')
    if not 0.0 <= float(slope_angle) <= 90.0:
        raise ValueError('slope_angle is outside valid bounds')
    if not 0.0 <= float(aspect) <= 360.0:
        raise ValueError('aspect is outside valid bounds')
    normalized_profile_date = profile_date.strip().replace('Z', '+00:00')
    try:
        parsed_profile_date = datetime.fromisoformat(normalized_profile_date)
    except ValueError as exc:
        raise ValueError('profile_date must be ISO-8601') from exc
    if parsed_profile_date.tzinfo is None or parsed_profile_date.utcoffset() is None:
        raise ValueError('profile_date must be timezone-aware UTC')
    if parsed_profile_date.utcoffset() != timezone.utc.utcoffset(parsed_profile_date):
        raise ValueError('profile_date must use UTC offset +00:00')
    profile_date_utc = parsed_profile_date.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')

    # These are the 18 layer columns defined by SNOWPACK's SMET initial
    # profile format; with nSnowLayerData=0 the [DATA] section is empty.
    layer_fields = (
        'timestamp Layer_Thick T Vol_Frac_I Vol_Frac_W Vol_Frac_V '
        'Vol_Frac_S Rho_S Conduc_S HeatCapac_S rg rb dd sp mk mass_hoar ne CDot metamo'
    )
    content = '\n'.join([
        'SMET 1.1 ASCII',
        '[HEADER]',
        f'station_id = {station_id}',
        f'station_name = {station_id}',
        f'latitude = {float(latitude):.6f}',
        f'longitude = {float(longitude):.6f}',
        f'altitude = {float(elevation):.1f}',
        'nodata = -999',
        'tz = 0',
        f'ProfileDate = {profile_date_utc}',
        'HS_Last = 0.000000',
        f'SlopeAngle = {float(slope_angle):.2f}',
        f'SlopeAzi = {float(aspect):.2f}',
        'nSoilLayerData = 0',
        'nSnowLayerData = 0',
        'SoilAlbedo = 0.20',
        'BareSoil_z0 = 0.020',
        'CanopyHeight = 0.00',
        'CanopyLeafAreaIndex = 0.00',
        'CanopyDirectThroughfall = 1.00',
        'WindScalingFactor = 1.00',
        'ErosionLevel = 0',
        'TimeCountDeltaHS = 0.000000',
        f'fields = {layer_fields}',
        '[DATA]',
        '',
    ])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding='utf-8')
    return output_path


def _resolve_snowpack_binary() -> Path | None:
    """Resolve the exact SNOWPACK executable used for preflight and execution."""
    snowpack_home = os.getenv('SNOWPACK_HOME', '')
    if snowpack_home:
        binary = Path(snowpack_home) / 'bin' / 'snowpack'
        if binary.is_file():
            return binary
    resolved = shutil.which('snowpack')
    return Path(resolved) if resolved else None


def snowpack_binary_available() -> bool:
    """Check if the exact SNOWPACK binary is available on the system."""
    return _resolve_snowpack_binary() is not None


def _canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    """Serialize a toolchain manifest deterministically for attestation."""
    return json.dumps(manifest, indent=2, sort_keys=True).encode('utf-8')


def _load_toolchain_manifest(
    binary: Path,
    *,
    binary_sha256: str,
    binary_version: str,
) -> tuple[Path | None, str, dict[str, Any] | None, bool]:
    """Load and cross-check the runtime toolchain manifest.

    The manifest is the runtime identity source. It must agree with the
    independently probed binary hash and version before native execution can
    be marked successful.
    """
    configured_path = os.getenv("SNOWPACK_TOOLCHAIN_MANIFEST_PATH", "")
    if configured_path:
        # An explicit operator path is authoritative. If it is missing or
        # unsafe, fail closed rather than silently falling back to a nearby
        # manifest with a different provenance.
        manifest_path = Path(configured_path)
    else:
        candidates = (
            binary.parent.parent / "toolchain-manifest.json",
            binary.parent / "toolchain-manifest.json",
        )
        manifest_path = next(
            (candidate for candidate in candidates
             if candidate.is_file() and not candidate.is_symlink()),
            None,
        )
    if manifest_path is None or manifest_path.is_symlink() or not manifest_path.is_file():
        return None, "", None, False
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        if not isinstance(manifest, dict):
            return manifest_path, "", None, False
        if 'image_digest' in manifest:
            # R6: legacy naming is ambiguous because a local Docker image ID
            # is not a registry/repository digest.
            return manifest_path, "", manifest, False
        expected_hash = manifest.get("binary_sha256")
        expected_version = manifest.get("binary_version")
        expected_path = manifest.get("binary_path")
        # R6: these values come from the workflow's preflight boundary. Do not
        # fall back to the manifest or a legacy digest field.
        image_id = os.getenv('SNOWPACK_IMAGE_ID', '')
        image_archive_sha256 = os.getenv('SNOWPACK_IMAGE_ARCHIVE_SHA256', '')
        image_repository_digest = os.getenv('SNOWPACK_IMAGE_REPOSITORY_DIGEST', '')
        if not isinstance(expected_hash, str) or not isinstance(expected_version, str):
            return manifest_path, hashlib.sha256(_canonical_manifest_bytes(manifest)).hexdigest(), manifest, False
        if not is_real_image_id(image_id):
            return manifest_path, hashlib.sha256(_canonical_manifest_bytes(manifest)).hexdigest(), manifest, False
        if not is_real_sha256(image_archive_sha256):
            return manifest_path, hashlib.sha256(_canonical_manifest_bytes(manifest)).hexdigest(), manifest, False
        if image_repository_digest and not is_real_image_id(image_repository_digest):
            return manifest_path, hashlib.sha256(_canonical_manifest_bytes(manifest)).hexdigest(), manifest, False
        manifest = dict(manifest)
        manifest['image_id'] = image_id
        manifest['image_archive_sha256'] = image_archive_sha256
        manifest['image_repository_digest'] = image_repository_digest
        manifest['image_identity_source'] = (
            'registry_digest_and_archive' if image_repository_digest
            else 'local_id_and_archive'
        )
        expected_version = ' '.join(expected_version.split())
        observed_version = ' '.join(binary_version.split())
        manifest['binary_version'] = expected_version
        path_matches = not expected_path or Path(expected_path).name == binary.name
        verified = (
            path_matches
            and expected_hash.lower() == binary_sha256.lower()
            and expected_version == observed_version
        )
        return (
            manifest_path,
            hashlib.sha256(_canonical_manifest_bytes(manifest)).hexdigest(),
            manifest,
            verified,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return manifest_path, "", None, False


def _native_config_has_paths(config_path: Path) -> bool:
    """Return whether an INI contains the paths required by SNOWPACK 3.7."""
    try:
        content = config_path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return False
    required = (
        'METEOPATH',
        'STATION1',
        'EXPERIMENT',
    )
    return all(re.search(rf'^\s*{key}\s*=', content, re.MULTILINE) for key in required)


def _smet_coordinates(smet_path: Path) -> tuple[float, float] | None:
    """Read finite WGS84 latitude/longitude metadata from a SMET header."""
    try:
        content = smet_path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return None

    in_header = False
    values: dict[str, float] = {}
    for line in content.splitlines():
        marker = line.strip().upper()
        if marker == '[HEADER]':
            in_header = True
            continue
        if marker == '[DATA]':
            break
        if not in_header or '=' not in line:
            continue
        key, raw_value = line.split('=', 1)
        key = key.strip().lower()
        if key not in {'latitude', 'longitude'}:
            continue
        try:
            value = float(raw_value.strip())
        except ValueError:
            return None
        if not math.isfinite(value):
            return None
        values[key] = value

    latitude = values.get('latitude')
    longitude = values.get('longitude')
    if latitude is None or longitude is None:
        return None
    if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
        return None
    return latitude, longitude


def _utm_zone_parameter(latitude: float, longitude: float) -> str:
    """Return MeteoIO's UTM zone parameter for WGS84 coordinates."""
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise ValueError('latitude and longitude must be finite')
    if not -80.0 <= latitude <= 84.0:
        raise ValueError('UTM latitude must be between -80 and 84 degrees')
    if not -180.0 <= longitude <= 180.0:
        raise ValueError('longitude must be between -180 and 180 degrees')

    zone_number = min(60, max(1, int((longitude + 180.0) // 6.0) + 1))
    # UTM latitude bands used by MeteoIO. X is intentionally repeated for
    # 72–84 degrees, matching the standard UTM definition.
    bands = 'CDEFGHJKLMNPQRSTUVWXX'
    band_index = min(len(bands) - 1, int((latitude + 80.0) // 8.0))
    return f'{zone_number}{bands[band_index]}'


def _last_smet_timestamp(smet_path: Path) -> str | None:
    """Extract the last valid SMET data timestamp for the optional ``-e`` flag."""
    try:
        content = smet_path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return None

    in_data = False
    last_time: datetime | None = None
    for line in content.splitlines():
        if line.strip().upper() == '[DATA]':
            in_data = True
            continue
        if not in_data or not line.strip() or line.lstrip().startswith('#'):
            continue
        raw_timestamp = line.split(maxsplit=1)[0]
        try:
            parsed = datetime.fromisoformat(raw_timestamp.replace('Z', '+00:00'))
        except ValueError:
            continue
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        last_time = parsed.astimezone(timezone.utc)
    if last_time is None:
        return None
    return last_time.strftime('%Y-%m-%dT%H:%M')


def _prepare_native_config(
    *,
    smet_path: Path,
    output_dir: Path,
    config_path: Path | None,
) -> Path:
    """Use a revision-compatible config, adapting legacy callers safely."""
    if config_path is not None:
        candidate = Path(config_path)
        if candidate.is_symlink():
            raise UnsafePathError(f'SNOWPACK config is symlinked: {candidate}')
        if candidate.is_file() and _native_config_has_paths(candidate):
            return candidate.resolve()

    station_id = re.sub(r'[^A-Za-z0-9_.-]+', '_', smet_path.stem).strip('._-') or 'station'
    coordinates = _smet_coordinates(smet_path)
    if coordinates is None:
        raise ValueError(
            'generated SNOWPACK config requires finite latitude/longitude in SMET header'
        )
    generated_path = output_dir / f'{station_id}.native.ini'
    return generate_snowpack_config(
        output_path=generated_path,
        season_start_date='1970-01-01',
        end_date='1970-01-01',
        station_id=station_id,
        latitude=coordinates[0],
        longitude=coordinates[1],
        meteo_path=smet_path.parent,
        output_dir=output_dir,
        experiment='native',
    )


def _discover_native_profile(output_dir: Path, station_id: str) -> Path | None:
    """Find exactly one non-empty profile produced for a station."""
    candidates = [
        path for path in sorted(output_dir.glob(f'{station_id}*.pro'))
        if path.is_file() and not path.is_symlink() and path.stat().st_size > 0
    ]
    if len(candidates) != 1:
        return None
    return candidates[0]


def run_snowpack_native(
    *,
    smet_path: Path,
    output_dir: Path,
    config_path: Path | None = None,
    begin_date: str | None = None,
    end_date: str | None = None,
    timeout_s: int = 60,
    run_id: str = '',
    toolchain_id: str = '',
) -> NativeExecutionEvidence | None:
    """Run SNOWPACK binary on a single SMET input file.

    C0-S5: Returns NativeExecutionEvidence with real subprocess data, NOT
    just a Path. The evidence is captured DURING execution and cannot be
    reconstructed after the fact.

    Args:
        smet_path: Path to the input .smet file
        output_dir: Directory for output .pro profile files
        config_path: Optional SNOWPACK .ini config file
        begin_date: Optional ISO start date passed to the official ``-b`` option
        end_date: Optional ISO end date passed to the official ``-e`` option
        timeout_s: Execution timeout in seconds
        run_id: Run ID for attestation binding
        toolchain_id: Toolchain ID for attestation binding

    Returns:
        NativeExecutionEvidence with real execution data, or None if binary unavailable
    """
    binary = _resolve_snowpack_binary()
    if binary is None:
        return None

    try:
        output_dir = ensure_safe_directory(output_dir, create=True)
        execution_config = _prepare_native_config(
            smet_path=Path(smet_path),
            output_dir=output_dir,
            config_path=config_path,
        )
    except (OSError, RuntimeError, UnsafePathError, ValueError):
        return None

    cmd = [str(binary), '-c', str(execution_config)]
    if begin_date:
        cmd.extend(['-b', begin_date])
    effective_end_date = end_date or _last_smet_timestamp(Path(smet_path))
    if effective_end_date:
        cmd.extend(['-e', effective_end_date])

    # C0-S5: Capture REAL execution evidence
    started_at = datetime.now(timezone.utc).isoformat()
    command_str = ' '.join(cmd)
    command_sha256 = hashlib.sha256(command_str.encode()).hexdigest()

    # Compute binary hash
    binary_sha256 = ''
    try:
        if binary.exists():
            h = hashlib.sha256()
            with open(binary, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    h.update(chunk)
            binary_sha256 = h.hexdigest()
    except (OSError, PermissionError):
        pass

    # Get binary version in an isolated directory.
    binary_version = ''
    version_exit_code = -1
    version_verified = False
    try:
        import tempfile as _tempfile
        with _tempfile.TemporaryDirectory() as _ver_cwd:
            ver_result = subprocess.run(
                [str(binary), '--version'],
                # The image manifest is built from ``snowpack --version
                # 2>&1``.  Capture one merged stream here as well; keeping
                # stdout and stderr separate and concatenating them later can
                # reorder multiline version output and falsely fail the
                # runtime attestation.
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=10,
                cwd=_ver_cwd,
            )
            version_exit_code = ver_result.returncode
            binary_version = ' '.join(ver_result.stdout.strip()[:200].split())
            version_verified = ver_result.returncode == 0 and bool(binary_version)
    except (subprocess.TimeoutExpired, OSError):
        version_exit_code = -1

    # C0.31: Cross-bind the independently probed binary to the runtime
    # toolchain manifest. A successful native run requires this verification.
    (
        toolchain_manifest_path,
        toolchain_manifest_sha256,
        toolchain_manifest,
        toolchain_manifest_verified,
    ) = _load_toolchain_manifest(
        binary,
        binary_sha256=binary_sha256,
        binary_version=binary_version,
    )
    if not toolchain_manifest_verified:
        # Keep the release fail-closed, but make a hosted mismatch diagnosable
        # without printing the runtime manifest or any credential-bearing
        # environment value into CI logs.
        expected_hash = (
            toolchain_manifest.get('binary_sha256', '')
            if isinstance(toolchain_manifest, dict) else ''
        )
        expected_version = (
            ' '.join(str(toolchain_manifest.get('binary_version', '')).split())
            if isinstance(toolchain_manifest, dict) else ''
        )
        print(
            'TOOLCHAIN_ATTESTATION_DIAGNOSTICS=' + json.dumps({
                'manifest_present': toolchain_manifest is not None,
                'manifest_path_present': bool(toolchain_manifest_path),
                'binary_path_name_match': bool(
                    isinstance(toolchain_manifest, dict)
                    and (
                        not toolchain_manifest.get('binary_path')
                        or Path(str(toolchain_manifest['binary_path'])).name == binary.name
                    )
                ),
                'binary_hash_present': bool(binary_sha256),
                'binary_hash_match': (
                    isinstance(expected_hash, str)
                    and expected_hash.lower() == binary_sha256.lower()
                ),
                'image_id_valid': is_real_image_id(
                    os.getenv('SNOWPACK_IMAGE_ID', '')
                ),
                'image_archive_sha256_valid': is_real_sha256(
                    os.getenv('SNOWPACK_IMAGE_ARCHIVE_SHA256', '')
                ),
                'version_exit_code': version_exit_code,
                'version_verified': version_verified,
                'observed_version_length': len(binary_version),
                'expected_version_length': len(expected_version),
                'version_match': expected_version == ' '.join(binary_version.split()),
                'expected_binary_hash_prefix': expected_hash[:12],
                'observed_binary_hash_prefix': binary_sha256[:12],
            }, sort_keys=True),
            file=sys.stderr,
        )

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=str(output_dir),
        )
        finished_at = datetime.now(timezone.utc).isoformat()
        stdout_sha256 = hashlib.sha256(result.stdout.encode()).hexdigest()
        stderr_sha256 = hashlib.sha256(result.stderr.encode()).hexdigest()

        # Persist the actual subprocess streams as a run artifact. The release
        # manifest can then hash and verify the log after bundle download.
        log_file = output_dir / f'{smet_path.stem}.log'
        if log_file.is_symlink():
            raise UnsafePathError(f'native execution log is symlinked: {log_file}')
        log_file.write_text(
            f'$ {command_str}\n[stdout]\n{result.stdout}\n[stderr]\n{result.stderr}\n',
            encoding='utf-8',
        )

        # Official SNOWPACK names profiles as <station>_<experiment>.pro.
        # Discover the one output in the controlled directory rather than
        # assuming the obsolete <station>.pro naming convention.
        pro_file = _discover_native_profile(output_dir, Path(smet_path).stem)
        success = (
            result.returncode == 0
            and version_verified
            and bool(binary_sha256)
            and toolchain_manifest_verified
            and pro_file is not None
        )

        return NativeExecutionEvidence(
            binary_path=str(binary),
            binary_sha256=binary_sha256,
            binary_version=binary_version,
            command=command_str,
            command_sha256=command_sha256,
            exit_code=result.returncode,
            started_at=started_at,
            finished_at=finished_at,
            toolchain_id=toolchain_id,
            run_id=run_id,
            stdout_sha256=stdout_sha256,
            stderr_sha256=stderr_sha256,
            version_exit_code=version_exit_code,
            version_verified=version_verified,
            toolchain_manifest_path=str(toolchain_manifest_path) if toolchain_manifest_path else '',
            toolchain_manifest_sha256=toolchain_manifest_sha256,
            toolchain_manifest=toolchain_manifest,
            toolchain_manifest_verified=toolchain_manifest_verified,
            image_id=str(toolchain_manifest.get('image_id', '')) if toolchain_manifest else '',
            image_archive_sha256=str(toolchain_manifest.get('image_archive_sha256', '')) if toolchain_manifest else '',
            image_repository_digest=str(toolchain_manifest.get('image_repository_digest', '')) if toolchain_manifest else '',
            image_identity_source=str(toolchain_manifest.get('image_identity_source', '')) if toolchain_manifest else '',
            pro_path=str(pro_file) if pro_file is not None else '',
            log_path=str(log_file),
            success=success,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        finished_at = datetime.now(timezone.utc).isoformat()
        return NativeExecutionEvidence(
            binary_path=str(binary),
            binary_sha256=binary_sha256,
            binary_version=binary_version,
            command=command_str,
            command_sha256=command_sha256,
            exit_code=-1,
            started_at=started_at,
            finished_at=finished_at,
            toolchain_id=toolchain_id,
            run_id=run_id,
            version_exit_code=version_exit_code,
            version_verified=version_verified,
            toolchain_manifest_path=str(toolchain_manifest_path) if toolchain_manifest_path else '',
            toolchain_manifest_sha256=toolchain_manifest_sha256,
            toolchain_manifest=toolchain_manifest,
            toolchain_manifest_verified=toolchain_manifest_verified,
            image_id=str(toolchain_manifest.get('image_id', '')) if toolchain_manifest else '',
            image_archive_sha256=str(toolchain_manifest.get('image_archive_sha256', '')) if toolchain_manifest else '',
            image_repository_digest=str(toolchain_manifest.get('image_repository_digest', '')) if toolchain_manifest else '',
            image_identity_source=str(toolchain_manifest.get('image_identity_source', '')) if toolchain_manifest else '',
            success=False,
        )


def _parse_native_pro_values(record: dict[str, str], code: str) -> list[float]:
    """Parse one coded SNOWPACK PRO record and enforce its declared count."""
    raw_line = record.get(code)
    if raw_line is None:
        raise ValueError(f'SNOWPACK .pro record is missing {code}')
    parts = raw_line.split(',')
    if len(parts) < 2:
        raise ValueError(f'SNOWPACK .pro record {code} has no declared count')
    try:
        declared_count = int(parts[1])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f'SNOWPACK .pro record {code} has an invalid declared count: {parts[1]!r}'
        ) from exc
    if declared_count < 0 or len(parts) - 2 != declared_count:
        raise ValueError(
            f'SNOWPACK .pro record {code} has {len(parts) - 2} values; '
            f'expected {declared_count}'
        )
    values: list[float] = []
    for raw_value in parts[2:]:
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f'SNOWPACK .pro record {code} contains a non-numeric value: {raw_value!r}'
            ) from exc
        if not math.isfinite(value):
            raise ValueError(f'SNOWPACK .pro record {code} contains a non-finite value')
        values.append(value)
    return values


def _parse_native_snowpack_pro(lines: list[str]) -> dict[str, Any]:
    """Parse SNOWPACK's coded ``0500`` profile records.

    SNOWPACK 3.7's legacy PRO format stores one profile as several coded
    records (0501, 0502, ...), rather than the whitespace-tabular format used
    by older test fixtures.  The summary fields below are explicit reductions
    of the last native profile; they are interpretation features, not
    independent avalanche validation.
    """
    in_data = False
    profiles: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in lines:
        stripped = line.strip()
        if stripped == '[DATA]':
            in_data = True
            continue
        if not in_data or not stripped or stripped.startswith('#'):
            continue
        if stripped.startswith('0500,'):
            if current is not None:
                profiles.append(current)
            current = {'0500': stripped}
            continue
        if current is None or not re.match(r'^\d{4},', stripped):
            continue
        code = stripped[:4]
        if code in current:
            raise ValueError(f'SNOWPACK .pro profile contains duplicate record {code}')
        current[code] = stripped
    if current is not None:
        profiles.append(current)
    if not profiles:
        raise ValueError('SNOWPACK .pro has no coded profile records')

    profile = profiles[-1]
    profile_date = profile['0500'].split(',', 1)[1].strip()
    positions = _parse_native_pro_values(profile, '0501')
    densities = _parse_native_pro_values(profile, '0502')
    temperatures_c = _parse_native_pro_values(profile, '0503')
    lwc_values = _parse_native_pro_values(profile, '0506')
    gradients = _parse_native_pro_values(profile, '0520')
    stability = _parse_native_pro_values(profile, '0530')
    grain_values = _parse_native_pro_values(profile, '0513')
    snow_shear = _parse_native_pro_values(profile, '0601') if '0601' in profile else None

    layer_count = len(positions)
    if layer_count == 0:
        raise ValueError('SNOWPACK .pro coded profile has no snow elements')
    for name, values in (
        ('density', densities),
        ('temperature', temperatures_c),
        ('liquid water content', lwc_values),
        ('temperature gradient', gradients),
    ):
        if len(values) != layer_count:
            raise ValueError(
                f'SNOWPACK .pro {name} record has {len(values)} values; '
                f'expected {layer_count}'
            )
    if len(grain_values) not in (layer_count, layer_count + 1):
        raise ValueError(
            f'SNOWPACK .pro grain record has {len(grain_values)} values; '
            f'expected {layer_count} or {layer_count + 1}'
        )
    if snow_shear is not None and len(snow_shear) != layer_count:
        raise ValueError(
            f'SNOWPACK .pro shear record has {len(snow_shear)} values; '
            f'expected {layer_count}'
        )
    if len(stability) != 8:
        raise ValueError(
            f'SNOWPACK .pro stability record has {len(stability)} values; expected 8'
        )

    grain_codes = [int(value) for value in grain_values[:layer_count]]
    if any(value < 0 or not float(value).is_integer() for value in grain_values):
        raise ValueError('SNOWPACK .pro grain type codes must be non-negative integers')
    snow_height_m = max(abs(value) for value in positions) / 100.0
    weakest_idx = int(np.argmin(densities))
    weak_layer_density = densities[weakest_idx]
    if snow_shear is not None:
        weak_layer_shear = max(0.0, snow_shear[weakest_idx])
        shear_source = 'native_0601'
    else:
        weak_layer_shear = max(0.1, 0.001 * weak_layer_density ** 1.5)
        shear_source = 'density_proxy_from_native_0502'
    weak_layer_depth = max(
        0.0,
        snow_height_m - abs(positions[weakest_idx]) / 100.0,
    )
    stability_candidates = (stability[3], stability[5], stability[7])
    if not all(math.isfinite(value) for value in stability_candidates):
        raise ValueError('SNOWPACK .pro stability indices are non-finite')
    stability_index = float(np.clip(min(stability_candidates), 0.0, 5.0))
    layers: list[dict[str, Any]] = []
    window_start = max(0, layer_count - 20)
    for index in range(window_start, layer_count):
        layer = {
            'height_m': round(abs(positions[index]) / 100.0, 4),
            'density_kgm3': densities[index],
            'temperature_c': temperatures_c[index],
            'grain_type_code': grain_codes[index],
            'liquid_water_content_pct': lwc_values[index],
            'temperature_gradient_k_per_m': gradients[index],
        }
        if snow_shear is not None:
            layer['shear_strength_kpa'] = snow_shear[index]
        layers.append(layer)

    return {
        'weak_layer_depth_m': round(weak_layer_depth, 3),
        'weak_layer_grain_type': _snowpack_f1f2f3_to_str(grain_codes[weakest_idx]),
        'weak_layer_grain_type_code': grain_codes[weakest_idx],
        'weak_layer_shear_strength_kpa': round(weak_layer_shear, 2),
        'weak_layer_shear_source': shear_source,
        'snowpack_stability_index': round(stability_index, 3),
        'stability_index_source': 'native_0530_minimum_of_Sdef_Sn38_Sk38',
        'temperature_gradient_per_m': round(float(np.mean(np.abs(gradients))), 4),
        'liquid_water_content_pct': round(float(np.mean(lwc_values)), 2),
        'layer_count': layer_count,
        'snow_height_m': round(snow_height_m, 3),
        'bulk_density_kgm3': round(float(np.mean(densities)), 1),
        'profile_date': profile_date,
        'native_format': 'pro_0500_records',
        'method': 'snowpack_native',
        'layers': layers,
    }


def _snowpack_f1f2f3_to_str(code: int) -> str:
    """Render a native Swiss F1F2F3 grain code without losing its meaning."""
    if code == 772:
        return 'melt_freeze_crust'
    if code <= 0:
        return 'unknown'
    digits = f'{code:03d}'
    primary = int(digits[0])
    names = {
        1: 'precipitation_particles',
        2: 'decomposing_fragmented_particles',
        3: 'rounded_grains',
        4: 'faceted_crystals',
        5: 'depth_hoar',
        6: 'surface_hoar',
        7: 'melt_forms',
        8: 'ice_formations',
        9: 'faceted_rounded_particles',
    }
    return names.get(primary, f'native_f1f2f3_{code}')


def parse_snowpack_pro(pro_path: Path) -> dict[str, Any]:
    """Parse a strict, headered SNOWPACK ``.pro`` profile.

    Required columns are validated before any scientific value is derived.
    Missing headers, malformed rows, missing numeric values, and unsupported
    column layouts fail closed instead of receiving plausible defaults.
    """
    if not pro_path.exists() or pro_path.is_symlink() or not pro_path.is_file():
        raise FileNotFoundError(f'SNOWPACK profile is not a regular file: {pro_path}')

    content = pro_path.read_text(encoding='utf-8')
    if not content.strip():
        raise ValueError('SNOWPACK .pro file is empty')
    lines = content.splitlines()

    if any(
        line.strip().startswith('0500,') and line.strip() != '0500,Date'
        for line in lines
    ):
        return _parse_native_snowpack_pro(lines)

    header_line = next(
        (line for line in lines if line.lstrip().startswith('#') and 'Date' in line),
        None,
    )
    if header_line is None:
        raise ValueError('SNOWPACK .pro file has no supported Date header')
    header_index = lines.index(header_line)
    columns = header_line.lstrip('#').strip().split()
    if len(columns) != len(set(columns)):
        raise ValueError('SNOWPACK .pro header contains duplicate columns')

    aliases = {
        'date': ('Date', 'date'),
        'snow_height': ('HS', 'hs'),
        'density': ('rho', 'RHO', 'density'),
        'temperature': ('T', 'temp', 'temperature'),
        'grain_type': ('grain_type', 'grain', 'graintype'),
        'lwc': ('LWC', 'lwc'),
    }
    col_idx = {column: index for index, column in enumerate(columns)}

    def _column_index(name: str) -> int:
        for alias in aliases[name]:
            if alias in col_idx:
                return col_idx[alias]
        raise ValueError(
            f'SNOWPACK .pro missing required {name} column; '
            f'available={columns}'
        )

    required_names = ('date', 'snow_height', 'density', 'temperature', 'grain_type')
    required_indices = {name: _column_index(name) for name in required_names}
    data_rows: list[list[str]] = []
    for line_number, line in enumerate(lines[header_index + 1:], start=header_index + 2):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        parts = line.split()
        if len(parts) != len(columns):
            raise ValueError(
                f'SNOWPACK .pro row {line_number} has {len(parts)} values; '
                f'expected {len(columns)}'
            )
        data_rows.append(parts)
    if not data_rows:
        raise ValueError('No data rows in SNOWPACK .pro file')

    def _required_float(row: list[str], name: str) -> float:
        raw = row[required_indices[name]]
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f'SNOWPACK .pro column {name} is not numeric: {raw!r}'
            ) from exc
        if not math.isfinite(value):
            raise ValueError(f'SNOWPACK .pro column {name} is non-finite')
        return value

    snow_height_m = _required_float(data_rows[-1], 'snow_height')
    layers: list[dict[str, Any]] = []
    densities: list[float] = []
    temps: list[float] = []
    for row in data_rows[-20:]:
        rho = _required_float(row, 'density')
        temp = _required_float(row, 'temperature')
        grain_value = _required_float(row, 'grain_type')
        if not grain_value.is_integer():
            raise ValueError(f'SNOWPACK .pro grain_type must be an integer: {grain_value}')
        densities.append(rho)
        temps.append(temp - 273.15)
        layers.append({
            'density_kgm3': rho,
            'temperature_c': temp - 273.15,
            'grain_type_code': int(grain_value),
        })

    bulk_density = float(np.mean(densities))
    temp_gradient = 0.0
    if len(temps) > 1 and snow_height_m > 0.01:
        temp_gradient = abs(temps[0] - temps[-1]) / max(0.01, snow_height_m)

    weakest_idx = int(np.argmin(densities))
    weak_layer_density = densities[weakest_idx]
    weak_layer_shear = max(0.1, 0.001 * weak_layer_density ** 1.5)
    weak_layer_depth = snow_height_m * (weakest_idx + 1) / len(densities)
    grain_code = int(_required_float(data_rows[-1], 'grain_type'))
    grain_type = _swiss_grain_code_to_str(grain_code)
    overburden_kpa = (bulk_density * 9.81 * snow_height_m) / 1000.0
    stability_index = (
        5.0
        if overburden_kpa < 0.01
        else float(np.clip(weak_layer_shear / overburden_kpa, 0.0, 5.0))
    )

    lwc = 0.0
    if 'LWC' in col_idx:
        lwc = _required_float(data_rows[-1], 'lwc')

    return {
        'weak_layer_depth_m': round(weak_layer_depth, 3),
        'weak_layer_grain_type': grain_type,
        'weak_layer_shear_strength_kpa': round(weak_layer_shear, 2),
        'snowpack_stability_index': round(stability_index, 3),
        'temperature_gradient_per_m': round(temp_gradient, 4),
        'liquid_water_content_pct': round(max(0.0, lwc * 100.0), 2),
        'layer_count': len(densities),
        'snow_height_m': round(snow_height_m, 3),
        'bulk_density_kgm3': round(bulk_density, 1),
        'method': 'snowpack_native',
        'layers': layers,
    }


def _swiss_grain_code_to_str(code: int) -> str:
    """Convert Swiss snow grain type code to string name.

    FICAM codes (Swiss classification):
    1-3: Precipitation particles (new snow)
    4-5: Decomposed/fragmented particles
    6-7: Rounded grains
    8-9: Faceted crystals
    10-11: Depth hoar
    12: Surface hoar
    13-14: Melt forms
    15: Ice layer
    """
    if code in (10, 11):
        return 'depth_hoar'
    if code in (8, 9):
        return 'faceted'
    if code == 12:
        return 'surface_hoar'
    if code in (13, 14):
        return 'melt_form'
    return 'rounded'


def generate_snowpack_config(
    *,
    output_path: Path,
    season_start_date: str,
    end_date: str,
    output_interval: int = 24,
    initial_state_path: Path | None = None,
    station_id: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    meteo_path: Path | None = None,
    output_dir: Path | None = None,
    experiment: str = 'snowpack',
) -> Path:
    """Generate a SNOWPACK .ini configuration file.

    Args:
        output_path: Path to write the config file
        season_start_date: Simulation start date (YYYY-MM-DD)
        end_date: Simulation end date (YYYY-MM-DD)
        output_interval: Output profile interval in hours
        station_id: SMET station identifier; defaults to the config stem
        latitude: WGS84 latitude used to derive the UTM zone
        longitude: WGS84 longitude used to derive the UTM zone
        meteo_path: Directory containing the input SMET file
        output_dir: Directory receiving native SNOWPACK outputs
        experiment: Safe SNOWPACK experiment suffix used in output names

    Returns:
        Path to the written config file

    ``season_start_date`` and ``end_date`` are retained for caller
    compatibility; the official SNOWPACK CLI controls the end date with
    ``-e``. The output keys follow the documented SNOWPACK 3.7 names.
    ``initial_state_path`` is optional for legacy callers; when supplied, its
    suffix selects the documented SNOW/CAAML/SNOOLD input plugin.
    """
    if output_interval <= 0:
        raise ValueError('output_interval must be positive')
    station_id = station_id or Path(output_path).stem
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', station_id):
        raise ValueError(f'Invalid SNOWPACK station_id: {station_id!r}')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', experiment):
        raise ValueError(f'Invalid SNOWPACK experiment: {experiment!r}')
    if (latitude is None) != (longitude is None):
        raise ValueError('latitude and longitude must be supplied together')
    if latitude is None or longitude is None:
        raise ValueError(
            'latitude and longitude are required to derive the SNOWPACK UTM zone'
        )
    coord_param = _utm_zone_parameter(float(latitude), float(longitude))
    input_dir = Path(meteo_path or Path(output_path).parent).resolve()
    native_output_dir = Path(output_dir or Path(output_path).parent).resolve()
    input_lines = [
        'COORDSYS = UTM',
        f'COORDPARAM = {coord_param}',
        'TIME_ZONE = 0',
        'METEO = SMET',
        f'METEOPATH = {input_dir}',
        f'STATION1 = {station_id}',
    ]
    if initial_state_path is not None:
        initial_state_path = Path(initial_state_path)
        state_format = {
            '.caaml': 'CAAML',
            '.smet': 'SMET',
            '.sno': 'SMET',
            '.snoold': 'SNOOLD',
        }.get(initial_state_path.suffix.lower())
        if state_format is None:
            raise ValueError(
                f'Unsupported SNOWPACK initial-state suffix: {initial_state_path.suffix!r}; '
                'expected .caaml, .smet, .sno, or .snoold'
            )
        input_lines.extend([
            f'SNOW = {state_format}',
            f'SNOWPATH = {initial_state_path.parent.resolve()}',
            f'SNOWFILE1 = {initial_state_path.name}',
        ])

    output_interval_days = output_interval / 24.0
    config_content = f"""[Input]
{chr(10).join(input_lines)}

[Output]
COORDSYS = UTM
COORDPARAM = {coord_param}
TIME_ZONE = 0
METEO = SMET
METEOPATH = {native_output_dir}
SNOWPATH = {native_output_dir}
EXPERIMENT = {experiment}
SNOW = SMET
SNOW_WRITE = TRUE
HAZ_WRITE = TRUE
PROF_WRITE = TRUE
PROF_FORMAT = PRO
PROF_START = 0.0
PROF_DAYS_BETWEEN = {output_interval_days:g}
TS_WRITE = TRUE
TS_FORMAT = SMET
TS_START = 0.0
TS_DAYS_BETWEEN = {output_interval_days:g}
OUT_HAZ = TRUE
OUT_METEO = TRUE
WRITE_PROCESSED_METEO = TRUE
OUT_MASS = TRUE
OUT_T = TRUE
OUT_LW = TRUE
OUT_SW = TRUE

[Snowpack]
# The source forcing is hourly. Keep the native integration step aligned with
# that cadence and explicitly re-accumulate PSUM over the same period.
CALCULATION_STEP_LENGTH = 60.0
ROUGHNESS_LENGTH = 0.002
HEIGHT_OF_METEO_VALUES = 4.5
HEIGHT_OF_WIND_VALUE = 4.5
# TSS is an explicitly derived bridge value (air-temperature/snow-state
# proxy), not an observed surface-temperature measurement.  SNOWPACK must use
# ILWR for the boundary calculation and retain this field for diagnostics.
MEAS_TSS = FALSE
SW_MODE = INCOMING
ATMOSPHERIC_STABILITY = MO_HOLTSLAG
CANOPY = FALSE
ENFORCE_MEASURED_SNOW_HEIGHTS = FALSE
CHANGE_BC = TRUE
THRESH_CHANGE_BC = -1.0
SNP_SOIL = FALSE
SOIL_FLUX = FALSE
GEO_HEAT = 0.06

[Interpolations1D]
PSUM::resample = accumulate
PSUM::accumulate::period = 3600

[SnowpackAdvanced]
NUMBER_SLOPES = 1
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(config_content, encoding='utf-8')
    return output_path
