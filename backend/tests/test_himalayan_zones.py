"""Unit tests for F17: Himalayan Region Configuration.

Verifies that:
- 4 Himalayan regions load from regions.json with correct bboxes
- Zone overrides load from TOML and have correct parameter values
- get_zone_override() returns correct values per zone_type
- Fallback to empty dict when zone_type is None or not found
- Zone-specific lapse rate is applied via fallback_lapse_rate
- Zone-specific season start is applied via winter_season_start
- Existing 8 regions still load without zone metadata (backward compat)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.common.regions import (
    Region,
    get_zone_override,
    load_regions,
    repo_root,
)
from backend.common.snowpack_proxy import winter_season_start
from backend.common.snowpack_physics import load_zone_overrides


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def regions() -> list[Region]:
    return load_regions()


@pytest.fixture
def himalayan_regions(regions: list[Region]) -> list[Region]:
    return [r for r in regions if r.zone_type is not None]


@pytest.fixture
def zone_overrides() -> dict:
    overrides_path = repo_root() / 'config' / 'himalayan_zone_overrides.toml'
    import tomllib
    with overrides_path.open('rb') as f:
        return tomllib.load(f)


# ---------------------------------------------------------------------------
# regions.json tests
# ---------------------------------------------------------------------------

class TestRegionsJson:
    def test_total_region_count(self, regions: list[Region]) -> None:
        assert len(regions) == 12, f"Expected 12 regions, got {len(regions)}"

    def test_himalayan_region_count(self, himalayan_regions: list[Region]) -> None:
        assert len(himalayan_regions) == 5, f"Expected 5 Himalayan zones, got {len(himalayan_regions)}"

    def test_existing_regions_have_no_zone_type(self, regions: list[Region]) -> None:
        existing = [r for r in regions if r.zone_type is None]
        assert len(existing) == 7, f"Expected 7 existing regions without zone_type, got {len(existing)}"

    @pytest.mark.parametrize("name,zone_type,climate_class", [
        ("Pir Panjal (NW Himalaya)", "pir_panjal", "maritime"),
        ("Shamshabari (NW Himalaya)", "shamshabari", "transition"),
        ("Great Himalaya (NW Himalaya)", "great_himalaya", "continental"),
        ("Karakoram & Ladakh", "karakoram_ladakh", "polar_dry"),
    ])
    def test_himalayan_zone_metadata(
        self, himalayan_regions: list[Region], name: str, zone_type: str, climate_class: str,
    ) -> None:
        region = next(r for r in himalayan_regions if r.name == name)
        assert region.zone_type == zone_type
        assert region.climate_class == climate_class

    @pytest.mark.parametrize("name,bbox_expected", [
        ("Pir Panjal (NW Himalaya)", (33.0, 73.5, 35.0, 75.5)),
        ("Shamshabari (NW Himalaya)", (34.0, 74.5, 35.5, 76.0)),
        ("Great Himalaya (NW Himalaya)", (34.5, 75.5, 36.5, 78.0)),
        ("Karakoram & Ladakh", (34.5, 76.5, 36.5, 79.0)),
    ])
    def test_himalayan_bboxes(
        self, himalayan_regions: list[Region], name: str, bbox_expected: tuple,
    ) -> None:
        region = next(r for r in himalayan_regions if r.name == name)
        assert tuple(region.bbox) == bbox_expected

    def test_all_himalayan_regions_have_elevation_metadata(
        self, himalayan_regions: list[Region],
    ) -> None:
        for r in himalayan_regions:
            assert r.elevation_min is not None, f"{r.name} missing elevation_min"
            assert r.elevation_max is not None, f"{r.name} missing elevation_max"
            assert r.elevation_max > r.elevation_min, f"{r.name} elevation_max <= elevation_min"

    def test_all_himalayan_regions_have_season_start(
        self, himalayan_regions: list[Region],
    ) -> None:
        for r in himalayan_regions:
            assert r.season_start is not None, f"{r.name} missing season_start"

    def test_all_himalayan_regions_have_lapse_rate(
        self, himalayan_regions: list[Region],
    ) -> None:
        for r in himalayan_regions:
            assert r.lapse_rate_c_per_m is not None, f"{r.name} missing lapse_rate_c_per_m"
            assert r.lapse_rate_c_per_m < 0, f"{r.name} lapse rate should be negative"

    def test_karakoram_season_starts_earlier(
        self, himalayan_regions: list[Region],
    ) -> None:
        karakoram = next(r for r in himalayan_regions if r.zone_type == "karakoram_ladakh")
        assert karakoram.season_start == "10-15", f"Karakoram season_start should be 10-15, got {karakoram.season_start}"

    def test_all_himalayan_timezones_are_kolkata(
        self, himalayan_regions: list[Region],
    ) -> None:
        for r in himalayan_regions:
            # Nepal uses Kathmandu; NW Himalayan zones use Kolkata
            assert r.timezone_name in ("Asia/Kolkata", "Asia/Kathmandu"), f"{r.name} timezone should be Asia/Kolkata or Asia/Kathmandu, got {r.timezone_name}"

    def test_regions_json_is_valid(self) -> None:
        regions_path = repo_root() / 'config' / 'regions.json'
        data = json.loads(regions_path.read_text(encoding='utf-8'))
        assert isinstance(data, list)
        assert len(data) == 12


# ---------------------------------------------------------------------------
# Zone overrides TOML tests
# ---------------------------------------------------------------------------

class TestZoneOverrides:
    def test_override_sections_exist(self, zone_overrides: dict) -> None:
        expected = {'pir_panjal', 'shamshabari', 'great_himalaya', 'karakoram_ladakh'}
        assert set(zone_overrides.keys()) == expected

    @pytest.mark.parametrize("zone_type,aging,density_top", [
        ("pir_panjal", 22, 300.0),
        ("shamshabari", 14, 280.0),
        ("great_himalaya", 8, 250.0),
        ("karakoram_ladakh", 6, 220.0),
    ])
    def test_albedo_aging_decreases_inland(
        self, zone_overrides: dict, zone_type: str, aging: int, density_top: float,
    ) -> None:
        section = zone_overrides[zone_type]
        assert section['albedo_mod_snow_aging'] == aging
        assert section['initial_top_density_snowpack'] == density_top

    def test_karakoram_has_coldest_temperature(self, zone_overrides: dict) -> None:
        temps = {z: zone_overrides[z]['temperature_bottom'] for z in zone_overrides}
        assert min(temps, key=temps.get) == 'karakoram_ladakh'
        assert temps['karakoram_ladakh'] == 248.35

    def test_karakoram_has_highest_dry_t_star(self, zone_overrides: dict) -> None:
        t_stars = {z: zone_overrides[z]['t_star_dry'] for z in zone_overrides}
        assert max(t_stars, key=t_stars.get) == 'karakoram_ladakh'
        assert t_stars['karakoram_ladakh'] == 50


# ---------------------------------------------------------------------------
# get_zone_override() tests
# ---------------------------------------------------------------------------

class TestGetZoneOverride:
    def test_returns_overrides_for_known_zone(self, himalayan_regions: list[Region]) -> None:
        karakoram = next(r for r in himalayan_regions if r.zone_type == "karakoram_ladakh")
        overrides = get_zone_override(karakoram)
        assert overrides != {}
        assert overrides['albedo_mod_snow_aging'] == 6
        assert overrides['initial_bottom_density_snowpack'] == 800.0

    def test_returns_empty_for_no_zone_type(self, regions: list[Region]) -> None:
        colorado = next(r for r in regions if r.name == "Colorado Rockies")
        overrides = get_zone_override(colorado)
        assert overrides == {}

    def test_returns_empty_for_unknown_zone_type(self) -> None:
        unknown = Region(
            name="Test Region",
            bbox=(0, 0, 1, 1),
            center=(0.5, 0.5),
            zoom=1,
            zone_type="nonexistent_zone",
        )
        overrides = get_zone_override(unknown)
        assert overrides == {}


# ---------------------------------------------------------------------------
# snowpack_physics.load_zone_overrides() tests
# ---------------------------------------------------------------------------

class TestSnowpackPhysicsZoneOverrides:
    def test_load_zone_overrides_none_returns_empty(self) -> None:
        assert load_zone_overrides(None) == {}

    def test_load_zone_overrides_unknown_returns_empty(self) -> None:
        assert load_zone_overrides("nonexistent") == {}

    def test_load_zone_overrides_karakoram(self) -> None:
        overrides = load_zone_overrides("karakoram_ladakh")
        assert overrides != {}
        assert overrides['albedo_mod_snow_aging'] == 6
        assert overrides['temperature_bottom'] == 248.35


# ---------------------------------------------------------------------------
# winter_season_start() zone-aware tests
# ---------------------------------------------------------------------------

class TestWinterSeasonStart:
    def test_default_nov1_for_january(self) -> None:
        as_of = datetime(2025, 1, 15, tzinfo=timezone.utc)
        result = winter_season_start(as_of)
        assert result.month == 11
        assert result.day == 1
        assert result.year == 2024

    def test_default_nov1_for_december(self) -> None:
        as_of = datetime(2025, 12, 15, tzinfo=timezone.utc)
        result = winter_season_start(as_of)
        assert result.month == 11
        assert result.day == 1
        assert result.year == 2025

    def test_zone_specific_oct15_for_december(self) -> None:
        as_of = datetime(2025, 12, 15, tzinfo=timezone.utc)
        result = winter_season_start(as_of, season_start_str="10-15")
        assert result.month == 10
        assert result.day == 15
        assert result.year == 2025

    def test_zone_specific_oct15_for_september(self) -> None:
        as_of = datetime(2025, 9, 15, tzinfo=timezone.utc)
        result = winter_season_start(as_of, season_start_str="10-15")
        assert result.month == 10
        assert result.day == 15
        assert result.year == 2024

    def test_invalid_season_start_falls_back_to_nov1(self) -> None:
        as_of = datetime(2025, 1, 15, tzinfo=timezone.utc)
        result = winter_season_start(as_of, season_start_str="invalid")
        assert result.month == 11
        assert result.day == 1

    def test_backward_compat_no_season_start_str(self) -> None:
        as_of = datetime(2025, 6, 15, tzinfo=timezone.utc)
        result = winter_season_start(as_of)
        assert result.month == 11
        assert result.day == 1
        assert result.year == 2024


# ---------------------------------------------------------------------------
# compute_dynamic_lapse_profile fallback_lapse_rate tests
# ---------------------------------------------------------------------------

class TestLapseRateFallback:
    def test_fallback_lapse_rate_used_when_no_pressure_levels(self) -> None:
        from backend.common.real_features import compute_dynamic_lapse_profile
        profile = {'temperature_2m': 5.0}
        result = compute_dynamic_lapse_profile(profile, 4000.0, fallback_lapse_rate=-0.0050)
        assert result['lapse_rate_c_per_m'] == -0.0050
        assert result['method'] == 'fallback_standard_lapse'

    def test_default_lapse_rate_when_no_fallback(self) -> None:
        from backend.common.real_features import compute_dynamic_lapse_profile
        from backend.common.real_features import STANDARD_LAPSE_RATE_C_PER_M
        profile = {'temperature_2m': 5.0}
        result = compute_dynamic_lapse_profile(profile, 4000.0)
        assert result['lapse_rate_c_per_m'] == STANDARD_LAPSE_RATE_C_PER_M


# ---------------------------------------------------------------------------
# Backward compatibility tests
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_existing_regions_load_without_zone_fields(self, regions: list[Region]) -> None:
        colorado = next(r for r in regions if r.name == "Colorado Rockies")
        assert colorado.zone_type is None
        assert colorado.climate_class is None
        assert colorado.elevation_min is None
        assert colorado.elevation_max is None
        assert colorado.season_start is None
        assert colorado.lapse_rate_c_per_m is None

    def test_existing_region_key_still_works(self, regions: list[Region]) -> None:
        colorado = next(r for r in regions if r.name == "Colorado Rockies")
        assert colorado.key == 'colorado_rockies'

    def test_himalayan_region_key_generation(self, himalayan_regions: list[Region]) -> None:
        karakoram = next(r for r in himalayan_regions if r.name == "Karakoram & Ladakh")
        assert karakoram.key == 'karakoram_&_ladakh'
