"""Candidate extraction — not yet wired to production.

``backend.daily_inference`` is the only governed runtime entrypoint.  The
modules in this package are retained for parity work and may not be launched
as a second publication path until they satisfy the same cadence, contract,
and release gates.
"""
from __future__ import annotations

CANONICAL_RUNTIME_ENTRYPOINT = 'backend.daily_inference'


def require_canonical_runtime(requested_entrypoint: str) -> None:
    """Fail closed when the extracted candidate path is launched directly."""
    if requested_entrypoint != CANONICAL_RUNTIME_ENTRYPOINT:
        raise RuntimeError(
            f'{requested_entrypoint} is a non-production extracted path; '
            f'use {CANONICAL_RUNTIME_ENTRYPOINT} until parity is approved'
        )


# Do not eagerly import the extracted modules here. Importing them makes the
# non-canonical publication graph appear live and can trigger circular imports
# (the extracted orchestrator imports ``require_canonical_runtime`` above).
# Research-only callers must import a submodule explicitly; its CLI entrypoint
# remains fail-closed.
