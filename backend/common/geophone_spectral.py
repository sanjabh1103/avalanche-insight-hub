"""F11: Geophone Spectral Analysis.

FFT/PSD computation from raw geophone voltage data.
"Triangular running spectrum" detection algorithm for active dry-slab flows.

Uses numpy FFT — no scipy dependency required.

Configurable via environment variables:
  GEOPHONE_SAMPLE_RATE_HZ — sampling rate in Hz (default: 100)
  GEOPHONE_WINDOW_SIZE — FFT window size in samples (default: 1024)
  GEOPHONE_OVERLAP — window overlap fraction 0-1 (default: 0.5)
  GEOPHONE_ENABLED — master switch (default: false)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np

GEOPHONE_ENABLED = os.getenv('GEOPHONE_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}
GEOPHONE_SAMPLE_RATE_HZ = float(os.getenv('GEOPHONE_SAMPLE_RATE_HZ', '100'))
GEOPHONE_WINDOW_SIZE = int(os.getenv('GEOPHONE_WINDOW_SIZE', '1024'))
GEOPHONE_OVERLAP = float(os.getenv('GEOPHONE_OVERLAP', '0.5'))

# Triangular spectrum detection parameters
TRIANGULAR_FREQ_LOW = 20.0  # Hz — low frequency bound for triangular pattern
TRIANGULAR_FREQ_HIGH = 150.0  # Hz — high frequency bound
TRIANGULAR_PEAK_RATIO = 0.6  # Minimum peak-to-mean ratio for detection
TRIANGULAR_MIN_PEAKS = 3  # Minimum number of harmonic peaks


@dataclass(frozen=True)
class GeophoneConfig:
    """Configuration for geophone spectral analysis."""
    sample_rate_hz: float = GEOPHONE_SAMPLE_RATE_HZ
    window_size: int = GEOPHONE_WINDOW_SIZE
    overlap: float = GEOPHONE_OVERLAP
    enabled: bool = GEOPHONE_ENABLED


@dataclass(frozen=True)
class GeophoneReading:
    """Raw geophone voltage reading."""
    timestamp: str
    voltage_data: np.ndarray
    channel_id: str
    sample_rate_hz: float = GEOPHONE_SAMPLE_RATE_HZ


@dataclass
class SpectralResult:
    """Result of spectral analysis on a geophone reading."""
    freqs: np.ndarray
    psd: np.ndarray
    spectrogram: np.ndarray  # 2D: (time_frames, freq_bins)
    dominant_freqs: list[float]
    timestamp: str
    channel_id: str


@dataclass
class SpectralFeatures:
    """Features extracted from spectral analysis for ML integration."""
    dominant_freq: float
    spectral_centroid: float
    spectral_spread: float
    peak_amplitude: float
    triangular_detected: bool
    triangular_confidence: float
    freq_band_energies: dict[str, float]  # band_name -> energy


def compute_fft(
    voltage_data: np.ndarray,
    sample_rate: float = GEOPHONE_SAMPLE_RATE_HZ,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute single-sided FFT of raw voltage data.

    Args:
        voltage_data: 1D array of voltage samples
        sample_rate: Sampling rate in Hz

    Returns:
        (freqs, magnitudes) — frequency bins and corresponding magnitudes
    """
    n = len(voltage_data)
    if n == 0:
        return np.array([]), np.array([])

    # Apply Hann window to reduce spectral leakage
    window = np.hanning(n)
    windowed = voltage_data * window

    fft_vals = np.fft.rfft(windowed)
    freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)
    magnitudes = np.abs(fft_vals) * 2.0 / n

    return freqs, magnitudes


def compute_psd(
    voltage_data: np.ndarray,
    sample_rate: float = GEOPHONE_SAMPLE_RATE_HZ,
    window_size: int = GEOPHONE_WINDOW_SIZE,
    overlap: float = GEOPHONE_OVERLAP,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute Power Spectral Density using Welch's method.

    Args:
        voltage_data: 1D array of voltage samples
        sample_rate: Sampling rate in Hz
        window_size: FFT window size
        overlap: Overlap fraction (0-1)

    Returns:
        (freqs, psd) — frequency bins and PSD values
    """
    n = len(voltage_data)
    if n < window_size:
        window_size = n
    if window_size == 0:
        return np.array([]), np.array([])

    hop = max(1, int(window_size * (1 - overlap)))
    n_frames = max(1, (n - window_size) // hop + 1)

    psd_accum = np.zeros(window_size // 2 + 1)
    count = 0

    for i in range(n_frames):
        start = i * hop
        segment = voltage_data[start:start + window_size]
        if len(segment) < window_size:
            break

        window = np.hanning(window_size)
        windowed = segment * window
        fft_vals = np.fft.rfft(windowed)
        power = np.abs(fft_vals) ** 2 / (sample_rate * np.sum(window ** 2))
        psd_accum += power
        count += 1

    if count == 0:
        return np.array([]), np.array([])

    psd = psd_accum / count
    freqs = np.fft.rfftfreq(window_size, d=1.0 / sample_rate)

    return freqs, psd


def compute_spectrogram(
    voltage_data: np.ndarray,
    sample_rate: float = GEOPHONE_SAMPLE_RATE_HZ,
    window_size: int = GEOPHONE_WINDOW_SIZE,
    overlap: float = GEOPHONE_OVERLAP,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute STFT spectrogram.

    Args:
        voltage_data: 1D array of voltage samples
        sample_rate: Sampling rate in Hz
        window_size: FFT window size
        overlap: Overlap fraction (0-1)

    Returns:
        (times, freqs, spectrogram) — time bins, frequency bins, 2D spectrogram
    """
    n = len(voltage_data)
    if n < window_size:
        window_size = n
    if window_size == 0:
        return np.array([]), np.array([]), np.array([])

    hop = max(1, int(window_size * (1 - overlap)))
    n_frames = max(1, (n - window_size) // hop + 1)

    freqs = np.fft.rfftfreq(window_size, d=1.0 / sample_rate)
    spectrogram = np.zeros((n_frames, len(freqs)))
    times = np.zeros(n_frames)

    for i in range(n_frames):
        start = i * hop
        segment = voltage_data[start:start + window_size]
        if len(segment) < window_size:
            break

        window = np.hanning(window_size)
        windowed = segment * window
        fft_vals = np.fft.rfft(windowed)
        spectrogram[i] = np.abs(fft_vals)
        times[i] = start / sample_rate

    return times, freqs, spectrogram[:i + 1] if i < n_frames else spectrogram


def detect_triangular_spectrum(
    freqs: np.ndarray,
    psd: np.ndarray,
    *,
    freq_low: float = TRIANGULAR_FREQ_LOW,
    freq_high: float = TRIANGULAR_FREQ_HIGH,
    peak_ratio: float = TRIANGULAR_PEAK_RATIO,
    min_peaks: int = TRIANGULAR_MIN_PEAKS,
) -> tuple[bool, float]:
    """Detect "triangular running spectrum" signature of active dry-slab flows.

    The triangular spectrum pattern shows evenly-spaced harmonic peaks
    in the 20-150 Hz range, characteristic of slab fracture propagation.

    Args:
        freqs: Frequency bins
        psd: Power spectral density values
        freq_low: Low frequency bound for detection
        freq_high: High frequency bound for detection
        peak_ratio: Minimum peak-to-mean ratio
        min_peaks: Minimum number of harmonic peaks

    Returns:
        (detected, confidence) — whether triangular pattern detected and confidence 0-1
    """
    if len(freqs) == 0 or len(psd) == 0:
        return False, 0.0

    # Filter to frequency band of interest
    mask = (freqs >= freq_low) & (freqs <= freq_high)
    band_freqs = freqs[mask]
    band_psd = psd[mask]

    if len(band_freqs) < min_peaks * 2:
        return False, 0.0

    # Find peaks: local maxima above mean * peak_ratio
    mean_psd = float(np.mean(band_psd))
    threshold = mean_psd * (1.0 + peak_ratio)

    peaks: list[float] = []
    for i in range(1, len(band_psd) - 1):
        if band_psd[i] > band_psd[i - 1] and band_psd[i] > band_psd[i + 1]:
            if band_psd[i] > threshold:
                peaks.append(float(band_freqs[i]))

    if len(peaks) < min_peaks:
        return False, 0.0

    # Check for harmonic spacing (evenly spaced peaks)
    if len(peaks) >= 2:
        spacings = np.diff(peaks)
        mean_spacing = float(np.mean(spacings))
        if mean_spacing > 0:
            spacing_cv = float(np.std(spacings) / mean_spacing)  # Coefficient of variation
            # Low CV means evenly spaced = harmonic = triangular pattern
            if spacing_cv < 0.3:
                confidence = min(1.0, len(peaks) / 10.0) * (1.0 - spacing_cv)
                return True, confidence

    # Multiple peaks without harmonic spacing — lower confidence
    confidence = min(0.5, len(peaks) / 10.0)
    return len(peaks) >= min_peaks, confidence


def extract_spectral_features(
    freqs: np.ndarray,
    psd: np.ndarray,
    *,
    triangular_detected: bool = False,
    triangular_confidence: float = 0.0,
) -> SpectralFeatures:
    """Extract ML-ready features from spectral analysis.

    Args:
        freqs: Frequency bins
        psd: PSD values
        triangular_detected: Whether triangular pattern was detected
        triangular_confidence: Confidence of triangular detection

    Returns:
        SpectralFeatures dataclass
    """
    if len(freqs) == 0 or len(psd) == 0:
        return SpectralFeatures(
            dominant_freq=0.0,
            spectral_centroid=0.0,
            spectral_spread=0.0,
            peak_amplitude=0.0,
            triangular_detected=False,
            triangular_confidence=0.0,
            freq_band_energies={},
        )

    # Dominant frequency (peak of PSD)
    dominant_idx = int(np.argmax(psd))
    dominant_freq = float(freqs[dominant_idx])

    # Spectral centroid (weighted mean frequency)
    total_power = float(np.sum(psd))
    if total_power > 0:
        spectral_centroid = float(np.sum(freqs * psd) / total_power)
        spectral_spread = float(np.sqrt(np.sum(((freqs - spectral_centroid) ** 2) * psd) / total_power))
    else:
        spectral_centroid = 0.0
        spectral_spread = 0.0

    # Peak amplitude
    peak_amplitude = float(np.max(psd))

    # Frequency band energies
    bands = {
        'low': (0, 20),
        'mid': (20, 150),
        'high': (150, 500),
    }
    band_energies: dict[str, float] = {}
    for name, (f_low, f_high) in bands.items():
        mask = (freqs >= f_low) & (freqs < f_high)
        band_energies[name] = float(np.sum(psd[mask])) if np.any(mask) else 0.0

    return SpectralFeatures(
        dominant_freq=dominant_freq,
        spectral_centroid=spectral_centroid,
        spectral_spread=spectral_spread,
        peak_amplitude=peak_amplitude,
        triangular_detected=triangular_detected,
        triangular_confidence=triangular_confidence,
        freq_band_energies=band_energies,
    )


def analyze_geophone_reading(
    reading: GeophoneReading,
    config: GeophoneConfig | None = None,
) -> SpectralResult:
    """Full spectral analysis of a geophone reading.

    Args:
        reading: GeophoneReading with voltage data
        config: Analysis configuration

    Returns:
        SpectralResult with FFT, PSD, spectrogram, and dominant frequencies
    """
    cfg = config or GeophoneConfig()

    freqs, psd = compute_psd(
        reading.voltage_data,
        sample_rate=reading.sample_rate_hz,
        window_size=cfg.window_size,
        overlap=cfg.overlap,
    )

    _, _, spectrogram = compute_spectrogram(
        reading.voltage_data,
        sample_rate=reading.sample_rate_hz,
        window_size=cfg.window_size,
        overlap=cfg.overlap,
    )

    # Find top 5 dominant frequencies
    dominant_freqs: list[float] = []
    if len(freqs) > 0 and len(psd) > 0:
        top_indices = np.argsort(psd)[-5:][::-1]
        dominant_freqs = [float(freqs[i]) for i in top_indices if psd[i] > 0]

    return SpectralResult(
        freqs=freqs,
        psd=psd,
        spectrogram=spectrogram,
        dominant_freqs=dominant_freqs,
        timestamp=reading.timestamp,
        channel_id=reading.channel_id,
    )


class GeophoneArray:
    """Multi-channel geophone array processor."""

    def __init__(self, config: GeophoneConfig | None = None) -> None:
        self.config = config or GeophoneConfig()
        self.channels: dict[str, GeophoneReading] = {}

    def add_channel(self, reading: GeophoneReading) -> None:
        self.channels[reading.channel_id] = reading

    def analyze_all(self) -> dict[str, SpectralResult]:
        """Analyze all channels in the array."""
        results: dict[str, SpectralResult] = {}
        for channel_id, reading in self.channels.items():
            results[channel_id] = analyze_geophone_reading(reading, self.config)
        return results

    def detect_triangular_across_channels(self) -> dict[str, tuple[bool, float]]:
        """Run triangular spectrum detection across all channels.

        Returns:
            Dict of channel_id -> (detected, confidence)
        """
        results: dict[str, tuple[bool, float]] = {}
        for channel_id, reading in self.channels.items():
            spectral = analyze_geophone_reading(reading, self.config)
            detected, confidence = detect_triangular_spectrum(spectral.freqs, spectral.psd)
            results[channel_id] = (detected, confidence)
        return results
