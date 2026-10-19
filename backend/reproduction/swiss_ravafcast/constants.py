from __future__ import annotations

from pathlib import Path


REPRODUCTION_SCHEMA_VERSION = 'swiss_ravafcast_reproduction_v1'
USAGE_BOUNDARY = 'research_only'

DATASET_DOI = '10.16904/envidat.330'
ENVIDAT_PACKAGE_ID = f'doi:{DATASET_DOI}'
ENVIDAT_DATASET_PAGE = 'https://www.envidat.ch/metadata/weather-snowpack-danger_ratings-data'
ENVIDAT_CKAN_PACKAGE_SHOW = 'https://www.envidat.ch/api/3/action/package_show'

DATA_ROOT = Path('backend/data/swiss_envidat')
WARNING_REGION_ROOT = Path('backend/data/swiss_warning_regions')
ARTIFACT_ROOT = Path('backend/artifacts/reproduction/swiss_ravafcast')

RF1_RESOURCE_KEY = 'data_rf1_forecast'
RF2_RESOURCE_KEY = 'data_rf2_tidy'
REQUIRED_RESOURCE_KEYS = (RF1_RESOURCE_KEY, RF2_RESOURCE_KEY)

REPRODUCTION_NON_GOALS = (
    'no_production_scoring',
    'no_model_status_mutation',
    'no_daily_inference_change',
    'no_train_model_change',
    'no_supabase_migration',
    'no_public_route_change',
)


def research_boundary_payload() -> dict[str, object]:
    return {
        'usage_boundary': USAGE_BOUNDARY,
        'schema_version': REPRODUCTION_SCHEMA_VERSION,
        'non_goals': list(REPRODUCTION_NON_GOALS),
    }

