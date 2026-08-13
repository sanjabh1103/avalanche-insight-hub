"""Build unconfirmed public-source Himalayan candidate cases.

These rows are meeting inputs only. They are not grounded Himalayan truth,
training labels, production evidence, or operational warning authority.
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.common.supabase_io import has_supabase_credentials, rest_upsert


REGION_KEY = 'himalayas_real_candidate'
CLAIM_BOUNDARY = 'publication_or_open_data_unconfirmed'


PUBLICATION_CANDIDATES: list[dict[str, Any]] = [
    {
        'slug': 'western-himalaya-2025-inventory-chandra-bhaga-upper-beas',
        'title': 'Western Himalaya 2025 inventory review: Chandra-Bhaga and Upper Beas',
        'case_type': 'model_gate',
        'region_name': 'Western Himalaya candidate inventory',
        'summary': 'Scientist should decide which event-level records from the 118-event inventory are suitable for grounded validation.',
        'source_citation': 'Abhinav and Sattar, Scientific Reports 15, Article 38093 (2025), https://www.nature.com/articles/s41598-025-22051-w',
        'source_note': 'The paper reports 118 avalanche events, with 86 from 2023. Use as an inventory candidate source until event-level rows are confirmed.',
        'event_year': 2025,
        'avalanche_problem_hint': 'not_assessed',
    },
    {
        'slug': 'draupadi-ka-danda-ii-2022-uttarakhand',
        'title': 'Draupadi Ka Danda II 2022 event confirmation candidate',
        'case_type': 'runout',
        'region_name': 'Uttarakhand candidate',
        'summary': 'Named fatal avalanche event cited as recent Western Himalaya context; requires scientist confirmation before validation use.',
        'source_citation': 'Abhinav and Sattar, Scientific Reports 15, Article 38093 (2025), https://www.nature.com/articles/s41598-025-22051-w',
        'source_note': 'Named in the Scientific Reports article as a notable recent fatal avalanche event in India.',
        'event_year': 2022,
        'avalanche_problem_hint': 'not_assessed',
    },
    {
        'slug': 'siachen-2021-ladakh',
        'title': 'Siachen 2021 event confirmation candidate',
        'case_type': 'runout',
        'region_name': 'Ladakh candidate',
        'summary': 'Named Siachen event candidate; requires partner/scientist confirmation and source row before validation use.',
        'source_citation': 'Abhinav and Sattar, Scientific Reports 15, Article 38093 (2025), https://www.nature.com/articles/s41598-025-22051-w',
        'source_note': 'The article lists Siachen glacier events including 2021 among notable recent fatal avalanche events.',
        'event_year': 2021,
        'avalanche_problem_hint': 'not_assessed',
    },
    {
        'slug': 'siachen-2019-ladakh',
        'title': 'Siachen 2019 event confirmation candidate',
        'case_type': 'runout',
        'region_name': 'Ladakh candidate',
        'summary': 'Named Siachen event candidate; requires partner/scientist confirmation and source row before validation use.',
        'source_citation': 'Abhinav and Sattar, Scientific Reports 15, Article 38093 (2025), https://www.nature.com/articles/s41598-025-22051-w',
        'source_note': 'The article lists Siachen glacier events including 2019 among notable recent fatal avalanche events.',
        'event_year': 2019,
        'avalanche_problem_hint': 'not_assessed',
    },
    {
        'slug': 'siachen-2016-ladakh',
        'title': 'Siachen 2016 event confirmation candidate',
        'case_type': 'runout',
        'region_name': 'Ladakh candidate',
        'summary': 'Named Siachen event candidate; requires partner/scientist confirmation and source row before validation use.',
        'source_citation': 'Abhinav and Sattar, Scientific Reports 15, Article 38093 (2025), https://www.nature.com/articles/s41598-025-22051-w',
        'source_note': 'The article lists Siachen glacier events including 2016 among notable recent fatal avalanche events.',
        'event_year': 2016,
        'avalanche_problem_hint': 'not_assessed',
    },
    {
        'slug': 'siachen-2012-ladakh',
        'title': 'Siachen 2012 event confirmation candidate',
        'case_type': 'runout',
        'region_name': 'Ladakh candidate',
        'summary': 'Named Siachen event candidate; requires partner/scientist confirmation and source row before validation use.',
        'source_citation': 'Abhinav and Sattar, Scientific Reports 15, Article 38093 (2025), https://www.nature.com/articles/s41598-025-22051-w',
        'source_note': 'The article lists Siachen glacier events including 2012 among notable recent fatal avalanche events.',
        'event_year': 2012,
        'avalanche_problem_hint': 'not_assessed',
    },
    {
        'slug': 'siachen-2010-ladakh',
        'title': 'Siachen 2010 event confirmation candidate',
        'case_type': 'runout',
        'region_name': 'Ladakh candidate',
        'summary': 'Named Siachen event candidate; requires partner/scientist confirmation and source row before validation use.',
        'source_citation': 'Abhinav and Sattar, Scientific Reports 15, Article 38093 (2025), https://www.nature.com/articles/s41598-025-22051-w',
        'source_note': 'The article lists Siachen glacier events including 2010 among notable recent fatal avalanche events.',
        'event_year': 2010,
        'avalanche_problem_hint': 'not_assessed',
    },
    {
        'slug': 'gulmarg-2024-jammu-kashmir',
        'title': 'Gulmarg 2024 event confirmation candidate',
        'case_type': 'runout',
        'region_name': 'Jammu and Kashmir candidate',
        'summary': 'Named Gulmarg event candidate; requires scientist confirmation before validation use.',
        'source_citation': 'Abhinav and Sattar, Scientific Reports 15, Article 38093 (2025), https://www.nature.com/articles/s41598-025-22051-w',
        'source_note': 'Named in the Scientific Reports article as a notable recent fatal avalanche event.',
        'event_year': 2024,
        'avalanche_problem_hint': 'not_assessed',
    },
    {
        'slug': 'mana-2025-uttarakhand',
        'title': 'Mana 2025 event confirmation candidate',
        'case_type': 'runout',
        'region_name': 'Uttarakhand candidate',
        'summary': 'Named Mana event candidate; requires scientist confirmation before validation use.',
        'source_citation': 'Abhinav and Sattar, Scientific Reports 15, Article 38093 (2025), https://www.nature.com/articles/s41598-025-22051-w',
        'source_note': 'Named in the Scientific Reports article as a notable recent fatal avalanche event.',
        'event_year': 2025,
        'avalanche_problem_hint': 'not_assessed',
    },
    {
        'slug': 'chamoli-2021-rock-ice-avalanche',
        'title': 'Chamoli 2021 rock-ice avalanche case-study candidate',
        'case_type': 'runout',
        'region_name': 'Chamoli / Garhwal candidate',
        'summary': 'High-priority case-study anchor for scientist discussion; not a snow-slab forecast truth row until the scientist team defines how to use it.',
        'source_citation': 'Journal of Rock Mechanics and Geotechnical Engineering 15(2), 296-308 (2023), https://www.sciencedirect.com/science/article/pii/S1674775522000956',
        'source_note': 'Peer-reviewed case study of the 7 February 2021 Chamoli rock and ice avalanche and long-runout disaster chain.',
        'event_year': 2021,
        'avalanche_problem_hint': 'not_assessed',
    },
    {
        'slug': 'icimod-rds-cryosphere-context',
        'title': 'ICIMOD RDS cryosphere context candidate source',
        'case_type': 'model_gate',
        'region_name': 'Hindu Kush Himalaya context source',
        'summary': 'Context source for station/weather and cryosphere data discovery; not an event-level validation case unless rows are downloaded and confirmed.',
        'source_citation': 'ICIMOD Regional Database System, https://rds.icimod.org/; ICIMOD cryosphere data release, https://www.icimod.org/cryosphere-data-release/',
        'source_note': 'Use as background data-source candidate. Registration and row-level provenance are required before validation use.',
        'event_year': None,
        'avalanche_problem_hint': 'not_assessed',
    },
]


def _stable_case_id(slug: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'avalanche-insight-hub:publication-candidate:{slug}'))


def build_candidate_case(definition: dict[str, Any]) -> dict[str, Any]:
    evidence = {
        'source_type': 'publication_or_open_data',
        'needs_scientist_confirmation': True,
        'training_eligible': False,
        'production_eligible': False,
        'grounded_himalayan_evidence': False,
        'synthetic_demo': False,
        'source_citation': definition['source_citation'],
        'source_note': definition['source_note'],
        'event_year': definition.get('event_year'),
        'avalanche_problem_hint': definition.get('avalanche_problem_hint', 'not_assessed'),
    }
    return {
        'id': _stable_case_id(str(definition['slug'])),
        'case_type': definition['case_type'],
        'status': 'pending',
        'priority': 5,
        'region_key': REGION_KEY,
        'region_name': definition['region_name'],
        'forecast_run_id': None,
        'forecast_grid_id': None,
        'forecast_hour': None,
        'cell_row': None,
        'cell_col': None,
        'title': definition['title'],
        'summary': definition['summary'],
        'evidence': evidence,
        'cell_snapshot': evidence.copy(),
        'model_metadata': {
            'source_type': 'publication_or_open_data',
            'training_eligible': False,
            'production_eligible': False,
            'grounded_himalayan_evidence': False,
        },
        'gate_key': 'publication_candidate_confirmation',
        'claim_boundary': CLAIM_BOUNDARY,
        'requires_two_reviewers': True,
        'signoff_scope': 'candidate_confirmation_only',
    }


def build_candidate_pack() -> dict[str, Any]:
    cases = [build_candidate_case(definition) for definition in PUBLICATION_CANDIDATES]
    return {
        'schema_version': 'publication-candidate-case-pack/v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'summary': {
            'case_count': len(cases),
            'region_key': REGION_KEY,
            'claim_boundary': CLAIM_BOUNDARY,
            'training_eligible': False,
            'production_eligible': False,
            'grounded_himalayan_evidence': False,
            'sync_default': 'dry_run_only',
        },
        'cases': cases,
    }


def sync_candidate_pack(pack: dict[str, Any]) -> dict[str, Any]:
    if not has_supabase_credentials():
        raise RuntimeError('SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for --sync-supabase')
    cases = [case for case in pack.get('cases', []) if isinstance(case, dict)]
    if cases:
        rest_upsert(
            'scientist_validation_cases',
            cases,
            on_conflict='id',
            returning='minimal',
            timeout_seconds=120,
        )
    return {
        'sync_status': 'ok',
        'cases_synced': len(cases),
        'claim_boundary': CLAIM_BOUNDARY,
        'training_eligible': False,
        'production_eligible': False,
        'grounded_himalayan_evidence': False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Build publication/open-data candidate cases for scientist confirmation.')
    parser.add_argument('--output', default='/private/tmp/himalayas-real-candidate-case-pack.json')
    parser.add_argument('--sync-supabase', action='store_true', help='Upsert candidate cases to scientist_validation_cases.')
    args = parser.parse_args(argv)

    pack = build_candidate_pack()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(pack, indent=2), encoding='utf-8')
    summary = {'output': str(output), **pack['summary']}
    if args.sync_supabase:
        summary['supabase_sync'] = sync_candidate_pack(pack)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
