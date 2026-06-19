"""Swiss RAvaFcast / EnviDat reproduction lane.

This package is intentionally isolated from `daily_inference.py`,
`train_model.py`, Supabase migrations, and public forecast routes.
"""

from backend.reproduction.swiss_ravafcast.constants import (
    REPRODUCTION_SCHEMA_VERSION,
    USAGE_BOUNDARY,
)

__all__ = [
    'REPRODUCTION_SCHEMA_VERSION',
    'USAGE_BOUNDARY',
]

