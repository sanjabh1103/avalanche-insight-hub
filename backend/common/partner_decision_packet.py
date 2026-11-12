"""Partner decision packet — P10.

Aggregates all P1-P9 evidence into a single decision packet for the user.

P10 exit gate: A single decision packet presents the verified inventory,
parser coverage, Swiss limitations, literature conformance, and parallel
lane readiness. The packet answers the strategic question:
"Can we use deep research or guesstimation to complete the implementation?"

The answer is documented with evidence from P1-P9.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.common.Partner_bulletin_adapter import (
    Partner_DANGER_LEVELS,
    EAWS_DANGER_LEVELS,
    Partner_DANGER_SEMANTICS,
)
from backend.common.Partner_archive_discovery import (
    Partner_ARCHIVE_DISCOVERY_ENABLED,
    build_archive_manifest,
    load_archive_manifest,
)
from backend.common.Partner_public_candidate import build_candidate_manifest
from backend.common.Partner_coverage_audit import build_coverage_report
from backend.common.swiss_conformance_audit import (
    SWISS_METADATA_URL,
    SWISS_RF2_RESOURCE_URL,
    build_conformance_decision,
    load_swiss_verification_snapshot,
)
from backend.common.Partner_literature_matrix import build_matrix_summary
from backend.common.Partner_parallel_lanes import build_lane_summary

DEFAULT_PACKET_PATH = Path('artifacts/Partner/Partner_decision_packet.json')
PACKET_HASH_SCOPE = 'canonical_json_with_provenance.packet_sha256_null'


@dataclass
class PartnerDecisionPacket:
    """P10: The complete Partner decision packet aggregating P1-P9 evidence.

    This packet answers the strategic question about using deep research
    or guesstimation to complete the avalanche danger level prediction system.
    """

    schema_version: str = 'Partner_decision_packet_v1'
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # P1: Danger semantics
    danger_semantics: dict[str, Any] = field(default_factory=dict)

    # P2: Archive discovery
    archive_discovery: dict[str, Any] = field(default_factory=dict)

    # P3: PDF parser coverage
    parser_coverage: dict[str, Any] = field(default_factory=dict)

    # P4: Public candidate inventory
    public_candidates: dict[str, Any] = field(default_factory=dict)

    # P5: Coverage audit
    coverage_audit: dict[str, Any] = field(default_factory=dict)

    # P6: Swiss reference repair
    swiss_reference: dict[str, Any] = field(default_factory=dict)

    # P7: Swiss conformance decision
    swiss_conformance: dict[str, Any] = field(default_factory=dict)

    # P8: Literature matrix
    literature_matrix: dict[str, Any] = field(default_factory=dict)

    # P9: Parallel lanes
    parallel_lanes: dict[str, Any] = field(default_factory=dict)

    # Runtime authorization view derived from the lane/evidence state.
    execution_readiness: dict[str, Any] = field(default_factory=dict)

    # Known gaps — explicitly recorded so they cannot be silently reintroduced as done
    known_gaps: list[str] = field(default_factory=list)

    # Strategic answer
    strategic_answer: dict[str, Any] = field(default_factory=dict)

    # G16: Provenance — code revision, source hashes, test ledger
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    """Serialize packet data deterministically for hashing and persistence."""
    return (
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False, default=str)
        + '\n'
    ).encode('utf-8')


def _packet_hash_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the self-hash payload with its hash field neutralized."""
    normalized = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    provenance = normalized.setdefault('provenance', {})
    provenance['packet_hash_scope'] = PACKET_HASH_SCOPE
    provenance['packet_sha256'] = None
    return normalized


def verify_decision_packet_hash(payload: dict[str, Any]) -> bool:
    """Verify the self-excluding SHA-256 recorded in a saved packet."""
    if not isinstance(payload, dict):
        return False
    provenance = payload.get('provenance')
    if not isinstance(provenance, dict):
        return False
    expected = provenance.get('packet_sha256')
    if not isinstance(expected, str) or len(expected) != 64:
        return False
    try:
        int(expected, 16)
    except ValueError:
        return False
    actual = hashlib.sha256(_canonical_json_bytes(_packet_hash_payload(payload))).hexdigest()
    return actual == expected


def verify_decision_packet_provenance(
    payload: dict[str, Any],
    *,
    repo_root: Path | None = None,
) -> tuple[bool, list[str]]:
    """Verify every source/input hash recorded by a saved packet.

    The self-hash protects packet bytes; this second check protects the
    packet's claim that it was generated from the current source and input
    snapshot. Missing files, unsafe paths, malformed hashes, and content
    mismatches are all blockers.
    """
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["packet must be a JSON object"]
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        return False, ["provenance must be a JSON object"]
    root = (repo_root or Path(__file__).resolve().parents[2]).resolve()

    source_hashes = provenance.get("source_file_hashes")
    input_hashes = provenance.get("input_file_hashes")
    if not isinstance(source_hashes, dict):
        errors.append("source_file_hashes must be a JSON object")
    if not isinstance(input_hashes, dict):
        errors.append("input_file_hashes must be a JSON object")
    if isinstance(source_hashes, dict):
        recorded_count = provenance.get("source_file_count")
        if recorded_count != len(source_hashes):
            errors.append(
                f"source_file_count={recorded_count!r} does not match {len(source_hashes)} hashes"
            )

    for group_name, hashes in (("source", source_hashes), ("input", input_hashes)):
        if not isinstance(hashes, dict):
            continue
        for relative_name, expected in sorted(hashes.items()):
            if not isinstance(relative_name, str) or not relative_name.strip():
                errors.append(f"{group_name} hash has an invalid path key")
                continue
            relative_path = Path(relative_name)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                errors.append(f"{group_name} path is unsafe: {relative_name!r}")
                continue
            if not isinstance(expected, str) or len(expected) != 64:
                errors.append(f"{group_name} hash has invalid length: {relative_name}")
                continue
            try:
                int(expected, 16)
            except ValueError:
                errors.append(f"{group_name} hash is not hexadecimal: {relative_name}")
                continue
            candidate = root / relative_path
            try:
                if not candidate.exists() or not candidate.is_file():
                    errors.append(f"{group_name} file is missing or not regular: {relative_name}")
                    continue
                actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
            except OSError as exc:
                errors.append(f"{group_name} file could not be read: {relative_name}: {exc}")
                continue
            if actual != expected.lower():
                errors.append(
                    f"{group_name} hash mismatch for {relative_name}: "
                    f"expected={expected}, actual={actual}"
                )
    return not errors, errors


def build_danger_semantics_summary() -> dict[str, Any]:
    """P1 summary: Partner and EAWS danger semantics are separated."""
    return {
        'status': 'complete',
        'Partner_levels': {str(k): v for k, v in Partner_DANGER_LEVELS.items()},
        'eaws_levels': {str(k): v for k, v in EAWS_DANGER_LEVELS.items()},
        'semantics_table_exists': len(Partner_DANGER_SEMANTICS) == 5,
        'level_3_is_orange_not_high': Partner_DANGER_LEVELS[3] == 'orange',
        'level_4_is_red_not_very_high': Partner_DANGER_LEVELS[4] == 'red',
    }


def build_parser_coverage_summary() -> dict[str, Any]:
    """P3 summary: parser behavior against a local, content-hashed fixture.

    A fixture run proves local parser behavior only. It is never described as
    a live or source-verified bulletin until the canonical Partner URL is bound
    to a verified registry entry.
    """

    fixture_path = Path(__file__).parent.parent / 'tests' / 'fixtures' / 'Partner_AWB_30-Apr-2026.pdf'
    if not fixture_path.exists():
        return {
            'status': 'fixture_missing',
            'side_by_side_parser': True,  # module exists
            'validity_window_parser': True,  # module exists
            'source_kind': 'local_fixture',
            'fixture_id': None,
            'rows_extracted': 0,
            'districts': [],
            'live_bulletin_rows_extracted': 0,  # Deprecated compatibility alias.
            'live_bulletin_districts': [],  # Deprecated compatibility alias.
            'provenance_verification': 'not_tested',
            'note': 'Local bulletin fixture not found; no source claim is made.',
        }

    try:
        from backend.common.Partner_bulletin_adapter import (
            parse_bulletin_with_provenance,
            _extract_pdf_text,
        )

        content = fixture_path.read_bytes()
        text, tables = _extract_pdf_text(content)
        result = parse_bulletin_with_provenance(
            text, 'Partner_AWB_30-Apr-2026',
            source_url='https://Partner.gov.in/Partner_AWB_30-Apr-2026.pdf',
            provenance_hash=hashlib.sha256(content).hexdigest(),
            tables=tables,
        )

        districts = []
        if result.record and result.record.rows:
            districts = [r.district for r in result.record.rows if r.district]

        duplicate_count = int(result.record.metadata.get('duplicate_row_count', 0)) if result.record else 0
        return {
            'status': 'complete' if result.is_complete else (
                'fixture_parsed_but_blocked' if result.complete_row_count > 0 else 'parsed_zero_rows'
            ),
            'side_by_side_parser': True,
            'validity_window_parser': True,
            'source_kind': 'local_fixture',
            'fixture_id': 'Partner_AWB_30-Apr-2026',
            'fixture_sha256': hashlib.sha256(content).hexdigest(),
            'source_url': 'https://www.Partner.gov.in/Partner/sites/default/files/avalanche_warning_bulletin/Partner_AWB_30-Apr-2026.pdf',
            'rows_extracted': result.complete_row_count,
            'unique_rows_extracted': result.complete_row_count,
            'duplicate_row_count': duplicate_count,
            'districts': districts,
            'live_bulletin_tested': 'LOCAL_FIXTURE:Partner_AWB_30-Apr-2026',
            'live_bulletin_rows_extracted': result.complete_row_count,
            'live_bulletin_districts': districts,
            'provenance_verification': 'verified' if result.is_complete else (
                'fail_closed (not in registry)' if result.parse_error == 'rows_missing_provenance' else 'unverified'
            ),
            'parse_error': result.parse_error,
            'is_complete': result.is_complete,
        }
    except Exception as exc:
        return {
            'status': 'parser_error',
            'side_by_side_parser': True,
            'validity_window_parser': True,
            'source_kind': 'local_fixture',
            'fixture_id': 'Partner_AWB_30-Apr-2026',
            'rows_extracted': 0,
            'districts': [],
            'live_bulletin_tested': 'LOCAL_FIXTURE:Partner_AWB_30-Apr-2026',
            'live_bulletin_rows_extracted': 0,
            'live_bulletin_districts': [],
            'provenance_verification': 'not_tested',
            'error': str(exc),
        }


def build_swiss_reference_summary() -> dict[str, Any]:
    """P6 summary: Swiss EnviDat reference repair.

    G7: Prefer the self-hashed retrieval snapshot when present. Its metadata,
    resource bytes, schema, and content hash can be reported as retrieval-time
    verified evidence, while raw-byte retention, runtime reproduction, rights,
    and Partner approval remain separate gates. Without a snapshot, the fallback
    remains metadata-identity-only and explicitly unverified.
    """
    snapshot_path = Path(__file__).parent.parent.parent / 'artifacts' / 'Partner' / 'swiss_rf2_verification.json'
    try:
        snapshot = load_swiss_verification_snapshot(snapshot_path)
    except ValueError as exc:
        snapshot = None
        snapshot_error = str(exc)
    else:
        snapshot_error = None

    if snapshot is not None:
        metadata_hash = str(snapshot.get('metadata_response_sha256') or '')
        metadata_hash_verified = len(metadata_hash) == 64 and all(
            character in '0123456789abcdefABCDEF' for character in metadata_hash
        )
        return {
            'status': 'content_verified_snapshot',
            'doi_based_id_fixed': True,
            'working_package_id': 'weather-snowpack-danger_ratings-data',
            'uuid': '54d7dc19-e70c-4998-bfb6-caffe41c83e6',
            'resources_discovered': 2,
            'metadata_url': str(snapshot.get('metadata_url') or SWISS_METADATA_URL),
            'rf2_resource_url': str(snapshot.get('source_url') or SWISS_RF2_RESOURCE_URL),
            'rf2_size_bytes': snapshot.get('byte_size'),
            'rf2_content_hash': snapshot.get('content_sha256'),
            'rf2_total_rows': snapshot.get('total_rows'),
            'rf2_level_5_count': snapshot.get('level_5_count'),
            'rf2_level_5_percentage': snapshot.get('level_5_percentage'),
            'metadata_response_hash': metadata_hash,
            'license_id': snapshot.get('license_id'),
            'resource_metadata_size': snapshot.get('resource_metadata_size'),
            'metadata_verification': {
                'uuid_verified': True,
                'slug_verified': True,
                'api_response_hash_verified': metadata_hash_verified,
                'resource_urls_verified': bool(snapshot.get('source_url')),
                'license_verified': bool(snapshot.get('license_id')),
                'byte_sizes_verified': (
                    isinstance(snapshot.get('byte_size'), int)
                    and isinstance(snapshot.get('resource_metadata_size'), int)
                    and snapshot.get('byte_size') == snapshot.get('resource_metadata_size')
                ),
                'content_hashes_verified': True,
                'raw_bytes_retained': bool(snapshot.get('raw_bytes_retained')),
            },
            'snapshot_path': str(snapshot_path),
            'snapshot_sha256': snapshot.get('snapshot_sha256'),
            'note': (
                'RF2 bytes, schema, and exact content hash were verified at retrieval '
                'time and recorded in a self-hashed snapshot. Raw bytes are not retained '
                'in the repository; runtime reproduction and rights review remain blocked.'
            ),
        }

    return {
        'status': 'metadata_identity_asserted',
        'doi_based_id_fixed': True,
        'working_package_id': 'weather-snowpack-danger_ratings-data',
        'uuid': '54d7dc19-e70c-4998-bfb6-caffe41c83e6',  # Identity asserted from the official metadata record.
        'resources_discovered': 2,
        # G7: All fields below are UNVERIFIED — require live EnviDat API call
        'rf1_size_bytes': 'unverified — requires live EnviDat API call',
        'rf2_size_bytes': 'unverified — requires live EnviDat API call',
        'api_response_hash': 'unverified — requires live EnviDat API call',
        'resource_urls': 'unverified — requires live EnviDat API call',
        'license': 'unverified — requires live EnviDat API call',
        'rf1_content_hash': 'unverified — requires live download + SHA-256',
        'rf2_content_hash': 'unverified — requires live download + SHA-256',
        'metadata_verification': {
            'uuid_verified': True,
            'slug_verified': True,
            'api_response_hash_verified': False,
            'resource_urls_verified': False,
            'license_verified': False,
            'byte_sizes_verified': False,
            'content_hashes_verified': False,
        },
        'snapshot_path': str(snapshot_path),
        'snapshot_error': snapshot_error,
        'note': 'UUID and slug are asserted from the official metadata identity. All other metadata '
                '(byte sizes, API hash, resource URLs, license, content hashes) require live EnviDat verification.',
    }


def build_strategic_answer() -> dict[str, Any]:
    """P10: The strategic answer to the user's question.

    Answers: "Can we use deep research or guesstimation to complete
    the avalanche danger level prediction system?"

    G10: All claims are generated from current matrix/packet fields.
    No hardcoded counts or unverified numbers.
    """
    # G10: Dynamically compute from current matrix state
    # N4: Guard against matrix building failure
    from backend.common.Partner_literature_matrix import build_matrix_summary
    try:
        matrix = build_matrix_summary()
        total_papers = matrix['total_papers']
        verified_count = matrix['verified_count']
        unverified_count = matrix['unverified_count']
        conformant_count = matrix['conformant_count']
    except Exception as exc:
        total_papers = 0
        verified_count = 0
        unverified_count = 0
        conformant_count = 0
        matrix_error = str(exc)
    else:
        matrix_error = None

    swiss_reference = build_swiss_reference_summary()
    swiss_counts_verified = (
        swiss_reference.get('status') == 'content_verified_snapshot'
        and swiss_reference.get('rf2_level_5_count') is not None
    )
    swiss_count_note = (
        'verified from the self-hashed RF2 retrieval snapshot'
        if swiss_counts_verified
        else 'unverified because no content-verified RF2 snapshot is available'
    )

    # N3: Import G5 conversion status for consistency
    from backend.common.Partner_reviewed_label_conversion import CONVERSION_STATUS

    return {
        'question': (
            'Can we use deep research from Partner publications or guesstimation '
            'to complete the avalanche danger level prediction system?'
        ),
        'answer': (
            'YES — for bounded engineering preparation only. The system cannot '
            'treat public research or unverified fixtures as Partner training evidence. '
            'Here is the evidence-based breakdown:'
        ),
        'what_deep_research_provides': [
            f'P8: {total_papers} Partner/Partner sources analyzed — {conformant_count} of {verified_count} verified sources '
            f'use the full 5-level scale (conformant). {unverified_count} entries have unverified bibliographic details.'
            + (f' [WARNING: matrix summary failed — {matrix_error}]' if matrix_error else ''),
            'P1: Partner 5-level danger semantics (Green/Yellow/Orange/Red/Black) documented',
            'P3: Local bulletin fixture parser executed; source verification and duplicate-row clearance remain blocked',
            'P2: Archive discovery contract classifies bulletins, closing letters, and malformed rows; acquisition is not yet complete',
            f"P6: Swiss EnviDat reference status is {swiss_reference.get('status')}; "
            'raw-byte retention, license, and runtime reproduction remain separate gates',
            'P7: Swiss 4-level scale is conformant with the RAvaFcast paper but NOT with Partner 5-level',
        ],
        'what_guesstimation_cannot_replace': [
            'Partner-approved historical 5-level labels for training (P11 blocked)',
            'Partner station data from 70 surface observatories',
            'Cryptographic approval/signature for provenance verification',
            f'Level 5 (Black/Extremely unsafe) examples — Swiss data counts are '
            f'{"verified" if swiss_counts_verified else "UNVERIFIED"} '
            f'({swiss_count_note}), '
            f'merged to Level 4 by the Swiss reproduction code',
        ],
        'recommended_path': [
            '1. IMPLEMENT P9 lane adapters as explicitly blocked/contract-only preparation — '
            'no executable ERA5/IMD/OSM or Partner station pipeline is currently authorized',
            '2. PREPARE P2-P5 archive discovery and candidate inventory without treating them as labels',
            '3. BLOCK P11 conditional training until Partner provides approved 5-level labels '
            'AND a candidate-to-label conversion path is implemented',
            '4. USE Swiss reference (P6/P7) for model architecture validation only, NOT for Partner labels',
            '5. PRESENT the P10 decision packet to Partner with the evidence from P1-P9',
        ],
        'risk_of_guesstimation': (
            'Guesstimating 5-level labels would violate the system\'s safety gates. '
            'The label governance (denylisted) requires label_confidence >= 0.45 '
            'and training_eligible=true. The P4 PublicBulletinCandidateV1 explicitly '
            'forces training_eligible=false (enforced via __post_init__). No conversion '
            'path from candidate to approved label currently exists in the codebase — '
            f'conversion status is {CONVERSION_STATUS}. '
            'This is a known gap that must be addressed before P11 conditional training can proceed.'
        ),
        'conclusion': (
            'The system is ready for parallel preparation (P9) and public bulletin '
            'inventory (P2-P5) without Partner approval. Conditional training (P11) '
            'remains blocked until Partner provides approved 5-level labels. '
            f'Deep research (P8) confirms the 5-level scale is the correct target '
            f'({conformant_count} verified conformant source(s)). '
            'Guesstimation is NOT a safe substitute for Partner-approved labels.'
        ),
    }


def build_execution_readiness(lane_summary: dict[str, Any]) -> dict[str, Any]:
    """Derive production permissions from current evidence, never assumptions."""
    permissions: dict[str, dict[str, bool]] = {}
    for lane in lane_summary.get('lanes', []):
        track = str(lane.get('track', '')).lower()
        permissions[track] = {
            'engineering_preparation': bool(lane.get('engineering_preparation_allowed')),
            'feature_generation': bool(lane.get('feature_generation_allowed')),
            'training': bool(lane.get('training_allowed')),
            'evaluation': bool(lane.get('evaluation_allowed')),
            'promotion': False,
            'serve': False,
        }
    return {
        'schema_version': 'Partner_execution_readiness_v1',
        'status': 'blocked_external_evidence',
        'track_permissions': permissions,
        'source': 'parallel_lanes_and_external_gate_state',
        'note': 'Non-framework runtime operations require a saved, hash-verified packet whose track permission is true.',
    }


def build_known_gaps(
    *,
    archive_discovery: dict[str, Any],
    public_candidates: dict[str, Any],
    swiss_reference: dict[str, Any],
    literature_matrix: dict[str, Any],
    parallel_lanes: dict[str, Any],
) -> list[str]:
    """Derive the decision packet's gap ledger from current evidence states."""
    from backend.common.Partner_reviewed_label_conversion import CONVERSION_STATUS

    gaps: list[str] = []
    if parallel_lanes.get('all_are_specification_only'):
        gaps.append('GAP-F: T2A and Track 1 source adapters remain specification-only; no executable lane pipeline is authorized.')
    gaps.append(
        'GAP-G: Conformance classification criteria for proxy/4-level references require explicit Partner review.'
    )
    if not public_candidates.get('content_verified') or not public_candidates.get('training_eligible'):
        gaps.append('GAP-H: Public candidates are fail-closed and cannot become labels without a reviewed label-construction path.')
    if CONVERSION_STATUS != 'complete':
        gaps.append(
            'GAP-I: No conversion path exists from PublicBulletinCandidateV1 to an approved Partner label — '
            f'conversion status is {CONVERSION_STATUS}.'
        )
    if swiss_reference.get('status') != 'content_verified_snapshot' or not swiss_reference.get('metadata_verification', {}).get('content_hashes_verified'):
        gaps.append(
            'GAP-J: Swiss RF2 content is not content-verified in the current packet; Level 5 merge and runtime reproduction remain blocked.'
        )
    else:
        gaps.append(
            'GAP-J: Swiss RF2 retrieval is content-verified in a self-hashed snapshot, but raw-byte retention, rights, and runtime reproduction remain blocked.'
        )
    unverified_count = int(literature_matrix.get('unverified_count', 0) or 0)
    decision_eligible_count = int(literature_matrix.get('decision_eligible_count', 0) or 0)
    if unverified_count or not decision_eligible_count:
        gaps.append(
            f'GAP-K: {unverified_count} literature entries remain asserted_unverified or unbound; '
            'only content-bound verified sources may influence decisions.'
        )
    gaps.append('GAP-L: Cryptographic Partner approval verification and independent-observation evidence are external hard gates.')
    if not parallel_lanes.get('feature_generation_allowed_count'):
        gaps.append('GAP-M: Track 1 station/anchor inputs and approved reference-lane evidence have not been supplied.')
    if not archive_discovery.get('discovery_complete'):
        gaps.append(
            f"GAP-N: Archive acquisition is not complete in the packet (status={archive_discovery.get('status')!r}); "
            'no archive denominator may be used for training claims.'
        )
    return gaps


def build_decision_packet() -> PartnerDecisionPacket:
    """Build the complete Partner decision packet aggregating P1-P9 evidence.

    P10 exit gate: A single decision packet presents the verified inventory,
    parser coverage, Swiss limitations, literature conformance, and parallel
    lane readiness.
    """
    packet = PartnerDecisionPacket()

    # P1: Danger semantics
    packet.danger_semantics = build_danger_semantics_summary()

    # P2: Archive discovery is evidence-bearing only after a bounded fetch run
    # has been persisted and its manifest hash has been verified.
    archive_snapshot_path = Path(__file__).parent.parent.parent / 'artifacts' / 'Partner' / 'Partner_archive_manifest.json'
    try:
        archive_snapshot = load_archive_manifest(archive_snapshot_path)
    except ValueError as exc:
        archive_snapshot = None
        archive_snapshot_error = str(exc)
    else:
        archive_snapshot_error = None

    if archive_snapshot is not None:
        archive_manifest = dict(archive_snapshot)
        archive_manifest.update({
            'snapshot_path': str(archive_snapshot_path),
            'snapshot_verified': True,
            'snapshot_error': None,
            'status': 'complete' if archive_snapshot.get('discovery_complete') else 'incomplete_snapshot',
            'note': (
                'Archive inventory is loaded from a self-hashed bounded snapshot. '
                'PDF bytes and label rights remain separate gates.'
            ),
        })
    else:
        archive_manifest = build_archive_manifest([])
        archive_manifest.update({
            'status': 'disabled' if not Partner_ARCHIVE_DISCOVERY_ENABLED else 'not_run',
            'discovery_enabled': Partner_ARCHIVE_DISCOVERY_ENABLED,
            'snapshot_path': str(archive_snapshot_path),
            'snapshot_verified': False,
            'snapshot_error': archive_snapshot_error,
            'note': (
                'Archive acquisition is disabled or has not been persisted; '
                'no archive inventory is claimed.'
            ),
        })
    packet.archive_discovery = archive_manifest

    # P3: Parser coverage
    packet.parser_coverage = build_parser_coverage_summary()

    # P4: Public candidates are not synthesized from the local parser fixture.
    packet.public_candidates = {
        'status': 'blocked_no_inventory',
        'candidates_collected': 0,
        'training_eligible': 0,
        'content_verified': False,
        'note': 'No source-verified public candidate inventory was collected.',
    }

    # P5: No coverage denominator is reported without P4 candidates.
    packet.coverage_audit = {
        'status': 'blocked_no_candidate_inventory',
        'archive_denominators_verified': False,
        'note': 'Coverage audit requires a source-verified candidate inventory and archive denominators.',
    }

    # P6: Swiss reference repair
    swiss_reference = build_swiss_reference_summary()
    packet.swiss_reference = swiss_reference

    # P7: Swiss conformance decision
    conformance = build_conformance_decision()
    packet.swiss_conformance = conformance.to_dict()

    # P8: Literature matrix
    packet.literature_matrix = build_matrix_summary()

    # P9: Parallel lanes
    packet.parallel_lanes = build_lane_summary()
    packet.execution_readiness = build_execution_readiness(packet.parallel_lanes)

    # Known gaps — derived from the current evidence states.
    packet.known_gaps = build_known_gaps(
        archive_discovery=packet.archive_discovery,
        public_candidates=packet.public_candidates,
        swiss_reference=packet.swiss_reference,
        literature_matrix=packet.literature_matrix,
        parallel_lanes=packet.parallel_lanes,
    )

    # Strategic answer
    packet.strategic_answer = build_strategic_answer()

    # G16: Provenance — code revision, source hashes, test ledger
    packet.provenance = build_provenance_summary()

    return packet


def build_provenance_summary() -> dict[str, Any]:
    """G16: Build provenance summary for the decision packet.

    Records the code revision, source file hashes, and test ledger
    so the packet can be reproduced and verified.
    """
    import subprocess
    from pathlib import Path

    # Get git revision
    # N11: Catch specific exceptions, not bare Exception
    try:
        revision = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'],
            cwd=Path(__file__).parent.parent.parent,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError, TimeoutError, OSError):
        revision = 'unavailable — not a git repo or git not installed'

    # P7: Detect branch name and warn if detached HEAD
    branch_name = None
    is_detached = False
    try:
        branch = subprocess.check_output(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=Path(__file__).parent.parent.parent,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode().strip()
        if branch == 'HEAD':
            is_detached = True
            branch_name = None
        else:
            branch_name = branch
    except (subprocess.CalledProcessError, FileNotFoundError, TimeoutError, OSError):
        branch_name = None

    # Get git status (dirty or clean)
    try:
        status = subprocess.check_output(
            ['git', 'status', '--porcelain'],
            cwd=Path(__file__).parent.parent.parent,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode().strip()
        is_dirty = bool(status)
    except (subprocess.CalledProcessError, FileNotFoundError, TimeoutError, OSError):
        is_dirty = None

    # Source file hashes for key modules
    source_files = [
        'backend/common/Partner_decision_packet.py',
        'backend/common/Partner_bulletin_adapter.py',
        'backend/common/Partner_public_candidate.py',
        'backend/common/Partner_coverage_audit.py',
        'backend/common/Partner_literature_matrix.py',
        'backend/common/Partner_parallel_lanes.py',
        'backend/common/swiss_conformance_audit.py',
        'backend/common/Partner_archive_discovery.py',
        'backend/common/Partner_reviewed_label_conversion.py',
        'backend/common/Partner_lane_sources.py',
        'backend/common/track_contracts/lane_execution_wrapper.py',
        'backend/common/track_contracts/lane_preflight.py',
        'backend/common/track_contracts/packet_loaders.py',
        'backend/common/track_contracts/experiment_manifest.py',
        'backend/common/track_contracts/prediction.py',
        'backend/common/track_contracts/authority_registry.py',
        'backend/common/track_contracts/content_resolver.py',
        'backend/common/track_contracts/artifact_registry.py',
        # Production submission boundaries: these must be provenance-bound so
        # a packet cannot silently omit a caller that can schedule Modal work.
        'backend/modal_worker_app.py',
        'backend/sar_unet_worker.py',
        'backend/scripts/run_modal_sar_training_direct.py',
        'backend/scripts/run_modal_sar_release_evaluation_direct.py',
        'backend/scripts/run_modal_sar_checkpoint_evaluation_direct.py',
        'backend/scripts/run_modal_sar_prediction_materialization_direct.py',
    ]
    import hashlib
    file_hashes = {}
    repo_root = Path(__file__).parent.parent.parent
    for f in source_files:
        full_path = repo_root / f
        if full_path.exists():
            content = full_path.read_bytes()
            file_hashes[f] = hashlib.sha256(content).hexdigest()
        else:
            file_hashes[f] = 'file not found'

    input_files = [
        'backend/tests/fixtures/Partner_AWB_30-Apr-2026.pdf',
        'docs/Post_PoC/readiness/Partner_MEETING_PACKAGE.md',
        'docs/Post_PoC/readiness/VERIFICATION_LEDGER.md',
        'artifacts/Partner/Partner_archive_manifest.json',
        'artifacts/Partner/swiss_rf2_verification.json',
    ]
    input_hashes: dict[str, str] = {}
    for relative_path in input_files:
        input_path = repo_root / relative_path
        if input_path.exists():
            input_hashes[relative_path] = hashlib.sha256(input_path.read_bytes()).hexdigest()
        else:
            input_hashes[relative_path] = 'file not found'

    return {
        'schema_version': 'Partner_provenance_v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'code_revision': revision,
        'branch_name': branch_name,
        'is_detached_head': is_detached,
        'worktree_dirty': is_dirty,
        'source_file_hashes': file_hashes,
        'source_file_count': len(file_hashes),
        'input_file_hashes': input_hashes,
        'artifact_path': str(DEFAULT_PACKET_PATH),
        'generation_command': (
            'python3 -c "from pathlib import Path; from backend.common.Partner_decision_packet '
            'import build_decision_packet, save_decision_packet; '
            'save_decision_packet(build_decision_packet(), Path(\'artifacts/Partner/Partner_decision_packet.json\'))"'
        ),
        'save_command': (
            'python3 -c "from pathlib import Path; from backend.common.Partner_decision_packet '
            'import build_decision_packet, save_decision_packet; '
            'save_decision_packet(build_decision_packet(), Path(\'artifacts/Partner/Partner_decision_packet.json\'))"'
        ),
        'test_command': 'python3 -m unittest discover -s backend/tests -p "test_*.py"',
        'packet_hash_scope': PACKET_HASH_SCOPE,
        'packet_sha256': None,
        'note': (
            'The packet records source-code and input hashes, the dirty worktree '
            'state, and an explicit save operation. A saved packet receives a '
            'self-excluding SHA-256 that can be verified without trusting its path.'
        ),
        'hash_mismatch_recovery': (
            'P2 (proactive): If source files change between packet generation and '
            'runtime verification (ContentResolver hash mismatch), regenerate the '
            'packet by running the generation_command. The packet is a snapshot — '
            'it is expected to become stale after code changes. Do NOT weaken hash '
            'verification to bypass mismatches; regenerate instead.'
        ),
    }


def save_decision_packet(packet: PartnerDecisionPacket, path: Path) -> str:
    """Atomically save a canonically serialized packet and return its hash.

    The recorded hash covers the canonical payload with
    ``provenance.packet_sha256`` set to null, avoiding a circular hash while
    still allowing a consumer to verify every other byte in the packet.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = packet.to_dict()
    hash_payload = _packet_hash_payload(payload)
    packet_hash = hashlib.sha256(_canonical_json_bytes(hash_payload)).hexdigest()
    payload.setdefault('provenance', {})['packet_hash_scope'] = PACKET_HASH_SCOPE
    payload['provenance']['packet_sha256'] = packet_hash
    encoded = _canonical_json_bytes(payload)
    with tempfile.NamedTemporaryFile(
        mode='wb', dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp', delete=False
    ) as handle:
        temporary_path = Path(handle.name)
        handle.write(encoded)
    os.replace(temporary_path, path)
    digest_path = path.with_suffix(path.suffix + '.sha256')
    digest_path.write_text(f'{packet_hash}  {path.name}\n', encoding='utf-8')
    return packet_hash


def load_decision_packet(path: Path) -> dict[str, Any] | None:
    """Load and verify a previously saved decision packet.

    Missing files still return ``None`` for compatibility. Malformed JSON or
    a self-hash mismatch raises ``ValueError`` so a caller cannot mistake a
    corrupt packet for an absent optional artifact.
    """
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'failed to load decision packet {path}: {exc}') from exc
    if not isinstance(payload, dict):
        raise ValueError('decision packet JSON must be an object')
    if payload.get('provenance', {}).get('packet_sha256') is not None and not verify_decision_packet_hash(payload):
        raise ValueError(f'decision packet hash mismatch: {path}')
    return payload
