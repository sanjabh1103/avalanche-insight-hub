"""Tests for F2 Regional Attention MTS-LSTM zone one-hot and attention gate."""

from __future__ import annotations

import numpy as np
import pytest

from backend.common.sequence_features import (
    STATIC_SEQUENCE_FEATURES,
    ZONE_ONEHOT_FEATURES,
    ZONE_TYPES,
    extract_zone_onehot,
)


# ---------------------------------------------------------------------------
# Zone one-hot tests
# ---------------------------------------------------------------------------


class TestExtractZoneOnehot:
    def test_valid_zone_pir_panjal(self):
        vec = extract_zone_onehot('pir_panjal')
        assert vec.shape == (4,)
        assert vec[0] == 1.0
        assert vec[1] == 0.0
        assert vec[2] == 0.0
        assert vec[3] == 0.0

    def test_valid_zone_shamshabari(self):
        vec = extract_zone_onehot('shamshabari')
        assert vec[1] == 1.0
        assert vec.sum() == 1.0

    def test_valid_zone_great_himalaya(self):
        vec = extract_zone_onehot('great_himalaya')
        assert vec[2] == 1.0
        assert vec.sum() == 1.0

    def test_valid_zone_karakoram_ladakh(self):
        vec = extract_zone_onehot('karakoram_ladakh')
        assert vec[3] == 1.0
        assert vec.sum() == 1.0

    def test_none_returns_zeros(self):
        vec = extract_zone_onehot(None)
        assert vec.shape == (4,)
        assert vec.sum() == 0.0

    def test_unknown_zone_returns_zeros(self):
        vec = extract_zone_onehot('unknown_zone')
        assert vec.sum() == 0.0

    def test_all_zones_covered(self):
        for zt in ZONE_TYPES:
            vec = extract_zone_onehot(zt)
            assert vec.sum() == 1.0

    def test_dtype_float32(self):
        vec = extract_zone_onehot('pir_panjal')
        assert vec.dtype == np.float32


# ---------------------------------------------------------------------------
# Zone one-hot in sequence features
# ---------------------------------------------------------------------------


class TestZoneOnehotInFeatures:
    def test_zone_types_count(self):
        assert len(ZONE_TYPES) == 4

    def test_zone_onehot_features_count(self):
        assert len(ZONE_ONEHOT_FEATURES) == 4

    def test_static_features_unchanged(self):
        """Base static features should not include zone one-hot."""
        for zf in ZONE_ONEHOT_FEATURES:
            assert zf not in STATIC_SEQUENCE_FEATURES


# ---------------------------------------------------------------------------
# ZoneAttentionGate model tests (requires torch)
# ---------------------------------------------------------------------------


torch = pytest.importorskip('torch')


class TestZoneAttentionGate:
    def test_gate_output_shape(self):
        from backend.models.mts_lstm import ZoneAttentionGate
        gate = ZoneAttentionGate(zone_dim=4)
        zone = torch.zeros(1, 4)
        zone[0, 0] = 1.0  # pir_panjal
        out = gate(zone)
        assert out.shape == (1, 2)

    def test_gate_softmax_weights_sum_to_one(self):
        from backend.models.mts_lstm import ZoneAttentionGate
        gate = ZoneAttentionGate(zone_dim=4)
        zone = torch.randn(8, 4)
        out = gate(zone)
        sums = out.sum(dim=-1)
        assert torch.allclose(sums, torch.ones(8), atol=1e-5)

    def test_gate_weights_non_negative(self):
        from backend.models.mts_lstm import ZoneAttentionGate
        gate = ZoneAttentionGate(zone_dim=4)
        zone = torch.randn(16, 4)
        out = gate(zone)
        assert (out >= 0).all()


class TestBranchedMTSLSTMWithZone:
    def test_forward_with_zone_onehot(self):
        from backend.models.mts_lstm import BranchedMTSLSTM
        model = BranchedMTSLSTM(
            hourly_input_size=6,
            daily_input_size=6,
            static_input_size=10,
            dropout=0.0,
            zone_dim=4,
        )
        hourly = torch.randn(4, 24, 6)
        daily = torch.randn(4, 7, 6)
        static = torch.randn(4, 14)  # 10 base + 4 zone
        zone = torch.zeros(4, 4)
        zone[:, 0] = 1.0
        out = model(hourly, daily, static, zone_onehot=zone)
        assert out.shape == (4,)

    def test_forward_without_zone_onehot(self):
        from backend.models.mts_lstm import BranchedMTSLSTM
        model = BranchedMTSLSTM(
            hourly_input_size=6,
            daily_input_size=6,
            static_input_size=10,
            dropout=0.0,
            zone_dim=4,
        )
        hourly = torch.randn(2, 24, 6)
        daily = torch.randn(2, 7, 6)
        static = torch.randn(2, 14)  # 10 base + 4 zone concatenated
        out = model(hourly, daily, static, zone_onehot=None)
        assert out.shape == (2,)

    def test_forward_with_base_static_only(self):
        """Backward compatibility: static with only 10 features (no zone)."""
        from backend.models.mts_lstm import BranchedMTSLSTM
        model = BranchedMTSLSTM(
            hourly_input_size=6,
            daily_input_size=6,
            static_input_size=10,
            dropout=0.0,
            zone_dim=4,
        )
        hourly = torch.randn(2, 24, 6)
        daily = torch.randn(2, 7, 6)
        static = torch.randn(2, 10)  # Only base features
        out = model(hourly, daily, static, zone_onehot=None)
        assert out.shape == (2,)

    def test_get_attention_weights(self):
        from backend.models.mts_lstm import BranchedMTSLSTM
        model = BranchedMTSLSTM(
            hourly_input_size=6,
            daily_input_size=6,
            static_input_size=10,
            dropout=0.0,
            zone_dim=4,
        )
        zone = torch.zeros(3, 4)
        zone[:, 1] = 1.0  # shamshabari
        weights = model.get_attention_weights(zone)
        assert weights.shape == (3, 2)
        assert torch.allclose(weights.sum(dim=-1), torch.ones(3), atol=1e-5)

    def test_different_zones_produce_different_outputs(self):
        from backend.models.mts_lstm import BranchedMTSLSTM
        model = BranchedMTSLSTM(
            hourly_input_size=6,
            daily_input_size=6,
            static_input_size=10,
            dropout=0.0,
            zone_dim=4,
        )
        model.eval()  # Disable dropout for deterministic test
        hourly = torch.randn(1, 24, 6)
        daily = torch.randn(1, 7, 6)
        static = torch.randn(1, 14)

        zone_a = torch.zeros(1, 4)
        zone_a[0, 0] = 1.0
        zone_b = torch.zeros(1, 4)
        zone_b[0, 1] = 1.0

        with torch.no_grad():
            out_a = model(hourly, daily, static, zone_onehot=zone_a)
            out_b = model(hourly, daily, static, zone_onehot=zone_b)

        # Different zones should produce different gate weights → different outputs
        assert not torch.allclose(out_a, out_b, atol=1e-6)
