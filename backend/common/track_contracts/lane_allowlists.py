"""Track 1 and T2A feature allowlists and denylists.

Track separation requires that each track has a distinct feature whitelist.
This module defines:

- TRACK1_ALLOWLIST: station/anchor + SNOWPACK + terrain features
- T2A_ALLOWLIST: open forcing + terrain features only (NO SNOWPACK)
- T2A_DENYLIST: station feeds, SNOWPACK (native/proxy/heuristic/synthetic)
- TRACK1_DENYLIST: open-forcing-only features that bypass station/SNOWPACK

These lists are derived from:
1. Partner approval request (page 5, Track architecture table)
2. PlanB.md (P0: "T2B must use different target, feature contract, model ID")
3. Aug07 Partner decision brief (Decision #6: station-free definition)
4. The 14 Aug MoM directive: "Do not mix the two tracks"

The existing FEATURE_COLUMNS in features.py (46 base features) include
SNOWPACK-derived fields that MUST NOT appear in T2A. This module provides
the validation that enforces that separation.

Hardening (per Codex audit G2):
- Empty feature lists are rejected (fail closed, not open)
- Minimum feature families are required (forcing+terrain for T2A, station+SNOWPACK for Track 1)
- Denylist matching uses normalized names (catches case, space, hyphen, underscore variants)
- SNOWPACK stability aliases (ssi, Sk38, Sn38, etc.) are denied in T2A
- Feature lineage is checked against known SNOWPACK/station derivation patterns
"""

from __future__ import annotations

import re


class FeatureContaminationError(ValueError):
    """Raised when a track's feature set contains denied features."""


# --- Feature name normalization ---

def normalize_feature_name(name: str) -> str:
    """Normalize a feature name for denylist matching.

    Removes case sensitivity, spaces, hyphens, and underscores so that
    variants like 'SNOWPACK', 'snow_pack', 'snow-pack', 'snow pack' all
    normalize to 'snowpack'.
    """
    return re.sub(r'[\s\-_]+', '', name.strip().lower())


# --- Pre-computed normalized denylists ---

_T2A_DENYLIST_NORMALIZED: frozenset[str] = frozenset(
    normalize_feature_name(name) for name in [
        # SNOWPACK-derived (native, proxy, heuristic, or synthetic)
        "snowpack", "ram_hardness", "shear_strength", "settlement_rate",
        "load_to_shear_ratio", "settlement_deficit", "weak_layer_depth",
        "grain_type_faceted", "grain_type_depth_hoar", "stability_index",
        "temp_gradient_profile", "liquid_water_content",
        "snow_depth_fused", "snow_depth_uncertainty", "sensor_consensus",
        # SNOWPACK stability aliases (from Swiss reproduction data_loader.py)
        "ssi", "sk38", "sn38", "ccl", "pwl", "pwl_100",
        "pen_depth", "penetration_depth",
        # Station/anchor inputs (not allowed in T2A)
        "station_snow_depth", "station_temperature", "station_wind",
        "station_humidity", "aws_observation", "edrmg_telemetry",
        "aavds_detection", "geophone_signal",
        # Partner SNOWPACK adapter outputs
        "Partner_snowpack_snow_depth_cm", "Partner_snowpack_shear_strength_kpa",
        "Partner_snowpack_settlement_index", "Partner_snowpack_weak_layer_depth_cm",
        "Partner_snowpack_grain_type", "Partner_snowpack_stability_index",
        # Generic SNOWPACK lineage prefixes
        "snowpack_", "snowpackstate", "snowpackstability",
        "snow_cover", "snowprofile", "snow_profile",
    ]
)

_TRACK1_DENYLIST_NORMALIZED: frozenset[str] = frozenset(
    normalize_feature_name(name) for name in [
        "snowfall_48h", "snowfall_72h", "snowfall_7d",
        "precipitation_48h", "precipitation_72h", "precipitation_7d",
        "wind_speed_avg_24h", "wind_speed_avg_48h", "wind_speed_avg_72h",
    ]
)

# --- Feature family definitions (for minimum family requirements) ---

T2A_FORCING_FEATURES: frozenset[str] = frozenset({
    "temperature_2m", "relative_humidity_2m", "wind_speed_10m",
    "wind_direction_10m", "wind_speed_100m", "wind_direction_100m",
    "shortwave_radiation", "precipitation", "rain", "snowfall",
    "cloud_cover", "cloud_cover_low", "cloud_cover_mid", "cloud_cover_high",
    "pressure_msl", "surface_pressure", "dew_point_2m",
    "wet_bulb_temperature_2m", "apparent_temperature",
    "vapour_pressure_deficit", "snowfall_24h", "snowfall_48h",
    "snowfall_72h", "snowfall_7d", "precipitation_24h", "precipitation_48h",
    "precipitation_72h", "precipitation_7d", "wind_speed_avg_24h",
    "wind_speed_avg_48h", "wind_speed_avg_72h", "wind_loading",
    "wind_directional_loading", "temp_gradient", "freezing_level_proxy",
    "freezing_level_margin", "rain_on_snow_signal", "wet_activation_signal",
    "elevation_precip_bias",
})

T2A_TERRAIN_FEATURES: frozenset[str] = frozenset({
    "elevation", "slope", "aspect", "terrain_roughness",
    "curvature_proxy", "northness", "eastness", "aspect_loading",
})

TRACK1_STATION_FEATURES: frozenset[str] = frozenset({
    "station_snow_depth", "station_temperature", "station_wind",
    "station_humidity", "aws_observation",
})

TRACK1_SNOWPACK_FEATURES: frozenset[str] = frozenset({
    "snowpack", "ram_hardness", "shear_strength", "settlement_rate",
    "load_to_shear_ratio", "settlement_deficit", "weak_layer_depth",
    "grain_type_faceted", "grain_type_depth_hoar", "stability_index",
    "temp_gradient_profile", "liquid_water_content",
})

# --- T2A ALLOWLIST: open forcing + terrain only ---

T2A_ALLOWLIST: frozenset[str] = T2A_FORCING_FEATURES | T2A_TERRAIN_FEATURES | frozenset({
    "day_of_year", "season_phase",
})

# --- T2A DENYLIST: everything that must NOT appear in T2A ---

T2A_DENYLIST: frozenset[str] = frozenset({
    "snowpack", "ram_hardness", "shear_strength", "settlement_rate",
    "load_to_shear_ratio", "settlement_deficit", "weak_layer_depth",
    "grain_type_faceted", "grain_type_depth_hoar", "stability_index",
    "temp_gradient_profile", "liquid_water_content",
    "snow_depth_fused", "snow_depth_uncertainty", "sensor_consensus",
    "station_snow_depth", "station_temperature", "station_wind",
    "station_humidity", "aws_observation", "edrmg_telemetry",
    "aavds_detection", "geophone_signal",
    "Partner_snowpack_snow_depth_cm", "Partner_snowpack_shear_strength_kpa",
    "Partner_snowpack_settlement_index", "Partner_snowpack_weak_layer_depth_cm",
    "Partner_snowpack_grain_type", "Partner_snowpack_stability_index",
})

# --- Track 1 ALLOWLIST: station/anchor + SNOWPACK + terrain ---

TRACK1_ALLOWLIST: frozenset[str] = TRACK1_STATION_FEATURES | TRACK1_SNOWPACK_FEATURES | frozenset({
    "elevation", "slope", "aspect", "terrain_roughness",
    "curvature_proxy", "northness", "eastness", "aspect_loading",
    "snowfall_24h", "precipitation_24h", "wind_loading",
    "wind_directional_loading", "temp_gradient", "freezing_level_proxy",
    "freezing_level_margin", "rain_on_snow_signal", "wet_activation_signal",
    "elevation_precip_bias", "day_of_year", "season_phase",
})

# --- Track 1 DENYLIST: features that would bypass station/SNOWPACK ---

TRACK1_DENYLIST: frozenset[str] = frozenset({
    "snowfall_48h", "snowfall_72h", "snowfall_7d",
    "precipitation_48h", "precipitation_72h", "precipitation_7d",
    "wind_speed_avg_24h", "wind_speed_avg_48h", "wind_speed_avg_72h",
})


def check_feature_lineage(feature_name: str) -> str | None:
    """Check if a feature name has SNOWPACK or station lineage.

    Returns the lineage category ('snowpack', 'station', or None) based on
    the feature name's derivation pattern, not just exact string matching.
    """
    normalized = normalize_feature_name(feature_name)
    # SNOWPACK lineage patterns
    snowpack_patterns = [
        'snowpack', 'snowpackstate', 'snowpackstability',
        'snowcover', 'snowprofile', 'snowprofile',
        'ramhardness', 'shearstrength', 'settlementrate',
        'loadtoshearratio', 'settlementdeficit', 'weaklayerdepth',
        'graintype', 'stabilityindex', 'tempgradientprofile',
        'liquidwatercontent', 'snowdepthfused', 'snowdepthuncertainty',
        'sensorconsensus', 'ssi', 'sk38', 'sn38', 'ccl', 'pwl',
        'pendepth', 'penetrationdepth',
    ]
    for pattern in snowpack_patterns:
        if pattern in normalized:
            return 'snowpack'
    # Station lineage patterns
    station_patterns = [
        'station', 'aws', 'awsobservation', 'edrmg', 'aavds',
        'geophone', 'anchor', 'localobs', 'localobservation',
    ]
    for pattern in station_patterns:
        if pattern in normalized:
            return 'station'
    return None


def _check_denylist_variants(feature_names: list[str], denylist_normalized: frozenset[str]) -> list[str]:
    """Check features against normalized denylist, catching variants."""
    violations = []
    for name in feature_names:
        normalized = normalize_feature_name(name)
        if normalized in denylist_normalized:
            violations.append(name)
        # Also check lineage
        lineage = check_feature_lineage(name)
        if lineage == 'snowpack' and 'snowpack' in denylist_normalized:
            violations.append(name)
        elif lineage == 'station' and 'stationsnowdepth' in denylist_normalized:
            violations.append(name)
    return violations


def _check_feature_families(
    feature_set: set[str],
    required_families: list[tuple[frozenset[str], str]],
) -> list[str]:
    """Check that all required feature families are represented.

    Returns list of missing family names.
    """
    missing = []
    for family, family_name in required_families:
        if not (feature_set & family):
            missing.append(family_name)
    return missing


def validate_t2a_features(feature_names: list[str]) -> None:
    """Validate that a feature list contains only T2A-allowed features.

    Raises FeatureContaminationError if:
    - Feature list is empty
    - Any denied feature is present (including variants by normalization)
    - Any feature has SNOWPACK or station lineage
    - Required feature families (forcing + terrain) are not represented
    - Any unapproved feature is present
    """
    if not feature_names:
        raise FeatureContaminationError(
            "T2A feature list is empty; cannot validate an empty feature set"
        )
    feature_set = set(feature_names)

    # Check denylist with variant matching
    denied = _check_denylist_variants(feature_names, _T2A_DENYLIST_NORMALIZED)
    denied = list(set(denied))  # deduplicate
    if denied:
        raise FeatureContaminationError(
            f"T2A feature list contaminated with denied features (including variants): {sorted(denied)}"
        )

    # Check for unapproved features
    unknown = feature_set - T2A_ALLOWLIST
    if unknown:
        raise FeatureContaminationError(
            f"T2A feature list contains unapproved features: {sorted(unknown)}"
        )

    # Check minimum feature families
    missing_families = _check_feature_families(feature_set, [
        (T2A_FORCING_FEATURES, "open_forcing"),
        (T2A_TERRAIN_FEATURES, "terrain"),
    ])
    if missing_families:
        raise FeatureContaminationError(
            f"T2A feature list missing required feature families: {missing_families}"
        )


def validate_track1_features(feature_names: list[str]) -> None:
    """Validate that a feature list contains only Track 1-allowed features.

    Raises FeatureContaminationError if:
    - Feature list is empty
    - Any denied feature is present (including variants)
    - Required feature families (station + SNOWPACK) are not represented
    - Any unapproved feature is present
    """
    if not feature_names:
        raise FeatureContaminationError(
            "Track 1 feature list is empty; cannot validate an empty feature set"
        )
    feature_set = set(feature_names)

    # Check denylist with variant matching
    denied = _check_denylist_variants(feature_names, _TRACK1_DENYLIST_NORMALIZED)
    denied = list(set(denied))
    if denied:
        raise FeatureContaminationError(
            f"Track 1 feature list contaminated with denied features: {sorted(denied)}"
        )

    # Check for unapproved features
    unknown = feature_set - TRACK1_ALLOWLIST
    if unknown:
        raise FeatureContaminationError(
            f"Track 1 feature list contains unapproved features: {sorted(unknown)}"
        )

    # Check minimum feature families
    missing_families = _check_feature_families(feature_set, [
        (TRACK1_STATION_FEATURES, "station_anchor"),
        (TRACK1_SNOWPACK_FEATURES, "snowpack"),
    ])
    if missing_families:
        raise FeatureContaminationError(
            f"Track 1 feature list missing required feature families: {missing_families}"
        )


def check_no_overlap(t2a_features: list[str], track1_features: list[str]) -> None:
    """Verify that T2A and Track 1 feature sets are properly isolated.

    They MAY share terrain and context features, but must NOT share
    SNOWPACK or station features (T2A) or T2A-only temporal aggregations
    (Track 1). This is a HARD check — any contamination raises an error.

    Per Codex audit P5: overlap checking must be hard-fail, not soft.
    """
    t2a_set = set(t2a_features)
    track1_set = set(track1_features)
    # T2A must not contain Track 1 SNOWPACK/station features (hard fail)
    t2a_contamination = t2a_set & TRACK1_ALLOWLIST & T2A_DENYLIST
    if t2a_contamination:
        raise FeatureContaminationError(
            f"T2A contains Track 1 SNOWPACK/station features (hard fail): "
            f"{sorted(t2a_contamination)}"
        )
    # Track 1 must not contain T2A-only features (hard fail)
    track1_contamination = track1_set & T2A_ALLOWLIST & TRACK1_DENYLIST
    if track1_contamination:
        raise FeatureContaminationError(
            f"Track 1 contains T2A-only features (hard fail): "
            f"{sorted(track1_contamination)}"
        )
    # Check for cross-lane lineage contamination (renamed features)
    for feature in t2a_features:
        lineage = check_feature_lineage(feature)
        if lineage in ('snowpack', 'station'):
            raise FeatureContaminationError(
                f"T2A feature '{feature}' has {lineage} lineage (hard fail)"
            )
