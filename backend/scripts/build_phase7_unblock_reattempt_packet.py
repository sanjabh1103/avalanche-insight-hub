from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_OUTPUT_ROOT = Path(
    'backend/artifacts/european-shadow-qualification/phase7-unblock-reattempt-2026-05-18',
)
DEFAULT_V7_INTEGRITY = Path(
    'backend/artifacts/european-shadow-qualification/'
    'snowslide-research-grade-v7-2026-05-18/integrity-audit/snowslide_v6_integrity_audit.json',
)
DEFAULT_V7_SWEEP = Path(
    'backend/artifacts/european-shadow-qualification/'
    'snowslide-research-grade-v7-2026-05-18/integrity-audit/snowslide_v7_threshold_sweep_report.json',
)
DEFAULT_V7_ACCEPTANCE = Path(
    'backend/artifacts/european-shadow-qualification/snowslide-research-grade-v7-2026-05-18/acceptance_report.json',
)
DEFAULT_V7_AVALCD = Path(
    'backend/artifacts/european-shadow-real-benchmarks/'
    'european-shadow-real-avalcd-scene-blended-v7-2026-05-18/european_shadow_benchmark_report.json',
)
DEFAULT_V7_DRY_RUN = Path(
    'backend/artifacts/european-shadow-heldout/snowslide-dry-run/scene-blended-v7/evaluate_release_result.json',
)

ALLOWED_SOTA_MODEL_FAMILIES = {'resnet34_unet', 'swinunet_tiny_diff'}
DEFAULT_SOURCES_CHECKED = [
    'https://github.com/mattiagatti/avalanche-deep-change-detection',
    'https://zenodo.org/records/15863589',
    'https://arxiv.org/abs/2603.22658',
    'https://arxiv.org/abs/1910.05411',
    'https://github.com/RiccardoGelato/AdaptingSAMToSARAvalancheDetection',
]
TOP_FIVE_UNBLOCK_PATHS = [
    {
        'rank': 1,
        'path': 'SOTA checkpoint evaluation',
        'why_it_may_unblock': 'A compatible reviewed checkpoint could separate repo training quality from evaluation or calibration defects without another training run.',
        'decision': 'Try only with direct HTTPS checkpoint URL, license note, and repo-compatible model family.',
    },
    {
        'rank': 2,
        'path': 'SnowSlide calibration bridge',
        'why_it_may_unblock': 'v7 probability masks are valid and lower thresholds recover positives, but the all-scene sweep still missed precision/F1 floors.',
        'decision': 'Already tried for v7; keep as a recheck path if a future SOTA or candidate changes probability scale.',
    },
    {
        'rank': 3,
        'path': 'Domain-calibrated v8 candidate design',
        'why_it_may_unblock': 'The known failure is probability transfer from AvalCD to SnowSlide, not blank masks or missing scenes.',
        'decision': 'Design only now; one bounded GPU run requires separate approval.',
    },
    {
        'rank': 4,
        'path': 'SnowSlide label/domain audit expansion',
        'why_it_may_unblock': 'Qualification failures can be affected by SAR ambiguity, terrain shadow, registration, or source-label mismatch.',
        'decision': 'Use diagnostics before any new training; do not use SnowSlide as a clean final holdout after tuning.',
    },
    {
        'rank': 5,
        'path': 'Fresh final holdout',
        'why_it_may_unblock': 'A separate final set is mandatory after SnowSlide-guided candidate selection.',
        'decision': 'Do not start until SnowSlide research-grade first passes.',
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f'required Phase 7 unblock input not found: {label} ({path})')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'Phase 7 unblock input must be a JSON object: {label} ({path})')
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _source_avalcd_metrics(report: dict[str, Any]) -> dict[str, Any]:
    for source_report in report.get('source_reports') or []:
        if isinstance(source_report, dict) and source_report.get('source_key') == 'avalcd_zenodo_v1':
            metrics = source_report.get('sar_prediction_metrics')
            return metrics if isinstance(metrics, dict) else {}
    return {}


def _metric_values(container: dict[str, Any]) -> dict[str, Any]:
    metrics = container.get('metrics') if isinstance(container.get('metrics'), dict) else container
    return {
        'precision': metrics.get('precision'),
        'recall': metrics.get('recall'),
        'f1': metrics.get('f1'),
        'false_positive_rate': metrics.get('false_positive_rate'),
        'threshold': metrics.get('threshold'),
        'postprocess_min_component_area_px': metrics.get('postprocess_min_component_area_px'),
        'postprocess_opening_size_px': metrics.get('postprocess_opening_size_px'),
    }


def _best_sweep_candidate(sweep: dict[str, Any]) -> dict[str, Any]:
    selected = sweep.get('selected_candidate')
    if isinstance(selected, dict):
        return selected
    candidates = [item for item in sweep.get('candidates') or [] if isinstance(item, dict)]
    if not candidates:
        return {}
    return max(
        candidates,
        key=lambda item: (
            float((item.get('metrics') or {}).get('f1') or 0.0),
            float((item.get('metrics') or {}).get('precision') or 0.0),
        ),
    )


def _validate_sota_candidate(
    *,
    checkpoint_url: str | None,
    license_note: str | None,
    model_family: str,
    source_label: str,
    sources_checked: list[str],
) -> dict[str, Any]:
    if not checkpoint_url:
        return {
            'status': 'sota_checkpoint_unavailable',
            'decision': 'skip_sota_evaluation',
            'reason': 'No reviewed direct HTTPS checkpoint URL is available.',
            'sources_checked': sources_checked,
            'required_before_use': [
                'direct HTTPS model file URL',
                'license and usage note',
                'model family compatibility with repo evaluator',
            ],
        }
    parsed = urlparse(checkpoint_url.strip())
    blockers: list[str] = []
    if parsed.scheme != 'https' or not parsed.netloc:
        blockers.append('checkpoint URL must be direct HTTPS')
    if model_family not in ALLOWED_SOTA_MODEL_FAMILIES:
        blockers.append(f'model_family must be one of {sorted(ALLOWED_SOTA_MODEL_FAMILIES)}')
    if not str(license_note or '').strip():
        blockers.append('license note is required before checkpoint evaluation')
    if blockers:
        return {
            'status': 'blocked_invalid_sota_checkpoint_input',
            'decision': 'do_not_fetch',
            'checkpoint_url': checkpoint_url,
            'source_label': source_label,
            'model_family': model_family,
            'blockers': blockers,
        }
    return {
        'status': 'sota_checkpoint_candidate_ready',
        'decision': 'evaluate_sota_checkpoint_first',
        'checkpoint_url': checkpoint_url,
        'source_label': source_label,
        'model_family': model_family,
        'license_note': str(license_note).strip(),
        'next_commands': [
            'python3 -m backend.scripts.fetch_sota_sar_weights --model-url <url> --model-family <family> --model-version <version>',
            'python3 -m backend.scripts.build_avalcd_first_gate_plan ...',
            'python3 -m backend.scripts.run_modal_sar_checkpoint_evaluation_direct ...',
        ],
    }


def _v8_candidate_design(
    *,
    integrity: dict[str, Any],
    sweep: dict[str, Any],
    acceptance: dict[str, Any],
    avalcd_metrics: dict[str, Any],
    dry_run: dict[str, Any],
) -> dict[str, Any]:
    best = _best_sweep_candidate(sweep)
    best_metrics = best.get('metrics') if isinstance(best.get('metrics'), dict) else {}
    avalcd_values = avalcd_metrics.get('metrics') if isinstance(avalcd_metrics.get('metrics'), dict) else {}
    candidate_warranted = (
        acceptance.get('decision') == 'blocked_research_grade'
        and integrity.get('decision') == 'blocked_threshold_calibration_failure'
        and int(sweep.get('passing_candidate_count') or 0) == 0
        and float(best_metrics.get('precision') or 0.0) >= 0.60
        and float(best_metrics.get('recall') or 0.0) >= 0.50
    )
    decision = (
        'bounded_v8_candidate_design_recommended'
        if candidate_warranted
        else 'no_gpu_candidate_design_until_evidence_improves'
    )
    return {
        'version': 'candidate_design_report_v8',
        'decision': decision,
        'candidate_model_version': 'avalcd_swinunet_tiny_diff_calibrated_transfer_shadow_20260518_v8_design_only',
        'initial_checkpoint_path': '/artifacts/20260518T124829Z/sar_model.pt',
        'hypothesis': (
            'v7 learned an AvalCD-compatible separator, but its selected probability threshold does not '
            'transfer to SnowSlide. A v8 candidate should target probability-scale stability and '
            'precision/F1 recovery under all-seven-scene SnowSlide evaluation.'
        ),
        'evidence': {
            'avalcd_v7': _metric_values(avalcd_values),
            'snowslide_selected_rule': {
                'metrics': _metric_values(dry_run),
                'decision': acceptance.get('decision'),
                'decision_rule': acceptance.get('decision_rule'),
            },
            'snowslide_best_non_gpu_sweep': {
                'threshold': best.get('threshold'),
                'postprocess_min_component_area_px': best.get('postprocess_min_component_area_px'),
                'postprocess_opening_size_px': best.get('postprocess_opening_size_px'),
                'metrics': _metric_values(best_metrics),
                'policy': best.get('policy'),
            },
            'integrity_decision': integrity.get('decision'),
            'selected_threshold_positive_pixels': integrity.get('selected_threshold_positive_pixels'),
            'lowest_threshold_positive_pixels': integrity.get('lowest_threshold_positive_pixels'),
        },
        'proposed_training_request_overrides': {
            'loss': 'focal_tversky',
            'focal_tversky_alpha': 0.35,
            'focal_tversky_beta': 0.65,
            'focal_tversky_gamma': 1.33,
            'negative_ratio': 6,
            'epochs': 4,
            'patience': 2,
            'learning_rate': 0.000005,
            'batch_size': 8,
            'f_beta': 0.75,
            'threshold_grid': [0.90, 0.95, 0.97, 0.98, 0.985, 0.99, 0.995, 0.998],
            'postprocess_min_component_area_px': 128,
            'postprocess_opening_size_px': 0,
            'materialized_dataset_root': '/tmp/avalcd-shadow-train5-val2-v8',
        },
        'implementation_prerequisites': [
            'Do not train directly on SnowSlide labels unless the leakage is explicitly accepted as qualification-set tuning.',
            'Before GPU authorization, add or document a calibration-analysis step that compares AvalCD and SnowSlide probability distributions.',
            'If adding a true calibration loss, implement and test it before building a candidate authorization request.',
        ],
        'why_not_blind_sweep': [
            'The failure is localized to probability transfer: v7 masks are valid but the AvalCD-selected threshold exceeds SnowSlide probability maxima.',
            'The best v7 non-GPU candidate is close but still misses precision and F1 floors, so v8 targets FP control and threshold stability.',
            'The run is bounded to one future candidate and must stop on AvalCD or SnowSlide failure.',
        ],
        'stop_criteria': [
            'Stop if AvalCD scene_blended precision < 0.60 or recall < 0.50.',
            'Stop if SnowSlide precision < 0.70, recall < 0.50, F1 < 0.60, or FPR > 0.002.',
            'Stop after one bounded v8 run even if metrics improve but remain below floors.',
            'Require fresh final holdout before any Phase 7 promotion discussion if SnowSlide influenced candidate selection.',
        ],
        'gpu_run_authorized': False,
        'requires_explicit_operator_approval': True,
        'production_scoring_allowed': False,
        'promotion_allowed': False,
        'phase7_ready': False,
    }


def _claude_prompt(report: dict[str, Any]) -> str:
    best = report['candidate_design_report_v8']['evidence']['snowslide_best_non_gpu_sweep']
    return f"""You are Claude 4.7 acting as an adversarial ML systems reviewer for an avalanche SAR shadow-qualification program.

Repository: /Users/sanjayb/avalanche-insight-hub
Branch: feature/european-data-shadow-pipeline
Current state: clean and pushed at d767b49 or later.

Goal:
Independently audit whether Phase 7 can be honestly unblocked without weakening gates. Do not propose production promotion unless every gate is satisfied.

Non-goals:
- Do not weaken SnowSlide research-grade floors.
- Do not treat beats_baseline=true as sufficient.
- Do not promote SAR or public scoring.
- Do not run another GPU job unless you can justify exactly one bounded candidate after non-GPU evidence.

Known phase status:
- Phase 4 v7 AvalCD scene-blended passed:
  - precision 0.6687
  - recall 0.5678
  - F1 0.6141
  - FPR 0.001111
  - threshold 0.9980000257492065
  - component area 96
- Phase 5 v7 SnowSlide selected-rule failed:
  - precision 0.0
  - recall 0.0
  - F1 0.0
  - FPR 0.0
  - beats_baseline false
  - scene_count 7
- v7 integrity audit says masks are valid, not blank:
  - decision {report['v7_integrity_decision']}
  - selected_threshold_positive_pixels {report['selected_threshold_positive_pixels']}
  - lower-threshold positives exist
- v7 no-GPU sweep failed:
  - passing_candidate_count {report['v7_sweep_passing_candidate_count']}
  - best candidate threshold {best.get('threshold')}, component area {best.get('postprocess_min_component_area_px')}
  - precision {best['metrics'].get('precision')}
  - recall {best['metrics'].get('recall')}
  - F1 {best['metrics'].get('f1')}
  - FPR {best['metrics'].get('false_positive_rate')}
  - blockers precision_floor and f1_floor
- SOTA checkpoint path status: {report['sota_checkpoint_review']['status']}
- Phase 6 fresh final holdout is blocked pending SnowSlide research-grade.
- Phase 7 readiness is false.

Important repo files:
- docs/European_Data_Shadow_Pipeline.md
- backend/scripts/fetch_sota_sar_weights.py
- backend/scripts/build_phase7_unblock_reattempt_packet.py
- backend/scripts/build_snowslide_v6_integrity_audit.py
- backend/scripts/run_snowslide_threshold_sweep.py
- backend/scripts/build_sar_candidate_authorization_request.py
- backend/scripts/build_avalcd_first_gate_plan.py
- backend/scripts/build_snowslide_acceptance_report.py
- backend/common/sar_acceptance_policy.py
- backend/sar_unet_training.py
- backend/sar_unet_worker.py
- backend/sar_release_promote.py

Artifacts to inspect:
- backend/artifacts/european-shadow-qualification/snowslide-research-grade-v7-2026-05-18/integrity-audit/snowslide_v6_integrity_audit.json
- backend/artifacts/european-shadow-qualification/snowslide-research-grade-v7-2026-05-18/integrity-audit/snowslide_v7_threshold_sweep_report.json
- backend/artifacts/european-shadow-qualification/snowslide-research-grade-v7-2026-05-18/acceptance_report.json
- backend/artifacts/european-shadow-real-benchmarks/european-shadow-real-avalcd-scene-blended-v7-2026-05-18/european_shadow_benchmark_report.json
- backend/artifacts/european-shadow-heldout/snowslide-dry-run/scene-blended-v7/evaluate_release_result.json
- backend/artifacts/european-shadow-qualification/phase7-unblock-reattempt-2026-05-18/phase7_unblock_reattempt_report.json

Research anchors:
- AvalCD paper reports F1 0.8061 and F2 0.8414 under its benchmark.
- AvalCD GitHub documents patch size 128, stride 64, SwinUNet, BCE pos_weight 3.0, and tiled inference.
- Bianchi SAR FCN reports F1 above 66 percent against manual labels.
- SAR avalanche detection has strong domain sensitivity, label noise, terrain shadow/layover, and snow-condition ambiguity.

Please perform an adversarial analysis:
1. Verify whether the SnowSlide zero-positive result is threshold calibration, mask quantization, path mismatch, or true domain failure.
2. Verify masks are loaded as probabilities and whether threshold 0.9980000257492065 is invalid for max values around 0.9960784316.
3. Verify whether the same threshold/postprocess rule is correctly carried from AvalCD to SnowSlide.
4. Decide whether SOTA checkpoint evaluation is possible from public sources without inventing a checkpoint.
5. Decide whether the proposed v8 design is scientifically justified and not a blind sweep.

Final decision must be one of:
- stop_no_valid_unblock
- sota_checkpoint_evaluation_first
- calibration_bug_fix_first
- one_bounded_v8_candidate_warranted
- fresh_final_holdout_ready

Output:
- Findings table with severity.
- Evidence checklist with file/artifact references.
- Recommended next path.
- Commands to run.
- Risks and stop criteria.
"""


def _render_markdown(report: dict[str, Any]) -> str:
    best = report['candidate_design_report_v8']['evidence']['snowslide_best_non_gpu_sweep']
    lines = [
        '# Phase 7 Unblock Reattempt Packet',
        '',
        f"- Decision: `{report['decision']}`",
        f"- SOTA checkpoint status: `{report['sota_checkpoint_review']['status']}`",
        f"- V8 design decision: `{report['candidate_design_report_v8']['decision']}`",
        f"- GPU run authorized: `{str(report['next_gpu_run_authorized']).lower()}`",
        f"- Production scoring allowed: `{str(report['production_scoring_allowed']).lower()}`",
        '',
        '## Evidence',
        '',
        f"- v7 integrity: `{report['v7_integrity_decision']}`",
        f"- v7 selected-threshold positives: `{report['selected_threshold_positive_pixels']}`",
        f"- v7 sweep passing candidates: `{report['v7_sweep_passing_candidate_count']}`",
        (
            f"- Best v7 non-GPU candidate: threshold `{best.get('threshold')}`, area "
            f"`{best.get('postprocess_min_component_area_px')}`, precision "
            f"`{best['metrics'].get('precision')}`, recall `{best['metrics'].get('recall')}`, "
            f"F1 `{best['metrics'].get('f1')}`"
        ),
        '',
        '## Next Step',
        '',
        report['next_checkpoint'],
        '',
        '## Top Five Unblock Paths',
        '',
        '| Rank | Path | Decision |',
        '|---:|---|---|',
    ]
    for item in report.get('top_five_unblock_paths') or []:
        lines.append(f"| {item['rank']} | {item['path']} | {item['decision']} |")
    lines.append('')
    return '\n'.join(lines)


def _render_candidate_design_markdown(candidate_design: dict[str, Any]) -> str:
    evidence = candidate_design['evidence']
    best = evidence['snowslide_best_non_gpu_sweep']
    overrides = candidate_design['proposed_training_request_overrides']
    lines = [
        '# Candidate Design Report V8',
        '',
        f"- Decision: `{candidate_design['decision']}`",
        f"- Candidate model version: `{candidate_design['candidate_model_version']}`",
        f"- Initial checkpoint: `{candidate_design['initial_checkpoint_path']}`",
        f"- GPU run authorized: `{str(candidate_design['gpu_run_authorized']).lower()}`",
        f"- Production scoring allowed: `{str(candidate_design['production_scoring_allowed']).lower()}`",
        '',
        '## Hypothesis',
        '',
        candidate_design['hypothesis'],
        '',
        '## Evidence',
        '',
        f"- AvalCD v7 precision/recall/F1: `{evidence['avalcd_v7'].get('precision')}` / `{evidence['avalcd_v7'].get('recall')}` / `{evidence['avalcd_v7'].get('f1')}`",
        f"- SnowSlide selected-rule precision/recall/F1: `{evidence['snowslide_selected_rule']['metrics'].get('precision')}` / `{evidence['snowslide_selected_rule']['metrics'].get('recall')}` / `{evidence['snowslide_selected_rule']['metrics'].get('f1')}`",
        f"- Best non-GPU SnowSlide threshold/area: `{best.get('threshold')}` / `{best.get('postprocess_min_component_area_px')}`",
        f"- Best non-GPU precision/recall/F1: `{best['metrics'].get('precision')}` / `{best['metrics'].get('recall')}` / `{best['metrics'].get('f1')}`",
        f"- Integrity decision: `{evidence['integrity_decision']}`",
        '',
        '## Proposed Future Request Overrides',
        '',
    ]
    for key, value in overrides.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend([
        '',
        '## Stop Criteria',
        '',
    ])
    for item in candidate_design['stop_criteria']:
        lines.append(f"- {item}")
    lines.extend([
        '',
        '## Guardrails',
        '',
        '- This artifact is design-only.',
        '- Build a separate candidate authorization request before any Modal GPU run.',
        '- A future SnowSlide pass still requires an independent fresh final holdout before Phase 7 review.',
        '',
    ])
    return '\n'.join(lines)


def build_phase7_unblock_reattempt_packet(
    *,
    v7_integrity_path: Path,
    v7_sweep_path: Path,
    v7_acceptance_path: Path,
    v7_avalcd_benchmark_path: Path,
    v7_dry_run_path: Path,
    output_root: Path,
    sota_checkpoint_url: str | None = None,
    sota_license_note: str | None = None,
    sota_model_family: str = 'swinunet_tiny_diff',
    sota_source_label: str = 'public_search',
    sources_checked: list[str] | None = None,
) -> dict[str, Any]:
    integrity = _load_json(v7_integrity_path, label='v7_integrity')
    sweep = _load_json(v7_sweep_path, label='v7_sweep')
    acceptance = _load_json(v7_acceptance_path, label='v7_acceptance')
    avalcd_report = _load_json(v7_avalcd_benchmark_path, label='v7_avalcd_benchmark')
    dry_run = _load_json(v7_dry_run_path, label='v7_dry_run')
    avalcd_metrics = _source_avalcd_metrics(avalcd_report)
    checked = sources_checked or list(DEFAULT_SOURCES_CHECKED)
    sota = _validate_sota_candidate(
        checkpoint_url=sota_checkpoint_url,
        license_note=sota_license_note,
        model_family=sota_model_family,
        source_label=sota_source_label,
        sources_checked=checked,
    )
    candidate_design = _v8_candidate_design(
        integrity=integrity,
        sweep=sweep,
        acceptance=acceptance,
        avalcd_metrics=avalcd_metrics,
        dry_run=dry_run,
    )
    if sota['status'] == 'sota_checkpoint_candidate_ready':
        decision = 'sota_checkpoint_evaluation_first'
    elif int(sweep.get('passing_candidate_count') or 0) > 0:
        decision = 'calibration_bug_fix_first'
    elif candidate_design['decision'] == 'bounded_v8_candidate_design_recommended':
        decision = 'one_bounded_v8_candidate_warranted'
    else:
        decision = 'stop_no_valid_unblock'
    report = {
        'version': 'phase7_unblock_reattempt_packet_v1',
        'generated_at': _now_iso(),
        'decision': decision,
        'sota_checkpoint_review': sota,
        'candidate_design_report_v8': candidate_design,
        'v7_integrity_decision': integrity.get('decision'),
        'selected_threshold_positive_pixels': integrity.get('selected_threshold_positive_pixels'),
        'lowest_threshold_positive_pixels': integrity.get('lowest_threshold_positive_pixels'),
        'v7_sweep_passing_candidate_count': sweep.get('passing_candidate_count'),
        'v7_acceptance_decision': acceptance.get('decision'),
        'phase7_ready': False,
        'next_gpu_run_authorized': False,
        'production_scoring_allowed': False,
        'promotion_allowed': False,
        'fresh_final_holdout_allowed': False,
        'top_five_unblock_paths': TOP_FIVE_UNBLOCK_PATHS,
        'claude_47_prompt_path': str(output_root / 'claude_47_adversarial_review_prompt.md'),
        'next_checkpoint': (
            'Evaluate the reviewed SOTA checkpoint on AvalCD first.'
            if decision == 'sota_checkpoint_evaluation_first'
            else 'Recheck the passing non-GPU calibration rule against AvalCD scene_blended before any GPU work.'
            if decision == 'calibration_bug_fix_first'
            else 'Send the adversarial prompt to Claude 4.7, then decide whether to authorize exactly one v8 candidate.'
            if decision == 'one_bounded_v8_candidate_warranted'
            else 'Stop; current evidence does not justify another candidate.'
        ),
        'source_inputs': {
            'v7_integrity': str(v7_integrity_path),
            'v7_sweep': str(v7_sweep_path),
            'v7_acceptance': str(v7_acceptance_path),
            'v7_avalcd_benchmark': str(v7_avalcd_benchmark_path),
            'v7_dry_run': str(v7_dry_run_path),
        },
    }
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / 'phase7_unblock_reattempt_report.json', report)
    _write_json(output_root / 'candidate_design_report_v8.json', candidate_design)
    (output_root / 'phase7_unblock_reattempt_report.md').write_text(_render_markdown(report), encoding='utf-8')
    (output_root / 'candidate_design_report_v8.md').write_text(
        _render_candidate_design_markdown(candidate_design),
        encoding='utf-8',
    )
    (output_root / 'claude_47_adversarial_review_prompt.md').write_text(_claude_prompt(report), encoding='utf-8')
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build a Phase 7 unblock reattempt packet and Claude 4.7 adversarial prompt.')
    parser.add_argument('--v7-integrity', type=Path, default=DEFAULT_V7_INTEGRITY)
    parser.add_argument('--v7-sweep', type=Path, default=DEFAULT_V7_SWEEP)
    parser.add_argument('--v7-acceptance', type=Path, default=DEFAULT_V7_ACCEPTANCE)
    parser.add_argument('--v7-avalcd-benchmark', type=Path, default=DEFAULT_V7_AVALCD)
    parser.add_argument('--v7-dry-run', type=Path, default=DEFAULT_V7_DRY_RUN)
    parser.add_argument('--sota-checkpoint-url')
    parser.add_argument('--sota-license-note')
    parser.add_argument('--sota-model-family', default='swinunet_tiny_diff')
    parser.add_argument('--sota-source-label', default='public_search')
    parser.add_argument('--sources-checked', default=','.join(DEFAULT_SOURCES_CHECKED))
    parser.add_argument('--output-root', type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_phase7_unblock_reattempt_packet(
        v7_integrity_path=args.v7_integrity,
        v7_sweep_path=args.v7_sweep,
        v7_acceptance_path=args.v7_acceptance,
        v7_avalcd_benchmark_path=args.v7_avalcd_benchmark,
        v7_dry_run_path=args.v7_dry_run,
        output_root=args.output_root,
        sota_checkpoint_url=args.sota_checkpoint_url,
        sota_license_note=args.sota_license_note,
        sota_model_family=args.sota_model_family,
        sota_source_label=args.sota_source_label,
        sources_checked=[item.strip() for item in args.sources_checked.split(',') if item.strip()],
    )
    print(json.dumps({
        'status': 'ok',
        'decision': report['decision'],
        'sota_checkpoint_status': report['sota_checkpoint_review']['status'],
        'candidate_design_decision': report['candidate_design_report_v8']['decision'],
        'phase7_ready': report['phase7_ready'],
        'next_gpu_run_authorized': report['next_gpu_run_authorized'],
        'production_scoring_allowed': report['production_scoring_allowed'],
        'output_root': str(args.output_root),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
