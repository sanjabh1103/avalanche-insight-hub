"""Fail-closed promotion decisions for research and shadow model outputs.

Advanced sensors and models may be enabled for diagnostics before they are
allowed to influence an authoritative product.  Promotion therefore requires
all of the following explicit evidence:

* the feature switch is enabled;
* external calibration has been completed;
* held-out validation has passed; and
* an explicit promotion gate has been recorded.

The environment defaults are intentionally false.  Callers can pass booleans
explicitly in tests or in a future signed gate manifest.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_flag(name: str) -> bool:
    return os.getenv(name, 'false').strip().lower() in {'1', 'true', 'yes', 'on'}


@dataclass(frozen=True)
class ShadowPromotionStatus:
    """Auditable decision for whether a candidate may affect active outputs."""

    model_key: str
    feature_enabled: bool
    external_calibrated: bool
    held_out_validated: bool
    promotion_gate_passed: bool
    shadow_only: bool
    reason: str

    @property
    def active(self) -> bool:
        return not self.shadow_only

    def to_dict(self) -> dict[str, object]:
        return {
            'model_key': self.model_key,
            'feature_enabled': self.feature_enabled,
            'external_calibrated': self.external_calibrated,
            'held_out_validated': self.held_out_validated,
            'promotion_gate_passed': self.promotion_gate_passed,
            'shadow_only': self.shadow_only,
            'active': self.active,
            'reason': self.reason,
        }


def evaluate_shadow_promotion(
    model_key: str,
    *,
    feature_enabled: bool,
    external_calibrated: bool | None = None,
    held_out_validated: bool | None = None,
    promotion_gate_passed: bool | None = None,
) -> ShadowPromotionStatus:
    """Evaluate a fail-closed promotion decision.

    When an evidence boolean is omitted, it is read from the model-specific
    environment variable, for example ``PINN_HELD_OUT_VALIDATED``.  Explicit
    arguments take precedence and make the decision deterministic in tests.
    """
    prefix = ''.join(char if char.isalnum() else '_' for char in model_key.upper())
    calibrated = (
        _env_flag(f'{prefix}_EXTERNAL_CALIBRATED')
        if external_calibrated is None
        else bool(external_calibrated)
    )
    validated = (
        _env_flag(f'{prefix}_HELD_OUT_VALIDATED')
        if held_out_validated is None
        else bool(held_out_validated)
    )
    promoted = (
        _env_flag(f'{prefix}_PROMOTION_GATE_PASSED')
        if promotion_gate_passed is None
        else bool(promotion_gate_passed)
    )

    failures: list[str] = []
    if not feature_enabled:
        failures.append('feature_disabled')
    if not calibrated:
        failures.append('external_calibration_missing')
    if not validated:
        failures.append('held_out_validation_missing')
    if not promoted:
        failures.append('promotion_gate_missing')

    shadow_only = bool(failures)
    return ShadowPromotionStatus(
        model_key=model_key,
        feature_enabled=bool(feature_enabled),
        external_calibrated=calibrated,
        held_out_validated=validated,
        promotion_gate_passed=promoted,
        shadow_only=shadow_only,
        reason='promoted' if not shadow_only else f"shadow_only:{','.join(failures)}",
    )
