#!/usr/bin/env python3
"""Demo: mSAFE 6-channel SAR avalanche detection pipeline.

Simulates the mSAFE algorithm (multi-channel Sentinel-1 SAR change detection)
using synthetic SAR backscatter data. The mSAFE algorithm processes 6 channels:
  - VV pre-event, VH pre-event, VV co-event, VH co-event, VV post-event, VH post-event

Produces a binary avalanche detection mask with confidence scores.
Based on: Negi et al. (2024) mSAFE algorithm for space-borne debris segmentation.
"""
from __future__ import annotations

import sys
import numpy as np


def generate_synthetic_sar_scene(
    size: int = 100,
    n_avalanche_zones: int = 3,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate synthetic 6-channel SAR data and ground truth mask.

    Returns:
        (sar_6ch, mask) where sar_6ch is (6, H, W) and mask is (H, W) binary
    """
    rng = np.random.RandomState(seed)
    # Base backscatter (rough terrain)
    base = rng.randn(size, size) * 2.0 + -10.0  # dB, ~-10 ± 2

    # Create avalanche zones (circular regions with backscatter change)
    mask = np.zeros((size, size), dtype=np.float32)
    zones = []
    for _ in range(n_avalanche_zones):
        cx, cy = rng.randint(20, size - 20, size=2)
        radius = rng.randint(5, 15)
        y, x = np.ogrid[:size, :size]
        zone = ((x - cx) ** 2 + (y - cy) ** 2) <= radius ** 2
        mask[zone] = 1.0
        zones.append((cx, cy, radius))

    # Pre-event: stable backscatter
    vv_pre = base + rng.randn(size, size) * 0.5
    vh_pre = base - 3.0 + rng.randn(size, size) * 0.5  # VH ~3dB lower

    # Co-event: significant change in avalanche zones
    change_vv = np.zeros((size, size), dtype=np.float32)
    change_vh = np.zeros((size, size), dtype=np.float32)
    for cx, cy, radius in zones:
        y, x = np.ogrid[:size, :size]
        zone = ((x - cx) ** 2 + (y - cy) ** 2) <= radius ** 2
        change_vv[zone] = -4.0 + rng.randn(int(zone.sum())) * 0.8  # ~4dB drop
        change_vh[zone] = -5.0 + rng.randn(int(zone.sum())) * 0.8

    vv_co = vv_pre + change_vv + rng.randn(size, size) * 0.3
    vh_co = vh_pre + change_vh + rng.randn(size, size) * 0.3

    # Post-event: partial recovery
    vv_post = vv_pre + change_vv * 0.5 + rng.randn(size, size) * 0.4
    vh_post = vh_pre + change_vh * 0.5 + rng.randn(size, size) * 0.4

    sar_6ch = np.stack([vv_pre, vh_pre, vv_co, vh_co, vv_post, vh_post], axis=0)
    return sar_6ch.astype(np.float32), mask


def msafe_detect(
    sar_6ch: np.ndarray,
    threshold_db: float = -3.0,
    min_cluster_pixels: int = 10,
) -> tuple[np.ndarray, np.ndarray]:
    """Run mSAFE detection on 6-channel SAR data.

    Algorithm:
    1. Compute VV and VH change ratios (co-event / pre-event)
    2. Compute combined change index
    3. Threshold to get binary detection
    4. Filter small clusters

    Returns:
        (detection_mask, confidence_map)
    """
    vv_pre = sar_6ch[0]
    vh_pre = sar_6ch[1]
    vv_co = sar_6ch[2]
    vh_co = sar_6ch[3]

    # Change ratios in dB
    vv_change = vv_co - vv_pre
    vh_change = vh_co - vh_pre

    # Combined change index (normalized)
    combined = (vv_change + vh_change) / 2.0

    # Confidence: sigmoid of negative change (more negative = more likely avalanche)
    confidence = 1.0 / (1.0 + np.exp(combined + 2.0))

    # Binary detection
    detection = (combined < threshold_db).astype(np.float32)

    # Simple cluster filtering: count connected pixels
    # (Simplified: just check pixel count in detection)
    n_detected = int(detection.sum())
    if n_detected < min_cluster_pixels:
        detection = np.zeros_like(detection)
        print(f'  [mSAFE] Detection rejected: only {n_detected} pixels (< {min_cluster_pixels})')

    return detection, confidence


def main() -> int:
    print('=== mSAFE 6-Channel SAR Avalanche Detection Demo ===\n')

    # Generate synthetic SAR data
    sar_6ch, ground_truth = generate_synthetic_sar_scene(size=100, n_avalanche_zones=3, seed=42)
    print(f'Generated synthetic SAR data: shape={sar_6ch.shape} (6 channels, 100x100)')
    print(f'Channels: VV_pre, VH_pre, VV_co, VH_co, VV_post, VH_post')
    print(f'Ground truth: {int(ground_truth.sum())} avalanche pixels')

    # Run mSAFE detection
    print('\nRunning mSAFE detection algorithm...')
    detection, confidence = msafe_detect(sar_6ch, threshold_db=-3.0, min_cluster_pixels=10)
    n_detected = int(detection.sum())
    print(f'Detection result: {n_detected} pixels detected')

    # Compute metrics
    tp = int((detection * ground_truth).sum())
    fp = int((detection * (1 - ground_truth)).sum())
    fn = int(((1 - detection) * ground_truth).sum())
    tn = int(((1 - detection) * (1 - ground_truth)).sum())

    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-6)
    iou = tp / max(tp + fp + fn, 1)

    print(f'\nDetection metrics:')
    print(f'  True Positives:  {tp}')
    print(f'  False Positives: {fp}')
    print(f'  False Negatives: {fn}')
    print(f'  True Negatives:  {tn}')
    print(f'  Precision: {precision:.3f}')
    print(f'  Recall:    {recall:.3f}')
    print(f'  F1 Score:  {f1:.3f}')
    print(f'  IoU:       {iou:.3f}')

    if f1 < 0.3:
        print('FAIL: F1 score too low')
        return 1
    print('PASS: F1 score acceptable (>0.3)')

    # Confidence statistics
    det_conf = confidence[detection > 0]
    if len(det_conf) > 0:
        print(f'\nConfidence statistics (detected pixels):')
        print(f'  Mean: {det_conf.mean():.3f}')
        print(f'  Min:  {det_conf.min():.3f}')
        print(f'  Max:  {det_conf.max():.3f}')

    # Adversarial check: no avalanche (all zeros ground truth)
    print('\n=== Adversarial Check: No Avalanche Scene ===\n')
    sar_clean, _ = generate_synthetic_sar_scene(size=100, n_avalanche_zones=0, seed=99)
    det_clean, conf_clean = msafe_detect(sar_clean, threshold_db=-3.0, min_cluster_pixels=10)
    n_clean = int(det_clean.sum())
    print(f'Clean scene detection: {n_clean} pixels')
    if n_clean > 5:
        print(f'WARN: {n_clean} false positive pixels in clean scene (noise-induced)')
    else:
        print('PASS: Clean scene correctly shows no detection')

    print('\n=== Demo Complete ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
