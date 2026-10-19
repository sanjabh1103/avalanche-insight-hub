"""Tests for F20: eDMRG-Compatible Data Ingestion Adapter."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from backend.common.edmrg_adapter import (
    EdmrgRecord,
    edmrg_to_sequence_branches,
    edmrg_to_weather_samples,
    load_field_mapping,
    merge_cadences,
    parse_edmrg_csv,
    parse_edmrg_json,
)


MANNED_CSV = """station_id,obs_time,air_temp,snow_depth,new_snow_24h,wind_speed,wind_dir,precip_24h
ST001,2024-01-15 03:00:00,-5.2,120.0,8.0,12.5,270,2.3
ST001,2024-01-15 06:00:00,-6.1,125.0,5.0,10.0,280,1.5
ST001,2024-01-15 09:00:00,-7.0,128.0,3.0,8.0,290,0.8
"""

AWS_JSON = json.dumps([
    {"station_id": "ST001", "timestamp": "2024-01-15T03:00:00", "temp_2m": -5.0, "snow_depth": 120.0, "wind_speed_10m": 12.0, "wind_dir_10m": 275, "precip_1h": 0.5},
    {"station_id": "ST001", "timestamp": "2024-01-15T04:00:00", "temp_2m": -5.5, "snow_depth": 121.0, "wind_speed_10m": 11.0, "wind_dir_10m": 278, "precip_1h": 0.3},
    {"station_id": "ST001", "timestamp": "2024-01-15T05:00:00", "temp_2m": -5.8, "snow_depth": 122.0, "wind_speed_10m": 10.5, "wind_dir_10m": 282, "precip_1h": 0.2},
    {"station_id": "ST001", "timestamp": "2024-01-15T06:00:00", "temp_2m": -6.0, "snow_depth": 123.0, "wind_speed_10m": 10.0, "wind_dir_10m": 280, "precip_1h": 0.1},
])


@pytest.fixture
def mapping():
    return load_field_mapping()


@pytest.fixture
def terrain():
    return {
        'elevation_m': 3500.0,
        'slope_deg': 35.0,
        'aspect_deg': 270.0,
        'curvature_proxy': 0.3,
        'terrain_roughness': 0.5,
        'northness': 0.0,
        'eastness': -1.0,
    }


@pytest.fixture
def static_feature_row():
    return {
        'slope': 0.58,
        'elevation': 0.70,
        'aspect_loading': 0.65,
        'terrain_roughness': 0.50,
        'curvature_proxy': 0.30,
        'northness': 0.0,
        'eastness': -1.0,
        'ram_hardness': 0.45,
        'shear_strength': 0.30,
        'settlement_rate': 0.25,
    }


class TestLoadFieldMapping:
    def test_load_default_mapping(self):
        mapping = load_field_mapping()
        assert 'manned_3h' in mapping
        assert 'aws_1h' in mapping
        assert 'station_id' in mapping['manned_3h']
        assert 'timestamp' in mapping['manned_3h']
        assert 'temperature_c' in mapping['manned_3h']

    def test_load_custom_mapping(self, tmp_path):
        custom = {
            'manned_3h': {'station_id': 'stn', 'timestamp': 'ts', 'temperature_c': 't'},
            'aws_1h': {'station_id': 'stn', 'timestamp': 'ts', 'temperature_c': 't'},
        }
        path = tmp_path / 'custom_mapping.json'
        path.write_text(json.dumps(custom))
        result = load_field_mapping(path)
        assert result['manned_3h']['station_id'] == 'stn'

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_field_mapping('/nonexistent/path.json')

    def test_missing_cadence_raises(self, tmp_path):
        bad = {'manned_3h': {'station_id': 'stn'}}
        path = tmp_path / 'bad.json'
        path.write_text(json.dumps(bad))
        with pytest.raises(ValueError, match='aws_1h'):
            load_field_mapping(path)


class TestParseEdmrgCsv:
    def test_parse_manned_csv(self, mapping):
        records = parse_edmrg_csv(MANNED_CSV, mapping['manned_3h'], 'manned_3h')
        assert len(records) == 3
        assert records[0].station_id == 'ST001'
        assert records[0].cadence == 'manned_3h'
        assert records[0].fields['temperature_c'] == pytest.approx(-5.2)
        assert records[0].fields['snow_depth_cm'] == pytest.approx(120.0)
        assert records[0].fields['new_snow_cm'] == pytest.approx(8.0)
        assert records[0].timestamp == datetime(2024, 1, 15, 3, 0, 0, tzinfo=timezone.utc)

    def test_records_sorted_by_timestamp(self, mapping):
        csv_unsorted = """station_id,obs_time,air_temp,snow_depth,new_snow_24h,wind_speed,wind_dir,precip_24h
ST001,2024-01-15 09:00:00,-7.0,128.0,3.0,8.0,290,0.8
ST001,2024-01-15 03:00:00,-5.2,120.0,8.0,12.5,270,2.3
ST001,2024-01-15 06:00:00,-6.1,125.0,5.0,10.0,280,1.5
"""
        records = parse_edmrg_csv(csv_unsorted, mapping['manned_3h'], 'manned_3h')
        assert records[0].timestamp < records[1].timestamp < records[2].timestamp

    def test_empty_csv(self, mapping):
        csv_data = "station_id,obs_time,air_temp,snow_depth,new_snow_24h,wind_speed,wind_dir,precip_24h\n"
        records = parse_edmrg_csv(csv_data, mapping['manned_3h'], 'manned_3h')
        assert len(records) == 0

    def test_missing_timestamp_skipped(self, mapping):
        csv_data = """station_id,obs_time,air_temp,snow_depth,new_snow_24h,wind_speed,wind_dir,precip_24h
ST001,,-5.2,120.0,8.0,12.5,270,2.3
ST001,2024-01-15 06:00:00,-6.1,125.0,5.0,10.0,280,1.5
"""
        records = parse_edmrg_csv(csv_data, mapping['manned_3h'], 'manned_3h')
        assert len(records) == 1


class TestParseEdmrgJson:
    def test_parse_aws_json(self, mapping):
        records = parse_edmrg_json(AWS_JSON, mapping['aws_1h'], 'aws_1h')
        assert len(records) == 4
        assert records[0].cadence == 'aws_1h'
        assert records[0].fields['temperature_c'] == pytest.approx(-5.0)
        assert records[0].fields['wind_speed_ms'] == pytest.approx(12.0)

    def test_parse_json_bytes(self, mapping):
        records = parse_edmrg_json(AWS_JSON.encode('utf-8'), mapping['aws_1h'], 'aws_1h')
        assert len(records) == 4

    def test_parse_pre_parsed_list(self, mapping):
        data = json.loads(AWS_JSON)
        records = parse_edmrg_json(data, mapping['aws_1h'], 'aws_1h')
        assert len(records) == 4

    def test_invalid_json_raises(self, mapping):
        with pytest.raises(json.JSONDecodeError):
            parse_edmrg_json('{invalid}', mapping['aws_1h'], 'aws_1h')

    def test_non_array_raises(self, mapping):
        with pytest.raises(ValueError, match='array'):
            parse_edmrg_json('{"key": "val"}', mapping['aws_1h'], 'aws_1h')


class TestMergeCadences:
    def test_merge_manned_and_aws(self, mapping):
        manned = parse_edmrg_csv(MANNED_CSV, mapping['manned_3h'], 'manned_3h')
        aws = parse_edmrg_json(AWS_JSON, mapping['aws_1h'], 'aws_1h')
        merged = merge_cadences(manned, aws)
        # 3 manned + 4 aws, but 2 timestamps overlap (03:00 and 06:00)
        assert len(merged) == 5
        # Check that merged record at 03:00 has fields from both
        record_at_3 = next(r for r in merged if r.timestamp == datetime(2024, 1, 15, 3, 0, 0, tzinfo=timezone.utc))
        assert record_at_3.cadence == 'merged'
        # AWS should override temperature (finer cadence wins)
        assert record_at_3.fields['temperature_c'] == pytest.approx(-5.0)
        # Manned-only field new_snow_cm should be preserved
        assert record_at_3.fields['new_snow_cm'] == pytest.approx(8.0)

    def test_merge_empty_lists(self):
        merged = merge_cadences([], [])
        assert len(merged) == 0

    def test_merge_only_manned(self, mapping):
        manned = parse_edmrg_csv(MANNED_CSV, mapping['manned_3h'], 'manned_3h')
        merged = merge_cadences(manned, [])
        assert len(merged) == 3
        assert all(r.cadence == 'manned_3h' for r in merged)


class TestEdmrgToWeatherSamples:
    def test_field_mapping(self, mapping):
        records = parse_edmrg_csv(MANNED_CSV, mapping['manned_3h'], 'manned_3h')
        samples = edmrg_to_weather_samples(records)
        assert len(samples) == 3
        s = samples[0]
        assert 'temperature_2m' in s
        assert s['temperature_2m'] == pytest.approx(-5.2)
        assert 'windspeed_10m' in s
        assert s['windspeed_10m'] == pytest.approx(12.5)
        assert 'winddirection_10m' in s
        assert s['winddirection_10m'] == pytest.approx(270.0)
        assert 'snowfall_24h' in s
        assert s['snowfall_24h'] == pytest.approx(8.0)
        assert 'precipitation_24h' in s
        assert s['precipitation_24h'] == pytest.approx(2.3)
        # snow_depth_cm should be converted to meters
        assert 'snow_depth' in s
        assert s['snow_depth'] == pytest.approx(1.20)

    def test_empty_records(self):
        samples = edmrg_to_weather_samples([])
        assert len(samples) == 0


class TestEdmrgToSequenceBranches:
    def test_produces_valid_branches(self, mapping, terrain, static_feature_row):
        records = parse_edmrg_csv(MANNED_CSV, mapping['manned_3h'], 'manned_3h')
        branches = edmrg_to_sequence_branches(
            records,
            terrain=terrain,
            static_feature_row=static_feature_row,
            zone_type='pir_panjal',
        )
        assert branches.hourly.shape == (24, 6)  # 24 hourly steps, 6 dynamic features
        assert branches.daily.shape == (7, 6)  # 7 daily steps, 6 dynamic features
        assert branches.static.shape == (14,)  # 10 static + 4 zone one-hot

    def test_zone_onehot(self, mapping, terrain, static_feature_row):
        records = parse_edmrg_csv(MANNED_CSV, mapping['manned_3h'], 'manned_3h')
        branches = edmrg_to_sequence_branches(
            records,
            terrain=terrain,
            static_feature_row=static_feature_row,
            zone_type='karakoram_ladakh',
        )
        # Last 4 elements of static are zone one-hot
        zone_vec = branches.static[-4:]
        assert zone_vec[3] == 1.0  # karakoram_ladakh is index 3
        assert zone_vec[0] == 0.0
        assert zone_vec[1] == 0.0
        assert zone_vec[2] == 0.0

    def test_no_zone(self, mapping, terrain, static_feature_row):
        records = parse_edmrg_csv(MANNED_CSV, mapping['manned_3h'], 'manned_3h')
        branches = edmrg_to_sequence_branches(
            records,
            terrain=terrain,
            static_feature_row=static_feature_row,
            zone_type=None,
        )
        zone_vec = branches.static[-4:]
        assert np.all(zone_vec == 0.0)

    def test_empty_records_produces_valid_shapes(self, terrain, static_feature_row):
        branches = edmrg_to_sequence_branches(
            [],
            terrain=terrain,
            static_feature_row=static_feature_row,
        )
        assert branches.hourly.shape == (24, 6)
        assert branches.daily.shape == (7, 6)
        # Weather-dependent fields (snowfall, precip, wind_loading) should be 0.0
        # Terrain-derived fields (wind_directional_loading, temp_gradient, freezing_level_proxy)
        # may be non-zero from _dynamic_feature_snapshot even with empty samples.
        assert np.all(branches.hourly[:, 0] == 0.0)  # snowfall_24h
        assert np.all(branches.hourly[:, 1] == 0.0)  # precipitation_24h
        assert np.all(branches.hourly[:, 2] == 0.0)  # wind_loading


class TestMissingFieldsHandling:
    def test_unknown_fields_ignored(self, mapping):
        csv_with_extra = """station_id,obs_time,air_temp,snow_depth,new_snow_24h,wind_speed,wind_dir,precip_24h,unknown_field
ST001,2024-01-15 03:00:00,-5.2,120.0,8.0,12.5,270,2.3,999
"""
        records = parse_edmrg_csv(csv_with_extra, mapping['manned_3h'], 'manned_3h')
        assert 'unknown_field' not in records[0].fields

    def test_missing_column_defaults_to_zero(self, mapping):
        csv_missing_col = """station_id,obs_time,air_temp,snow_depth,wind_speed,wind_dir,precip_24h
ST001,2024-01-15 03:00:00,-5.2,120.0,12.5,270,2.3
"""
        records = parse_edmrg_csv(csv_missing_col, mapping['manned_3h'], 'manned_3h')
        # new_snow_cm column missing → field absent (not zero, just absent)
        assert 'new_snow_cm' not in records[0].fields
        # But weather_samples should handle it gracefully
        samples = edmrg_to_weather_samples(records)
        assert 'snowfall_24h' not in samples[0]  # unmapped, so absent

    def test_empty_string_value_skipped(self, mapping):
        csv_empty_val = """station_id,obs_time,air_temp,snow_depth,new_snow_24h,wind_speed,wind_dir,precip_24h
ST001,2024-01-15 03:00:00,,120.0,8.0,12.5,270,2.3
"""
        records = parse_edmrg_csv(csv_empty_val, mapping['manned_3h'], 'manned_3h')
        assert 'temperature_c' not in records[0].fields
