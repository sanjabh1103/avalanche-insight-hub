"""WeatherNext source adapter skeleton (Phase 3-prep + Phase 0.5 hardening).

Provides a skeleton interface for WeatherNext as a candidate atmospheric
ensemble source. This module is DISABLED by default and must not be
enabled in production without Partner source approval.

Per Imp_plan.md Phase 3:
  - Pin exact repository release/checkpoint and model SHA.
  - Verify fields, resolution, update frequency, ensemble size, forecast
    horizon and licence.
  - Check whether all SNOWPACK forcing variables exist.
  - Use the Mini model only for interface and compute smoke tests.
  - WeatherNext must be explicitly classified as promoted, shadow-only or
    rejected after source qualification.

Per Imp_plan.md cross-cutting rules:
  - Never promote an unapproved source or label.
  - WeatherNext demonstrates probabilistic atmospheric forecasting, not
    avalanche forecasting.

Per deep-research-codex-sol.md reconciliation (Phase 0.5):
  - WeatherNext 2 is 64-member, 0.25°, 6-hourly, 15-day (360h).
  - WN2 does NOT expose complete SNOWPACK forcing (no surface radiation,
    no 2m relative humidity, no precipitation phase, no snow height/SWE).
  - Direct WN→SMET is unsafe; must use terrain correction → reconstruction.
  - WN-C is a research pattern only, not an avalanche predictor.
  - UNPINNED identities must be rejected when classification is shadow_only
    or promoted — no floating heads in qualified sources.
  - Invalid hashes (non-SHA-256 format) must be rejected when qualified.

This module is additive and does not modify any denylisted file.
"""
from __future__ import annotations

import os
import re
import math
from dataclasses import dataclass, field
from typing import Any


# Environment flag — must be explicitly set to enable even skeleton mode
WEATHERNEXT_ENABLED = os.getenv('WEATHERNEXT_ENABLED', 'false').lower() in ('1', 'true', 'yes')

# WeatherNext source classification states
SOURCE_CLASSIFICATION_STATES = frozenset({
    'unqualified',     # Default: not yet evaluated
    'candidate',       # Identified but not yet qualified
    'shadow_only',     # Qualified for shadow/research use only
    'promoted',        # Qualified and approved for operational use
    'rejected',        # Evaluated and rejected
})

# Phase 0.5 P1.3: WN2 official specification per Google documentation.
# Source: https://developers.google.com/weathernext/guides/model-specs-vmg
WN2_DEFAULT_ENSEMBLE_SIZE = 64
WN2_DEFAULT_FORECAST_HORIZON_H = 360  # 15 days
WN2_DEFAULT_RESOLUTION_DEG = 0.25
WN2_DEFAULT_UPDATE_FREQUENCY_H = 6

# Phase 0.5 P1.3: WN2 official surface field names (exact schema names).
# These are the EXACT field names from the Google WeatherNext 2 model
# specification, NOT aliases. Wind is provided as U/V components, not speed.
# Precipitation is 6-hour accumulation, not instantaneous.
WN2_OFFICIAL_SURFACE_FIELDS = (
    '2m_temperature',                          # K — 2 meter temperature
    '10m_u_component_of_wind',                 # m/s — 10 meter U wind component
    '10m_v_component_of_wind',                 # m/s — 10 meter V wind component
    '100m_u_component_of_wind',                # m/s — 100 meter U wind component
    '100m_v_component_of_wind',                # m/s — 100 meter V wind component
    'mean_sea_level_pressure',                 # Pa — Mean sea level pressure
    'total_precipitation_6hr',                 # m — 6-hour accumulated precipitation
    'sea_surface_temperature',                 # K — Sea surface temperature
)

# Phase 0.5 P1.3: WN2 pressure-level fields (at 50,100,150,200,250,300,400,
# 500,600,700,850,925,1000 hPa).
WN2_OFFICIAL_PRESSURE_LEVEL_VARIABLES = (
    'geopotential',
    'specific_humidity',
    'temperature',
    'u_component_of_wind',
    'v_component_of_wind',
    'vertical_velocity',
)
WN2_PRESSURE_LEVELS_HPA = (50, 100, 150, 200, 250, 300, 400, 500, 600, 700, 850, 925, 1000)

# Backward-compatible alias (deprecated — use WN2_OFFICIAL_SURFACE_FIELDS)
WN2_DOCUMENTED_FIELDS = WN2_OFFICIAL_SURFACE_FIELDS

# Phase 0.5 P1.3: WN2 fields MISSING for SNOWPACK forcing.
# WN2 does NOT provide: surface radiation, 2m relative humidity,
# precipitation phase, snow height, or SWE. These must be reconstructed
# or supplied by another source before SNOWPACK can consume the forcing.
WN2_MISSING_FOR_SNOWPACK = (
    'surface_shortwave_radiation',       # ISWR — must be reconstructed
    'surface_longwave_radiation',        # ILWR — must be reconstructed
    'relative_humidity_2m',              # RH — must be derived from specific humidity
    'precipitation_phase',               # Must be derived from temperature
    'snow_height',                       # Must be supplied by another source
    'snow_water_equivalent',             # Must be supplied by another source
)

# SHA-256 format regex
_SHA256_RE = re.compile(r'^[0-9a-f]{64}$')

# UNPINNED sentinel — must be rejected when source is qualified
_UNPINNED = 'UNPINNED'


@dataclass(frozen=True)
class WeatherNextSourceManifest:
    """Manifest describing a WeatherNext source checkpoint.

    Per Imp_plan.md Phase 3: pin exact repository release/checkpoint and
    model SHA, verify fields/resolution/frequency/ensemble size/horizon/licence.

    Phase 0.5: UNPINNED identities and invalid hashes are rejected when
    classification is shadow_only or promoted. A qualified source must
    have pinned, hash-verified provenance.
    """
    repo_url: str                    # e.g., "https://github.com/google-deepmind/weathernext"
    release_tag: str                 # Git tag or commit SHA
    model_checkpoint: str            # Model checkpoint identifier
    model_sha256: str                # SHA-256 of model weights
    licence: str                     # Licence identifier
    fields: tuple[str, ...]          # Available atmospheric fields
    resolution_deg: float            # Spatial resolution in degrees
    update_frequency_h: int          # Update frequency in hours
    ensemble_size: int               # Number of ensemble members
    forecast_horizon_h: int          # Maximum forecast horizon in hours
    classification: str = 'unqualified'
    is_mini: bool = False            # True for Mini model (smoke tests only)
    notes: str = ''

    def validate(self) -> list[str]:
        """Validate the manifest. Returns list of errors (empty = valid)."""
        errors: list[str] = []
        for field_name, value in (
            ('repo_url', self.repo_url),
            ('release_tag', self.release_tag),
            ('model_checkpoint', self.model_checkpoint),
            ('model_sha256', self.model_sha256),
            ('licence', self.licence),
        ):
            if not isinstance(value, str) or not value.strip():
                errors.append(f'WeatherNextSourceManifest: {field_name} is required')
        if not isinstance(self.fields, (tuple, list)) or any(
            not isinstance(field_name, str) or not field_name.strip()
            for field_name in self.fields
        ):
            errors.append('WeatherNextSourceManifest: fields must contain non-empty strings')
        if self.classification not in SOURCE_CLASSIFICATION_STATES:
            errors.append(
                f'WeatherNextSourceManifest: invalid classification "{self.classification}". '
                f'Valid: {sorted(SOURCE_CLASSIFICATION_STATES)}'
            )
        if type(self.ensemble_size) is not int or self.ensemble_size <= 0:
            errors.append(
                f'WeatherNextSourceManifest: ensemble_size must be > 0, got {self.ensemble_size}'
            )
        if type(self.forecast_horizon_h) is not int or self.forecast_horizon_h <= 0:
            errors.append(
                f'WeatherNextSourceManifest: forecast_horizon_h must be > 0, '
                f'got {self.forecast_horizon_h}'
            )
        if type(self.update_frequency_h) is not int or self.update_frequency_h <= 0:
            errors.append(
                f'WeatherNextSourceManifest: update_frequency_h must be a positive int, '
                f'got {self.update_frequency_h}'
            )
        if (
            isinstance(self.resolution_deg, bool)
            or not isinstance(self.resolution_deg, (int, float))
            or not math.isfinite(float(self.resolution_deg))
            or self.resolution_deg <= 0
        ):
            errors.append(
                f'WeatherNextSourceManifest: resolution_deg must be a positive finite number, '
                f'got {self.resolution_deg!r}'
            )

        # Phase 0.5: UNPINNED identities rejected when source is qualified
        # (shadow_only or promoted). A qualified source must have pinned provenance.
        if self.classification in ('shadow_only', 'promoted'):
            if self.release_tag == _UNPINNED or not self.release_tag:
                errors.append(
                    f'WeatherNextSourceManifest: classification "{self.classification}" '
                    f'requires pinned release_tag (not UNPINNED). '
                    f'Qualified sources must have pinned provenance — no floating heads.'
                )
            if self.model_checkpoint == _UNPINNED or not self.model_checkpoint:
                errors.append(
                    f'WeatherNextSourceManifest: classification "{self.classification}" '
                    f'requires pinned model_checkpoint (not UNPINNED). '
                    f'Qualified sources must have pinned provenance.'
                )
            if not isinstance(self.model_sha256, str) or not self.model_sha256.strip():
                errors.append(
                    f'WeatherNextSourceManifest: classification "{self.classification}" '
                    f'requires pinned model_sha256 (not UNPINNED). '
                    f'Qualified sources must have hash-verified provenance.'
                )
            elif self.model_sha256 == _UNPINNED:
                errors.append(
                    f'WeatherNextSourceManifest: classification "{self.classification}" '
                    f'requires pinned model_sha256 (not UNPINNED). '
                    f'Qualified sources must have hash-verified provenance.'
                )
            elif not _SHA256_RE.fullmatch(self.model_sha256.lower()):
                errors.append(
                    f'WeatherNextSourceManifest: classification "{self.classification}" '
                    f'requires valid SHA-256 model_sha256 (64-char hex). '
                    f'Got: {self.model_sha256[:20]}...'
                )

        return errors

    @property
    def is_approved_for_operational(self) -> bool:
        """Only 'promoted' classification allows operational use."""
        return self.classification == 'promoted'

    @property
    def is_approved_for_shadow(self) -> bool:
        """Shadow or promoted classification allows shadow/research use."""
        return self.classification in ('shadow_only', 'promoted')


@dataclass(frozen=True)
class WeatherNextForcingAssessment:
    """Explicit decision about using a WeatherNext manifest as forcing.

    A complete field list is not enough to authorize direct WN→SMET use. The
    atmospheric candidate still needs a pinned, auditable forcing bridge for
    terrain adjustment, units, and any reconstructed snowpack variables.
    """

    manifest_valid: bool
    shadow_eligible: bool
    direct_complete: bool
    direct_variables: tuple[str, ...]
    missing_variables: tuple[str, ...]
    forcing_bridge_required: bool
    can_feed_snowpack: bool
    reason: str


# SNOWPACK required forcing variables
SNOWPACK_FORCING_VARIABLES = frozenset({
    'TA',     # Air temperature
    'RH',     # Relative humidity
    'VW',     # Wind speed
    'ISWR',   # Incoming short-wave radiation
    'ILWR',   # Incoming long-wave radiation
    'PSUM',   # Precipitation
})


def check_weathernext_variable_completeness(
    manifest: WeatherNextSourceManifest,
) -> dict[str, bool]:
    """Check whether WeatherNext provides all SNOWPACK forcing variables.

    Returns a dict mapping SNOWPACK variable names to True/False (present/missing).
    WeatherNext may not provide all variables directly — some may need to be
    derived or supplied by another source.

    Phase 0.5 P1.3 (corrected): Uses official WN2 field names from Google
    documentation. Wind requires BOTH U and V components (not just one).
    Precipitation is 6-hour accumulation (total_precipitation_6hr).
    Specific humidity at pressure levels is NOT direct 2m RH — it requires
    a derivation bridge. RH is only marked present if relative_humidity_2m
    or an explicit wind_speed field exists.
    """
    raw_fields = manifest.fields if isinstance(manifest.fields, (tuple, list)) else ()
    fields_lower = [field_name.lower() for field_name in raw_fields if isinstance(field_name, str)]

    def _has(name: str) -> bool:
        return name.lower() in fields_lower

    # TA: requires 2m_temperature (direct)
    ta = _has('2m_temperature') or _has('temperature_2m')

    # VW: requires BOTH 10m_u AND 10m_v, OR an explicit wind_speed field.
    # One U/V component alone is insufficient for SNOWPACK forcing.
    has_u = _has('10m_u_component_of_wind') or _has('u10') or _has('10m_u')
    has_v = _has('10m_v_component_of_wind') or _has('v10') or _has('10m_v')
    has_wind_speed = _has('wind_speed') or _has('windspeed') or _has('vw')
    vw = (has_u and has_v) or has_wind_speed

    # RH: requires relative_humidity_2m directly. specific_humidity at
    # pressure levels is derivable but NOT direct — requires a bridge.
    # Do not mark RH as available based on specific_humidity alone.
    rh = _has('relative_humidity_2m') or _has('rh_2m') or _has('humidity_2m')

    # ISWR: requires surface shortwave radiation (direct)
    iswr = (
        _has('surface_shortwave_radiation') or _has('shortwave_radiation')
        or _has('iswr') or _has('swrad')
    )

    # ILWR: requires surface longwave radiation (direct)
    ilwr = (
        _has('surface_longwave_radiation') or _has('longwave_radiation')
        or _has('ilwr') or _has('lwrad')
    )

    # PSUM: requires total_precipitation_6hr (direct, 6-hour accumulation)
    psum = (
        _has('total_precipitation_6hr') or _has('total_precipitation')
        or _has('precipitation') or _has('psum')
    )

    return {
        'TA': ta,
        'RH': rh,
        'VW': vw,
        'ISWR': iswr,
        'ILWR': ilwr,
        'PSUM': psum,
    }


def get_missing_variables(manifest: WeatherNextSourceManifest) -> list[str]:
    """Get list of SNOWPACK forcing variables missing from WeatherNext."""
    completeness = check_weathernext_variable_completeness(manifest)
    return [var for var, present in completeness.items() if not present]


def assess_weathernext_forcing(
    manifest: WeatherNextSourceManifest,
) -> WeatherNextForcingAssessment:
    """Return a fail-closed WeatherNext-to-SNOWPACK readiness assessment.

    This is deliberately an assessment, not a forcing converter. Even a
    qualified source with complete direct fields cannot bypass the Himalayan
    terrain/downscaling and reconstructed-field bridge. ``can_feed_snowpack``
    therefore remains false until a separate, provenance-bound bridge is
    implemented and supplied by the caller.
    """
    manifest_errors = manifest.validate()
    completeness = check_weathernext_variable_completeness(manifest)
    direct_variables = tuple(sorted(
        variable for variable, present in completeness.items() if present
    ))
    missing_variables = tuple(sorted(
        variable for variable, present in completeness.items() if not present
    ))
    if manifest_errors:
        return WeatherNextForcingAssessment(
            manifest_valid=False,
            shadow_eligible=False,
            direct_complete=not missing_variables,
            direct_variables=direct_variables,
            missing_variables=missing_variables,
            forcing_bridge_required=True,
            can_feed_snowpack=False,
            reason='manifest_invalid',
        )
    if not manifest.is_approved_for_shadow:
        return WeatherNextForcingAssessment(
            manifest_valid=True,
            shadow_eligible=False,
            direct_complete=not missing_variables,
            direct_variables=direct_variables,
            missing_variables=missing_variables,
            forcing_bridge_required=True,
            can_feed_snowpack=False,
            reason='source_not_qualified_for_shadow',
        )
    if missing_variables:
        return WeatherNextForcingAssessment(
            manifest_valid=True,
            shadow_eligible=True,
            direct_complete=False,
            direct_variables=direct_variables,
            missing_variables=missing_variables,
            forcing_bridge_required=True,
            can_feed_snowpack=False,
            reason='missing_direct_snowpack_fields',
        )
    return WeatherNextForcingAssessment(
        manifest_valid=True,
        shadow_eligible=True,
        direct_complete=True,
        direct_variables=direct_variables,
        missing_variables=(),
        forcing_bridge_required=True,
        can_feed_snowpack=False,
        reason='forcing_bridge_required_before_snowpack',
    )


def is_weathernext_enabled() -> bool:
    """Check if WeatherNext adapter is enabled.

    Default is False. Must be explicitly enabled via WEATHERNEXT_ENABLED env var.
    Even when enabled, the source must be classified as 'shadow_only' or 'promoted'
    before any data can be used.
    """
    return WEATHERNEXT_ENABLED


def create_default_manifest() -> WeatherNextSourceManifest:
    """Create a default unqualified manifest for the WeatherNext repository.

    This is a skeleton — the actual release tag, checkpoint, and SHA must be
    pinned during Phase 3 source qualification.

    Phase 0.5: corrected to WN2 official specification (64-member, 360h horizon).
    The previous default of ensemble_size=50 and horizon=72h did not match WN2.
    """
    return WeatherNextSourceManifest(
        repo_url='https://github.com/google-deepmind/weathernext',
        release_tag='UNPINNED',
        model_checkpoint='UNPINNED',
        model_sha256='UNPINNED',
        licence='Apache-2.0 (verify)',
        fields=WN2_OFFICIAL_SURFACE_FIELDS,
        resolution_deg=WN2_DEFAULT_RESOLUTION_DEG,
        update_frequency_h=WN2_DEFAULT_UPDATE_FREQUENCY_H,
        ensemble_size=WN2_DEFAULT_ENSEMBLE_SIZE,
        forecast_horizon_h=WN2_DEFAULT_FORECAST_HORIZON_H,
        classification='unqualified',
        is_mini=False,
        notes=(
            'Skeleton manifest for WN2. Release tag, checkpoint, and SHA must be pinned '
            'during Phase 3. WN2 is 64-member, 0.25°, 6-hourly, 15-day. '
            f'Official surface fields: {", ".join(WN2_OFFICIAL_SURFACE_FIELDS)}. '
            f'Missing for SNOWPACK: {", ".join(WN2_MISSING_FOR_SNOWPACK)}. '
            'Direct WN→SMET is unsafe; must use forcing bridge. '
            'Wind is U/V components (derive magnitude). '
            'Precipitation is 6hr accumulation.'
        ),
    )
