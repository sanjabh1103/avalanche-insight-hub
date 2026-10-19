from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.reproduction.swiss_ravafcast.constants import RF1_RESOURCE_KEY, RF2_RESOURCE_KEY
from backend.reproduction.swiss_ravafcast.aggregate import build_aggregation_from_rf4_result
from backend.reproduction.swiss_ravafcast.data_loader import load_and_validate
from backend.reproduction.swiss_ravafcast.evaluate import write_reproduction_summary
from backend.reproduction.swiss_ravafcast.interpolate_gpxyz import build_gpxyz_readiness_payload
from backend.reproduction.swiss_ravafcast.interpolate_gpxyz import build_station_metadata_payload
from backend.reproduction.swiss_ravafcast.interpolate_gpxyz import write_station_metadata_template
from backend.reproduction.swiss_ravafcast.manifest import read_manifest
from backend.reproduction.swiss_ravafcast.train_rf4 import (
    SwissRF4Config,
    build_rf4_feature_audit,
    markdown_feature_audit,
    train_rf4_danger,
)


def _validate_data(args: argparse.Namespace) -> int:
    manifest = read_manifest(args.manifest)
    resources = {resource['resource_key']: resource for resource in manifest['resources']}
    reports = []
    for key in (RF1_RESOURCE_KEY, RF2_RESOURCE_KEY):
        resource = resources[key]
        _frame, report = load_and_validate(Path(resource['local_path']), resource_key=key)
        reports.append(report.as_dict())
    payload = {
        'schema_version': 'swiss_ravafcast_validation_report_v1',
        'usage_boundary': manifest['usage_boundary'],
        'reports': reports,
        'production_scoring_allowed': False,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _train_rf4(args: argparse.Namespace) -> int:
    manifest = read_manifest(args.manifest)
    resources = {resource['resource_key']: resource for resource in manifest['resources']}
    frame, _report = load_and_validate(Path(resources[RF2_RESOURCE_KEY]['local_path']), resource_key=RF2_RESOURCE_KEY)
    result = train_rf4_danger(
        frame,
        config=SwissRF4Config(
            seed=args.seed,
            n_estimators=args.n_estimators,
            min_samples_leaf=args.min_samples_leaf,
        ),
        feature_set_name=args.feature_set,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding='utf-8')
    return 0


def _audit_rf4_features(args: argparse.Namespace) -> int:
    manifest = read_manifest(args.manifest)
    resources = {resource['resource_key']: resource for resource in manifest['resources']}
    frame, _report = load_and_validate(Path(resources[RF2_RESOURCE_KEY]['local_path']), resource_key=RF2_RESOURCE_KEY)
    payload = build_rf4_feature_audit(
        frame,
        config=SwissRF4Config(
            seed=args.seed,
            n_estimators=args.n_estimators,
            min_samples_leaf=args.min_samples_leaf,
        ),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
    if args.output_markdown:
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output_markdown.write_text(markdown_feature_audit(payload), encoding='utf-8')
    return 0


def _audit_gpxyz(args: argparse.Namespace) -> int:
    manifest = read_manifest(args.manifest)
    resources = {resource['resource_key']: resource for resource in manifest['resources']}
    frame, _report = load_and_validate(Path(resources[RF2_RESOURCE_KEY]['local_path']), resource_key=RF2_RESOURCE_KEY)
    payload = build_gpxyz_readiness_payload(frame)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
    return 0


def _audit_station_metadata(args: argparse.Namespace) -> int:
    manifest = read_manifest(args.manifest)
    resources = {resource['resource_key']: resource for resource in manifest['resources']}
    frame, _report = load_and_validate(Path(resources[RF2_RESOURCE_KEY]['local_path']), resource_key=RF2_RESOURCE_KEY)
    metadata_frame = None
    if args.station_metadata:
        import pandas as pd

        metadata_frame = pd.read_csv(args.station_metadata)
    payload = build_station_metadata_payload(frame, metadata_frame)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
    return 0


def _write_station_metadata_template(args: argparse.Namespace) -> int:
    manifest = read_manifest(args.manifest)
    resources = {resource['resource_key']: resource for resource in manifest['resources']}
    frame, _report = load_and_validate(Path(resources[RF2_RESOURCE_KEY]['local_path']), resource_key=RF2_RESOURCE_KEY)
    write_station_metadata_template(frame, args.output)
    return 0


def _aggregate_elev_simple(args: argparse.Namespace) -> int:
    result = json.loads(args.rf4_result.read_text(encoding='utf-8'))
    payload = build_aggregation_from_rf4_result(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
    return 0


def _summarize_reproduction(args: argparse.Namespace) -> int:
    write_reproduction_summary(
        validation_report_path=args.validation_report,
        rf4_result_path=args.rf4_result,
        gpxyz_report_path=args.gpxyz_report,
        aggregation_result_path=args.aggregation_result,
        output_json=args.output,
        output_markdown=args.output_markdown,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Swiss RAvaFcast research-only reproduction tools')
    subparsers = parser.add_subparsers(dest='command', required=True)

    validate = subparsers.add_parser('validate-data', help='Validate downloaded EnviDat RF1/RF2 CSVs')
    validate.add_argument('--manifest', type=Path, required=True)
    validate.add_argument('--output', type=Path)
    validate.set_defaults(func=_validate_data)

    train = subparsers.add_parser('train-rf4', help='Train research-only 4-class Swiss danger RF')
    train.add_argument('--manifest', type=Path, required=True)
    train.add_argument('--output', type=Path, required=True)
    train.add_argument('--seed', type=int, default=20260522)
    train.add_argument('--n-estimators', type=int, default=300)
    train.add_argument('--min-samples-leaf', type=int, default=2)
    train.add_argument(
        '--feature-set',
        choices=('auto_numeric_current', 'paper_candidate_whitelist', 'leakage_guarded'),
        default='auto_numeric_current',
    )
    train.set_defaults(func=_train_rf4)

    audit = subparsers.add_parser('audit-rf4-features', help='Compare RF4 feature sets and parity-risk signals')
    audit.add_argument('--manifest', type=Path, required=True)
    audit.add_argument('--output', type=Path, required=True)
    audit.add_argument('--output-markdown', type=Path)
    audit.add_argument('--seed', type=int, default=20260522)
    audit.add_argument('--n-estimators', type=int, default=80)
    audit.add_argument('--min-samples-leaf', type=int, default=2)
    audit.set_defaults(func=_audit_rf4_features)

    gpxyz = subparsers.add_parser('audit-gpxyz', help='Check whether RF2 has station coordinates for GPxyz')
    gpxyz.add_argument('--manifest', type=Path, required=True)
    gpxyz.add_argument('--output', type=Path, required=True)
    gpxyz.set_defaults(func=_audit_gpxyz)

    station_metadata = subparsers.add_parser(
        'audit-station-metadata',
        help='Validate reviewed station coordinates for GPxyz readiness',
    )
    station_metadata.add_argument('--manifest', type=Path, required=True)
    station_metadata.add_argument('--station-metadata', type=Path)
    station_metadata.add_argument('--output', type=Path, required=True)
    station_metadata.set_defaults(func=_audit_station_metadata)

    station_template = subparsers.add_parser(
        'write-station-metadata-template',
        help='Write a station coordinate worksheet for reviewed GPxyz metadata collection',
    )
    station_template.add_argument('--manifest', type=Path, required=True)
    station_template.add_argument('--output', type=Path, required=True)
    station_template.set_defaults(func=_write_station_metadata_template)

    aggregate = subparsers.add_parser(
        'aggregate-elev-simple',
        help='Aggregate RF4 evaluation rows into warning-region/elevation-band summaries',
    )
    aggregate.add_argument('--rf4-result', type=Path, required=True)
    aggregate.add_argument('--output', type=Path, required=True)
    aggregate.set_defaults(func=_aggregate_elev_simple)

    summarize = subparsers.add_parser(
        'summarize-reproduction',
        help='Build a consolidated research-only status report from Swiss reproduction artifacts',
    )
    summarize.add_argument('--validation-report', type=Path, required=True)
    summarize.add_argument('--rf4-result', type=Path, required=True)
    summarize.add_argument('--gpxyz-report', type=Path, required=True)
    summarize.add_argument('--aggregation-result', type=Path, required=True)
    summarize.add_argument('--output', type=Path, required=True)
    summarize.add_argument('--output-markdown', type=Path)
    summarize.set_defaults(func=_summarize_reproduction)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
