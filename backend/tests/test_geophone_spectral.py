"""Tests for F11: Geophone Spectral Analysis."""
from __future__ import annotations

import unittest
from typing import Any

import numpy as np

from backend.common.geophone_spectral import (
    GeophoneArray,
    GeophoneConfig,
    GeophoneReading,
    SpectralFeatures,
    SpectralResult,
    analyze_geophone_reading,
    compute_fft,
    compute_psd,
    compute_spectrogram,
    detect_triangular_spectrum,
    extract_spectral_features,
)


class ComputeFFTTests(unittest.TestCase):
    """Tests for FFT computation."""

    def test_fft_basic(self) -> None:
        sample_rate = 100.0
        t = np.arange(1024) / sample_rate
        signal = np.sin(2 * np.pi * 10 * t)  # 10 Hz sine wave
        freqs, mags = compute_fft(signal, sample_rate)
        self.assertEqual(len(freqs), len(mags))
        # Peak should be near 10 Hz
        peak_idx = int(np.argmax(mags))
        self.assertAlmostEqual(freqs[peak_idx], 10.0, places=0)

    def test_fft_empty(self) -> None:
        freqs, mags = compute_fft(np.array([]))
        self.assertEqual(len(freqs), 0)
        self.assertEqual(len(mags), 0)

    def test_fft_dc_signal(self) -> None:
        signal = np.ones(512) * 5.0
        freqs, mags = compute_fft(signal, 100.0)
        self.assertGreater(len(freqs), 0)
        # DC component should be dominant
        self.assertGreater(mags[0], mags[-1])


class ComputePSDTests(unittest.TestCase):
    """Tests for PSD computation."""

    def test_psd_basic(self) -> None:
        sample_rate = 100.0
        t = np.arange(2048) / sample_rate
        signal = np.sin(2 * np.pi * 25 * t)  # 25 Hz
        freqs, psd = compute_psd(signal, sample_rate, window_size=512, overlap=0.5)
        self.assertEqual(len(freqs), len(psd))
        self.assertGreater(len(freqs), 0)
        peak_idx = int(np.argmax(psd))
        self.assertAlmostEqual(freqs[peak_idx], 25.0, places=0)

    def test_psd_short_signal(self) -> None:
        signal = np.array([1.0, 2.0, 3.0])
        freqs, psd = compute_psd(signal, 100.0, window_size=1024, overlap=0.5)
        # Should adapt window_size down
        self.assertGreater(len(freqs), 0)

    def test_psd_empty(self) -> None:
        freqs, psd = compute_psd(np.array([]))
        self.assertEqual(len(freqs), 0)


class ComputeSpectrogramTests(unittest.TestCase):
    """Tests for spectrogram computation."""

    def test_spectrogram_basic(self) -> None:
        sample_rate = 100.0
        t = np.arange(2048) / sample_rate
        signal = np.sin(2 * np.pi * 30 * t)
        times, freqs, spec = compute_spectrogram(signal, sample_rate, window_size=512, overlap=0.5)
        self.assertGreater(len(times), 0)
        self.assertGreater(len(freqs), 0)
        self.assertEqual(spec.shape, (len(times), len(freqs)))

    def test_spectrogram_empty(self) -> None:
        times, freqs, spec = compute_spectrogram(np.array([]))
        self.assertEqual(len(times), 0)


class TriangularSpectrumDetectionTests(unittest.TestCase):
    """Tests for triangular running spectrum detection."""

    def test_detect_triangular_harmonic(self) -> None:
        # Create signal with harmonics at 30, 60, 90, 120 Hz
        sample_rate = 500.0
        t = np.arange(2048) / sample_rate
        signal = sum(np.sin(2 * np.pi * f * t) for f in [30, 60, 90, 120])
        freqs, psd = compute_psd(signal, sample_rate, window_size=1024, overlap=0.5)
        detected, confidence = detect_triangular_spectrum(freqs, psd)
        self.assertTrue(detected)
        self.assertGreater(confidence, 0.0)

    def test_detect_triangular_noise(self) -> None:
        np.random.seed(42)
        signal = np.random.randn(2048)
        freqs, psd = compute_psd(signal, 500.0, window_size=1024, overlap=0.5)
        detected, confidence = detect_triangular_spectrum(freqs, psd)
        # Random noise should not produce strong triangular pattern
        # Allow detection but require low confidence
        if detected:
            self.assertLessEqual(confidence, 0.5)

    def test_detect_triangular_empty(self) -> None:
        detected, confidence = detect_triangular_spectrum(np.array([]), np.array([]))
        self.assertFalse(detected)
        self.assertEqual(confidence, 0.0)


class ExtractSpectralFeaturesTests(unittest.TestCase):
    """Tests for spectral feature extraction."""

    def test_extract_features_basic(self) -> None:
        freqs = np.array([0, 10, 20, 50, 100, 200])
        psd = np.array([0.1, 0.5, 0.3, 0.8, 0.2, 0.1])
        features = extract_spectral_features(freqs, psd)
        self.assertEqual(features.dominant_freq, 50.0)
        self.assertGreater(features.spectral_centroid, 0)
        self.assertGreater(features.peak_amplitude, 0)
        self.assertIn('low', features.freq_band_energies)
        self.assertIn('mid', features.freq_band_energies)
        self.assertIn('high', features.freq_band_energies)

    def test_extract_features_empty(self) -> None:
        features = extract_spectral_features(np.array([]), np.array([]))
        self.assertEqual(features.dominant_freq, 0.0)
        self.assertEqual(features.spectral_centroid, 0.0)
        self.assertFalse(features.triangular_detected)


class AnalyzeGeophoneReadingTests(unittest.TestCase):
    """Tests for full geophone reading analysis."""

    def test_analyze_reading(self) -> None:
        sample_rate = 200.0
        t = np.arange(2048) / sample_rate
        voltage = np.sin(2 * np.pi * 40 * t)
        reading = GeophoneReading(
            timestamp='2026-06-25T10:00:00Z',
            voltage_data=voltage,
            channel_id='ch_01',
            sample_rate_hz=sample_rate,
        )
        result = analyze_geophone_reading(reading)
        self.assertIsInstance(result, SpectralResult)
        self.assertEqual(result.channel_id, 'ch_01')
        self.assertGreater(len(result.dominant_freqs), 0)
        # Dominant freq should be near 40 Hz (within FFT resolution)
        self.assertAlmostEqual(result.dominant_freqs[0], 40.0, places=0)


class GeophoneArrayTests(unittest.TestCase):
    """Tests for multi-channel geophone array."""

    def test_array_multiple_channels(self) -> None:
        sample_rate = 200.0
        t = np.arange(1024) / sample_rate
        array = GeophoneArray()
        for i in range(3):
            reading = GeophoneReading(
                timestamp='2026-06-25T10:00:00Z',
                voltage_data=np.sin(2 * np.pi * (20 + i * 10) * t),
                channel_id=f'ch_{i}',
                sample_rate_hz=sample_rate,
            )
            array.add_channel(reading)

        results = array.analyze_all()
        self.assertEqual(len(results), 3)
        for ch_id in ['ch_0', 'ch_1', 'ch_2']:
            self.assertIn(ch_id, results)

    def test_array_triangular_detection(self) -> None:
        sample_rate = 500.0
        t = np.arange(2048) / sample_rate
        signal = sum(np.sin(2 * np.pi * f * t) for f in [30, 60, 90, 120])
        array = GeophoneArray()
        array.add_channel(GeophoneReading(
            timestamp='2026-06-25T10:00:00Z',
            voltage_data=signal,
            channel_id='ch_triangular',
            sample_rate_hz=sample_rate,
        ))
        results = array.detect_triangular_across_channels()
        self.assertIn('ch_triangular', results)
        detected, _ = results['ch_triangular']
        self.assertTrue(detected)


class SeismicIntegratorGeophoneTests(unittest.TestCase):
    """Integration tests for geophone + seismic integrator."""

    def test_integrate_geophone_disabled(self) -> None:
        from backend.common.seismic_integrator import (
            SeismicAmplification,
            integrate_geophone_data,
        )
        amp = SeismicAmplification(
            factor=0.5,
            window_phase=1,
            hours_since_event=5.0,
            magnitude=5.0,
            epicenter_distance_km=50.0,
            epicenter_lat=33.0,
            epicenter_lng=76.0,
        )
        # Without GEOPHONE_ENABLED, should return unchanged
        result = integrate_geophone_data(amp, geophone_readings=None)
        self.assertIsNone(result.geophone_spectral_features)

    def test_integrate_geophone_no_readings(self) -> None:
        from backend.common.seismic_integrator import (
            SeismicAmplification,
            integrate_geophone_data,
        )
        amp = SeismicAmplification(
            factor=0.5,
            window_phase=1,
            hours_since_event=5.0,
            magnitude=5.0,
            epicenter_distance_km=50.0,
            epicenter_lat=33.0,
            epicenter_lng=76.0,
        )
        result = integrate_geophone_data(amp, geophone_readings=[])
        self.assertIsNone(result.geophone_spectral_features)


if __name__ == '__main__':
    unittest.main()
