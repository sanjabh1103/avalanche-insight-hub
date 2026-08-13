"""SMP profile preservation module (Phase 7-prep).

Preserves the vertical profile structure from SnowMicroPen (SMP) measurements
rather than reducing it to scalar proxies.

Per Imp_plan.md Phase 7:
  - Preserve the vertical profile rather than reducing it to scalar proxies.
  - Derive density, SSA, layer boundaries and grain estimates with uncertainty.
  - Use snowdragon only as a research derivative until local calibration is proven.
  - Align SMP/pit layers with SNOWPACK depth references.
  - Treat SMP as targeted validation, not dense regional ground truth.

Per Imp_plan.md cross-cutting rules:
  - Never present synthetic or heuristic data as field validation.
  - SMP-derived quantities become less certain as processing moves from raw
    force to density, SSA, grain type and stability.

This module is additive and does not modify any denylisted file.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


class SMPInputUnavailable(RuntimeError):
    """Raised when raw SMP files cannot be safely processed."""


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


@dataclass(frozen=True)
class SMPRawLineage:
    """Immutable identity for the raw PNT/INI pair and processor revision."""

    pnt_filename: str
    pnt_sha256: str
    ini_filename: str
    ini_sha256: str
    processor_name: str
    processor_version: str
    processor_git_hash: str

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.pnt_filename.lower().endswith('.pnt'):
            errors.append('SMPRawLineage: pnt_filename must end with .pnt')
        if not self.ini_filename.lower().endswith('.ini'):
            errors.append('SMPRawLineage: ini_filename must end with .ini')
        for field_name, value in (
            ('pnt_sha256', self.pnt_sha256),
            ('ini_sha256', self.ini_sha256),
        ):
            if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', value):
                errors.append(f'SMPRawLineage: {field_name} must be a SHA-256 digest')
        for field_name, value in (
            ('processor_name', self.processor_name),
            ('processor_version', self.processor_version),
            ('processor_git_hash', self.processor_git_hash),
        ):
            if not isinstance(value, str) or not value.strip():
                errors.append(f'SMPRawLineage: {field_name} is required')
        return errors


@dataclass(frozen=True)
class SMPSample:
    """A single raw SMP force measurement at a depth."""
    depth_mm: float
    force_n: float
    timestamp: str = ''


@dataclass(frozen=True)
class SMPDerivedLayer:
    """A derived layer from SMP processing (with uncertainty)."""
    depth_mm: float
    thickness_mm: float
    density_kgm3: float
    density_uncertainty: float       # 1-sigma uncertainty
    ssa_m2_kg: float
    ssa_uncertainty: float
    grain_type_estimate: str         # Estimated, not certain
    grain_type_confidence: float     # 0-1
    rupture_force_n: float | None = None
    structural_element_length_mm: float | None = None


@dataclass(frozen=True)
class SMPProfile:
    """Complete SMP profile preserving vertical structure.

    This is the key data structure: instead of reducing to scalar proxies
    (shear strength, settlement index), the full vertical profile is preserved.
    """
    profile_id: str
    station_id: str
    latitude: float
    longitude: float
    elevation_m: float
    timestamp: str                   # ISO 8601
    snow_depth_mm: float
    device_serial: str
    operator: str
    processing_version: str
    raw_samples: tuple[SMPSample, ...] = ()
    derived_layers: tuple[SMPDerivedLayer, ...] = ()
    depth_reference: str = 'ground'  # 'ground' or 'surface'
    quality_flags: tuple[str, ...] = ()
    is_calibrated: bool = False       # Must be False until local calibration is proven
    raw_lineage: SMPRawLineage | None = None

    @property
    def has_raw_data(self) -> bool:
        return len(self.raw_samples) > 0

    @property
    def has_derived_layers(self) -> bool:
        return len(self.derived_layers) > 0

    @property
    def n_samples(self) -> int:
        return len(self.raw_samples)

    @property
    def n_layers(self) -> int:
        return len(self.derived_layers)

    def validate(self) -> list[str]:
        """Validate the SMP profile. Returns list of errors (empty = valid)."""
        errors: list[str] = []

        if not self.profile_id:
            errors.append('SMPProfile: profile_id is required')
        if not self.station_id:
            errors.append('SMPProfile: station_id is required')
        if not isinstance(self.timestamp, str) or not self.timestamp:
            errors.append('SMPProfile: timestamp is required')
        snow_depth_valid = _finite_number(self.snow_depth_mm) and self.snow_depth_mm > 0
        if not snow_depth_valid:
            errors.append(
                f'SMPProfile: snow_depth_mm must be > 0, got {self.snow_depth_mm}'
            )
        if not self.device_serial:
            errors.append('SMPProfile: device_serial is required')
        if not self.processing_version:
            errors.append('SMPProfile: processing_version is required')
        if self.raw_lineage is not None:
            errors.extend(self.raw_lineage.validate())

        # Validate timestamp format and require an unambiguous UTC instant.
        if isinstance(self.timestamp, str):
            try:
                parsed_timestamp = datetime.fromisoformat(self.timestamp.replace('Z', '+00:00'))
            except ValueError:
                errors.append(f'SMPProfile: timestamp "{self.timestamp}" is not valid ISO 8601')
            else:
                if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() is None:
                    errors.append('SMPProfile: timestamp must be timezone-aware UTC')
                elif parsed_timestamp.utcoffset() != timezone.utc.utcoffset(parsed_timestamp):
                    errors.append('SMPProfile: timestamp must use UTC offset +00:00')

        for field_name, value, lower, upper in (
            ('latitude', self.latitude, -90.0, 90.0),
            ('longitude', self.longitude, -180.0, 180.0),
            ('elevation_m', self.elevation_m, -500.0, 10000.0),
        ):
            if not _finite_number(value):
                errors.append(f'SMPProfile: {field_name} must be finite')
            elif not lower <= float(value) <= upper:
                errors.append(f'SMPProfile: {field_name} is outside supported range')

        previous_depth = -math.inf
        for index, sample in enumerate(self.raw_samples):
            if not _finite_number(sample.depth_mm) or not _finite_number(sample.force_n):
                errors.append(f'SMPProfile: raw sample {index} must contain finite values')
                continue
            if snow_depth_valid and not 0.0 <= sample.depth_mm <= self.snow_depth_mm:
                errors.append(
                    f'SMPProfile: raw sample {index} depth must be within 0..snow_depth_mm'
                )
            if sample.depth_mm < previous_depth:
                errors.append('SMPProfile: raw sample depths must be non-decreasing')
            previous_depth = sample.depth_mm

        # Check derived layers have uncertainty
        for layer in self.derived_layers:
            if not all(_finite_number(value) for value in (
                layer.depth_mm, layer.thickness_mm, layer.density_kgm3,
                layer.ssa_m2_kg, layer.density_uncertainty, layer.ssa_uncertainty,
            )):
                errors.append(f'SMPProfile: derived layer at {layer.depth_mm}mm has non-finite values')
            if snow_depth_valid and _finite_number(layer.depth_mm) and not 0.0 <= layer.depth_mm <= self.snow_depth_mm:
                errors.append(f'SMPProfile: derived layer at {layer.depth_mm}mm is outside snow depth')
            if (
                not _finite_number(layer.thickness_mm)
                or not _finite_number(layer.density_kgm3)
                or not _finite_number(layer.ssa_m2_kg)
                or layer.thickness_mm <= 0
                or layer.density_kgm3 <= 0
                or layer.ssa_m2_kg <= 0
            ):
                errors.append(f'SMPProfile: derived layer at {layer.depth_mm}mm has invalid physical values')
            if not _finite_number(layer.density_uncertainty) or layer.density_uncertainty <= 0:
                errors.append(
                    f'SMPProfile: derived layer at {layer.depth_mm}mm has '
                    f'no density uncertainty. Uncertainty is required.'
                )
            if (
                not _finite_number(layer.grain_type_confidence)
                or not 0.0 <= layer.grain_type_confidence <= 1.0
            ):
                errors.append(
                    f'SMPProfile: grain_type_confidence must be 0-1, '
                    f'got {layer.grain_type_confidence}'
                )

        return errors

    def to_scalar_proxy(self) -> dict[str, float | None]:
        """Derive backward-compatible scalar proxies from the full profile.

        This preserves backward compatibility with existing consumers that
        expect scalar values, while the full profile structure is retained.
        """
        if not self.derived_layers:
            return {
                'estimated_shear_strength_kpa': None,
                'snow_settlement_index': None,
            }

        # Derive scalar proxies from layers (with explicit uncertainty)
        densities = [l.density_kgm3 for l in self.derived_layers]
        avg_density = sum(densities) / len(densities)

        # Settlement index: higher density = more consolidated
        settlement_index = min(1.0, avg_density / 800.0)

        # Shear strength: rough estimate from density (very uncertain)
        # This is a proxy — the full profile should be used for real analysis
        estimated_shear = avg_density / 100.0  # Very rough proxy

        return {
            'estimated_shear_strength_kpa': estimated_shear,
            'snow_settlement_index': settlement_index,
        }


def ingest_smp_profile_files(
    pnt_path: Path,
    ini_path: Path,
    *,
    processor_name: str,
    processor_version: str,
    processor_git_hash: str,
    profile_loader: Callable[[Path, Path], SMPProfile],
) -> SMPProfile:
    """Load raw PNT/INI data through an approved processor with full lineage.

    ``profile_loader`` is deliberately injected. The repository does not guess
    the binary PNT format or install ``snowmicropyn`` implicitly. An approved
    integration can provide a loader backed by ``snowmicropyn.Profile.load``.
    This function never writes either input file.
    """

    pnt_path = Path(pnt_path)
    ini_path = Path(ini_path)
    if pnt_path.suffix.lower() != '.pnt' or ini_path.suffix.lower() != '.ini':
        raise SMPInputUnavailable('SMP input pair must be .pnt and .ini files')
    if pnt_path.stem != ini_path.stem:
        raise SMPInputUnavailable('PNT and INI files must share the same profile stem')
    for path in (pnt_path, ini_path):
        if path.is_symlink() or not path.is_file():
            raise SMPInputUnavailable(f'SMP input is missing or symlinked: {path.name}')
    try:
        pnt_bytes = pnt_path.read_bytes()
        ini_bytes = ini_path.read_bytes()
    except OSError as exc:
        raise SMPInputUnavailable(f'cannot read SMP input pair: {exc}') from exc
    if not pnt_bytes or not ini_bytes:
        raise SMPInputUnavailable('SMP PNT and INI inputs must be non-empty')
    lineage = SMPRawLineage(
        pnt_filename=pnt_path.name,
        pnt_sha256=hashlib.sha256(pnt_bytes).hexdigest(),
        ini_filename=ini_path.name,
        ini_sha256=hashlib.sha256(ini_bytes).hexdigest(),
        processor_name=processor_name,
        processor_version=processor_version,
        processor_git_hash=processor_git_hash,
    )
    lineage_errors = lineage.validate()
    if lineage_errors:
        raise SMPInputUnavailable('; '.join(lineage_errors))
    try:
        profile = profile_loader(pnt_path, ini_path)
    except Exception as exc:
        raise SMPInputUnavailable(f'approved SMP processor failed: {exc}') from exc
    try:
        current_pnt_hash = hashlib.sha256(pnt_path.read_bytes()).hexdigest()
        current_ini_hash = hashlib.sha256(ini_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise SMPInputUnavailable(f'cannot re-read SMP inputs after processing: {exc}') from exc
    if current_pnt_hash != lineage.pnt_sha256 or current_ini_hash != lineage.ini_sha256:
        raise SMPInputUnavailable('SMP input changed during processing; raw lineage is invalid')
    if not isinstance(profile, SMPProfile):
        raise SMPInputUnavailable('approved SMP processor must return SMPProfile')
    profile_errors = profile.validate()
    if profile_errors:
        raise SMPInputUnavailable('; '.join(profile_errors))
    return SMPProfile(
        profile_id=profile.profile_id,
        station_id=profile.station_id,
        latitude=profile.latitude,
        longitude=profile.longitude,
        elevation_m=profile.elevation_m,
        timestamp=profile.timestamp,
        snow_depth_mm=profile.snow_depth_mm,
        device_serial=profile.device_serial,
        operator=profile.operator,
        processing_version=profile.processing_version,
        raw_samples=profile.raw_samples,
        derived_layers=profile.derived_layers,
        depth_reference=profile.depth_reference,
        quality_flags=profile.quality_flags,
        is_calibrated=profile.is_calibrated,
        raw_lineage=lineage,
    )


def align_smp_to_snowpack_depth(
    smp_profile: SMPProfile,
    snowpack_depth_reference: str = 'ground',
) -> SMPProfile:
    """Align SMP profile depth reference with SNOWPACK depth reference.

    SNOWPACK uses 'ground' reference (0 = ground, increasing upward).
    SMP typically uses 'surface' reference (0 = surface, increasing downward).

    This function converts between the two reference systems.

    Args:
        smp_profile: The SMP profile to align.
        snowpack_depth_reference: Target depth reference ('ground' or 'surface').

    Returns:
        New SMPProfile with aligned depth reference.
    """
    if smp_profile.depth_reference == snowpack_depth_reference:
        return smp_profile  # Already aligned

    snow_depth = smp_profile.snow_depth_mm

    if snowpack_depth_reference == 'ground' and smp_profile.depth_reference == 'surface':
        # Convert surface-referenced to ground-referenced
        new_samples = tuple(
            SMPSample(
                depth_mm=snow_depth - s.depth_mm,
                force_n=s.force_n,
                timestamp=s.timestamp,
            )
            for s in smp_profile.raw_samples
        )
        new_layers = tuple(
            SMPDerivedLayer(
                depth_mm=snow_depth - l.depth_mm,
                thickness_mm=l.thickness_mm,
                density_kgm3=l.density_kgm3,
                density_uncertainty=l.density_uncertainty,
                ssa_m2_kg=l.ssa_m2_kg,
                ssa_uncertainty=l.ssa_uncertainty,
                grain_type_estimate=l.grain_type_estimate,
                grain_type_confidence=l.grain_type_confidence,
                rupture_force_n=l.rupture_force_n,
                structural_element_length_mm=l.structural_element_length_mm,
            )
            for l in smp_profile.derived_layers
        )
    elif snowpack_depth_reference == 'surface' and smp_profile.depth_reference == 'ground':
        # Convert ground-referenced to surface-referenced
        new_samples = tuple(
            SMPSample(
                depth_mm=snow_depth - s.depth_mm,
                force_n=s.force_n,
                timestamp=s.timestamp,
            )
            for s in smp_profile.raw_samples
        )
        new_layers = tuple(
            SMPDerivedLayer(
                depth_mm=snow_depth - l.depth_mm,
                thickness_mm=l.thickness_mm,
                density_kgm3=l.density_kgm3,
                density_uncertainty=l.density_uncertainty,
                ssa_m2_kg=l.ssa_m2_kg,
                ssa_uncertainty=l.ssa_uncertainty,
                grain_type_estimate=l.grain_type_estimate,
                grain_type_confidence=l.grain_type_confidence,
                rupture_force_n=l.rupture_force_n,
                structural_element_length_mm=l.structural_element_length_mm,
            )
            for l in smp_profile.derived_layers
        )
    else:
        return smp_profile

    return SMPProfile(
        profile_id=smp_profile.profile_id,
        station_id=smp_profile.station_id,
        latitude=smp_profile.latitude,
        longitude=smp_profile.longitude,
        elevation_m=smp_profile.elevation_m,
        timestamp=smp_profile.timestamp,
        snow_depth_mm=smp_profile.snow_depth_mm,
        device_serial=smp_profile.device_serial,
        operator=smp_profile.operator,
        processing_version=smp_profile.processing_version,
        raw_samples=new_samples,
        derived_layers=new_layers,
        depth_reference=snowpack_depth_reference,
        quality_flags=smp_profile.quality_flags,
        is_calibrated=smp_profile.is_calibrated,
    )
