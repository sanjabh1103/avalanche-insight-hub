"""Postprocessor adapter interfaces (Phase 8-prep).

Defines adapter interfaces for avapro, aggregatepro, and qmah post-processors.

Per Imp_plan.md Phase 8:
  - Run avapro on native PRO/SMET outputs.
  - Map problem outputs to Partner-approved local terminology.
  - Run aggregatepro by region, climate class, elevation band, aspect, horizon.
  - Evaluate qmah separately because it is a distinct, evolving repository.
  - Keep qmah research/shadow-only until compatibility, licence and maintenance
    gates pass.
  - Never convert these outputs automatically into official danger levels.

This module is additive and does not modify any denylisted file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# Postprocessor status
# ---------------------------------------------------------------------------

POSTPROCESSOR_STATUS = frozenset({
    'not_installed',        # Postprocessor binary/package not available
    'shadow',               # Running in shadow/research mode only
    'operational',          # Fully operational (requires Partner approval)
    'failed',               # Execution failed
    'inputs_unavailable',   # Inputs absent; never interpreted as completion
})

LEGACY_POSTPROCESSOR_STATUS = frozenset({'skipped'})


def normalize_postprocessor_status(status: object) -> str:
    """Map the legacy skipped value without conflating it with completion."""
    if status == 'skipped':
        return 'inputs_unavailable'
    if not isinstance(status, str) or status not in POSTPROCESSOR_STATUS:
        raise ValueError(
            f'Invalid postprocessor status {status!r}; '
            f'valid={sorted(POSTPROCESSOR_STATUS)}'
        )
    return status


# ---------------------------------------------------------------------------
# Common result structure
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PostprocessorResult:
    """Result from a postprocessor run."""
    postprocessor: str              # 'avapro', 'aggregatepro', 'qmah'
    status: str                     # One of POSTPROCESSOR_STATUS
    output_paths: tuple[str, ...] = ()
    problem_types: tuple[str, ...] = ()
    error: str | None = None
    is_advisory_only: bool = True   # Must always be True until Partner approves
    provenance: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> list[str]:
        """Validate the result. Returns list of errors (empty = valid)."""
        errors: list[str] = []
        if self.postprocessor not in ('avapro', 'aggregatepro', 'qmah'):
            errors.append(f'PostprocessorResult: invalid postprocessor "{self.postprocessor}"')
        if self.status not in POSTPROCESSOR_STATUS:
            errors.append(
                f'PostprocessorResult: invalid status "{self.status}". '
                f'Valid: {sorted(POSTPROCESSOR_STATUS)}'
            )
        if not self.is_advisory_only:
            errors.append(
                'PostprocessorResult: is_advisory_only must be True. '
                'Never convert postprocessor outputs automatically into official danger levels.'
            )
        return errors

    def validate_output_paths(self, output_root: Path) -> list[str]:
        """Reject output paths that escape the declared postprocessor root.

        Adapters are interfaces today, but their result paths will eventually
        be consumed by release manifests. Validate containment here so an
        adapter cannot smuggle absolute, traversal, or symlinked paths into a
        later artifact bundle.
        """
        errors: list[str] = []
        root = Path(output_root).resolve(strict=False)
        for raw_path in self.output_paths:
            if not isinstance(raw_path, str) or not raw_path.strip():
                errors.append('PostprocessorResult: output paths must be non-empty strings')
                continue
            relative = Path(raw_path)
            if relative.is_absolute() or '..' in relative.parts:
                errors.append(
                    f'PostprocessorResult: output path must be relative and contained: {raw_path!r}'
                )
                continue
            candidate = root / relative
            current = root
            symlink_found = False
            for component in relative.parts:
                current = current / component
                if current.is_symlink():
                    symlink_found = True
                    break
            if symlink_found:
                errors.append(
                    f'PostprocessorResult: symlinked output path is not allowed: {raw_path!r}'
                )
                continue
            try:
                if not candidate.resolve(strict=False).is_relative_to(root):
                    errors.append(
                        f'PostprocessorResult: output path escapes declared root: {raw_path!r}'
                    )
            except OSError as exc:
                errors.append(
                    f'PostprocessorResult: cannot resolve output path {raw_path!r}: {exc}'
                )
        return errors


# ---------------------------------------------------------------------------
# avapro adapter interface
# ---------------------------------------------------------------------------

class AvaproAdapter(Protocol):
    """Interface for avapro (Avalanche Problem Prediction) adapter.

    Per Imp_plan.md Phase 8:
      - Run avapro on native PRO/SMET outputs.
      - Map problem outputs to Partner-approved local terminology.
    """

    def run(
        self,
        *,
        pro_files: list[Path],
        smet_files: list[Path],
        region_key: str,
        elevation_band: str,
        aspect_class: str,
    ) -> PostprocessorResult:
        """Run avapro on native SNOWPACK outputs.

        Args:
            pro_files: List of .pro files to process.
            smet_files: List of .smet files to process.
            region_key: Region identifier.
            elevation_band: Elevation band name.
            aspect_class: Aspect class (N/E/S/W).

        Returns:
            PostprocessorResult with problem types and output paths.
        """
        ...


class DefaultAvaproAdapter:
    """Default avapro adapter (not installed — returns not_installed status)."""

    def run(
        self,
        *,
        pro_files: list[Path],
        smet_files: list[Path],
        region_key: str,
        elevation_band: str,
        aspect_class: str,
    ) -> PostprocessorResult:
        return PostprocessorResult(
            postprocessor='avapro',
            status='not_installed',
            error='avapro is not installed. Install from AWSOME/snowpacktools.',
            is_advisory_only=True,
        )


# ---------------------------------------------------------------------------
# aggregatepro adapter interface
# ---------------------------------------------------------------------------

class AggregateproAdapter(Protocol):
    """Interface for aggregatepro (Profile Aggregation) adapter.

    Per Imp_plan.md Phase 8:
      - Run aggregatepro by region, climate class, elevation band, aspect,
        forecast horizon.
      - Test aggregation sensitivity under sparse profile coverage.
    """

    def run(
        self,
        *,
        pro_files: list[Path],
        region_key: str,
        climate_class: str,
        elevation_band: str,
        aspect_class: str,
        forecast_horizon_h: int,
    ) -> PostprocessorResult:
        """Run aggregatepro on native SNOWPACK outputs.

        Args:
            pro_files: List of .pro files to aggregate.
            region_key: Region identifier.
            climate_class: Climate class (maritime, transition, continental, polar_dry).
            elevation_band: Elevation band name.
            aspect_class: Aspect class (N/E/S/W).
            forecast_horizon_h: Forecast horizon in hours.

        Returns:
            PostprocessorResult with representative profile outputs.
        """
        ...


class DefaultAggregateproAdapter:
    """Default aggregatepro adapter (not installed — returns not_installed status)."""

    def run(
        self,
        *,
        pro_files: list[Path],
        region_key: str,
        climate_class: str,
        elevation_band: str,
        aspect_class: str,
        forecast_horizon_h: int,
    ) -> PostprocessorResult:
        return PostprocessorResult(
            postprocessor='aggregatepro',
            status='not_installed',
            error='aggregatepro is not installed. Install from snowpacktools.',
            is_advisory_only=True,
        )


# ---------------------------------------------------------------------------
# qmah adapter interface
# ---------------------------------------------------------------------------

class QmahAdapter(Protocol):
    """Interface for qmah (Quantitative Module of Avalanche Hazard) adapter.

    Per Imp_plan.md Phase 8:
      - Evaluate qmah separately because it is a distinct, evolving repository.
      - Keep qmah research/shadow-only until compatibility, licence and
        maintenance gates pass.
    """

    def run(
        self,
        *,
        pro_files: list[Path],
        smet_files: list[Path],
        region_key: str,
        elevation_band: str,
        aspect_class: str,
    ) -> PostprocessorResult:
        """Run qmah on native SNOWPACK outputs.

        Args:
            pro_files: List of .pro files to process.
            smet_files: List of .smet files to process.
            region_key: Region identifier.
            elevation_band: Elevation band name.
            aspect_class: Aspect class (N/E/S/W).

        Returns:
            PostprocessorResult with stability indices and hazard metrics.
        """
        ...


class DefaultQmahAdapter:
    """Default qmah adapter (shadow-only — returns shadow status).

    qmah is kept research/shadow-only until compatibility, licence and
    maintenance gates pass.
    """

    def run(
        self,
        *,
        pro_files: list[Path],
        smet_files: list[Path],
        region_key: str,
        elevation_band: str,
        aspect_class: str,
    ) -> PostprocessorResult:
        return PostprocessorResult(
            postprocessor='qmah',
            status='shadow',
            error='qmah is in shadow/research mode. '
                  'Compatibility, licence and maintenance gates must pass before operational use.',
            is_advisory_only=True,
        )


# ---------------------------------------------------------------------------
# Problem type mapping (Partner-approved local terminology)
# ---------------------------------------------------------------------------

# EAWS standard problem types → Partner-approved local terminology mapping
# This is a candidate mapping — must be reviewed by Partner
PROBLEM_TYPE_MAPPING: dict[str, str] = {
    'new_snow': 'storm_slab',
    'wind_slab': 'wind_slab',
    'persistent_weak_layer': 'persistent_weak_layer',
    'wet_snow': 'wet_snow',
}

# Reverse mapping
REVERSE_PROBLEM_TYPE_MAPPING: dict[str, str] = {v: k for k, v in PROBLEM_TYPE_MAPPING.items()}


def map_problem_to_local_terminology(eaws_problem: str) -> str:
    """Map an EAWS standard problem type to Partner-approved local terminology.

    This is a candidate mapping — must be reviewed by Partner before operational use.
    """
    return PROBLEM_TYPE_MAPPING.get(eaws_problem, eaws_problem)
