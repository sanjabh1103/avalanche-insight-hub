# Revised Full-Pivot Plan: Autonomous SAR + MTS-LSTM Avalanche Platform

## Summary

This revision treats the customer proposal as a real platform pivot, but only where it is technically defensible. The current repo already has strong pieces we should reuse: async `forecast_grids`, topo-aware ingestion, Gemini news extraction, field-report PWA, SVM-RFE/KMeansSMOTE/RF training, Chebyshev IPA, and TreeSHAP UX. The gaps are the actual segmentation stack, a true multi-timescale sequence model, weighted autonomous-label governance, and batch-only serving.

The plan below assumes these locked decisions:
- Full pivot, not a hybrid stopgap.
- Paid APIs and GPU infrastructure are allowed.
- First-wave Groundsource scope is `news + field reports`, not social.
- Autonomous labels may enter training directly, but only through confidence weights.
- The edge fallback is removed; `forecast_grids` becomes the only serving path.
- First production SAR wave must store both masks and derived geometry.

## Key Changes

### 1. Serving and Ops Baseline
1. Make batch output authoritative. `forecast_grids` is the only runtime source; if no fresh row exists, the UI shows `stale/unavailable` instead of synthesizing a heuristic forecast.
2. Fix current operational blockers before the pivot: correct the weekly train cron mismatch, add missing dependency installs, and stop treating optional GPU paths as production-ready.
3. Reuse the existing Modal-style remote worker hooks for GPU jobs instead of inventing a second orchestration plane. GitHub Actions remains the scheduler/control plane; GPU workers do segmentation, sequence training, and batch inference.

### 2. Autonomous Data Genesis
1. Add a SAR artifact pipeline that stores:
   - source scene metadata,
   - raster mask assets,
   - polygonized avalanche geometry,
   - centroid summaries,
   - model version,
   - confidence score,
   - provenance fields.
2. Seed the SAR segmentation model from external avalanche SAR corpora / pretrained work, not from local manual labeling. Current literature on avalanche segmentation depends on manually annotated Sentinel-1 masks, so “zero local history” must mean “bootstrap from external labeled corpora + local weak labels,” not “train from nothing.”
3. Use the current GEE threshold/shadow-mask pipeline as a candidate-mining and QA baseline during bootstrap. Do not delete it until segmentation quality is proven.
4. Keep Groundsource scope to `NewsData + Gemini + field reports`. No social connectors in wave 1.
5. Replace binary `training_eligible` thinking for autonomous sources with weighted governance:
   - `label_confidence` from source/model,
   - `source_weight` by provenance,
   - `corroboration_weight` when SAR/news/field reports agree,
   - recency decay.
6. Low-confidence autonomous labels are excluded below a hard floor; above that floor they auto-enter training with weights, not as full-strength labels.

### 3. Prediction Engine Pivot
1. Replace the pseudo-sequence LSTM with a true MTS-LSTM implementation using a maintained sequence framework such as NeuralHydrology-style branched LSTMs.
2. Build a proper sequence feature store:
   - daily weather branch,
   - hourly weather branch,
   - static terrain branch,
   - event-derived supervision windows from SAR masks, news, and field reports.
3. The production hazard probability comes from MTS-LSTM, not the current RF.
4. Keep static terrain in the risk layer through Chebyshev IPA fusion after the sequence model score. Terrain remains a fusion input; legacy HIM-STRAT-style physical proxies are removed from the production score once cutover passes.
5. Do not force `KMeansSMOTE` into the sequence model. For the MTS-LSTM, use weighted sampling + class-weighted / focal loss. Sequence-space SMOTE is not a credible production choice here.

### 4. Calibration, Explainability, and Surrogates
1. Preserve the existing SVM-RFE + KMeansSMOTE + cost-sensitive tree stack, but change its role:
   - explanation surrogate,
   - calibration benchmark,
   - shadow baseline during cutover.
2. Apply SVM-RFE before sequence assembly to lock the approved weather driver set for the MTS-LSTM input channels.
3. Keep `KMeansSMOTE` in the tree surrogate / tabular benchmark path where it is already feasible and implemented.
4. Use exact TreeSHAP only on the tree surrogate. Do not claim TreeSHAP on the MTS-LSTM itself.
5. User-facing narratives remain SHAP-based, but the contract must say they explain the surrogate aligned to the production forecast, not the recurrent model internals.
6. Uncertainty for the production score comes from sequence-model ensembling or MC-dropout-style inference; tree variance is retained only for the surrogate path.

### 5. Cutover and Removal of Legacy Paths
1. Run the new SAR segmentation and MTS-LSTM in shadow mode first against the current RF-centric batch pipeline.
2. Promote the new pipeline only if all gates pass on held-out and rolling operational windows:
   - segmentation F1 / IoU,
   - PSS,
   - Brier / ECE,
   - latency and GPU cost ceiling,
   - forecast freshness SLA,
   - explanation consistency.
3. After promotion:
   - remove edge heuristic forecast generation,
   - retire RF as the production scorer,
   - keep the tree model only as surrogate / regression-test benchmark,
   - keep the old GEE threshold path as a fallback label miner until segmentation has stable regional coverage.

## Public Interfaces / Data Contracts

- `forecast_grids` payload must grow to include:
  - `dynamic_model_type`,
  - `dynamic_model_version`,
  - `surrogate_model_version`,
  - `uncertainty_method`,
  - `label_snapshot_id`,
  - `sar_mask_asset_refs`,
  - `sar_event_geometries`,
  - explicit `stale` state.
- Event records must support weighted autonomous provenance:
  - `label_confidence`,
  - `training_weight`,
  - `source_model`,
  - `source_scene_ids`,
  - `geometry_type`,
  - `mask_asset_ref`.
- GPU worker API surface should be explicit:
  - `sar-segment`,
  - `train-mtslstm`,
  - `infer-mtslstm`,
  - `train-surrogate`,
  - `evaluate-release`.
- Frontend contract changes:
  - no runtime forecast synthesis,
  - stale/unavailable state when batch output is missing,
  - mask + geometry overlays in addition to grid cells.

## Test Plan

- Unit tests:
  - label-weight computation,
  - SAR mask polygonization,
  - sequence window builder,
  - MTS-LSTM input shape and branch handoff,
  - surrogate SHAP contract,
  - stale-state rendering.
- Integration tests:
  - news article -> Gemini extraction -> weighted event row,
  - field report -> topo snap -> weighted event row,
  - SAR scene -> mask asset -> geometry -> weighted event row,
  - batch inference -> `forecast_grids` only -> UI load without fallback.
- Acceptance gates:
  - segmentation beats the current threshold baseline on held-out SAR scenes,
  - MTS-LSTM beats the current RF baseline on PSS and calibration,
  - surrogate explanations remain available for every served forecast cell,
  - no forecast is served from client or edge synthesis after cutover.

## Assumptions and Defaults

- GPU work runs through the existing optional remote-worker shape, promoted to first-class infrastructure.
- `news + field reports` is the only Groundsource scope in wave 1.
- Autonomous labels flow directly into training with weights; they are not blocked on manual promotion.
- First SAR production release stores full masks plus derived geometry, not centroids only.
- TreeSHAP remains in the product via a surrogate tree model because exact TreeSHAP is a tree-method explainer, while the production scorer becomes MTS-LSTM.
- This plan is based on the current repo state plus the external feasibility anchors that matter most:
  - avalanche SAR segmentation depends on manually annotated Sentinel-1 corpora rather than true zero-label bootstrapping,
  - MTS-LSTM is a branched multi-timescale sequence model, not the current pseudo-sequence LSTM,
  - standard GitHub-hosted runners are CPU-bound,
  - Google Maps geocoding is billed and quota-managed.
