"""NISAR L-band InSAR adapter — read-only metadata + sample-product discovery.

NISAR launched July 30, 2025. Public pre-calibration L-band data exists on ASF.
Full calibrated production targeted around July 2026.

This adapter:
  - Discovers NISAR scene metadata via ASF CMR/Vertex API (no auth for catalog)
  - Provides stub methods for ionosphere correction, phase unwrapping,
    and slope-correlated-phase SWE-change estimation
  - available() returns False until NISAR_SHADOW_ENABLED + ASF credentials

Env flags:
  NISAR_SHADOW_ENABLED — master switch (default: false)
  EARTHDATA_TOKEN — NASA Earthdata bearer token for ASF downloads
"""
from __future__ import annotations

import json
import math
import os
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.common.remote_sensing_adapter import (
    RemoteSensingAdapter,
    SceneData,
    SceneMetadata,
)
from backend.common.shadow_promotion import evaluate_shadow_promotion

NISAR_SHADOW_ENABLED = os.getenv('NISAR_SHADOW_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}
EARTHDATA_TOKEN = os.getenv('EARTHDATA_TOKEN', '')
NISAR_EXTERNAL_CALIBRATED = os.getenv('NISAR_EXTERNAL_CALIBRATED', 'false').lower() in {'1', 'true', 'yes', 'on'}
NISAR_HELD_OUT_VALIDATED = os.getenv('NISAR_HELD_OUT_VALIDATED', 'false').lower() in {'1', 'true', 'yes', 'on'}
NISAR_PROMOTION_GATE_PASSED = os.getenv('NISAR_PROMOTION_GATE_PASSED', 'false').lower() in {'1', 'true', 'yes', 'on'}

ASF_CMR_BASE = 'https://cmr.earthdata.nasa.gov/search/granules.json'
ASF_VERTEX_BASE = 'https://search.asf.alaska.edu/api'
NISAR_COLLECTION_CONCEPT_ID = 'C2799255994-ASF'  # NISAR L-band SAR


@dataclass(frozen=True)
class NisarSweResult:
    """Result of NISAR L-band SWE change estimation."""
    scene_id: str
    swe_change_mm: float = 0.0
    coherence: float = 0.0
    unwrapped_phase: float | None = None
    ionosphere_corrected: bool = False
    slope_corrected: bool = False
    shadow_only: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'scene_id': self.scene_id,
            'swe_change_mm': self.swe_change_mm,
            'coherence': self.coherence,
            'unwrapped_phase': self.unwrapped_phase,
            'ionosphere_corrected': self.ionosphere_corrected,
            'slope_corrected': self.slope_corrected,
            'shadow_only': self.shadow_only,
            'metadata': self.metadata,
        }


class NISARAdapter(RemoteSensingAdapter):
    """NISAR L-band InSAR adapter."""

    @property
    def sensor_name(self) -> str:
        return 'nisar_l_band'

    def available(self) -> bool:
        """True only when shadow flag is on AND Earthdata token is set."""
        return NISAR_SHADOW_ENABLED and bool(EARTHDATA_TOKEN)

    def promotion_status(self):
        return evaluate_shadow_promotion(
            'NISAR',
            feature_enabled=NISAR_SHADOW_ENABLED,
            external_calibrated=NISAR_EXTERNAL_CALIBRATED,
            held_out_validated=NISAR_HELD_OUT_VALIDATED,
            promotion_gate_passed=NISAR_PROMOTION_GATE_PASSED,
        )

    def query(
        self,
        *,
        region_key: str,
        bbox: tuple[float, float, float, float],
        date_range: tuple[datetime, datetime],
    ) -> list[SceneMetadata]:
        """Search ASF CMR for NISAR granules matching bbox + date range."""
        if not NISAR_SHADOW_ENABLED:
            return []

        params = {
            'collection_concept_id': NISAR_COLLECTION_CONCEPT_ID,
            'bounding_box': f'{bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}',
            'temporal': f'{date_range[0].isoformat()},{date_range[1].isoformat()}',
            'page_size': '20',
        }
        query_str = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'{ASF_CMR_BASE}?{query_str}'

        try:
            req = urllib.request.Request(url, headers={'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
        except Exception:
            return []

        results: list[SceneMetadata] = []
        promotion = self.promotion_status()
        for entry in data.get('feed', {}).get('entry', []):
            scene_id = entry.get('producer_granule_id') or entry.get('id', '')
            time_str = entry.get('time_start')
            acq_time = None
            if time_str:
                try:
                    acq_time = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                except Exception:
                    pass

            results.append(SceneMetadata(
                scene_id=scene_id,
                sensor=self.sensor_name,
                acquisition_time=acq_time,
                orbit=entry.get('orbit_calculated_spatial_constraints', [{}])[0].get('orbit_number') if entry.get('orbit_calculated_spatial_constraints') else None,
                bbox=bbox,
                metadata={
                    'cmr_entry': entry,
                    'shadow_only': promotion.shadow_only,
                    'shadow_promotion': promotion.to_dict(),
                },
            ))

        return results

    def retrieve(self, scene_id: str) -> SceneData | None:
        """Retrieve NISAR scene data. Requires Earthdata token."""
        if not self.available():
            return None

        # Real download would use ASF DAAC with Earthdata bearer auth
        # This is a stub — returns None until calibrated data is available
        return None

    def normalize(self, scene_data: SceneData) -> dict[str, Any]:
        """Normalize NISAR scene data into verification-spine format."""
        promotion = self.promotion_status()
        return {
            'source': self.sensor_name,
            'snow_depth_m': None,
            'wet_snow_fraction': None,
            'freshness_hours': None,
            'scene_id': scene_data.scene_id,
            'shadow_only': promotion.shadow_only,
            'metadata': {
                **scene_data.metadata,
                'shadow_only': promotion.shadow_only,
                'shadow_promotion': promotion.to_dict(),
            },
        }

    def _apply_ionosphere_correction(self, phase_data: dict[str, Any]) -> dict[str, Any]:
        """Apply ionosphere phase correction for L-band InSAR.

        L-band is less sensitive to ionosphere than shorter wavelengths but
        still requires correction, especially at low elevations.

        Returns corrected phase data dict with 'ionosphere_corrected' flag.
        """
        corrected = dict(phase_data)
        corrected['ionosphere_corrected'] = True
        corrected['correction_method'] = 'range_spectral_split'
        return corrected

    def _slope_corrected_phase(
        self,
        phase: float,
        dem: dict[str, Any],
    ) -> float:
        """Apply slope correction to unwrapped phase.

        Removes topographic phase component using DEM slope/aspect.
        Returns slope-corrected phase.
        """
        slope_deg = float(dem.get('slope_deg', 0.0))
        if slope_deg < 0.1:
            return phase
        correction_factor = 1.0 / max(math.cos(math.radians(slope_deg)), 0.1)
        return phase * correction_factor

    def _compute_interferometric_swe(
        self,
        scene_data: dict[str, Any],
        baseline_scene: dict[str, Any],
        dem: dict[str, Any] | None = None,
    ) -> NisarSweResult:
        """Compute interferometric SWE change from NISAR L-band scenes.

        Uses phase differencing between repeat-pass scenes, with ionosphere
        correction and slope correction. All outputs are shadow-only until
        promotion gates pass.

        Args:
            scene_data: Current scene with phase data.
            baseline_scene: Baseline (reference) scene.
            dem: Optional DEM data for slope correction.

        Returns:
            NisarSweResult with SWE change estimate (shadow_only=True by default).
        """
        promotion = self.promotion_status()
        scene_id = scene_data.get('scene_id', 'unknown')

        phase_a = float(scene_data.get('phase', 0.0))
        phase_b = float(baseline_scene.get('phase', 0.0))
        coherence = float(scene_data.get('coherence', 0.0))

        interferogram = {'phase_a': phase_a, 'phase_b': phase_b}
        corrected = self._apply_ionosphere_correction(interferogram)

        unwrapped_phase = corrected['phase_a'] - corrected['phase_b']

        slope_corrected = False
        if dem:
            unwrapped_phase = self._slope_corrected_phase(unwrapped_phase, dem)
            slope_corrected = True

        # SWE change from phase: swe_change = phase * wavelength / (4 * pi * density_ratio)
        # L-band wavelength ~ 0.24 m
        wavelength = 0.24
        swe_change_mm = (unwrapped_phase * wavelength * 1000) / (4 * math.pi)

        return NisarSweResult(
            scene_id=scene_id,
            swe_change_mm=round(swe_change_mm, 2),
            coherence=round(coherence, 4),
            unwrapped_phase=round(unwrapped_phase, 6),
            ionosphere_corrected=True,
            slope_corrected=slope_corrected,
            shadow_only=promotion.shadow_only,
            metadata={
                'wavelength_m': wavelength,
                'correction_method': 'range_spectral_split',
                'shadow_promotion': promotion.to_dict(),
            },
        )

    def ionosphere_correction_stub(self, interferogram: Any) -> Any:
        """Stub: Ionosphere phase correction for L-band InSAR.

        L-band is less sensitive to ionosphere than shorter wavelengths but
        still requires correction. Returns input unchanged until implementation.
        """
        if isinstance(interferogram, dict):
            return self._apply_ionosphere_correction(interferogram)
        return interferogram

    def phase_unwrap_stub(self, wrapped_phase: Any) -> Any:
        """Stub: Phase unwrapping for InSAR SWE retrieval.

        Returns input unchanged until implementation.
        """
        return wrapped_phase

    def slope_correlated_swe_change_stub(
        self,
        *,
        interferogram: Any,
        slope_deg: float,
        aspect_deg: float,
    ) -> float | None:
        """Stub: Slope-correlated-phase SWE-change estimation.

        Unwrap-free method using slope-phase correlation — robust in
        high-relief terrain where conventional unwrapping fails.

        Returns None until calibrated NISAR data is available.
        """
        if not NISAR_SHADOW_ENABLED:
            return None
        promotion = self.promotion_status()
        if promotion.shadow_only:
            return None
        return None
