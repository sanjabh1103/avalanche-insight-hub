"""F13: Uncertainty Quantification & Brier Blocking.

Computes Brier score from model metadata (training-time metrics already
available in lstm_head_meta.brier_score or rf_metrics.brier_score), blocks
publication when Brier exceeds a configurable threshold (default 0.15), and
computes conformal prediction intervals on grid cell probabilities.

Split conformal prediction is supported via ``ConformalCalibrator`` which
uses empirical residuals from a calibration set to produce distribution-free
prediction intervals with finite-sample coverage guarantees.

Env flags:
  BRIER_BLOCK_THRESHOLD — publish block threshold (default: 0.15)
  CONFORMAL_ALPHA — miscoverage rate for conformal intervals (default: 0.1 → 90%)
  CONFORMAL_CALIBRATION_SET_PATH — optional CSV path for calibration data
"""
from __future__ import annotations

import csv
import hashlib
import math
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np


BRIER_BLOCK_THRESHOLD = float(os.getenv('BRIER_BLOCK_THRESHOLD', '0.15'))
CONFORMAL_ALPHA = float(os.getenv('CONFORMAL_ALPHA', '0.1'))

# Confidence classification thresholds
CONFIDENCE_HIGH_THRESHOLD = 0.08
CONFIDENCE_MEDIUM_THRESHOLD = 0.15

# Default uncertainty std when model doesn't provide one
DEFAULT_UNCERTAINTY_STD = 0.1

# Optional calibration set path for split conformal prediction
CONFORMAL_CALIBRATION_SET_PATH = os.getenv('CONFORMAL_CALIBRATION_SET_PATH', '')


@dataclass
class ConformalCalibrator:
    """Split conformal prediction calibrator.

    Uses empirical residuals from a calibration set to produce
    distribution-free prediction intervals with finite-sample
    coverage guarantees (1-alpha).

    Call ``calibrate`` with (predictions, truths) to compute the
    empirical quantile of absolute residuals. Then call
    ``predict_interval`` to get calibrated (lower, upper) bounds.
    """
    alpha: float = CONFORMAL_ALPHA
    _quantile: float | None = None
    _residuals: list[float] = field(default_factory=list)

    def calibrate(
        self,
        predictions: Sequence[float],
        truths: Sequence[float],
    ) -> None:
        """Compute empirical quantile from calibration set residuals."""
        residuals = sorted(
            abs(float(t) - float(p))
            for p, t in zip(predictions, truths)
            if math.isfinite(float(p)) and math.isfinite(float(t))
        )
        self._residuals = residuals
        if not residuals:
            self._quantile = None
            return
        # Empirical quantile: ceil((n+1) * (1-alpha)) / n for finite-sample coverage
        n = len(residuals)
        idx = int(math.ceil((n + 1) * (1.0 - self.alpha))) - 1
        idx = max(0, min(idx, n - 1))
        self._quantile = residuals[idx]

    @property
    def is_calibrated(self) -> bool:
        return self._quantile is not None

    def coverage(self) -> float | None:
        """Empirical coverage on the calibration set."""
        if not self._residuals or self._quantile is None:
            return None
        q = self._quantile
        covered = sum(1 for r in self._residuals if r <= q)
        return covered / len(self._residuals)

    def predict_interval(self, probability: float) -> tuple[float, float]:
        """Produce conformal prediction interval.

        Falls back to normal approximation if not calibrated.
        """
        if self._quantile is not None:
            q = self._quantile
            lower = max(0.0, min(1.0, float(probability) - q))
            upper = max(0.0, min(1.0, float(probability) + q))
            return (lower, upper)
        # Fallback: normal approximation with default std
        return compute_conformal_interval(probability, DEFAULT_UNCERTAINTY_STD, self.alpha)


def compute_split_conformal_interval(
    probability: float,
    calibrator: ConformalCalibrator,
) -> tuple[float, float]:
    """Compute split conformal prediction interval using a calibrated calibrator."""
    return calibrator.predict_interval(probability)


def load_calibrator_from_csv(
    csv_path: str,
    alpha: float = CONFORMAL_ALPHA,
) -> ConformalCalibrator:
    """Load a ConformalCalibrator from a CSV with 'prediction' and 'truth' columns."""
    predictions: list[float] = []
    truths: list[float] = []
    with open(csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                predictions.append(float(row['prediction']))
                truths.append(float(row['truth']))
            except (KeyError, ValueError):
                continue
    calibrator = ConformalCalibrator(alpha=alpha)
    calibrator.calibrate(predictions, truths)
    return calibrator


@dataclass(frozen=True)
class CalibrationManifest:
    """Versioned calibration manifest with explicit method and fallback metadata.

    Attributes:
        version: Manifest schema version.
        sha256: SHA-256 hash of the calibration CSV file.
        sample_count: Number of calibration samples loaded.
        alpha: Miscoverage rate used.
        empirical_coverage: Empirical coverage on the fit set (same residuals used for calibration).
        fit_coverage: Coverage computed on the calibration (fit) set. Alias for empirical_coverage.
        held_out_coverage: Coverage on a held-out evaluation set, if provided. None if not available.
        uq_method: 'split_conformal' or 'normal_fallback'.
    """
    version: str
    sha256: str
    sample_count: int
    alpha: float
    empirical_coverage: float | None
    fit_coverage: float | None
    held_out_coverage: float | None
    uq_method: str
    held_out_source_hash: str = ''
    calibration_state: str = 'fit_only'

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


CALIBRATION_MANIFEST_VERSION = '1.0.0'

_HELD_OUT_SET_PATH = os.getenv('CONFORMAL_HELD_OUT_SET_PATH', '') or str(Path(__file__).resolve().parent.parent / 'config' / 'default_held_out_calibration.csv')


def _compute_held_out_source_hash(path: str) -> str:
    """Compute SHA-256 of the held-out CSV file for immutable lineage."""
    try:
        p = Path(path)
        if p.exists():
            return hashlib.sha256(p.read_bytes()).hexdigest()
    except Exception:
        pass
    return ''


def _evaluate_held_out_coverage(
    calibrator: ConformalCalibrator | None,
    alpha: float,
) -> float | None:
    """Evaluate conformal coverage on a held-out set if available.

    Reads from CONFORMAL_HELD_OUT_SET_PATH env var. The CSV must have
    'probability' and 'truth' columns. Returns None if no path is set
    or evaluation fails.

    Coverage is computed against the **fitted calibrator's quantile**
    (from the calibration set), NOT a re-derived threshold from the
    held-out residuals. This ensures the held-out coverage reflects
    the true generalization of the conformal interval.
    """
    if not _HELD_OUT_SET_PATH or calibrator is None or not calibrator.is_calibrated:
        return None
    fitted_quantile = calibrator._quantile
    if fitted_quantile is None:
        return None
    try:
        held_path = Path(_HELD_OUT_SET_PATH)
        if not held_path.exists():
            return None
        import csv as csv_module
        with held_path.open('r') as f:
            reader = csv_module.DictReader(f)
            rows = list(reader)
        if not rows:
            return None
        residuals: list[float] = []
        for row in rows:
            try:
                prob = float(row.get('probability', 0))
                truth = float(row.get('truth', 0))
                residuals.append(abs(prob - truth))
            except (TypeError, ValueError):
                continue
        if not residuals:
            return None
        n = len(residuals)
        covered = sum(1 for r in residuals if r <= fitted_quantile)
        return round(covered / n, 4)
    except Exception:
        return None


def load_calibrator_with_manifest(
    csv_path: str,
    alpha: float = CONFORMAL_ALPHA,
) -> tuple[ConformalCalibrator | None, CalibrationManifest]:
    """Load a ConformalCalibrator with a CalibrationManifest.

    Returns (None, manifest_with_normal_fallback) if the file is missing or invalid.
    """
    path = Path(csv_path)
    if not path.exists():
        return None, CalibrationManifest(
            version=CALIBRATION_MANIFEST_VERSION,
            sha256='',
            sample_count=0,
            alpha=alpha,
            empirical_coverage=None,
            fit_coverage=None,
            held_out_coverage=None,
            uq_method='normal_fallback',
            calibration_state='fallback',
        )

    try:
        file_bytes = path.read_bytes()
        sha256 = hashlib.sha256(file_bytes).hexdigest()
        calibrator = load_calibrator_from_csv(csv_path, alpha=alpha)
        sample_count = len(calibrator._residuals)
        # G-08: Use the calibrator's own coverage() method, which uses the same
        # finite-sample ceil((n+1)(1-alpha)) quantile rule as calibrate().
        # Do NOT recompute with a separate formula.
        fit_coverage = calibrator.coverage()
        if fit_coverage is not None:
            fit_coverage = round(fit_coverage, 4)
        # Evaluate held-out coverage if CONFORMAL_HELD_OUT_SET_PATH is set
        held_out_coverage = _evaluate_held_out_coverage(calibrator, alpha)
        _held_out_hash = _compute_held_out_source_hash(_HELD_OUT_SET_PATH) if held_out_coverage is not None else ''
        _cal_state = 'calibrated_with_held_out' if held_out_coverage is not None else 'fit_only'
        return calibrator, CalibrationManifest(
            version=CALIBRATION_MANIFEST_VERSION,
            sha256=sha256,
            sample_count=sample_count,
            alpha=alpha,
            empirical_coverage=fit_coverage,
            fit_coverage=fit_coverage,
            held_out_coverage=held_out_coverage,
            uq_method='split_conformal',
            held_out_source_hash=_held_out_hash,
            calibration_state=_cal_state,
        )
    except Exception:
        return None, CalibrationManifest(
            version=CALIBRATION_MANIFEST_VERSION,
            sha256='',
            sample_count=0,
            alpha=alpha,
            empirical_coverage=None,
            fit_coverage=None,
            held_out_coverage=None,
            uq_method='normal_fallback',
            calibration_state='fallback',
        )


def reliability_diagram(
    predictions: Sequence[float],
    truths: Sequence[float],
    n_bins: int = 10,
) -> list[dict[str, Any]]:
    """Compute reliability diagram bins for coverage monitoring."""
    bins = []
    for i in range(n_bins):
        lo = i / n_bins
        hi = (i + 1) / n_bins
        mask = [lo <= float(p) < hi for p in predictions]
        count = sum(mask)
        if count == 0:
            bins.append({'bin_lo': lo, 'bin_hi': hi, 'count': 0, 'avg_prediction': None, 'avg_truth': None})
            continue
        idxs = [j for j, m in enumerate(mask) if m]
        avg_pred = sum(float(predictions[j]) for j in idxs) / count
        avg_truth = sum(float(truths[j]) for j in idxs) / count
        bins.append({
            'bin_lo': round(lo, 3),
            'bin_hi': round(hi, 3),
            'count': count,
            'avg_prediction': round(avg_pred, 4),
            'avg_truth': round(avg_truth, 4),
        })
    return bins


@dataclass(frozen=True)
class UQResult:
    """Summary of uncertainty quantification for a forecast run."""
    brier_score: float | None
    forecast_confidence: str  # 'high' | 'medium' | 'low' | 'unknown'
    publish_blocked: bool
    block_reason: str | None
    conformal_alpha: float


def compute_brier_score(model_metadata: dict[str, Any]) -> float | None:
    """Extract Brier score from model metadata.

    Tries lstm_head_meta.brier_score first, then rf_metrics.brier_score.

    Args:
        model_metadata: The model_metadata dict from daily_inference.py

    Returns:
        Brier score as float, or None if not available
    """
    # Try LSTM head meta first
    lstm_head_meta = model_metadata.get('lstm_head_meta')
    if isinstance(lstm_head_meta, dict):
        brier = lstm_head_meta.get('brier_score')
        if brier is not None:
            try:
                return float(brier)
            except (TypeError, ValueError):
                pass
        # Try calibrated brier
        brier_calibrated = lstm_head_meta.get('brier_score_calibrated')
        if brier_calibrated is not None:
            try:
                return float(brier_calibrated)
            except (TypeError, ValueError):
                pass

    # Fallback to RF metrics
    rf_metrics = model_metadata.get('rf_metrics')
    if isinstance(rf_metrics, dict):
        brier = rf_metrics.get('brier_score')
        if brier is not None:
            try:
                return float(brier)
            except (TypeError, ValueError):
                pass

    return None


def classify_forecast_confidence(brier_score: float | None) -> str:
    """Classify forecast confidence from Brier score.

    Args:
        brier_score: Brier score or None

    Returns:
        'high', 'medium', 'low', or 'unknown'
    """
    if brier_score is None:
        return 'unknown'
    if brier_score <= CONFIDENCE_HIGH_THRESHOLD:
        return 'high'
    if brier_score <= CONFIDENCE_MEDIUM_THRESHOLD:
        return 'medium'
    return 'low'


def should_block_publication(
    brier_score: float | None,
    threshold: float = BRIER_BLOCK_THRESHOLD,
) -> tuple[bool, str | None]:
    """Determine if publication should be blocked based on Brier score.

    Args:
        brier_score: Brier score or None
        threshold: Block threshold (default from env var)

    Returns:
        (blocked, reason) — reason is None if not blocked
    """
    if brier_score is None:
        if os.getenv('BLOCK_ON_UNKNOWN_BRIER', 'true').lower() not in ('false', '0', 'off', 'no'):
            return (True, 'brier_score_unknown_publication_blocked')
        return (False, None)
    if brier_score > threshold:
        reason = f'brier_score_{brier_score:.3f}_exceeds_threshold_{threshold:.3f}'
        return (True, reason)
    return (False, None)


def compute_conformal_interval(
    probability: float,
    uncertainty_std: float | None,
    alpha: float = CONFORMAL_ALPHA,
) -> tuple[float, float]:
    """Compute prediction interval using normal approximation.

    This is the legacy fallback. Prefer ``compute_split_conformal_interval``
    with a calibrated ``ConformalCalibrator`` for distribution-free guarantees.

    Args:
        probability: Point estimate probability (0-1)
        uncertainty_std: Standard deviation of uncertainty, or None
        alpha: Miscoverage rate (default 0.1 → 90% coverage)

    Returns:
        (lower, upper) — clamped to [0, 1]
    """
    if uncertainty_std is None or not math.isfinite(uncertainty_std) or uncertainty_std < 0:
        uncertainty_std = DEFAULT_UNCERTAINTY_STD

    # z-score for (1 - alpha/2) quantile of standard normal
    # For alpha=0.1, z ≈ 1.645 (90% coverage)
    z = _norm_ppf(1.0 - alpha / 2.0)

    lower = probability - z * uncertainty_std
    upper = probability + z * uncertainty_std

    # Clamp to [0, 1]
    lower = max(0.0, min(1.0, lower))
    upper = max(0.0, min(1.0, upper))

    return (lower, upper)


def _norm_ppf(p: float) -> float:
    """Approximate inverse CDF (percent-point function) of standard normal.

    Uses a rational approximation (Beasley-Springer-Moro) without scipy.
    """
    if p <= 0.0:
        return -float('inf')
    if p >= 1.0:
        return float('inf')

    # Common values lookup
    _lookup = {
        0.90: 1.2816,
        0.95: 1.6449,
        0.975: 1.9600,
        0.99: 2.3263,
        0.995: 2.5758,
    }
    if p in _lookup:
        return _lookup[p]

    # Beasley-Springer-Moro algorithm
    a = [2.50662823884, -18.61500062529, 41.39119773534, -25.44106049637]
    b = [-8.47351093090, 23.08336743743, -21.06224101826, 3.13082909833]
    c = [0.3374754822726147, 0.9761690190917186, 0.1607979714918209,
         0.0276438810333863, 0.0038405729373609, 0.0003953396142645,
         0.0000324144662414, 0.0000021458912714]
    d = [0.0007648418702549, 0.0070797113112278, 0.04188589812614,
         0.16691402461438, 0.65947037966025, 2.53591467996089]

    plow = 0.08
    phigh = 1.0 - plow

    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        result = c[0]
        for i in range(1, 8):
            result = result * q + c[i]
        return result
    elif p <= phigh:
        q = p - 0.5
        r = q * q
        num = a[3]
        for i in range(2, -1, -1):
            num = num * r + a[i]
        num = num * r + 1.0
        den = b[3]
        for i in range(2, -1, -1):
            den = den * r + b[i]
        den = den * r + 1.0
        return q * (num / den)
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        result = c[0]
        for i in range(1, 8):
            result = result * q + c[i]
        return -result


def apply_uq_to_cells(
    cells: list[dict[str, Any]],
    model_metadata: dict[str, Any],
    calibrator: ConformalCalibrator | None = None,
) -> tuple[list[dict[str, Any]], UQResult]:
    """Apply uncertainty quantification to all grid cells.

    For each cell:
      - Extract probability and uncertainty_std
      - Compute conformal interval (split conformal if calibrator provided)
      - Set forecast_confidence, conformal_lower, conformal_upper, brier_score

    Args:
        cells: List of cell dicts
        model_metadata: Model metadata dict
        calibrator: Optional ConformalCalibrator for split conformal intervals

    Returns:
        (updated_cells, UQResult)
    """
    brier = compute_brier_score(model_metadata)
    confidence = classify_forecast_confidence(brier)
    blocked, reason = should_block_publication(brier, BRIER_BLOCK_THRESHOLD)

    for cell in cells:
        # Extract probability
        prob = cell.get('probability')
        if prob is None:
            prob = 0.5
        try:
            prob = float(prob)
        except (TypeError, ValueError):
            prob = 0.5

        # Extract uncertainty std
        unc_std = cell.get('uncertainty_std')
        if unc_std is not None:
            try:
                unc_std = float(unc_std)
            except (TypeError, ValueError):
                unc_std = None
        else:
            # Try uncertainty span as fallback
            unc_span = cell.get('uncertainty_span')
            if unc_span is not None:
                try:
                    unc_span = float(unc_span)
                    unc_std = unc_span / (2.0 * _norm_ppf(1.0 - CONFORMAL_ALPHA / 2.0))
                except (TypeError, ValueError):
                    unc_std = None

        # Compute conformal interval
        if calibrator is not None and calibrator.is_calibrated:
            lower, upper = compute_split_conformal_interval(prob, calibrator)
        else:
            lower, upper = compute_conformal_interval(prob, unc_std, CONFORMAL_ALPHA)

        cell['forecast_confidence'] = confidence
        cell['brier_score'] = brier
        cell['conformal_lower'] = lower
        cell['conformal_upper'] = upper

        # If publication is blocked, clear eligibility
        if blocked:
            cell['public_eligible'] = False
            cell['risk_score'] = 0
            cell['runout_seed'] = False
            existing_reasons = cell.get('public_mask_reasons', [])
            if isinstance(existing_reasons, list):
                existing_reasons = existing_reasons + [reason]
            else:
                existing_reasons = [reason]
            cell['public_mask_reasons'] = existing_reasons

    uq_result = UQResult(
        brier_score=brier,
        forecast_confidence=confidence,
        publish_blocked=blocked,
        block_reason=reason,
        conformal_alpha=CONFORMAL_ALPHA,
    )

    return cells, uq_result
