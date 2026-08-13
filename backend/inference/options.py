"""Proof mode options dataclass — shared by inference modules."""
from __future__ import annotations

from dataclasses import dataclass, field


class ProofModeOptions:
    enabled: bool = False
    profile: str = 'standard'
    skip_tree_shap: bool = False
    skip_shap_cache: bool = False
    skip_runout_generation: bool = False
    skip_compatibility_write: bool = False
    emit_stage_metrics: bool = False

    def as_metadata(self) -> dict[str, object]:
        return {
            'lifeboat_mode': self.enabled,
            'lifeboat_profile': self.profile if self.enabled else None,
            'skip_tree_shap': self.skip_tree_shap,
            'skip_shap_cache': self.skip_shap_cache,
            'skip_runout_generation': self.skip_runout_generation,
            'skip_compatibility_write': self.skip_compatibility_write,
            'emit_stage_metrics': self.emit_stage_metrics,
        }