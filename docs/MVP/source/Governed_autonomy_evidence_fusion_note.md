# Governed Autonomy Evidence Fusion Note

Updated: May 7, 2026

This note reframes the current autonomy story into what the repo actually proves today: governed evidence fusion under sparse-data constraints, not autonomous avalanche truth generation.

For slide generation, treat this file as `Repo/admin verified` plus `Artifact/doc proof only`. It supports evidence-governance claims, not active autonomy or promoted candidate-model claims.

## What The Current Repo Actually Does

The present evidence-fusion path is implemented in `backend/common/label_governance.py`, `backend/common/model_status_state.py`, and the operator surfaces that expose their summaries.

| Mechanism | Current implementation | What it proves | What it does not prove |
|---|---|---|---|
| `label_confidence` | Resolved from persisted label governance metadata, raw `label_confidence`, or fallback `confidence`, then clamped to `[0, 1]`. | Each record carries an explicit confidence signal before training weight is assigned. | Confidence is still a governed proxy, not field-certified avalanche truth. |
| `training_weight` | Combined from `label_confidence`, source weight, corroboration weight, recency decay, and training-reason penalties; clamped to `[0.1, 1.5]`. | Low-quality or stale records can be down-weighted instead of treated as equally trustworthy. | Weighted training does not eliminate label noise or domain shift. |
| Source weighting | Current base weights are explicit: `field_report=1.0`, `gemini_news=0.8`, `gee_sar=0.9`, `sar_unet=1.1`, `historical_backfill_v2_local_topo=0.85`. | Source trust is inspectable instead of hidden inside opaque heuristics. | These weights are governance choices, not scientist-signed calibration truth. |
| Corroboration | Each distinct corroborating source adds `0.15` up to a cap of `1.45`. | Multi-source support is rewarded in a transparent way. | Corroboration quality can still be weak if multiple sources repeat the same wrong story. |
| Recency decay | Half-life is `30` days, clamped to `[0.2, 1.0]`. | Old evidence does not dominate indefinitely. | Recency weighting cannot detect stale-but-persistent conceptual errors on its own. |
| Weak / audit-only handling | `sar_low_coverage` paths are penalized; `sar_single_pass_audit_only`, `sar_ambiguous_audit_only`, and `sar_unet_shadow_mode` remain non-training paths. | The repo already prevents some weak evidence from silently becoming core training truth. | This is governance protection, not scientist validation closure. |
| Model-status summaries | `autonomous_evidence_summary`, `dynamic_model_candidate`, `stability_summary`, and `latest_benchmark_summary` are persisted and surfaced in admin. | The operator lane can inspect evidence mix, blocked gates, runtime traces, and bounded stability. | Visibility does not equal promotion or public-claim eligibility. |

## Where Autonomy Helps Today

- It reduces exclusive dependence on manual reports by ingesting SAR- and news-derived evidence through explicit governance.
- It makes evidence weighting, recency, and corroboration inspectable instead of implicit.
- It gives the admin lane a concrete evidence-mix summary that can be challenged before training or promotion claims are made.
- It supports candidate-model review by preserving blocked gates and runtime evidence instead of upgrading by default.

## Where Autonomy Stops Today

- It does not create scientist-approved avalanche truth.
- It does not validate critical layers, weak layers, or snowpack structure in the field.
- It does not satisfy the release gates needed for promoted MTS-LSTM, authoritative SAR, or authority-grade warning posture.
- It does not remove the need for scientist review of failure slices, region transfer, or consequence interpretation.

## Failure Taxonomy

| Failure mode | How it can happen now | Current guard | Remaining risk | Required human review |
|---|---|---|---|---|
| Missing-event risk | Sparse reporting or missed SAR/news coverage leaves true avalanches absent from the governed dataset. | Evidence fusion accepts multiple source families and exposes source counts and region coverage. | The current artifact mix can still be narrow and incomplete. | Scientist review of benchmark case inventory and under-capture regions. |
| False-positive extraction | News or automated extraction reports an avalanche event that is ambiguous, duplicated, or wrongly localized. | `label_confidence`, source weighting, corroboration weighting, and audit-only exclusions. | Bad evidence can still enter as weak or down-weighted records. | Operator/scientist spot review of suspicious source clusters and extracted narratives. |
| Corroboration mismatch | Multiple sources support inconsistent details for the same event. | Distinct corroboration sources are tracked, and training weights stay bounded. | “More sources” can still reflect repeated error rather than independent confirmation. | Scientist judgment on what counts as materially independent corroboration. |
| Weak-layer blindness | Surface evidence exists, but critical-layer / persistent weak-layer state is not captured. | Current product copy and docs explicitly avoid claiming critical-layer closure. | Sparse-data autonomy can still look stronger than the underlying snow science. | Scientist-led review of weak-layer questions and acceptance criteria before promotion. |
| Stale source dominance | Old labels or patterns retain influence after conditions drift. | `30`-day half-life decay, `confidence_decayed`, and explicit drift mode state. | Recency decay reduces but does not solve concept drift or regional season shifts. | Scientist review of drift slices and whether accelerated decay remains adequate. |
| Regional transfer failure | A weight or heuristic that behaves acceptably in one region fails when transferred elsewhere. | Region coverage is surfaced in summaries; candidate gates remain blocked unless downstream evidence passes. | Transfer risk remains high across sparse-data mountain regions. | Scientist review of region-specific benchmark slices before any generalization claim. |

## Scientist-Safe Bottom Line

- The current autonomy story is strongest as governed evidence fusion.
- The repo can prove weighting, decay, corroboration, and blocked-gate discipline.
- The repo cannot yet prove autonomous avalanche truth generation, critical-layer closure, or authority-grade operational standing.
