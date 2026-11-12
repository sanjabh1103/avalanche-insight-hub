"""Partner literature-to-contract matrix — P8.

Extracts task/geo/unit/inputs/scale from each Partner/Partner research paper
to build a comparison matrix against the system's implementation contract.

P8 exit gate: A matrix exists with one row per paper, columns for
task, geography, prediction unit, inputs, danger scale, and
conformance status against the Partner 5-level contract.

P6 (proactive): DOIs are stored in each LiteratureEntryV1 but are NOT
resolved or verified against actual publications. A future DOI resolution
verification workflow should cross-check title/authors against the resolved
DOI to ensure bibliographic details are correct.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LiteratureEntryV1:
    """A single research paper entry in the literature-to-contract matrix.

    P8 contract: task, geography, prediction_unit, inputs, danger_scale,
    and conformance status against the Partner 5-level contract.

    The `verified` field distinguishes entries whose bibliographic details
    (title, authors, year, source) have been confirmed against the actual
    publication from entries that are unverified placeholders.
    """

    paper_id: str  # Short identifier (e.g., 'singh_2005')
    title: str
    authors: str
    year: int
    source: str  # Journal/conference

    # Extracted contract dimensions
    task: str  # What the paper predicts (e.g., 'avalanche_day', 'danger_level')
    geography: str  # Where (e.g., 'Pir Panjal', 'NW Himalaya')
    prediction_unit: str  # Unit of prediction (e.g., 'daily', 'per_station')
    inputs: list[str]  # Input features used
    danger_scale: str  # Scale used (e.g., 'binary', '3-level', '5-level')

    # Conformance against Partner 5-level contract
    conformance_status: str  # 'conformant', 'partial', 'non_conformant', 'unverified'
    conformance_notes: str

    # Verification status — False means bibliographic details are unverified
    verified: bool = False
    # G9: Granular verification status for asserted fields
    verification_status: str = 'verified'  # 'verified', 'asserted_unverified', 'unverified'
    # G9: Source type — distinguishes papers from datasets, operational docs, code
    source_type: str = 'paper'  # 'paper', 'dataset', 'operational', 'code'

    # Metadata
    doi: str | None = None
    source_url: str | None = None  # G9: URL for non-DOI sources
    source_hash: str | None = None  # G9: Hash of source content for verification
    # Bibliographic identity and byte-level binding are separate proof layers.
    source_binding_status: str = 'unverified'  # content_verified, fixture_only, identity_only, unverified
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def decision_usable(self) -> bool:
        """Whether this entry may influence a lane or strategic decision."""
        return (
            self.verified
            and self.verification_status == 'verified'
            and self.source_binding_status == 'content_verified'
            and isinstance(self.source_url, str)
            and bool(self.source_url.strip())
            and isinstance(self.source_hash, str)
            and len(self.source_hash) == 64
        )


# The literature matrix — Partner/Partner publications on Himalayan avalanche forecasting.
#
# VERIFICATION STATUS:
#   - perezguillén_2022: VERIFIED (DOI confirmed, EnviDat dataset exists)
#   - Partner_bulletin_2024: VERIFIED (operational document, not a paper, but real)
#   - singh_2005, singh_2008, sharma_2010, gusain_2016: UNVERIFIED
#     These entries were created with plausible-sounding bibliographic details
#     that could NOT be confirmed against actual publications. The titles,
#     authors, years, and sources may be inaccurate or fabricated.
#     They are retained as unverified placeholders with verified=False.
#     New entries must be verified against the actual publication before adding.
LITERATURE_MATRIX: list[LiteratureEntryV1] = [
    LiteratureEntryV1(
        paper_id='singh_2005',
        title='UNVERIFIED — previously claimed "A knowledge-based expert system for avalanche forecasting in the Himalayas"',
        authors='UNVERIFIED — previously claimed "Singh, Ganju"',
        year=2005,
        source='UNVERIFIED — previously claimed "Cold Regions Science and Technology"',
        task='avalanche_day',
        geography='Pir Panjal, NW Himalaya',
        prediction_unit='daily per station',
        inputs=['snow_meteorological', 'snow_profile', 'synoptic_weather'],
        danger_scale='binary (avalanche/no_avalanche)',
        conformance_status='unverified',
        conformance_notes='Bibliographic details unverified. Binary output does not map to 5-level Partner scale. '
                          'Must be verified against actual publication before use in decision-making.',
        verified=False,
        verification_status='asserted_unverified',
        source_type='paper',
        source_binding_status='unverified',
        notes='Entry created with plausible-sounding details that could not be confirmed. DOI was also unverified.',
    ),
    LiteratureEntryV1(
        paper_id='singh_2008',
        title='UNVERIFIED — previously claimed "Avalanche prediction using statistical and neural network models"',
        authors='UNVERIFIED — previously claimed "Singh, Sood, Gupta"',
        year=2008,
        source='UNVERIFIED — previously claimed "Natural Hazards"',
        task='avalanche_day',
        geography='Pir Panjal, NW Himalaya',
        prediction_unit='daily per station',
        inputs=['snow_meteorological', 'temperature', 'wind', 'new_snow_depth'],
        danger_scale='binary (avalanche/no_avalanche)',
        conformance_status='unverified',
        conformance_notes='Bibliographic details unverified. Binary classification does not produce 5-level danger ratings. '
                          'Must be verified against actual publication before use.',
        verified=False,
        verification_status='asserted_unverified',
        source_type='paper',
        source_binding_status='unverified',
        notes='Entry created with plausible-sounding details that could not be confirmed.',
    ),
    LiteratureEntryV1(
        paper_id='sharma_2010',
        title='UNVERIFIED — previously claimed "Neural network models for avalanche danger prediction in Himalayan region"',
        authors='UNVERIFIED — previously claimed "Sharma, Ganju"',
        year=2010,
        source='UNVERIFIED — previously claimed "Journal of Earth System Science"',
        task='danger_level',
        geography='NW Himalaya (multiple zones)',
        prediction_unit='daily per zone',
        inputs=['snow_meteorological', 'snow_profile', 'terrain_features'],
        danger_scale='4-level (1-4)',
        conformance_status='unverified',
        conformance_notes='Bibliographic details unverified. If real, uses 4-level scale (1-4), not full 5-level Partner scale. '
                          'Must be verified against actual publication before use.',
        verified=False,
        verification_status='asserted_unverified',
        source_type='paper',
        source_binding_status='unverified',
        notes='Entry created with plausible-sounding details that could not be confirmed.',
    ),
    LiteratureEntryV1(
        paper_id='gusain_2016',
        title='UNVERIFIED — previously claimed "Snowpack characteristics and avalanche danger in the Indian Himalaya"',
        authors='UNVERIFIED — previously claimed "Gusain, Mishra, Singh"',
        year=2016,
        source='UNVERIFIED — previously claimed "Annals of Glaciology"',
        task='danger_level',
        geography='Pir Panjal, Great Himalaya, Ladakh',
        prediction_unit='daily per zone',
        inputs=['snow_profile', 'snow_meteorological', 'SNOWPACK_simulation'],
        danger_scale='5-level (1-5)',
        conformance_status='unverified',
        conformance_notes='Bibliographic details unverified. If real, would be conformant with 5-level Partner scale. '
                          'Must be verified against actual publication before claiming conformance.',
        verified=False,
        verification_status='asserted_unverified',
        source_type='paper',
        source_binding_status='unverified',
        notes='Entry created with plausible-sounding details that could not be confirmed.',
    ),
    LiteratureEntryV1(
        paper_id='Partner_bulletin_2024',
        title='Partner Avalanche Warning Bulletin operational methodology',
        authors='Partner (institutional)',
        year=2024,
        source='Partner Public Bulletins',
        task='danger_level',
        geography='All Himalayan zones (J&K, Ladakh, HP, UK, Sikkim)',
        prediction_unit='daily per district per altitude band',
        inputs=['snow_meteorological', 'snow_profile', 'terrain_features', 'expert_judgment'],
        danger_scale='5-level (1-5, color-coded)',
        conformance_status='conformant',
        conformance_notes='The operational Partner bulletin uses the full 5-level scale '
                          'with color codes (Green/Yellow/Orange/Red/Black). '
                          'This is the canonical reference for the system contract. '
                          'Verified via live bulletin fixture (Partner_AWB_30-Apr-2026.pdf).',
        verified=True,
        verification_status='verified',
        source_type='operational',
        source_url='https://www.Partner.gov.in/Partner/sites/default/files/avalanche_warning_bulletin/Partner_AWB_30-Apr-2026.pdf',
        source_hash='0cf86ec59b4c8d4a82b63179588a098aaa5ad24f032997c1772f626b3b5792bd',
        source_binding_status='fixture_only',
        notes='Bibliographic/operational identity is verified; the local fixture is content-bound, but live URL bytes are not verified.',
    ),
    LiteratureEntryV1(
        paper_id='perezguillén_2022',
        title='Weather, snowpack and danger ratings data for automated avalanche danger level predictions',
        authors='Pérez-Guillén, Techel, Hendrick, Volpi, van Herwijnen, Olevski, Obozinski, Pérez-Cruz, Schweizer',
        year=2022,
        source='EnviDat (Swiss reference)',
        task='danger_level',
        geography='Swiss Alps (reference, not Himalayan)',
        prediction_unit='daily per warning region',
        inputs=['snow_meteorological', 'snow_profile', 'terrain_features'],
        danger_scale='4-level (1-4, EAWS)',
        conformance_status='non_conformant',
        conformance_notes='Swiss RAvaFcast reference uses 4-level EAWS scale. '
                          'Level 5 is merged into Level 4 (counts UNVERIFIED — data file not present). '
                          'Cannot be directly used as Partner labels without addressing Level 5 gap. '
                          'See P7 Swiss conformance decision for details.',
        doi='10.16904/envidat.330',
        source_url='https://www.envidat.ch/metadata/weather-snowpack-danger_ratings-data',
        verified=True,
        verification_status='verified',
        source_type='dataset',
        source_binding_status='identity_only',
        notes='Dataset identity and DOI are asserted; resource bytes and license remain unverified in this checkout.',
    ),
]


def build_literature_matrix() -> list[LiteratureEntryV1]:
    """Return the full literature-to-contract matrix.

    P8 exit gate: A matrix exists with one row per paper, columns for
    task, geography, prediction unit, inputs, danger scale, and
    conformance status.
    """
    return LITERATURE_MATRIX


def get_conformant_papers() -> list[LiteratureEntryV1]:
    """Return only VERIFIED papers that are conformant with the Partner 5-level contract."""
    return [p for p in LITERATURE_MATRIX if p.conformance_status == 'conformant' and p.verified]


def get_partial_papers() -> list[LiteratureEntryV1]:
    """Return VERIFIED papers with partial conformance (e.g., binary or 4-level)."""
    return [p for p in LITERATURE_MATRIX if p.conformance_status == 'partial' and p.verified]


def get_non_conformant_papers() -> list[LiteratureEntryV1]:
    """Return VERIFIED papers that are non-conformant with the Partner 5-level contract."""
    return [p for p in LITERATURE_MATRIX if p.conformance_status == 'non_conformant' and p.verified]


def get_unverified_papers() -> list[LiteratureEntryV1]:
    """Return papers whose bibliographic details are unverified."""
    return [p for p in LITERATURE_MATRIX if not p.verified]


def build_matrix_summary() -> dict[str, Any]:
    """Build a summary of the literature matrix for the Partner decision packet.

    P8 exit gate: The summary reports conformance counts and identifies
    which papers can serve as reference for the 5-level Partner contract.
    Unverified entries are reported separately and excluded from conformance counts.

    P8 (proactive): This function uses len() for all counts, which returns 0
    for empty lists. No division operations are performed, so it is safe
    even if LITERATURE_MATRIX is empty.
    """
    conformant = get_conformant_papers()
    partial = get_partial_papers()
    non_conformant = get_non_conformant_papers()
    unverified = get_unverified_papers()

    # Collect all unique danger scales (from verified entries only)
    danger_scales = sorted({p.danger_scale for p in LITERATURE_MATRIX if p.verified})

    # Collect all unique geographies (from verified entries only)
    geographies = sorted({p.geography for p in LITERATURE_MATRIX if p.verified})

    # Collect all unique input types (from verified entries only)
    all_inputs: set[str] = set()
    for p in LITERATURE_MATRIX:
        if p.verified:
            all_inputs.update(p.inputs)
    input_types = sorted(all_inputs)

    verified_count = sum(1 for p in LITERATURE_MATRIX if p.verified)
    decision_eligible = [p for p in LITERATURE_MATRIX if p.decision_usable]

    return {
        'schema_version': 'Partner_literature_matrix_v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'total_papers': len(LITERATURE_MATRIX),
        'verified_count': verified_count,
        'unverified_count': len(unverified),
        'decision_eligible_count': len(decision_eligible),
        'decision_eligible_entries': [p.paper_id for p in decision_eligible],
        'verified_without_content_binding': [
            p.paper_id for p in LITERATURE_MATRIX if p.verified and not p.decision_usable
        ],
        'conformant_count': len(conformant),
        'partial_count': len(partial),
        'non_conformant_count': len(non_conformant),
        'danger_scales_observed': danger_scales,
        'geographies_covered': geographies,
        'input_types_observed': input_types,
        'conformant_papers': [p.paper_id for p in conformant],
        'partial_papers': [p.paper_id for p in partial],
        'non_conformant_papers': [p.paper_id for p in non_conformant],
        'unverified_papers': [p.paper_id for p in unverified],
        'key_finding': (
            f'{len(conformant)} of {verified_count} verified sources use the full 5-level Partner scale. '
            f'{len(partial)} use partial scales (binary or 4-level). '
            f'{len(non_conformant)} use non-conformant scales (Swiss 4-level EAWS). '
            f'{len(unverified)} entries have unverified bibliographic details and are excluded from conformance counts. '
            f'{len(decision_eligible)} entries are content-bound and eligible to influence decisions.'
        ),
        'entries': [p.to_dict() for p in LITERATURE_MATRIX],
    }


def save_matrix_summary(summary: dict[str, Any], path: Path) -> None:
    """Save matrix summary to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))


def load_matrix_summary(path: Path) -> dict[str, Any] | None:
    """Load a previously saved matrix summary fail-closed."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(payload, dict):
            raise ValueError('E030_malformed_evidence: literature matrix must be a JSON object')
        return payload
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'literature matrix load failed: {exc}') from exc
