from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


EUROPEAN_SHADOW_MANIFEST_VERSION = 'european_shadow_manifest_v1'
EUROPEAN_STAGED_RECORD_VERSION = 'european_staged_record_v1'
EUROPEAN_SHADOW_EVALUATION_GATE_VERSION = 'european_shadow_evaluation_gates_v1'

REGISTRY_ONLY_ROLE = 'registry_only'
STAGING_ROLE = 'staging'
BENCHMARK_ROLE = 'benchmark'
SHADOW_TRAINING_ROLE = 'shadow_training'
FEATURE_JOIN_ROLE = 'feature_join'
PRODUCTION_SCORING_ROLE = 'production_scoring'

OCCURRENCE_LABELS_LANE = 'occurrence_labels'
ACCIDENT_EVENT_LABELS_LANE = 'accident_event_labels'
SAR_MASKS_LANE = 'sar_masks'
SAR_DETECTION_ACTIVITY_LANE = 'sar_detection_activity'
DANGER_RATING_LABELS_LANE = 'danger_rating_labels'
WEATHER_SNOWPACK_FEATURES_LANE = 'weather_snowpack_features'
BULLETIN_CONTEXT_LANE = 'bulletin_context'
TERRAIN_PATH_PRIORS_LANE = 'terrain_path_priors'
SEQUENCE_ACTIVITY_LANE = 'sequence_activity'

SAR_TRAINING_MANIFEST_VERSION = 'sar_training_manifest_v1'
SAR_TRAINING_ALLOWED_SPLITS = {'train', 'val', 'authoritative_test'}

LABEL_LANES = {
    OCCURRENCE_LABELS_LANE,
    SAR_MASKS_LANE,
    SAR_DETECTION_ACTIVITY_LANE,
    DANGER_RATING_LABELS_LANE,
    TERRAIN_PATH_PRIORS_LANE,
    SEQUENCE_ACTIVITY_LANE,
}
SAR_MANIFEST_LANES = {SAR_MASKS_LANE, SAR_DETECTION_ACTIVITY_LANE}


@dataclass(frozen=True)
class EuropeanSource:
    source_key: str
    label: str
    region_keys: tuple[str, ...]
    data_lane: str
    record_count: int | None
    record_count_kind: str
    curation_level: str
    license: str
    source_url: str
    citation: str
    attribution_required: bool
    requires_license_review: bool
    allowed_roles: tuple[str, ...]
    default_training_role: str
    recommended_weight: float
    risk_notes: tuple[str, ...]

    def as_manifest_dict(self) -> dict[str, Any]:
        return {
            'source_key': self.source_key,
            'label': self.label,
            'region_keys': list(self.region_keys),
            'data_lane': self.data_lane,
            'record_count': self.record_count,
            'record_count_kind': self.record_count_kind,
            'curation_level': self.curation_level,
            'license': self.license,
            'source_url': self.source_url,
            'citation': self.citation,
            'attribution_required': self.attribution_required,
            'requires_license_review': self.requires_license_review,
            'allowed_roles': list(self.allowed_roles),
            'default_training_role': self.default_training_role,
            'recommended_weight': self.recommended_weight,
            'risk_notes': list(self.risk_notes),
        }


@dataclass(frozen=True)
class DatasetFamilyAssessment:
    family_key: str
    dataset_family: str
    source_keys: tuple[str, ...]
    best_use: str
    enhancement_value: float
    main_caution: str
    implementation_status: str
    remaining_work: tuple[str, ...]

    def as_manifest_dict(self) -> dict[str, Any]:
        return {
            'family_key': self.family_key,
            'dataset_family': self.dataset_family,
            'source_keys': list(self.source_keys),
            'best_use': self.best_use,
            'enhancement_value': self.enhancement_value,
            'main_caution': self.main_caution,
            'implementation_status': self.implementation_status,
            'remaining_work': list(self.remaining_work),
        }


def _source(
    *,
    source_key: str,
    label: str,
    region_keys: tuple[str, ...],
    data_lane: str,
    record_count: int | None,
    record_count_kind: str,
    curation_level: str,
    license: str,
    source_url: str,
    citation: str,
    attribution_required: bool = True,
    requires_license_review: bool = True,
    allowed_roles: tuple[str, ...] = (REGISTRY_ONLY_ROLE, STAGING_ROLE, BENCHMARK_ROLE, SHADOW_TRAINING_ROLE),
    default_training_role: str = SHADOW_TRAINING_ROLE,
    recommended_weight: float = 0.6,
    risk_notes: tuple[str, ...] = (),
) -> EuropeanSource:
    return EuropeanSource(
        source_key=source_key,
        label=label,
        region_keys=tuple(region_keys),
        data_lane=data_lane,
        record_count=record_count,
        record_count_kind=record_count_kind,
        curation_level=curation_level,
        license=license,
        source_url=source_url,
        citation=citation,
        attribution_required=attribution_required,
        requires_license_review=requires_license_review,
        allowed_roles=tuple(allowed_roles),
        default_training_role=default_training_role,
        recommended_weight=float(recommended_weight),
        risk_notes=tuple(risk_notes),
    )


def european_source_registry() -> dict[str, EuropeanSource]:
    sources = [
        _source(
            source_key='swiss_spot6_2018',
            label='Swiss SPOT6 avalanche outlines, 24 January 2018',
            region_keys=('swiss_alps',),
            data_lane=OCCURRENCE_LABELS_LANE,
            record_count=18737,
            record_count_kind='manual avalanche outlines from EnviDat metadata',
            curation_level='expert/manual satellite outline mapping',
            license='EnviDat dataset terms; proper citation and dataset limitations required',
            source_url='https://www.envidat.ch/metadata/spot6-avalanche-outlines-24-january-2018',
            citation='Hafner, E. and Buehler, Y. (2019). SPOT6 Avalanche outlines 24 January 2018. EnviDat. https://doi.org/10.16904/envidat.77',
            recommended_weight=0.75,
            risk_notes=(
                'Extreme-event Swiss Alps sample, not a normal-season distribution.',
                'Optical mapping can miss forested or cloud-obscured avalanches.',
                'Use only in shadow validation or regional calibration until transfer-bias checks pass.',
            ),
        ),
        _source(
            source_key='swiss_spot6_2019',
            label='Swiss SPOT6 avalanche outlines, 16 January 2019',
            region_keys=('swiss_alps',),
            data_lane=OCCURRENCE_LABELS_LANE,
            record_count=6041,
            record_count_kind='manual avalanche outlines from EnviDat metadata',
            curation_level='expert/manual satellite outline mapping',
            license='EnviDat dataset terms; proper citation and dataset limitations required',
            source_url='https://www.envidat.ch/metadata/spot6-avalanche-outlines-16-january-2019',
            citation='Hafner, E. and Buehler, Y. (2021). SPOT6 Avalanche outlines 16 January 2019. EnviDat. https://doi.org/10.16904/envidat.235',
            recommended_weight=0.75,
            risk_notes=(
                'Extreme-event Swiss Alps sample, not a normal-season distribution.',
                'Manual optical outlines are strong spatial labels but still region-specific.',
                'Use as a benchmark and shadow calibration lane before any model promotion.',
            ),
        ),
        _source(
            source_key='swiss_1999_aerial_outlines',
            label='Swiss 1999 avalanche outlines from aerial imagery',
            region_keys=('swiss_alps',),
            data_lane=OCCURRENCE_LABELS_LANE,
            record_count=11120,
            record_count_kind='manual avalanche outlines from EnviDat metadata',
            curation_level='expert/manual aerial imagery outline mapping',
            license='EnviDat dataset terms; proper citation and example-key limitations required',
            source_url='https://www.envidat.ch/metadata/avalanche-outlines',
            citation='Hafner, E. and Buehler, Y. Avalanche outlines February and March 1999 from aerial imagery. EnviDat. https://doi.org/10.16904/envidat.579',
            recommended_weight=0.65,
            risk_notes=(
                'Historical winter-of-1999 sample has climate and sensor-era drift.',
                'Useful for runout/path priors and stress testing, not direct public scoring.',
            ),
        ),
        _source(
            source_key='french_epa_historical',
            label='French EPA avalanche permanent survey',
            region_keys=('french_alps',),
            data_lane=OCCURRENCE_LABELS_LANE,
            record_count=54641,
            record_count_kind='published Alpine study subset for 1946-2009 full winters',
            curation_level='standardized long-running path/site event chronology',
            license='avalanches.fr/EPA access terms must be reviewed before local ingestion',
            source_url='https://www.avalanches.fr/',
            citation='French Enquete Permanente sur les Avalanches (EPA); see avalanches.fr and published EPA temporal-trend studies.',
            recommended_weight=0.55,
            risk_notes=(
                'EPA is path/site based and has observation/reporting protocol biases.',
                'Long history is valuable for frequency and seasonality, but geometry may be coarser than satellite masks.',
                'Do not mix directly into Himalayan or global production scoring without local recalibration gates.',
            ),
        ),
        _source(
            source_key='french_clpa_extent_priors',
            label='French CLPA avalanche phenomenon localization map',
            region_keys=('french_alps',),
            data_lane=TERRAIN_PATH_PRIORS_LANE,
            record_count=None,
            record_count_kind='mapped phenomenon extents; count depends on exported layer',
            curation_level='official avalanche extent/localization mapping',
            license='avalanches.fr/CLPA access terms must be reviewed before local ingestion',
            source_url='https://www.avalanches.fr/',
            citation='French Carte de Localisation des Phenomenes d Avalanche (CLPA); see avalanches.fr.',
            allowed_roles=(REGISTRY_ONLY_ROLE, STAGING_ROLE, BENCHMARK_ROLE),
            default_training_role=BENCHMARK_ROLE,
            recommended_weight=0.45,
            risk_notes=(
                'CLPA is better treated as a spatial prior or audit surface than as dated occurrence truth.',
                'Use to detect impossible terrain/path predictions and to evaluate runout plausibility.',
            ),
        ),
        _source(
            source_key='norway_sar_fcn_labels',
            label='Norwegian Sentinel-1 SAR manually labeled avalanche examples',
            region_keys=('scandinavia_norway',),
            data_lane=SAR_MASKS_LANE,
            record_count=6345,
            record_count_kind='manual labels reported for 117 Sentinel-1 images',
            curation_level='manual SAR avalanche labels used for FCN/U-Net style segmentation research',
            license='research paper/data-release terms must be reviewed before local ingestion',
            source_url='https://arxiv.org/abs/1910.05411',
            citation='Bianchi, F. M., Grahn, J., Eckerstorfer, M., Malnes, E., and Vickers, H. Snow avalanche segmentation in SAR images with Fully Convolutional Neural Networks.',
            recommended_weight=0.7,
            risk_notes=(
                'SAR labels are strong for debris segmentation but sensor/backscatter conditions differ by region.',
                'Keep in SAR shadow training and evaluate against held-out regional scenes before promotion.',
            ),
        ),
        _source(
            source_key='norway_sar_activity_monitoring',
            label='Norwegian 472k Sentinel-1 avalanche activity monitoring detections',
            region_keys=('scandinavia_norway',),
            data_lane=SAR_DETECTION_ACTIVITY_LANE,
            record_count=472000,
            record_count_kind='updated recommendation count for large-scale automated Sentinel-1 detections',
            curation_level='model/operational detections requiring source-package audit',
            license='operational/research availability varies by release; verify package and redistribution terms',
            source_url='https://www.researchgate.net/publication/344607890_Norway%27s_operational_avalanche_activity_monitoring_system_using_Sentinel-1',
            citation='Norwegian Sentinel-1 avalanche activity monitoring literature by Eckerstorfer, Malnes, and collaborators.',
            allowed_roles=(REGISTRY_ONLY_ROLE, STAGING_ROLE, BENCHMARK_ROLE),
            default_training_role=BENCHMARK_ROLE,
            recommended_weight=0.35,
            risk_notes=(
                'Large count is not equivalent to expert-curated independent ground truth.',
                'Use first for activity-rate benchmarking, recall stress tests, and false-positive analysis.',
            ),
        ),
        _source(
            source_key='avalcd_zenodo_v1',
            label='AvalCD bi-temporal Sentinel-1 avalanche change-detection scenes',
            region_keys=('swiss_alps', 'scandinavia_norway'),
            data_lane=SAR_MASKS_LANE,
            record_count=None,
            record_count_kind='scene and patch count comes from downloaded AvalCD manifest',
            curation_level='annotated SAR change-detection benchmark scenes',
            license='Zenodo record license must be reviewed before local ingestion',
            source_url='https://doi.org/10.5281/zenodo.15863589',
            citation='AvalCD benchmark dataset, Zenodo DOI 10.5281/zenodo.15863589.',
            recommended_weight=0.7,
            risk_notes=(
                'Keep as SAR shadow-training input through the existing sar_training_manifest_v1 contract.',
                'Do not publish SAR outputs until held-out SAR and RF baseline promotion gates pass.',
            ),
        ),
        _source(
            source_key='slf_data_service_weather_snowpack',
            label='SLF data service weather and snowpack data',
            region_keys=('swiss_alps',),
            data_lane=WEATHER_SNOWPACK_FEATURES_LANE,
            record_count=None,
            record_count_kind='API-backed measurements; count depends on station, product, and date range',
            curation_level='official SLF open-data service',
            license='CC BY 4.0 according to SLF data service; verify product-specific terms and attribution',
            source_url='https://www.slf.ch/en/services-and-products/slf-data-service/',
            citation='WSL Institute for Snow and Avalanche Research SLF data service.',
            allowed_roles=(REGISTRY_ONLY_ROLE, STAGING_ROLE, BENCHMARK_ROLE, FEATURE_JOIN_ROLE),
            default_training_role=FEATURE_JOIN_ROLE,
            recommended_weight=0.6,
            risk_notes=(
                'Weather and snowpack measurements are covariates, not avalanche occurrence labels.',
                'Use for benchmark feature reconstruction and calibration diagnostics.',
            ),
        ),
        _source(
            source_key='slf_bulletin_caaml',
            label='SLF avalanche bulletin CAAML API',
            region_keys=('swiss_alps',),
            data_lane=DANGER_RATING_LABELS_LANE,
            record_count=None,
            record_count_kind='API-backed bulletin products; count depends on date range and bulletin geography',
            curation_level='official avalanche danger bulletin data',
            license='CC BY 4.0 according to SLF data service; verify product-specific terms and attribution',
            source_url='https://aws.slf.ch/api/bulletin/caaml',
            citation='SLF avalanche bulletin CAAML API.',
            allowed_roles=(REGISTRY_ONLY_ROLE, STAGING_ROLE, BENCHMARK_ROLE),
            default_training_role=BENCHMARK_ROLE,
            recommended_weight=0.45,
            risk_notes=(
                'Danger ratings are expert forecasts, not observed avalanche occurrence truth.',
                'Use for benchmark alignment and forecast calibration, not as direct debris labels.',
            ),
        ),
        _source(
            source_key='slf_accident_datasets',
            label='SLF avalanche accident datasets',
            region_keys=('swiss_alps',),
            data_lane=ACCIDENT_EVENT_LABELS_LANE,
            record_count=None,
            record_count_kind='two EnviDat accident datasets; exact rows depend on selected all-accident or fatal-only export',
            curation_level='high-provenance accident/event records with person-involved or fatality filters',
            license='SLF/EnviDat terms; CC BY 4.0 and product-specific DOI/terms must be verified before storage',
            source_url='https://www.slf.ch/en/avalanches/avalanches-and-avalanche-accidents/accident-data/',
            citation='WSL Institute for Snow and Avalanche Research SLF. Avalanche accidents since 1970/71 (doi:10.16904/envidat.411) and fatal avalanche accidents since 1936/37 (doi:10.16904/envidat.412).',
            allowed_roles=(REGISTRY_ONLY_ROLE, STAGING_ROLE, BENCHMARK_ROLE),
            default_training_role=BENCHMARK_ROLE,
            recommended_weight=0.3,
            risk_notes=(
                'Accident-only labels are high provenance but not representative of all avalanches.',
                'Use for benchmark spot checks, casualty-context analysis, and danger-rating calibration diagnostics.',
                'Do not treat accident frequency as avalanche occurrence frequency.',
            ),
        ),
        _source(
            source_key='eaws_bulletin_context',
            label='EAWS bulletin context and danger-scale harmonization',
            region_keys=('swiss_alps', 'french_alps', 'scandinavia_norway'),
            data_lane=BULLETIN_CONTEXT_LANE,
            record_count=None,
            record_count_kind='context feed; no occurrence-label count',
            curation_level='public warning-context standardization surface',
            license='source-specific bulletin/API terms must be reviewed before storage or redistribution',
            source_url='https://www.avalanches.org/',
            citation='European Avalanche Warning Services (EAWS) public warning context.',
            allowed_roles=(REGISTRY_ONLY_ROLE, STAGING_ROLE, BENCHMARK_ROLE),
            default_training_role=BENCHMARK_ROLE,
            recommended_weight=0.25,
            risk_notes=(
                'Bulletin text and danger scale provide context and calibration targets, not independent event truth.',
                'Keep out of direct model fitting unless converted into explicit benchmark labels.',
            ),
        ),
    ]
    return {source.source_key: source for source in sources}


def dataset_family_assessments() -> dict[str, DatasetFamilyAssessment]:
    assessments = [
        DatasetFamilyAssessment(
            family_key='norway_472k_sar_detections',
            dataset_family='Norway 472k SAR detections',
            source_keys=('norway_sar_activity_monitoring', 'norway_sar_fcn_labels'),
            best_use='Sequence forecasting, SAR detector pretraining, avalanche activity priors',
            enhancement_value=5.0,
            main_caution='Automated detections need false-positive handling and temporal uncertainty.',
            implementation_status='source registry and benchmark-only gates implemented',
            remaining_work=(
                'Verify source package, license, and exact row/scene schema.',
                'Stage detections with temporal uncertainty and false-positive fields.',
                'Build activity-rate benchmark before any detector pretraining use.',
            ),
        ),
        DatasetFamilyAssessment(
            family_key='swiss_spot6_24778_outlines',
            dataset_family='Swiss SPOT6 24,778 outlines',
            source_keys=('swiss_spot6_2018', 'swiss_spot6_2019'),
            best_use='High-quality occurrence polygons and optical/SAR validation benchmark',
            enhancement_value=4.5,
            main_caution='Extreme-event bias; not continuous all-season data.',
            implementation_status='source registry, license gates, and shadow occurrence staging contract implemented',
            remaining_work=(
                'Download and checksum EnviDat exports after license review.',
                'Normalize polygons to staged records with event-date and geometry refs.',
                'Build extreme-event benchmark split separate from normal-season validation.',
            ),
        ),
        DatasetFamilyAssessment(
            family_key='french_epa_clpa',
            dataset_family='French EPA/CLPA',
            source_keys=('french_epa_historical', 'french_clpa_extent_priors'),
            best_use='Long-term event history and terrain/path priors',
            enhancement_value=4.5,
            main_caution='Site-selection and observability bias; not full spatial coverage.',
            implementation_status='source registry and benchmark/path-prior gates implemented',
            remaining_work=(
                'Verify export terms and field schema from avalanches.fr.',
                'Split dated EPA event history from undated CLPA terrain/path priors.',
                'Create observability-bias audit slices before model fitting.',
            ),
        ),
        DatasetFamilyAssessment(
            family_key='swiss_weather_snowpack_danger',
            dataset_family='Swiss weather/snowpack/danger ratings',
            source_keys=('slf_data_service_weather_snowpack', 'slf_bulletin_caaml'),
            best_use='Danger-level model benchmarking, calibration, feature engineering',
            enhancement_value=4.0,
            main_caution='Danger ratings are expert forecast labels, not direct avalanche occurrence truth.',
            implementation_status='feature-join and benchmark gates implemented',
            remaining_work=(
                'Build API connector with station/date-range manifests and attribution metadata.',
                'Join covariates to staged occurrence labels without relabeling forecasts as observations.',
                'Add calibration slices comparing model danger outputs to SLF danger ratings.',
            ),
        ),
        DatasetFamilyAssessment(
            family_key='avalcd',
            dataset_family='AvalCD',
            source_keys=('avalcd_zenodo_v1',),
            best_use='SAR change-detection benchmark and repo-native 4-channel SAR path',
            enhancement_value=4.0,
            main_caution='Smaller occurrence count than the note implies; best for detector benchmarking.',
            implementation_status='source registry and conversion into existing sar_training_manifest_v1 implemented',
            remaining_work=(
                'Verify Zenodo license and retrieve the source manifest/assets.',
                'Stage AvalCD scenes with reviewed license IDs and storage refs.',
                'Run SAR detector benchmark and keep outputs shadow-only until gates pass.',
            ),
        ),
        DatasetFamilyAssessment(
            family_key='slf_accident_datasets',
            dataset_family='SLF accident datasets',
            source_keys=('slf_accident_datasets',),
            best_use='High-provenance event labels',
            enhancement_value=3.0,
            main_caution='Accident-only bias; not representative of all avalanches.',
            implementation_status='benchmark-only source registry and license gates implemented',
            remaining_work=(
                'Download all-accident and fatal-only EnviDat exports after terms review.',
                'Normalize caught/fatality fields and location uncertainty.',
                'Use as benchmark spot checks, not as occurrence-frequency training truth.',
            ),
        ),
        DatasetFamilyAssessment(
            family_key='eaws_slf_bulletins',
            dataset_family='EAWS/SLF bulletins',
            source_keys=('eaws_bulletin_context', 'slf_bulletin_caaml'),
            best_use='Evaluation context and warning semantics',
            enhancement_value=2.5,
            main_caution='Should not be used as observed event labels.',
            implementation_status='context and benchmark source gates implemented',
            remaining_work=(
                'Build bulletin-context ingestion with source attribution and no occurrence-label promotion.',
                'Map danger semantics to evaluation context fields.',
                'Keep public wording as EAWS-style experimental, not official warning equivalence.',
            ),
        ),
    ]
    return {assessment.family_key: assessment for assessment in assessments}


def summarize_dataset_family_assessments(
    assessments: Iterable[DatasetFamilyAssessment] | None = None,
) -> dict[str, Any]:
    values = [
        float(assessment.enhancement_value)
        for assessment in (list(assessments) if assessments is not None else dataset_family_assessments().values())
    ]
    if not values:
        return {
            'family_count': 0,
            'average_enhancement_value': None,
            'high_value_family_count': 0,
            'highest_enhancement_value': None,
        }
    return {
        'family_count': len(values),
        'average_enhancement_value': round(sum(values) / len(values), 2),
        'high_value_family_count': sum(1 for value in values if value >= 4.0),
        'highest_enhancement_value': max(values),
    }


def get_european_source(source_key: str) -> EuropeanSource:
    key = str(source_key or '').strip()
    registry = european_source_registry()
    if key not in registry:
        raise KeyError(f'unknown European source "{source_key}"')
    return registry[key]


def source_usage_issues(
    source: EuropeanSource,
    *,
    requested_role: str,
    license_review_id: str | None = None,
) -> list[str]:
    role = str(requested_role or '').strip() or STAGING_ROLE
    issues: list[str] = []
    if role == PRODUCTION_SCORING_ROLE:
        issues.append('European sources are blocked from production scoring until explicit promotion gates pass.')
    if role not in source.allowed_roles:
        issues.append(f'source "{source.source_key}" does not allow role "{role}"')
    if source.requires_license_review and role not in {REGISTRY_ONLY_ROLE, STAGING_ROLE}:
        if not str(license_review_id or '').strip():
            issues.append(f'source "{source.source_key}" requires a license_review_id before role "{role}"')
    if role == SHADOW_TRAINING_ROLE and source.data_lane not in LABEL_LANES:
        issues.append(f'source "{source.source_key}" lane "{source.data_lane}" is not a training-label lane')
    return issues


def assert_source_usable_for_role(
    source: EuropeanSource,
    *,
    requested_role: str,
    license_review_id: str | None = None,
) -> None:
    issues = source_usage_issues(source, requested_role=requested_role, license_review_id=license_review_id)
    if issues:
        raise ValueError('; '.join(issues))


def summarize_sources_by_lane(sources: Iterable[EuropeanSource]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for source in sources:
        lane = source.data_lane
        entry = summary.setdefault(lane, {
            'source_count': 0,
            'known_record_count': 0,
            'unknown_record_count_sources': [],
            'source_keys': [],
        })
        entry['source_count'] += 1
        entry['source_keys'].append(source.source_key)
        if source.record_count is None:
            entry['unknown_record_count_sources'].append(source.source_key)
        else:
            entry['known_record_count'] += int(source.record_count)
    for entry in summary.values():
        entry['source_keys'] = sorted(entry['source_keys'])
        entry['unknown_record_count_sources'] = sorted(entry['unknown_record_count_sources'])
    return dict(sorted(summary.items()))


def build_shadow_evaluation_gate_manifest() -> dict[str, Any]:
    return {
        'version': EUROPEAN_SHADOW_EVALUATION_GATE_VERSION,
        'public_scoring_default': 'unchanged_current_rf_baseline',
        'production_scoring_allowed': False,
        'baseline_model': {
            'model_version': 'surrogate_rf_v1',
            'role': 'current_public_baseline',
            'required_comparator': True,
        },
        'candidate_gates': [
            {
                'candidate': 'rf_recalibrated_with_european_shadow_lane',
                'required_before_promotion': [
                    'time-split PSS strictly greater than current RF baseline',
                    'Brier score less than or equal to current RF baseline',
                    'no material degradation on non-European local validation slices',
                    'license and attribution audit complete for every included source',
                ],
            },
            {
                'candidate': 'mts_lstm_v1',
                'required_before_promotion': [
                    'existing strict_pss_gt_rf_and_brier_lte_rf gate passes',
                    'SAR volume gates pass across minimum events, regions, and scene dates',
                    'European sequence features evaluated as shadow covariates only',
                ],
            },
            {
                'candidate': 'sar_unet_or_swinunet',
                'required_before_promotion': [
                    'held-out SAR F-score and false-positive gates pass',
                    'AvalCD/SPOT6-derived labels remain in shadow manifests until reviewed',
                    'public hazard contract continues to show fallback/candidate state until promoted',
                ],
            },
        ],
    }


def build_european_shadow_manifest(
    *,
    selected_keys: Iterable[str] | None = None,
    snapshot_id: str | None = None,
    license_review_ids: dict[str, str] | None = None,
) -> dict[str, Any]:
    registry = european_source_registry()
    keys = list(selected_keys) if selected_keys is not None else sorted(registry)
    missing = sorted(set(keys) - set(registry))
    if missing:
        raise KeyError(f'unknown European source(s): {", ".join(missing)}')
    review_ids = license_review_ids or {}
    sources = [registry[key] for key in keys]
    selected_key_set = set(keys)
    family_assessments = [
        assessment
        for assessment in dataset_family_assessments().values()
        if set(assessment.source_keys).intersection(selected_key_set)
    ]
    generated_at = datetime.now(timezone.utc).isoformat()
    return {
        'version': EUROPEAN_SHADOW_MANIFEST_VERSION,
        'snapshot_id': str(snapshot_id or f'european-shadow-{generated_at[:10]}'),
        'generated_at': generated_at,
        'source_count': len(sources),
        'sources': [source.as_manifest_dict() for source in sources],
        'summary_by_lane': summarize_sources_by_lane(sources),
        'dataset_family_assessments': [
            assessment.as_manifest_dict()
            for assessment in family_assessments
        ],
        'dataset_family_summary': summarize_dataset_family_assessments(family_assessments),
        'usage_gates': {
            source.source_key: {
                role: {
                    'allowed': not source_usage_issues(
                        source,
                        requested_role=role,
                        license_review_id=review_ids.get(source.source_key),
                    ),
                    'issues': source_usage_issues(
                        source,
                        requested_role=role,
                        license_review_id=review_ids.get(source.source_key),
                    ),
                }
                for role in (REGISTRY_ONLY_ROLE, STAGING_ROLE, BENCHMARK_ROLE, SHADOW_TRAINING_ROLE, FEATURE_JOIN_ROLE, PRODUCTION_SCORING_ROLE)
            }
            for source in sources
        },
        'evaluation_gates': build_shadow_evaluation_gate_manifest(),
    }


def _clean_string(value: Any) -> str:
    return str(value or '').strip()


def normalize_staged_european_record(
    raw: dict[str, Any],
    *,
    source_key: str | None = None,
    requested_role: str = STAGING_ROLE,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError('raw European staged record must be a JSON object')
    source = get_european_source(source_key or _clean_string(raw.get('source_key')))
    role = _clean_string(requested_role) or STAGING_ROLE
    license_review_id = _clean_string(raw.get('license_review_id')) or None
    assert_source_usable_for_role(source, requested_role=role, license_review_id=license_review_id)

    external_id = _clean_string(raw.get('external_id') or raw.get('event_id') or raw.get('scene_id'))
    if not external_id:
        raise ValueError('European staged record is missing external_id/event_id/scene_id')
    region_key = _clean_string(raw.get('region_key'))
    if region_key not in source.region_keys:
        raise ValueError(
            f'record region_key "{region_key}" is not allowed for source "{source.source_key}"; '
            f'expected one of: {", ".join(source.region_keys)}',
        )

    metadata = raw.get('metadata') if isinstance(raw.get('metadata'), dict) else {}
    asset_refs = {
        key: _clean_string(raw.get(key))
        for key in ('geometry_ref', 'stack_ref', 'truth_mask_ref', 'bulletin_ref', 'feature_ref')
        if _clean_string(raw.get(key))
    }
    raw_weight = raw.get('training_weight', source.recommended_weight)
    try:
        weight = min(float(raw_weight), source.recommended_weight)
    except (TypeError, ValueError):
        weight = source.recommended_weight

    training_eligible = role == SHADOW_TRAINING_ROLE and source.data_lane in LABEL_LANES
    return {
        'version': EUROPEAN_STAGED_RECORD_VERSION,
        'source_key': source.source_key,
        'source_label': source.label,
        'data_lane': source.data_lane,
        'external_id': external_id,
        'scene_id': _clean_string(raw.get('scene_id')) or external_id,
        'event_id': _clean_string(raw.get('event_id')) or external_id,
        'region_key': region_key,
        'event_time': _clean_string(raw.get('event_time') or raw.get('timestamp')) or None,
        'label': raw.get('label', 1 if source.data_lane in LABEL_LANES else None),
        'requested_role': role,
        'training_eligible': training_eligible,
        'production_eligible': False,
        'training_weight': weight,
        'license_review_id': license_review_id,
        'attribution': source.citation if source.attribution_required else None,
        'asset_refs': asset_refs,
        'metadata': {
            **metadata,
            'source_url': source.source_url,
            'default_training_role': source.default_training_role,
            'risk_notes': list(source.risk_notes),
        },
    }


def staged_record_to_sar_training_scene(record: dict[str, Any], *, split: str = 'train') -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError('staged SAR record must be a JSON object')
    source = get_european_source(_clean_string(record.get('source_key')))
    if source.data_lane not in SAR_MANIFEST_LANES:
        raise ValueError(f'source "{source.source_key}" lane "{source.data_lane}" cannot build a SAR training scene')
    normalized_split = _clean_string(split).lower()
    if normalized_split not in SAR_TRAINING_ALLOWED_SPLITS:
        raise ValueError(
            f'unsupported SAR split "{split}"; expected one of: {", ".join(sorted(SAR_TRAINING_ALLOWED_SPLITS))}',
        )
    asset_refs = record.get('asset_refs') if isinstance(record.get('asset_refs'), dict) else {}
    stack_ref = _clean_string(asset_refs.get('stack_ref') or record.get('stack_ref'))
    truth_mask_ref = _clean_string(asset_refs.get('truth_mask_ref') or record.get('truth_mask_ref'))
    if not stack_ref:
        raise ValueError(f'staged SAR record "{record.get("external_id")}" is missing stack_ref')
    if not truth_mask_ref:
        raise ValueError(f'staged SAR record "{record.get("external_id")}" is missing truth_mask_ref')
    return {
        'source_dataset': source.source_key,
        'event_id': _clean_string(record.get('event_id') or record.get('external_id')),
        'scene_id': _clean_string(record.get('scene_id') or record.get('external_id')),
        'region_key': _clean_string(record.get('region_key')),
        'split': normalized_split,
        'stack_ref': stack_ref,
        'truth_mask_ref': truth_mask_ref,
        'metadata': {
            'european_shadow_source_label': source.label,
            'license_review_id': record.get('license_review_id'),
            'production_eligible': False,
        },
    }


def build_sar_training_manifest_from_staged_records(
    records: Iterable[dict[str, Any]],
    *,
    dataset_version: str = 'european-shadow-sar-v1',
    split: str = 'train',
) -> dict[str, Any]:
    scenes = [staged_record_to_sar_training_scene(record, split=split) for record in records]
    if not scenes:
        raise ValueError('at least one staged SAR record is required')
    return {
        'version': SAR_TRAINING_MANIFEST_VERSION,
        'dataset_version': dataset_version,
        'scenes': scenes,
    }
