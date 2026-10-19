"""AWSOME toolchain runner for operational SNOWPACK automation.

AWSOME (Avalanche Warning Service Operational Meteo Environment) is an
open-source framework (AGPL v3) that automates:
  1. Weather data ingestion → SMET format conversion
  2. SNOWPACK execution per station/grid cell
  3. Post-processing: profile comparison, clustering, avalanche problem extraction
  4. Dashboard visualization of snowpack simulations

This module provides a Python interface to the AWSOME toolchain, with
fallback to direct SNOWPACK execution when AWSOME is not installed.

Phase 0.5 false-green closure:
  - 'completed' requires native binary invoked, clean output dir, manifest
    validation, hash verification, no fallback, and linked identifiers.
  - 'toolchain_unavailable' replaces 'skipped' when binary is missing.
  - 'native_running' is used during actual native execution.
  - 'fallback_proxy' is used when falling back to proxy/heuristic mode.
  - Selected Himalayan band drives actual elevation, not region elevation_max.
  - Output directory is cleaned before each run to prevent stale-file false greens.
  - Acceptance-mode inputs enforce no_fallback and manifest linkage.

Usage:
    # Run AWSOME for a single region
    python3 backend/common/awsome_runner.py --region himalayas_nepal

    # Run for all regions
    python3 backend/common/awsome_runner.py --all-regions

    # Dry-run (validate config without executing SNOWPACK)
    python3 backend/common/awsome_runner.py --region himalayas_nepal --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from backend.common.regions import load_regions, Region
from backend.common.himalayan_regimes import get_regime, HimalayanRegime, ElevationBand
from backend.common.snowpack_paths import UnsafePathError, ensure_safe_directory
from backend.common.snowpack_contracts import validate_release_engine, validate_release_run_id


AWSOME_HOME = os.getenv('AWSOME_HOME', '')
AWSOME_REGIONS_CONFIG = Path(__file__).resolve().parents[2] / 'config' / 'awsome_regions.yaml'
_REQUIRED_NATIVE_OUTPUT_SUFFIXES = frozenset({'.smet', '.pro', '.sno', '.haz'})
_COMPLETED_REQUIRED_SUFFIXES = frozenset({'.smet', '.pro', '.sno', '.haz', '.log'})

# Himalayan region keys that require regime configuration
_HIMALAYAN_REGION_KEYS = frozenset({
    'himalayas_nepal', 'pir_panjal_nw_himalaya', 'shamshabari_nw_himalaya',
    'great_himalaya_nw_himalaya', 'karakoram_&_ladakh',
})

# Phase 0.5 P1.0: Track classification with 4 explicit tracks.
# No region defaults to Partner-approved — that requires explicit approval.
#   track_2_nepal_engineering: Nepal open-data, station-free, no Partner data
#   track_1_indian_candidate: Indian Himalayan regions, NOT yet Partner-approved
#   track_1_Partner_approved: Partner-approved Indian sector (requires Partner agreement)
#   portability: Non-Himalayan regions, smoke-test only
_TRACK_2_REGIONS = frozenset({'himalayas_nepal'})
_TRACK_1_INDIAN_CANDIDATE_REGIONS = frozenset({
    'pir_panjal_nw_himalaya',
    'shamshabari_nw_himalaya',
    'great_himalaya_nw_himalaya',
    'karakoram_&_ladakh',
})
# No regions are Partner-approved yet — this set is empty until Partner agreement.
_TRACK_1_Partner_APPROVED_REGIONS: frozenset[str] = frozenset()

# Approval states for track classification
APPROVAL_STATES = frozenset({
    'not_approved',         # Default: no Partner approval
    'candidate',            # Identified but not approved
    'Partner_approved',        # Partner has approved this region/track
    'not_applicable',       # Portability/smoke-test regions — Partner approval N/A
})

# C0.28: Explicit engine contract. Release mode must select one engine and
# never switch. 'auto' is allowed only outside release mode.
ENGINE_SNOWPACK_DIRECT = 'snowpack_direct'
ENGINE_AWSOME = 'awsome'
ENGINE_AUTO = 'auto'
_VALID_ENGINES = frozenset({ENGINE_SNOWPACK_DIRECT, ENGINE_AWSOME, ENGINE_AUTO})

def _validate_manifest_ids_for_release(
    *,
    forcing_id: str,
    geometry_id: str,
    toolchain_id: str,
    registry_path: Path | None = None,
    region_key: str | None = None,
    elevation_band: str | None = None,
) -> list[str]:
    """C0.32: Validate IDs through the hash-verified approved registry.

    The resolver intentionally fails closed when the registry is absent. No
    placeholder or hardcoded synthetic ID is treated as authoritative.
    """
    from backend.common.snowpack_manifest_registry import validate_release_manifest_ids

    return validate_release_manifest_ids(
        forcing_id=forcing_id,
        geometry_id=geometry_id,
        toolchain_id=toolchain_id,
        registry_path=registry_path,
        region_key=region_key,
        elevation_band=elevation_band,
    )


def _track_for_region(region_key: str) -> str:
    """Phase 0.5 P1.0: return the track classification for a region.

    Four tracks:
      track_2_nepal_engineering: Nepal open-data engineering sandbox.
      track_1_indian_candidate: Indian Himalayan regions, NOT yet Partner-approved.
      track_1_Partner_approved: Partner-approved Indian sector.
      portability: Non-Himalayan regions, smoke-test only.

    No region defaults to Partner-approved. That requires explicit approval.
    Unknown regions (not in any set) raise ValueError — fail closed.
    """
    if region_key in _TRACK_2_REGIONS:
        return 'track_2_nepal_engineering'
    if region_key in _TRACK_1_Partner_APPROVED_REGIONS:
        return 'track_1_Partner_approved'
    if region_key in _TRACK_1_INDIAN_CANDIDATE_REGIONS:
        return 'track_1_indian_candidate'
    # C0.40: Explicit portability registry. Do not infer portability by
    # excluding the Himalayan sets; future Himalayan regions must be explicit.
    if region_key in _EXPLICIT_PORTABILITY_REGIONS:
        return 'portability'
    raise ValueError(
        f'Unknown region "{region_key}" — cannot classify track. '
        f'Add to _TRACK_2_REGIONS, _TRACK_1_INDIAN_CANDIDATE_REGIONS, '
        f'_TRACK_1_Partner_APPROVED_REGIONS, or portability regions list.'
    )


# C0.40: Explicit portability registry — NOT inferred from exclusion.
# Every non-Himalayan region must be explicitly listed here.
# Future Himalayan additions must NOT be misclassified as portability.
_EXPLICIT_PORTABILITY_REGIONS = frozenset({
    'colorado_rockies',
    'swiss_alps',
    'french_alps',
    'andes_patagonia',
    'cascades_wa',
    'scandinavia_norway',
    'japanese_alps',
})


def _approval_state_for_region(region_key: str) -> str:
    """Phase 0.5 P1.0: return the approval state for a region.

    No region is Partner-approved until explicitly added to
    _TRACK_1_Partner_APPROVED_REGIONS. Portability regions are not_applicable
    for Partner approval. Unknown regions raise ValueError — fail closed.
    """
    if region_key in _TRACK_1_Partner_APPROVED_REGIONS:
        return 'Partner_approved'
    if region_key in _TRACK_1_INDIAN_CANDIDATE_REGIONS:
        return 'candidate'
    if region_key in _TRACK_2_REGIONS:
        return 'not_approved'  # Nepal is engineering, not Partner validation
    # C0.40: Portability is explicit, never inferred by exclusion.
    if region_key in _EXPLICIT_PORTABILITY_REGIONS:
        return 'not_applicable'
    raise ValueError(
        f'Unknown region "{region_key}" — cannot determine approval state.'
    )


def _official_warning_eligible(
    region_key: str,
    *,
    native_completed: bool = False,
    validation_passed: bool = False,
    provenance_passed: bool = False,
    promotion_attested: bool = False,
) -> bool:
    """Phase 0.5 P1.0: official warning eligibility requires ALL gates.

    Region membership (Partner approval) is necessary but NOT sufficient.
    Must also have:
      - native_completed: native SNOWPACK execution completed successfully
      - validation_passed: scientific validation gate passed
      - provenance_passed: provenance/manifest verification passed
      - promotion_attested: promotion attestation signed off

    No single gate alone makes a region eligible for official warnings.
    """
    if region_key not in _TRACK_1_Partner_APPROVED_REGIONS:
        return False
    return native_completed and validation_passed and provenance_passed and promotion_attested


def _native_output_status(output_dir: Path) -> tuple[str, list[str]]:
    """Return completed/partial and missing native output suffixes.

    Phase 0.5: 'completed' now requires .log in addition to .smet/.pro/.sno/.haz.
    """
    try:
        output_dir = ensure_safe_directory(output_dir)
    except (OSError, RuntimeError, UnsafePathError):
        return 'partial', sorted(_COMPLETED_REQUIRED_SUFFIXES)
    available = {
        path.suffix for path in output_dir.iterdir()
        if path.is_file() and not path.is_symlink() and path.stat().st_size > 0
    }
    missing = sorted(_COMPLETED_REQUIRED_SUFFIXES - available)
    return ('completed' if not missing else 'partial', missing)


def _native_artifact_roles(
    output_dir: Path,
    *,
    forcing_smet_path: Path,
    station_id: str,
    experiment: str,
) -> dict[str, str]:
    """Assign explicit roles to the pinned SNOWPACK SMET outputs.

    With ``WRITE_PROCESSED_METEO`` enabled, the pinned SNOWPACK revision
    writes ``<station>_<experiment>_forcing.smet``. Its model time-series
    writer emits ``<station>_<experiment>.smet``. The input forcing is the
    separately generated ``<station>.smet``. Filename substring heuristics
    are unsafe because all three files share the ``.smet`` suffix.
    """
    expected = {
        forcing_smet_path.resolve(): 'forcing_smet',
        (output_dir / f'{station_id}_{experiment}_forcing.smet').resolve(): 'processed_meteo',
        (output_dir / f'{station_id}_{experiment}.smet').resolve(): 'model_timeseries_smet',
    }
    roles: dict[str, str] = {}
    for path in sorted(output_dir.iterdir()):
        if path.is_file() and not path.is_symlink() and path.suffix == '.smet':
            role = expected.get(path.resolve())
            if role:
                roles[str(path)] = role
    return roles


def _band_elevation_midpoint(band: ElevationBand | None) -> float:
    """Phase 0.5: compute the midpoint elevation of a selected Himalayan band.

    This replaces the previous behavior of using the region's elevation_max,
    which could cause a Nepal 'lower' run to execute at 5500m instead of
    the lower-band range (3500-4200m).
    """
    if band is None:
        return 3000.0
    return (band.elevation_min_m + band.elevation_max_m) / 2.0


def _representative_site_fixture(
    region: Region,
    band: ElevationBand | None,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Phase 0.5: return a representative site fixture for band-specific execution.

    Until DEM/geometry is supplied, this uses an explicit representative site
    labeled candidate-only. The fixture carries:
      - latitude/longitude from region center
      - elevation from band midpoint (not region elevation_max)
      - slope/aspect from region params
      - candidate_only=True label

    This fixture must NOT satisfy native/completed gates on its own; it is
    metadata only, not a substitute for real geometry manifests.
    """
    center_lat, center_lng = region.center
    return {
        'latitude': center_lat,
        'longitude': center_lng,
        'elevation_m': _band_elevation_midpoint(band),
        'slope_angle': float(params.get('slope_angle', 30)),
        'aspect': float(params.get('aspect', 180)),
        'candidate_only': True,
        'label': 'representative_site_fixture_candidate_v0',
        'band_elevation_min_m': band.elevation_min_m if band else None,
        'band_elevation_max_m': band.elevation_max_m if band else None,
    }


def _clean_output_directory(output_dir: Path) -> None:
    """Phase 0.5: clean an output directory before a native run.

    Stale files in the output directory can create a false 'completed' status
    when suffix presence alone is checked. This removes all files in the
    directory before the run starts.

    Scope: only the run-specific output directory. Does NOT touch parent
    directories or unrelated paths.
    """
    output_dir = ensure_safe_directory(output_dir, create=True)
    for item in output_dir.iterdir():
        if item.is_symlink():
            raise UnsafePathError(f'symlinked output item is not allowed: {item}')
        if item.is_file():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)


def awsome_available() -> bool:
    """Check if AWSOME toolchain is installed."""
    if not AWSOME_HOME:
        return False
    return Path(AWSOME_HOME).exists() and (Path(AWSOME_HOME) / 'awsome-cli.py').exists()


def load_awsome_region_config() -> dict[str, Any]:
    """Load the AWSOME region configuration YAML."""
    if not AWSOME_REGIONS_CONFIG.exists():
        return {}
    with open(AWSOME_REGIONS_CONFIG, encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def get_region_snowpack_params(region_key: str) -> dict[str, Any]:
    """Get canonical SNOWPACK parameters for a configured region.

    Configuration drift is a correctness failure. Unknown region keys are
    rejected instead of silently receiving generic defaults.
    """
    config = load_awsome_region_config()
    if region_key not in config:
        raise KeyError(
            f'Region "{region_key}" is not present in canonical AWSOME config'
        )
    return dict(config[region_key])


def run_awsome_for_region(
    *,
    region: Region,
    as_of: datetime | None = None,
    dry_run: bool = False,
    output_dir: Path | None = None,
    elevation_band: str | None = None,
    # Phase 0.5: acceptance-mode inputs
    no_fallback: bool = False,
    toolchain_manifest_id: str = '',
    forcing_manifest_id: str = '',
    geometry_manifest_id: str = '',
    approved_forcing_manifest: dict[str, str] | None = None,
    approved_geometry_manifest: dict[str, str] | None = None,
    # C0-S4: Explicit run_id — one ID across result, manifest, invocation
    run_id: str = '',
    # C2-prep: explicit initial-state and forecast-semantics contracts for
    # acceptance/release execution. The native runtime wiring remains a
    # separate toolchain/data gate.
    initial_state_contract: Any | None = None,
    forecast_semantics_contract: Any | None = None,
    # Runtime path for a profile-backed initial state inside the release bundle.
    # The contract retains the safe relative bundle path; this is the resolved
    # path actually handed to the native configuration.
    initial_state_path: Path | None = None,
    # C0.28: Explicit engine contract. Release mode must select one engine
    # and never switch. 'auto' is allowed only outside release mode.
    engine: str = ENGINE_AUTO,
) -> dict[str, Any]:
    """Run AWSOME/SNOWPACK automation for a single region.

    When AWSOME is installed, delegates to the AWSOME CLI.
    When AWSOME is not available, falls back to direct SNOWPACK execution
    via the snowpack_physics module.

    Phase 0.5 acceptance-mode inputs:
        no_fallback: If True, proxy/fallback execution is forbidden. The run
            must either complete natively or fail. This prevents false greens
            from fallback paths.
        toolchain_manifest_id: Identifier linking to a pinned toolchain manifest.
        forcing_manifest_id: Identifier linking to a validated forcing manifest.
        geometry_manifest_id: Identifier linking to a geometry/DEM manifest.
        run_id: C0-S4 — Explicit run ID. If provided, used in result, manifest,
            and invocation. If not provided, generated as region_timestamp.

    Args:
        region: Region to process
        as_of: Current datetime (defaults to now)
        dry_run: If True, validate config without executing SNOWPACK
        output_dir: Optional output directory for profiles
        elevation_band: Optional elevation band name (e.g., 'lower')

    Returns:
        Dict with status, method, and profile paths
    """
    as_of = as_of or datetime.now(timezone.utc)
    region_key = region.key
    try:
        if no_fallback:
            validate_release_engine(engine, no_fallback=no_fallback)
            effective_run_id = validate_release_run_id(run_id)
        elif run_id:
            effective_run_id = validate_release_run_id(run_id)
        else:
            effective_run_id = f'{region_key}_{as_of.strftime("%Y%m%dT%H%M%SZ")}'
    except ValueError as exc:
        return {
            'region': region_key,
            'as_of': as_of.isoformat(),
            'dry_run': dry_run,
            'method': None,
            'engine': engine,
            'status': 'failed',
            'profiles': [],
            'error': str(exc),
        }
    try:
        params = get_region_snowpack_params(region_key)
    except KeyError as exc:
        return {
            'region': region_key,
            'as_of': as_of.isoformat(),
            'params': {},
            'dry_run': dry_run,
            'method': None,
            'status': 'failed',
            'profiles': [],
            'error': str(exc),
        }

    regime = get_regime(region_key)
    if region_key in _HIMALAYAN_REGION_KEYS and regime is None:
        return {
            'region': region_key,
            'as_of': as_of.isoformat(),
            'params': params,
            'dry_run': dry_run,
            'method': None,
            'status': 'failed',
            'profiles': [],
            'error': f'No Himalayan regime configuration for {region_key}',
        }
    selected_band_name = elevation_band or (regime.band_names[0] if regime else None)
    if regime and selected_band_name not in regime.band_names:
        return {
            'region': region_key,
            'as_of': as_of.isoformat(),
            'params': params,
            'dry_run': dry_run,
            'method': None,
            'status': 'failed',
            'profiles': [],
            'error': f'Unknown elevation band "{selected_band_name}" for {region_key}',
        }

    # Phase 0.5: get the actual band object for elevation-specific execution
    selected_band = regime.get_band(selected_band_name) if regime else None

    approved_forcing_payload: list[dict[str, Any]] | None = None
    approved_geometry_payload: dict[str, Any] | None = None
    if no_fallback and not dry_run:
        if approved_forcing_manifest is None or approved_geometry_manifest is None:
            return {
                'region': region_key,
                'as_of': as_of.isoformat(),
                'params': params,
                'dry_run': dry_run,
                'method': None,
                'engine': engine,
                'status': 'failed',
                'profiles': [],
                'error': 'release execution requires resolved forcing and geometry payloads',
            }
        try:
            from backend.common.snowpack_manifest_registry import load_approved_payload
            approved_forcing_payload = load_approved_payload(approved_forcing_manifest)
            approved_geometry_payload = load_approved_payload(approved_geometry_manifest)
        except (TypeError, ValueError, KeyError) as exc:
            return {
                'region': region_key,
                'as_of': as_of.isoformat(),
                'params': params,
                'dry_run': dry_run,
                'method': None,
                'engine': engine,
                'status': 'failed',
                'profiles': [],
                'error': f'approved input payload resolution failed: {exc}',
            }

    # G0.7: approved geometry bytes, not a representative fixture, drive the
    # actual native site inputs in release execution.
    if approved_geometry_payload is not None:
        required_geometry = ('latitude', 'longitude', 'elevation_m', 'slope_angle', 'aspect')
        missing_geometry = [field for field in required_geometry if field not in approved_geometry_payload]
        if missing_geometry:
            return {
                'region': region_key,
                'as_of': as_of.isoformat(),
                'params': params,
                'dry_run': dry_run,
                'method': None,
                'engine': engine,
                'status': 'failed',
                'profiles': [],
                'error': f'approved geometry payload missing fields: {missing_geometry}',
            }
        site_fixture = dict(approved_geometry_payload)
        site_fixture['candidate_only'] = False
        site_fixture['label'] = 'approved_geometry_manifest'
    else:
        # Phase 0.5: representative site fixture (candidate-only until DEM supplied)
        site_fixture = _representative_site_fixture(region, selected_band, params)

    # C0.28: Enforce engine contract. Release mode (no_fallback=True) must
    # select one engine and never switch. 'auto' is allowed only outside
    # release mode.
    if engine not in _VALID_ENGINES:
        return {
            'region': region_key,
            'as_of': as_of.isoformat(),
            'params': params,
            'dry_run': dry_run,
            'method': None,
            'status': 'failed',
            'profiles': [],
            'error': f'Invalid engine "{engine}". Must be one of {sorted(_VALID_ENGINES)}.',
        }
    result: dict[str, Any] = {
        'region': region_key,
        'as_of': as_of.isoformat(),
        'params': params,
        'regime': regime.region_key if regime else None,
        'elevation_band': selected_band_name,
        'site_fixture': site_fixture,
        'dry_run': dry_run,
        'method': None,
        'engine': engine,
        'status': 'planned',
        'profiles': [],
        'error': None,
        # C0-S4: Explicit run_id — one ID across result, manifest, invocation
        'run_id': effective_run_id,
        # Phase 0.5: acceptance-mode metadata
        'no_fallback': no_fallback,
        'toolchain_manifest_id': toolchain_manifest_id,
        'forcing_manifest_id': forcing_manifest_id,
        'geometry_manifest_id': geometry_manifest_id,
        # Phase 0.5 P1.0: Track + approval state enforcement in code.
        # official_warning_eligible requires ALL gates (Partner + native + validation
        # + provenance + promotion). At construction time, status is 'planned'
        # so native_completed is False. The status is updated later if native
        # execution succeeds, but official_warning_eligible is only meaningful
        # after all gates pass — which requires explicit attestation.
        'track': _track_for_region(region_key),
        'approval_state': _approval_state_for_region(region_key),
        'official_warning_eligible': _official_warning_eligible(
            region_key,
            native_completed=False,  # Updated after native execution if successful
            validation_passed=False,  # Requires explicit validation gate
            provenance_passed=False,  # Requires manifest verification
            promotion_attested=False,  # Requires promotion attestation
        ),
    }

    if no_fallback and not dry_run:
        if initial_state_contract is None or forecast_semantics_contract is None:
            result['status'] = 'failed'
            result['error'] = (
                'release execution requires initial-state and forecast-semantics contracts'
            )
            return result
        if getattr(initial_state_contract, 'state_type', '') == 'profile':
            if initial_state_path is None or initial_state_path.is_symlink() or not initial_state_path.is_file():
                result['status'] = 'failed'
                result['error'] = (
                    'profile initial-state execution requires a regular runtime payload path'
                )
                return result
        elif initial_state_path is not None:
            result['status'] = 'failed'
            result['error'] = 'snow_free initial state must not provide a profile payload path'
            return result
        try:
            from backend.common.snowpack_release_semantics import (
                validate_release_semantics_context,
            )
            validate_release_semantics_context(
                state=initial_state_contract,
                forecast=forecast_semantics_contract,
                run_id=effective_run_id,
                region_key=region_key,
                elevation_band=selected_band_name or '',
                forcing_manifest_id=forcing_manifest_id,
            )
        except (TypeError, ValueError) as exc:
            result['status'] = 'failed'
            result['error'] = f'release semantics validation failed: {exc}'
            return result
        from backend.common.snowpack_release_semantics import (
            forecast_semantics_to_dict,
            initial_state_to_dict,
        )
        result['initial_state_contract'] = initial_state_to_dict(initial_state_contract)
        result['forecast_semantics_contract'] = forecast_semantics_to_dict(
            forecast_semantics_contract
        )

    if dry_run:
        result['status'] = 'configuration_validated'
        result['method'] = 'dry_run'
        band_range = ''
        if selected_band:
            band_range = f', band {selected_band_name}: {selected_band.elevation_min_m}-{selected_band.elevation_max_m}m'
        result['message'] = f'Config validated for {region_key}: elevation {params["elevation_min"]}-{params["elevation_max"]}m{band_range}'

        # Phase 0.5 P0.9 (advisor point 5): structural validation in dry-run mode.
        # Fail fast on contract breaks (missing IDs in acceptance mode), but
        # skip runtime-only assertions (artifacts present, run_id).
        if no_fallback:
            if not toolchain_manifest_id:
                result['error'] = 'Acceptance mode requires toolchain_manifest_id'
                result['status'] = 'failed'
            if not forcing_manifest_id:
                result['error'] = 'Acceptance mode requires forcing_manifest_id'
                result['status'] = 'failed'
            if not geometry_manifest_id:
                result['error'] = 'Acceptance mode requires geometry_manifest_id'
                result['status'] = 'failed'

        return result

    # C0.28: Engine contract — select engine based on explicit contract.
    # When engine=snowpack_direct, skip AWSOME entirely.
    # When engine=awsome, use AWSOME and never fall through to direct.
    # When engine=auto (non-release only), try AWSOME first, then direct.
    use_awsome = engine in (ENGINE_AWSOME, ENGINE_AUTO) and awsome_available()
    use_direct = engine in (ENGINE_SNOWPACK_DIRECT, ENGINE_AUTO)

    # Try AWSOME CLI first (only if engine allows it)
    if use_awsome:
        try:
            awsome_cli = Path(AWSOME_HOME) / 'awsome-cli.py'
            output_dir = output_dir or Path(AWSOME_HOME) / 'output' / region_key
            # Phase 0.5: clean output directory before run
            _clean_output_directory(output_dir)

            cmd = [
                sys.executable,
                str(awsome_cli),
                '--region', region_key,
                '--date', as_of.date().isoformat(),
                '--output', str(output_dir),
                '--config', str(AWSOME_REGIONS_CONFIG),
            ]

            result['status'] = 'native_running'
            # G6: Capture execution evidence for AWSOME CLI path too
            # G9: Hash the actual script and interpreter — no empty binary_sha256
            import hashlib as _hashlib
            from datetime import datetime as _dt, timezone as _tz
            _started_at = _dt.now(_tz.utc).isoformat()
            _cmd_str = ' '.join(cmd)
            _cmd_sha = _hashlib.sha256(_cmd_str.encode()).hexdigest()
            # G9: Hash the AWSOME CLI script
            _script_sha = ''
            try:
                with open(awsome_cli, 'rb') as _sf:
                    _script_sha = _hashlib.sha256(_sf.read()).hexdigest()
            except (OSError, PermissionError):
                pass
            # G9: Hash the Python interpreter
            _interp_sha = ''
            try:
                with open(sys.executable, 'rb') as _if:
                    _interp_sha = _hashlib.sha256(_if.read()).hexdigest()
            except (OSError, PermissionError):
                pass
            # Require an explicit AWSOME version probe before accepting completion.
            import tempfile as _tempfile
            _version_exit_code = -1
            _version_text = ''
            try:
                with _tempfile.TemporaryDirectory() as _version_cwd:
                    _version_proc = subprocess.run(
                        [sys.executable, str(awsome_cli), '--version'],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        cwd=_version_cwd,
                    )
                    _version_exit_code = _version_proc.returncode
                    _version_text = (_version_proc.stdout + _version_proc.stderr).strip()[:200]
            except (subprocess.TimeoutExpired, OSError):
                pass
            _version_verified = _version_exit_code == 0 and bool(_version_text)
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            _finished_at = _dt.now(_tz.utc).isoformat()
            _stdout_sha = _hashlib.sha256(proc.stdout.encode()).hexdigest()
            _stderr_sha = _hashlib.sha256(proc.stderr.encode()).hexdigest()
            # Store evidence in result for attestation
            # G9: binary_sha256 is the script hash; interpreter hash recorded separately
            result['execution_evidence'] = {
                'binary_path': str(awsome_cli),
                'binary_sha256': _script_sha,  # G9: Hash of the actual script
                'binary_version': _version_text,
                'command': _cmd_str,
                'command_sha256': _cmd_sha,
                'exit_code': proc.returncode,
                'started_at': _started_at,
                'finished_at': _finished_at,
                'toolchain_id': toolchain_manifest_id,
                'run_id': effective_run_id,
                'stdout_sha256': _stdout_sha,
                'stderr_sha256': _stderr_sha,
                'version_exit_code': _version_exit_code,
                'version_verified': _version_verified,
                'interpreter_path': sys.executable,
                'interpreter_sha256': _interp_sha,
                'execution_kind': 'awsome_cli',
                'success': proc.returncode == 0 and _version_verified and bool(_script_sha),
            }

            if proc.returncode == 0:
                profiles = [p for p in output_dir.glob('*.pro') if p.is_file() and p.stat().st_size > 0]
                if not profiles:
                    result['status'] = 'failed'
                    result['method'] = 'awsome'
                    result['error'] = 'AWSOME returned success but produced no non-empty .pro output'
                    return result
                # Phase 0.5: build and validate artifact manifest
                from backend.common.snowpack_artifact_manifest import (
                    build_manifest_from_directory,
                    verify_manifest_against_directory,
                )
                manifest = build_manifest_from_directory(
                    run_id=effective_run_id,
                    region_key=region_key,
                    elevation_band=selected_band_name or '',
                    aspect_class=site_fixture.get('label', 'unknown'),
                    binary_version='awsome',
                    output_dir=output_dir,
                    created_at=as_of.isoformat(),
                    native_binary_invoked=True,
                    toolchain_id=toolchain_manifest_id,
                    forcing_manifest_id=forcing_manifest_id,
                    geometry_manifest_id=geometry_manifest_id,
                )
                manifest_errors = manifest.validate()
                # Phase 0.5 P0.9: call validate_completed() — the REAL completed check
                completed_errors = manifest.validate_completed()
                verify_errors = verify_manifest_against_directory(manifest, output_dir)
                all_errors = manifest_errors + verify_errors

                native_status, missing_outputs = _native_output_status(output_dir)
                if not _version_verified or not _script_sha:
                    native_status = 'partial'
                    missing_outputs = sorted(set(missing_outputs) | {'version_verified', 'binary_sha256'})
                # Phase 0.5 P0.9: downgrade to partial if validate_completed() fails
                if native_status == 'completed' and completed_errors:
                    native_status = 'partial'
                result['status'] = native_status
                result['method'] = 'awsome'
                result['profiles'] = [str(p) for p in profiles]
                result['missing_outputs'] = missing_outputs
                result['artifacts'] = [
                    str(path) for path in sorted(output_dir.iterdir())
                    if path.is_file() and path.stat().st_size > 0
                ]
                result['manifest'] = json.loads(__import__('backend.common.snowpack_artifact_manifest', fromlist=['manifest_to_json']).manifest_to_json(manifest))
                result['manifest_errors'] = all_errors + completed_errors
                if all_errors or missing_outputs or completed_errors:
                    result['error'] = f'AWSOME output validation failed: {all_errors + completed_errors + missing_outputs}'
                    if native_status == 'completed' and (all_errors or completed_errors):
                        result['status'] = 'partial'  # Downgrade if manifest fails
                return result
            else:
                result['error'] = f'AWSOME CLI failed: {proc.stderr[:500]}'
        except Exception as exc:
            result['error'] = f'AWSOME execution error: {exc}'

        # C0.28: If engine=awsome and AWSOME failed, do NOT fall through to
        # direct SNOWPACK. The engine contract forbids switching engines.
        if engine == ENGINE_AWSOME:
            result['status'] = 'failed'
            result['method'] = 'awsome'
            if not result.get('error'):
                result['error'] = 'AWSOME engine selected but execution failed. ' \
                                  'Engine contract forbids fallback to direct SNOWPACK.'
            return result

    # C0.28: Direct SNOWPACK execution — only if engine allows it.
    # When engine=auto (non-release), this is a fallback.
    # When engine=snowpack_direct, this is the primary path.
    if not use_direct:
        result['status'] = 'failed'
        result['method'] = None
        result['error'] = result.get('error') or 'No engine available for execution.'
        return result

    # Fallback: direct SNOWPACK execution via the non-denylisted SMET bridge.
    try:
        from backend.common.meteoio_openmeteo import (
            generate_snowpack_config,
            parse_snowpack_pro,
            run_snowpack_native,
            snowpack_binary_available,
            write_snow_free_smet_profile,
            write_smet_file,
        )
        from backend.common.snowpack_physics import fetch_weather_history_for_snowpack
        from backend.common.snowpack_proxy import winter_season_start

        if not snowpack_binary_available():
            # Phase 0.5: use toolchain_unavailable instead of skipped
            result['status'] = 'toolchain_unavailable'
            result['method'] = 'unavailable'
            result['error'] = 'Neither AWSOME nor SNOWPACK binary available. Run: bash scripts/setup_awsome.sh'
            return result

        # G0.7: use approved geometry bytes when running release mode.
        if approved_geometry_payload is not None:
            center_lat = float(approved_geometry_payload['latitude'])
            center_lng = float(approved_geometry_payload['longitude'])
            elevation = float(approved_geometry_payload['elevation_m'])
            slope = float(approved_geometry_payload['slope_angle'])
            aspect = float(approved_geometry_payload['aspect'])
        else:
            center_lat, center_lng = region.center
            elevation = _band_elevation_midpoint(selected_band)
            slope = float(params.get('slope_angle', 30))
            aspect = float(params.get('aspect', 180))
        output_dir = output_dir or (
            Path(__file__).resolve().parents[2]
            / 'backend' / 'artifacts' / 'snowpack' / region_key
            / as_of.strftime('%Y%m%dT%H%M%SZ')
        )
        # Phase 0.5: clean output directory before run to prevent stale-file false greens
        _clean_output_directory(output_dir)

        if approved_forcing_payload is not None:
            weather_history = approved_forcing_payload
        else:
            weather_history = fetch_weather_history_for_snowpack(
                lat=center_lat,
                lng=center_lng,
                as_of=as_of,
                season_start=winter_season_start(
                    as_of,
                    str(params.get('season_start') or '11-01'),
                ),
            )
        if not weather_history:
            result['status'] = 'failed'
            result['method'] = 'snowpack_direct'
            result['error'] = 'No approved or weather-history forcing available for native SNOWPACK'
            return result

        has_precipitation_phase = any(
            isinstance(sample, dict) and sample.get('precipitation_phase') is not None
            for sample in weather_history
        )
        if has_precipitation_phase and not all(
            isinstance(sample, dict) and sample.get('precipitation_phase') is not None
            for sample in weather_history
        ):
            result['status'] = 'failed'
            result['method'] = 'snowpack_direct'
            result['error'] = (
                'forcing contains partial precipitation_phase coverage; '
                'PSUM_PH must be complete or omitted'
            )
            return result

        # A snow-free contract is an explicit native seed, not an instruction
        # to rely on SNOWPACK's undocumented default initial state.  Generate
        # the zero-layer SMET seed inside the controlled run directory so it
        # is included in the release evidence and remains bound to the
        # approved geometry and state start time.
        if (
            initial_state_contract is not None
            and getattr(initial_state_contract, 'state_type', '') == 'snow_free'
            and initial_state_path is None
        ):
            # Keep the seed under input-manifests, not native-output: the
            # release manifest must contain exactly one final .sno role.
            initial_state_path = (
                output_dir.parent
                / 'input-manifests'
                / 'initial-state-payload'
                / f'{region_key}-initial.sno'
            )
            write_snow_free_smet_profile(
                output_path=initial_state_path,
                station_id=f'{region_key}-initial',
                latitude=center_lat,
                longitude=center_lng,
                elevation=elevation,
                profile_date=initial_state_contract.start_time,
                slope_angle=slope,
                aspect=aspect,
            )

        # R9: bind the actual forcing timestamps to the declared forecast
        # window before generating SMET. This is a chronology/identity check,
        # not a claim that the source has scientific skill.
        if forecast_semantics_contract is not None:
            from backend.common.snowpack_release_semantics import (
                validate_forcing_samples_against_forecast,
            )
            try:
                result['forcing_window'] = validate_forcing_samples_against_forecast(
                    weather_history,
                    forecast_semantics_contract,
                )
            except (TypeError, ValueError) as exc:
                result['status'] = 'failed'
                result['method'] = 'snowpack_direct'
                result['error'] = f'forcing/forecast semantics mismatch: {exc}'
                return result

        smet_path = output_dir / f'{region_key}.smet'
        config_path = output_dir / 'snowpack.ini'
        write_smet_file(
            output_path=smet_path,
            station_id=region_key,
            latitude=center_lat,
            longitude=center_lng,
            elevation=elevation,
            samples=weather_history,
            slope_angle=slope,
            aspect=aspect,
            strict=True,
            include_precipitation_phase=has_precipitation_phase,
        )
        season_start = winter_season_start(
            as_of,
            str(params.get('season_start') or '11-01'),
        )
        generate_snowpack_config(
            output_path=config_path,
            season_start_date=season_start.isoformat(),
            end_date=as_of.date().isoformat(),
            initial_state_path=initial_state_path,
            station_id=region_key,
            latitude=center_lat,
            longitude=center_lng,
            meteo_path=smet_path.parent,
            output_dir=output_dir,
            experiment='native',
        )
        # Phase 0.5: mark as native_running during execution
        result['status'] = 'native_running'
        result['method'] = 'snowpack_direct'
        evidence = run_snowpack_native(
            smet_path=smet_path,
            output_dir=output_dir,
            config_path=config_path,
            begin_date=(
                initial_state_contract.start_time
                if initial_state_contract is not None
                else None
            ),
            end_date=as_of.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M'),
            timeout_s=300,
            run_id=effective_run_id,
            toolchain_id=toolchain_manifest_id,
        )
        if evidence is None:
            result['status'] = 'failed'
            result['method'] = 'snowpack_direct'
            result['error'] = 'SNOWPACK binary not available'
            return result

        # C0-S5: Store execution evidence in result for attestation
        result['execution_evidence'] = {
            'binary_path': evidence.binary_path,
            'binary_sha256': evidence.binary_sha256,
            'binary_version': evidence.binary_version,
            'command': evidence.command,
            'command_sha256': evidence.command_sha256,
            'exit_code': evidence.exit_code,
            'started_at': evidence.started_at,
            'finished_at': evidence.finished_at,
            'toolchain_id': evidence.toolchain_id,
            'run_id': evidence.run_id,
            'stdout_sha256': evidence.stdout_sha256,
            'stderr_sha256': evidence.stderr_sha256,
            'version_exit_code': evidence.version_exit_code,
            'version_verified': evidence.version_verified,
            'toolchain_manifest_path': evidence.toolchain_manifest_path,
            'toolchain_manifest_sha256': evidence.toolchain_manifest_sha256,
            'toolchain_manifest': evidence.toolchain_manifest,
            'toolchain_manifest_verified': evidence.toolchain_manifest_verified,
            'image_id': evidence.image_id,
            'image_archive_sha256': evidence.image_archive_sha256,
            'image_repository_digest': evidence.image_repository_digest,
            'image_identity_source': evidence.image_identity_source,
            'pro_path': evidence.pro_path,
            'log_path': evidence.log_path,
            'execution_kind': 'snowpack_direct',
            'success': evidence.success,
        }

        pro_path = Path(evidence.pro_path) if evidence.pro_path else None
        if pro_path is None or pro_path.is_symlink() or not pro_path.is_file() or pro_path.stat().st_size == 0:
            result['status'] = 'failed'
            result['method'] = 'snowpack_direct'
            result['error'] = f'SNOWPACK execution produced no non-empty .pro output (exit_code={evidence.exit_code})'
            return result

        parsed = parse_snowpack_pro(pro_path)
        native_status, missing_outputs = _native_output_status(output_dir)
        if not evidence.version_verified or not evidence.binary_sha256:
            native_status = 'partial'
            result['error'] = 'SNOWPACK version verification or binary hash evidence failed'

        # Phase 0.5: build and validate artifact manifest
        from backend.common.snowpack_artifact_manifest import (
            build_manifest_from_directory,
            verify_manifest_against_directory,
            manifest_to_json,
        )
        # C0.31: Use the actual probed version from execution evidence, not
        # binary.name (which is just the filename, not the version string).
        binary_version = evidence.binary_version or 'snowpack_direct:unknown'

        manifest = build_manifest_from_directory(
            run_id=effective_run_id,
            region_key=region_key,
            elevation_band=selected_band_name or '',
            aspect_class=site_fixture.get('label', 'unknown'),
            binary_version=binary_version,
            output_dir=output_dir,
            created_at=as_of.isoformat(),
            native_binary_invoked=True,
            toolchain_id=toolchain_manifest_id,
            forcing_manifest_id=forcing_manifest_id,
            geometry_manifest_id=geometry_manifest_id,
            artifact_roles=_native_artifact_roles(
                output_dir,
                forcing_smet_path=smet_path,
                station_id=region_key,
                experiment='native',
            ),
        )
        manifest_errors = manifest.validate()
        # Phase 0.5 P0.9: call validate_completed() — the REAL completed check
        completed_errors = manifest.validate_completed()
        verify_errors = verify_manifest_against_directory(manifest, output_dir)
        all_errors = manifest_errors + verify_errors

        # Phase 0.5 P0.9: downgrade to partial if validate_completed() fails
        if native_status == 'completed' and (all_errors or completed_errors):
            native_status = 'partial'

        result['status'] = native_status
        result['method'] = 'snowpack_direct'
        result['profiles'] = [str(pro_path)]
        result['missing_outputs'] = missing_outputs
        result['artifacts'] = [
            str(path) for path in sorted(output_dir.iterdir())
            if path.is_file() and path.stat().st_size > 0
        ]
        result['profile'] = parsed
        result['manifest'] = json.loads(manifest_to_json(manifest))
        # P0.9a: include completed_errors in manifest_errors (was missing)
        result['manifest_errors'] = all_errors + completed_errors
        if missing_outputs:
            result['error'] = f'SNOWPACK output incomplete; missing: {missing_outputs}'
        if all_errors or completed_errors:
            result['error'] = (result.get('error') or '') + f'; manifest errors: {all_errors + completed_errors}'
        return result
    except Exception as exc:
        result['status'] = 'failed'
        result['error'] = str(exc)

    return result


def run_awsome_all_regions(
    *,
    as_of: datetime | None = None,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Run AWSOME/SNOWPACK for all configured regions.

    Args:
        as_of: Current datetime
        dry_run: If True, validate configs without executing

    Returns:
        List of result dicts, one per region
    """
    regions = load_regions()
    results: list[dict[str, Any]] = []

    for region in regions:
        result = run_awsome_for_region(
            region=region,
            as_of=as_of,
            dry_run=dry_run,
        )
        results.append(result)

    return results


def validate_awsome_setup() -> dict[str, Any]:
    """Validate AWSOME/SNOWPACK installation status.

    Returns a diagnostic dict useful for CI checks and debugging.
    """
    from backend.common.meteoio_openmeteo import snowpack_binary_available

    return {
        'awsome_installed': awsome_available(),
        'awsome_home': AWSOME_HOME or '(not set)',
        'snowpack_binary': snowpack_binary_available(),
        'regions_config': AWSOME_REGIONS_CONFIG.exists(),
        'regions_config_path': str(AWSOME_REGIONS_CONFIG),
        'region_count': len(load_awsome_region_config()),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for AWSOME runner."""
    parser = argparse.ArgumentParser(description='AWSOME SNOWPACK automation runner')
    parser.add_argument('--region', help='Single region key to process')
    parser.add_argument('--all-regions', action='store_true', help='Process all regions')
    parser.add_argument('--dry-run', action='store_true', help='Validate without executing')
    parser.add_argument('--validate', action='store_true', help='Check installation status')
    # C0.4: Add release-mode CLI arguments
    parser.add_argument('--elevation-band', help='Elevation band (lower/middle/upper)')
    parser.add_argument('--run-id', help='Explicit run ID for the execution')
    parser.add_argument('--no-fallback', action='store_true', help='Acceptance mode — no fallback allowed')
    parser.add_argument('--release', action='store_true', help='Release mode — only completed exits 0')
    parser.add_argument('--output-bundle', help='Canonical release bundle directory; only the release orchestrator may publish it')
    parser.add_argument('--toolchain-id', help='Toolchain manifest ID')
    parser.add_argument('--forcing-id', help='Forcing manifest ID')
    parser.add_argument('--geometry-id', help='Geometry manifest ID')
    parser.add_argument('--initial-state-manifest', help='Initial snow/soil state contract JSON')
    parser.add_argument('--forecast-semantics-manifest', help='Forecast cycle/window/member contract JSON')
    parser.add_argument('--manifest-registry', help='Approved SNOWPACK manifest registry JSON')
    # C0.28: Explicit engine selection
    parser.add_argument('--engine', choices=['auto', 'snowpack_direct', 'awsome'],
                        default='auto', help='Execution engine (release mode requires non-auto)')
    args = parser.parse_args(argv)

    if args.validate:
        status = validate_awsome_setup()
        print(json.dumps(status, indent=2))
        return 0 if status['snowpack_binary'] or status['awsome_installed'] else 1

    if args.all_regions:
        results = run_awsome_all_regions(dry_run=args.dry_run)
        print(json.dumps(results, indent=2))
        return 0

    if args.region:
        # C0.27: every release invocation delegates to the canonical
        # orchestrator. The runner remains a diagnostic/non-release interface.
        if args.output_bundle and not args.release:
            print(
                'ERROR: --output-bundle is owned exclusively by the canonical '
                'release orchestrator; diagnostic runner output is stdout-only.',
                file=sys.stderr,
            )
            return 1

        if args.release:
            if not args.output_bundle:
                print('ERROR: --release requires --output-bundle', file=sys.stderr)
                return 1
            if not args.no_fallback:
                print(
                    'ERROR: --release requires --no-fallback; release mode cannot '
                    'permit fallback or engine switching.',
                    file=sys.stderr,
                )
                return 1
            if args.engine == 'auto':
                print(
                    'ERROR: --release requires an explicit --engine '
                    '(snowpack_direct or awsome), not auto.',
                    file=sys.stderr,
                )
                return 1
            from backend.scripts.run_snowpack_release import run_release_orchestration
            return run_release_orchestration(
                region_key=args.region,
                elevation_band=args.elevation_band or '',
                run_id=args.run_id or '',
                toolchain_id=args.toolchain_id or '',
                forcing_id=args.forcing_id or '',
                geometry_id=args.geometry_id or '',
                initial_state_manifest_path=(
                    Path(args.initial_state_manifest)
                    if args.initial_state_manifest else None
                ),
                forecast_semantics_manifest_path=(
                    Path(args.forecast_semantics_manifest)
                    if args.forecast_semantics_manifest else None
                ),
                engine=args.engine,
                output_bundle=Path(args.output_bundle),
                manifest_registry_path=(
                    Path(args.manifest_registry) if args.manifest_registry else None
                ),
            )

        regions = load_regions()
        region = next((r for r in regions if r.key == args.region), None)
        if region is None:
            print(f'ERROR: Region "{args.region}" not found')
            return 1

        result = run_awsome_for_region(
            region=region,
            dry_run=args.dry_run,
            elevation_band=args.elevation_band,
            no_fallback=args.no_fallback,
            toolchain_manifest_id=args.toolchain_id or '',
            forcing_manifest_id=args.forcing_id or '',
            geometry_manifest_id=args.geometry_id or '',
            run_id=args.run_id or '',  # C0-S4: thread run_id through all layers
            engine=args.engine,  # C0.28: thread engine through all layers
        )
        print(json.dumps(result, indent=2))

        # C0.5: In release mode, only 'completed' exits 0.
        # In normal mode, only 'failed' exits 1.
        if args.release:
            if result['status'] != 'completed':
                return 1
        else:
            if result['status'] == 'failed':
                return 1

        # C0.27: The runner is stdout-only outside release mode.
        # Bundle publication belongs exclusively to the canonical orchestrator.
        return 0 if result['status'] != 'failed' else 1

    parser.print_help()
    return 1


if __name__ == '__main__':
    sys.exit(main())
