"""F3: Synthetic 6-channel SAR patch generator for testing.

Generates realistic-shaped 6-channel tensors matching the mSAFE input format:
  Channel 0: VV_diff (co-polarized backscatter difference)
  Channel 1: VH_diff (cross-polarized backscatter difference)
  Channel 2: VV_VH_prod (product of squared diffs)
  Channel 3: InSAR coherence
  Channel 4: DEM slope angle
  Channel 5: PAR (Potential Angle of Reach)

Also generates corresponding binary avalanche masks.
"""
from __future__ import annotations

import numpy as np


def _generate_avalanche_blob(
    size: int,
    rng: np.random.Generator,
    *,
    min_blobs: int = 1,
    max_blobs: int = 3,
) -> np.ndarray:
    """Generate a binary mask with avalanche-like elongated blobs."""
    mask = np.zeros((size, size), dtype=np.float32)
    num_blobs = rng.integers(min_blobs, max_blobs + 1)
    for _ in range(num_blobs):
        # Start near top (release zone) and flow downward
        start_x = rng.integers(size // 4, 3 * size // 4)
        start_y = rng.integers(0, size // 3)
        length = rng.integers(size // 6, size // 2)
        width = rng.integers(3, max(4, size // 16))
        angle = rng.uniform(-0.3, 0.3)  # slight deviation from vertical

        for dy in range(length):
            y = start_y + dy
            x = int(start_x + dy * angle)
            if 0 <= y < size and 0 <= x < size:
                half_w = max(1, int(width * (1.0 - dy / length * 0.5)))
                x_start = max(0, x - half_w)
                x_end = min(size, x + half_w + 1)
                mask[y, x_start:x_end] = 1.0
    return mask


def _generate_synthetic_dem(
    size: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Generate a synthetic DEM with smooth terrain."""
    x = np.linspace(0, 4 * np.pi, size, dtype=np.float32)
    y = np.linspace(0, 4 * np.pi, size, dtype=np.float32)
    xx, yy = np.meshgrid(x, y)
    dem = (
        3000.0 + 500.0 * np.sin(xx) * np.cos(yy)
        + 200.0 * np.sin(2 * xx + 0.5) + 100.0 * np.cos(3 * yy)
    )
    dem += rng.normal(0, 20, (size, size)).astype(np.float32)
    return dem.astype(np.float32)


def _compute_slope(dem: np.ndarray) -> np.ndarray:
    """Compute slope angle (degrees) from DEM using gradient."""
    dy, dx = np.gradient(dem)
    slope_rad = np.arctan(np.sqrt(dx ** 2 + dy ** 2))
    return np.degrees(slope_rad).astype(np.float32)


def _compute_par(dem: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    """Compute Potential Angle of Reach (PAR) from DEM.

    PAR estimates the likelihood of an avalanche reaching a specific pixel
    based on the angle between the pixel and the furthest uphill release point.
    Values typically range 0-90 degrees; steeper angles = more reachable.
    """
    rows, cols = dem.shape
    par = np.zeros((rows, cols), dtype=np.float32)

    # For each pixel, find the max angle to any uphill pixel within a window
    window = min(rows, cols) // 4
    for r in range(0, rows, 4):  # subsample for speed
        r_end = min(r + 4, rows)
        for c in range(0, cols, 4):
            c_end = min(c + 4, cols)
            r_start = max(0, r - window)
            r_stop = min(rows, r + window)
            c_start = max(0, c - window)
            c_stop = min(cols, c + window)

            sub_dem = dem[r_start:r_stop, c_start:c_stop]
            max_elev = float(sub_dem.max())
            pixel_elev = float(dem[r, c])

            if max_elev > pixel_elev:
                # Find distance to max elevation point
                max_idx = np.unravel_index(np.argmax(sub_dem), sub_dem.shape)
                dist = np.sqrt(
                    (max_idx[0] + r_start - r) ** 2
                    + (max_idx[1] + c_start - c) ** 2
                )
                if dist > 0:
                    angle = np.degrees(np.arctan((max_elev - pixel_elev) / dist))
                    par[r:r_end, c:c_end] = angle

    return par


def generate_synthetic_6channel_patch(
    size: int = 128,
    *,
    seed: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate a synthetic 6-channel SAR patch and avalanche mask.

    Args:
        size: Patch dimension (size x size pixels).
        seed: Random seed for reproducibility.

    Returns:
        Tuple of (input_6ch, mask) where:
        - input_6ch: shape (6, size, size), float32
        - mask: shape (1, size, size), float32, binary
    """
    rng = np.random.default_rng(seed)

    # Generate avalanche mask
    mask = _generate_avalanche_blob(size, rng)

    # Generate synthetic pre/post SAR backscatter (2-channel each: VV, VH)
    # In dB, range -25 to -5
    pre_vv = rng.uniform(-25, -5, (size, size)).astype(np.float32)
    pre_vh = rng.uniform(-25, -5, (size, size)).astype(np.float32)
    post_vv = pre_vv + rng.normal(0, 2, (size, size)).astype(np.float32)
    post_vh = pre_vh + rng.normal(0, 2, (size, size)).astype(np.float32)

    # Add avalanche signal: brighten avalanche pixels in post image
    avalanche_signal = rng.uniform(3, 8, (size, size)).astype(np.float32) * mask
    post_vv += avalanche_signal
    post_vh += avalanche_signal * 0.7

    # Compute SAR features
    vv_diff = (post_vv - pre_vv).astype(np.float32)
    vh_diff = (post_vh - pre_vh).astype(np.float32)
    vv_vh_prod = (vv_diff ** 2 * vh_diff ** 2).astype(np.float32)

    # Generate DEM-derived features
    dem = _generate_synthetic_dem(size, rng)
    slope = _compute_slope(dem)
    par = _compute_par(dem)

    # Generate InSAR coherence (0-1, lower in avalanche areas)
    coherence = rng.uniform(0.3, 0.9, (size, size)).astype(np.float32)
    coherence = coherence * (1.0 - mask * 0.4)  # lower coherence in avalanches

    # Stack into 6-channel tensor
    input_6ch = np.stack([vv_diff, vh_diff, vv_vh_prod, coherence, slope, par], axis=0)

    # Mask shape: (1, H, W)
    mask_out = mask[np.newaxis, :, :]

    return input_6ch.astype(np.float32), mask_out.astype(np.float32)


def generate_synthetic_2channel_pair(
    size: int = 128,
    *,
    seed: int | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Generate synthetic 2-channel pre/post SAR pair and mask.

    For backward compatibility testing with the 2-channel pipeline.

    Returns:
        Tuple of (pre_2ch, post_2ch, mask) where:
        - pre_2ch: shape (2, size, size), float32 (VV, VH)
        - post_2ch: shape (2, size, size), float32 (VV, VH)
        - mask: shape (1, size, size), float32, binary
    """
    rng = np.random.default_rng(seed)
    mask = _generate_avalanche_blob(size, rng)

    pre_vv = rng.uniform(-25, -5, (size, size)).astype(np.float32)
    pre_vh = rng.uniform(-25, -5, (size, size)).astype(np.float32)
    post_vv = pre_vv + rng.normal(0, 2, (size, size)).astype(np.float32)
    post_vh = pre_vh + rng.normal(0, 2, (size, size)).astype(np.float32)

    avalanche_signal = rng.uniform(3, 8, (size, size)).astype(np.float32) * mask
    post_vv += avalanche_signal
    post_vh += avalanche_signal * 0.7

    pre = np.stack([pre_vv, pre_vh], axis=0).astype(np.float32)
    post = np.stack([post_vv, post_vh], axis=0).astype(np.float32)
    mask_out = mask[np.newaxis, :, :].astype(np.float32)

    return pre, post, mask_out
