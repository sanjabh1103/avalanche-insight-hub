#!/usr/bin/env python3
"""Demo: MTS-LSTM with ZoneAttentionGate training on CPU with synthetic data.

Generates synthetic sequence data with zone labels, instantiates BranchedMTSLSTM,
trains for 3 epochs, saves model weights, and verifies ZoneAttentionGate produces
different outputs for different zones.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import numpy as np

# Ensure torch is available
try:
    import torch
    import torch.nn as nn
except ImportError:
    print('ERROR: torch not installed. Install with: pip install torch')
    sys.exit(1)

from backend.models.mts_lstm import BranchedMTSLSTM, ZoneAttentionGate


HOURLY_FEATURES = 6   # temp, snowfall, wind_speed, wind_dir, radiation, humidity
DAILY_FEATURES = 4    # max_temp, min_temp, total_snowfall, avg_wind
STATIC_FEATURES = 3   # elevation, slope, aspect
ZONE_DIM = 4          # pir_panjal, shamshabari, great_himalaya, karakoram_ladakh
HOURLY_STEPS = 24
DAILY_STEPS = 7


def generate_synthetic_batch(
    n_samples: int,
    zone_idx: int,
    positive_ratio: float = 0.2,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    """Generate synthetic (hourly, daily, static, zone_onehot, label) batch."""
    hourly = torch.randn(n_samples, HOURLY_STEPS, HOURLY_FEATURES)
    daily = torch.randn(n_samples, DAILY_STEPS, DAILY_FEATURES)
    static = torch.randn(n_samples, STATIC_FEATURES)

    zone_onehot = torch.zeros(n_samples, ZONE_DIM)
    zone_onehot[:, zone_idx] = 1.0

    # Labels: make zone-specific patterns (some zones more avalanche-prone)
    base_prob = [0.15, 0.20, 0.30, 0.25][zone_idx]
    noise = torch.randn(n_samples) * 0.5
    logits = base_prob + noise + hourly[:, -1, 0] * 0.1  # temp influence
    labels = (torch.sigmoid(logits) > 0.5).float()

    return hourly, daily, static, zone_onehot, labels


def main() -> int:
    os.environ.setdefault('MTS_LSTM_EPOCHS', '3')
    epochs = int(os.environ.get('MTS_LSTM_EPOCHS', '3'))
    torch.manual_seed(42)
    np.random.seed(42)

    print('=== MTS-LSTM CPU Training Demo with ZoneAttentionGate ===\n')

    # Build model
    model = BranchedMTSLSTM(
        hourly_input_size=HOURLY_FEATURES,
        daily_input_size=DAILY_FEATURES,
        static_input_size=STATIC_FEATURES,
        dropout=0.15,
        zone_dim=ZONE_DIM,
    )
    print(f'Model created: {sum(p.numel() for p in model.parameters())} parameters')
    print(f'  hourly_lstm: {model.hourly_lstm}')
    print(f'  daily_lstm: {model.daily_lstm}')
    print(f'  zone_gate: {model.zone_gate}')

    # Generate training data from all 4 zones
    all_hourly, all_daily, all_static, all_zone, all_labels = [], [], [], [], []
    for z in range(ZONE_DIM):
        n = 60 if z < 2 else 80  # varying sample counts
        h, d, s, zoh, lbl = generate_synthetic_batch(n, z)
        all_hourly.append(h)
        all_daily.append(d)
        all_static.append(s)
        all_zone.append(zoh)
        all_labels.append(lbl)

    train_hourly = torch.cat(all_hourly)
    train_daily = torch.cat(all_daily)
    train_static = torch.cat(all_static)
    train_zone = torch.cat(all_zone)
    train_labels = torch.cat(all_labels)

    n_pos = int(train_labels.sum().item())
    n_neg = len(train_labels) - n_pos
    print(f'\nTraining data: {len(train_labels)} samples ({n_pos} positive, {n_neg} negative)')

    # Generate validation data
    val_hourly, val_daily, val_static, val_zone, val_labels = generate_synthetic_batch(50, 2)
    print(f'Validation data: {len(val_labels)} samples')

    # Training loop
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    pos_weight = torch.tensor([n_neg / max(n_pos, 1)])
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    print(f'\nTraining for {epochs} epochs...')
    for epoch in range(epochs):
        model.train()
        optimizer.zero_grad()
        logits = model(train_hourly, train_daily, train_static, train_zone)
        loss = criterion(logits, train_labels)
        loss.backward()
        optimizer.step()

        # Validation
        model.eval()
        with torch.no_grad():
            val_logits = model(val_hourly, val_daily, val_static, val_zone)
            val_loss = criterion(val_logits, val_labels)
            val_preds = (torch.sigmoid(val_logits) > 0.5).float()
            val_acc = (val_preds == val_labels).float().mean().item()

        print(f'  Epoch {epoch+1}/{epochs}: train_loss={loss.item():.4f} val_loss={val_loss.item():.4f} val_acc={val_acc:.3f}')

    # Verify ZoneAttentionGate produces different weights for different zones
    print('\n=== ZoneAttentionGate Verification ===\n')
    model.eval()
    with torch.no_grad():
        for z in range(ZONE_DIM):
            zoh = torch.zeros(1, ZONE_DIM)
            zoh[0, z] = 1.0
            weights = model.get_attention_weights(zoh)
            zone_names = ['pir_panjal', 'shamshabari', 'great_himalaya', 'karakoram_ladakh']
            print(f'  {zone_names[z]:20s}: hourly_weight={weights[0,0]:.4f} daily_weight={weights[0,1]:.4f}')

    # Save model weights
    with tempfile.TemporaryDirectory() as tmpdir:
        weights_path = Path(tmpdir) / 'mts_lstm_demo_weights.pt'
        torch.save(model.state_dict(), str(weights_path))
        print(f'\nModel weights saved to {weights_path} ({weights_path.stat().st_size} bytes)')

        # Verify weights can be loaded
        model2 = BranchedMTSLSTM(
            hourly_input_size=HOURLY_FEATURES,
            daily_input_size=DAILY_FEATURES,
            static_input_size=STATIC_FEATURES,
            zone_dim=ZONE_DIM,
        )
        model2.load_state_dict(torch.load(str(weights_path), weights_only=True))
        model2.eval()
        with torch.no_grad():
            test_h = torch.randn(1, HOURLY_STEPS, HOURLY_FEATURES)
            test_d = torch.randn(1, DAILY_STEPS, DAILY_FEATURES)
            test_s = torch.randn(1, STATIC_FEATURES)
            test_z = torch.zeros(1, ZONE_DIM)
            test_z[0, 2] = 1.0  # great_himalaya
            out1 = model(test_h, test_d, test_s, test_z)
            out2 = model2(test_h, test_d, test_s, test_z)
            diff = (out1 - out2).abs().max().item()
            print(f'Weight reload verification: max diff = {diff:.8f} {"PASS" if diff < 1e-5 else "FAIL"}')

    # Verify state_dict has zone_attention parameters
    state_dict = model.state_dict()
    zone_params = [k for k in state_dict if 'zone' in k.lower()]
    print(f'\nZoneAttentionGate parameters in state_dict: {zone_params}')
    if not zone_params:
        print('FAIL: No zone_attention parameters found in state_dict')
        return 1
    print('PASS: ZoneAttentionGate parameters present in model')

    # Verify different zones produce different outputs
    with torch.no_grad():
        test_h = torch.randn(1, HOURLY_STEPS, HOURLY_FEATURES)
        test_d = torch.randn(1, DAILY_STEPS, DAILY_FEATURES)
        test_s = torch.randn(1, STATIC_FEATURES)
        outputs = []
        for z in range(ZONE_DIM):
            zoh = torch.zeros(1, ZONE_DIM)
            zoh[0, z] = 1.0
            out = model(test_h, test_d, test_s, zoh)
            outputs.append(out.item())
        print(f'\nZone-specific outputs for same input: {[f"{o:.4f}" for o in outputs]}')
        if len(set(f'{o:.4f}' for o in outputs)) > 1:
            print('PASS: Different zones produce different outputs')
        else:
            print('WARN: All zones produce identical outputs (may need more training)')

    print('\n=== Demo Complete ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
