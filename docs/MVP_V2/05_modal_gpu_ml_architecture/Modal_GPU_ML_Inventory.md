# Modal.com, GPU, And ML Inventory

Updated: May 8, 2026

This file is the customer-safe source of truth for how machine learning, Modal.com, and GPU-backed workloads actually appear in the current repo.

## Naming Guardrail

- Use `Modal.com`.
- Do not use `Model.com`.
- Do not imply that every ML path is GPU-backed.
- Do not imply that every Modal-backed path is already driving the live public forecast.

## Current Bottom Line

- The live forecast experience is still anchored on the explainable `surrogate_rf_v1` baseline.
- The current active full-grid artifact reports `explainability_mode=heuristic_fallback`; TreeSHAP is an implemented explanation path and hardening gate, not the stronger active-run proof for this artifact.
- Same-day public proof is governed by `publication_proof.json`; if that artifact is missing or failed, this file should not be used to imply a current forecast artifact.
- Modal.com currently powers off-path remote compute for SAR segmentation, SAR training, and MTS-LSTM training.
- The `mts_lstm_v1` path is a real candidate shadow model, but it is still blocked by promotion gates and is not the active public scorer.

## Source Spine

- Repo truth:
  - `backend/models/surrogate_rf.py`
  - `backend/lstm_model.py`
  - `backend/train_model.py`
  - `backend/daily_inference.py`
  - `backend/modal_worker_app.py`
  - `backend/sar_unet_worker.py`
  - `backend/sar_unet_training.py`
  - `backend/common/sar_model_family.py`
  - `backend/scripts/trigger_and_poll_training.py`
  - `backend/scripts/trigger_and_poll_inference.py`
  - `backend/scripts/trigger_and_verify_shadow_regression.py`
- Runbook truth:
  - [Modal Worker Runbook](../../MODAL_WORKER.md)
- Current proof-tier docs:
  - [Scientist_claim_ledger.md](Scientist_claim_ledger.md)
  - [Scientist_evidence_surface_ledger.md](Scientist_evidence_surface_ledger.md)
  - [Demo_decision_brief.md](Demo_decision_brief.md)
  - [Demo_research_appendix.md](Demo_research_appendix.md)
  - [Reserches.md](Reserches.md)
- External grounding:
  - [Modal GPU docs](https://frontend.modal.com/docs/guide/gpu)
  - [Modal Volumes docs](https://frontend.modal.com/docs/guide/volumes)
  - [Modal multi-node training docs](https://frontend.modal.com/docs/guide/multi-node-training)
  - [PyTorch performance tuning guide](https://docs.pytorch.org/tutorials/recipes/recipes/tuning_guide.html)
  - [NHESS 2025 avalanche RF plus SHAP paper](https://nhess.copernicus.org/articles/25/1331/2025/)
  - [NHESS 2024 critical-layer validation paper](https://nhess.copernicus.org/articles/24/2727/2024/nhess-24-2727-2024.html)
  - [NHESS 2020 multiorbital SAR avalanche mapping paper](https://www.nat-hazards-earth-syst-sci.net/20/1783/2020/)

## Table 1. Machine-Learning Method Inventory

| Method | Current truth status | GPU use now | Modal use now | Code components | Current role in app | Benefit to MVP | Blocked phrasing | Safe phrasing |
|---|---|---|---|---|---|---|---|---|
| `surrogate_rf_v1` | `Active in current MVP` | `No` | `No` | `backend/models/surrogate_rf.py` (`RandomForestClassifier`, locked `KMeansSMOTE`, `RFE`, `SVC`, `CalibratedClassifierCV`); `backend/train_model.py`; `backend/daily_inference.py` | Current explainable hazard-probability baseline used for forecast generation and release-evidence reporting. | Gives the live MVP a governed, calibrated, rare-event-aware baseline that is compatible with current SHAP and operator-governance surfaces. | “A Modal GPU model is already driving the live forecast.” | “The live MVP is still anchored on an explainable random-forest baseline.” |
| `tree_shap_surrogate` | `Implemented explanation path; current active artifact uses heuristic fallback` | `No` | `No` | `backend/models/surrogate_rf.py` (`build_tree_shap_explainer`, `compute_tree_shap`); `backend/daily_inference.py`; `src/lib/shapLoader.ts` | Explanation layer for the active tree baseline when computed; the current May 8 active run reports `heuristic_fallback`. | Keeps a clear route to inspectable cell-level explanations while preventing the active artifact from claiming a stronger explanation proof than it has. | “TreeSHAP is proven on the current active full-grid artifact.” | “TreeSHAP is implemented, and the current active full-grid artifact uses heuristic explanation fallback until the stronger explanation refresh completes.” |
| `mts_lstm_v1` | `Repo/admin verified candidate shadow model` | `Training: yes`; `Inference: no` | `Yes` | `backend/lstm_model.py` (multi-timescale LSTM head plus gate summary); `backend/train_model.py`; `backend/daily_inference.py`; `backend/modal_worker_app.py` | Candidate multi-timescale sequence model with explicit PSS, Brier, SAR release, and volume gates. | Creates a credible next-step path beyond the baseline while keeping promotion discipline explicit. | “Production MTS-LSTM is active on the public route.” | “The repo contains an MTS-LSTM candidate that must earn promotion through explicit gates.” |
| `sar_unet` family: `resnet34_unet` | `Repo/admin verified shadow SAR family` | `Yes` | `Yes` | `backend/sar_unet_worker.py`; `backend/sar_unet_training.py`; `backend/common/sar_model_family.py` (`resnet34_unet`); `backend/modal_worker_app.py` | Two-channel VV/VH SAR segmentation path for candidate avalanche-activity detection. | Adds a weather-independent remote-sensing evidence path that can enrich sparse avalanche-activity capture if it clears held-out qualification. | “Operational SAR avalanche detection is already promoted.” | “SAR U-Net support exists as a shadow remote-sensing path and remains artifact-gated.” |
| `sar_unet` family: `swinunet_tiny_diff` | `Repo/admin verified candidate bi-temporal SAR family` | `Yes` | `Yes` | `backend/sar_unet_worker.py`; `backend/sar_unet_training.py`; `backend/common/sar_model_family.py`; `backend/models/swinunet_tiny_diff.py` (`swinunet_tiny_diff`) | Bi-temporal pre/post SAR change-detection candidate reserved for deeper qualification work. | Extends the SAR path toward richer temporal context and more advanced segmentation than the simpler two-channel family. | “The Swin SAR family is already the live detection engine.” | “The bi-temporal Swin U-Net family is implemented as a candidate path, not a live public claim.” |

Bulletin formatting, map masking, export actions, and runout overlays are intentionally excluded from this table because they are downstream consumers of model output, not ML methods themselves.

## Table 2. GPU-Backed Subset

| Method | Modal function or endpoint | Hardware config | Training vs inference | Exact output artifact | Current prediction impact | Customer-safe wording |
|---|---|---|---|---|---|---|
| `sar_unet` segmentation | `POST /sar-segment` -> `sar_segment_remote` | `gpu='T4'`; `device='cuda'`; Modal volume-backed artifacts | `Inference / segmentation` | Governed SAR events, `mask_asset_refs`, `sar_detection_artifacts`, held-out prediction masks under the `sar-masks` namespace | `Indirect today`: enriches SAR evidence and future candidate qualification, but does not prove promoted public SAR scoring. | “Modal GPUs let us run remote SAR segmentation off the user path while keeping SAR claims gated.” |
| `sar_unet` supervised training | `POST /train-sar-unet` -> `train_sar_unet_remote` | `gpu='T4'`; `timeout=14400`; Modal volume-backed checkpoints | `Training` | Shadow checkpoint, validation metrics, threshold-selection artifacts, candidate model version metadata | `Indirect today`: improves the candidate SAR path, not the live public forecast. | “Modal GPUs are already wired for SAR training, but that path is still a candidate workflow.” |
| `mts_lstm_v1` training | `POST /train-mtslstm` -> `train_mts_lstm_remote` | `gpu='T4'`; `timeout=14400`; runtime provider set to `modal` in remote flows | `Training` | `model.joblib`, `training_metrics.json`, `dynamic_model_candidate.json`, `lstm_head_meta` inside the training artifact | `Indirect today`: produces candidate-model evidence only; activation remains blocked until promotion gates pass. | “Modal GPUs are currently used to train the candidate sequence model, not to justify saying that the public scorer has already changed.” |

Important boundary: `infer_mts_lstm_remote` is Modal-backed but not GPU-backed today. In `backend/modal_worker_app.py` it is configured with `cpu=MODAL_INFER_CPU` and `memory=MODAL_INFER_MEMORY_MB`, so the current inference path is remote and reproducible, but not a current GPU claim.

## Table 3. Modal.com Integration Map

| Integration surface | Code components | What Modal is doing | Why it helps operationally | Directly affects live public predictions? | Evidence anchor |
|---|---|---|---|---|---|
| Authenticated worker surface | `backend/modal_worker_app.py`; [Modal Worker Runbook](../../MODAL_WORKER.md) | Hosts one ASGI worker base URL with authenticated endpoints for SAR segmentation, SAR training, MTS-LSTM training, MTS-LSTM inference, and release evaluation. | Keeps heavy ML and remote-sensing logic off the public Vite app and off the thin GitHub control plane. | `No, indirect only` | `worker_api`; endpoint contract sections in `docs/MODAL_WORKER.md` |
| Persistent artifact and model storage | `modal.Volume.from_name('avalanche-artifacts')`; volume reload/commit calls in `backend/modal_worker_app.py` | Persists DEM files, checkpoints, training artifacts, and held-out outputs across worker invocations. | Makes remote ML jobs reproducible and prevents model/DEM assets from being re-downloaded or rebuilt for every call. | `Indirect` | Modal Volumes docs; `seed_artifact_volume`; volume commit/reload calls |
| SAR segmentation dispatch chain | `backend/scripts/trigger_and_verify_shadow_regression.py`; `backend/modal_worker_app.py`; `backend/sar_unet_worker.py` | Submits and polls remote SAR segmentation and held-out evaluation jobs through Modal-backed worker endpoints. | Lets the team run SAR candidate workflows without requiring GPU dependencies in the browser or CI runner itself. | `Indirect today` | `/sar-segment`; `evaluate-release`; runbook SAR sections |
| MTS-LSTM training dispatch chain | `backend/scripts/trigger_and_poll_training.py`; `backend/modal_worker_app.py`; `backend/train_model.py`; `backend/lstm_model.py` | Runs shadow-only sequence-model training with Modal as the runtime provider and returns gate summaries. | Supports heavier sequence-model experimentation while preserving batch-first public delivery. | `No, not the live public scorer` | `/train-mtslstm`; `runtime_provider='modal'`; candidate gate summaries |
| MTS-LSTM inference dispatch chain | `backend/scripts/trigger_and_poll_inference.py`; `backend/modal_worker_app.py`; `backend/daily_inference.py` | Runs remote batch inference against artifacts and returns inference manifests; today this path is CPU/memory-sized on Modal rather than GPU-sized. | Keeps batch inference reproducible and cleanly separated from local operator shells. | `Not on the active public scorer today` | `/infer-mtslstm`; `infer_mts_lstm_remote`; current CPU/memory configuration |
| Secret sync and worker bootstrap | `backend/scripts/bootstrap_release_gate.py`; `docs/MODAL_WORKER.md` | Syncs secrets, deploys the worker, seeds DEM/model volumes, and propagates the live worker URL into the rollout path. | Turns Modal from an ad hoc experiment into a repeatable operator workflow. | `Indirect` | `refs-ready` flow; Modal deploy/seed runbook steps |

## Table 4. Accuracy-Improvement Opportunities

| Opportunity | Why it could improve accuracy | Exact repo insertion point | Recommended Modal/GPU shape | Evidence basis | Proof tier today | Main blocker |
|---|---|---|---|---|---|---|
| Promote `mts_lstm_v1` with longer GPU training and stricter benchmark evidence | A true multi-timescale sequence path can capture temporal structure that a static tree baseline may miss, but only if it consistently beats the current RF baseline on gated metrics. | `backend/lstm_model.py`; `backend/train_model.py`; `backend/modal_worker_app.py`; `backend/scripts/trigger_and_poll_training.py` | Keep Modal as the remote training plane; move from a single `T4` proof shape to `L4` or `A100` only if longer runs or sweep evidence justify it. | Repo shadow-model path; client ANN/HIM-STRAT lineage; Modal GPU docs | `Shadow-gated or config-gated` | Promotion gates, benchmark-pack completion, SAR release gate, and SAR volume thresholds are still unmet. |
| Add a GPU-backed MTS-LSTM batch-inference mode for larger ensembles | GPU-backed batch inference could make larger seeded ensembles or MC-dropout uncertainty runs cheaper and more practical for regional publication artifacts. | `backend/modal_worker_app.py`; `backend/daily_inference.py`; `backend/scripts/trigger_and_poll_inference.py` | Add an explicit GPU-capable inference mode while preserving today’s CPU-sized default until a cost/latency case is proven. | Current CPU-only Modal inference configuration; PyTorch performance guidance for heavier inference workloads | `Repo/admin verified opportunity` | No proof yet that the current batch-inference footprint needs GPU to support the published MVP. |
| Qualify the `swinunet_tiny_diff` SAR family on larger held-out runs | Bi-temporal pre/post stacks can improve avalanche-change separation and reduce dependence on simpler two-channel heuristics. | `backend/sar_unet_worker.py`; `backend/sar_unet_training.py`; `backend/common/sar_model_family.py`; held-out manifest flow in `docs/MODAL_WORKER.md` | Keep Modal GPUs for training and batched inference; consider `L4` or `A100` only if patch size, batch size, or memory pressure outgrows the current `T4` slice. | Repo model family; SAR CNN literature; Modal GPU docs | `Shadow-gated or config-gated` | Held-out labels, checkpoint qualification, and promotion artifacts remain the bottleneck. |
| Expand multiorbital SAR batching and larger-scene mosaics | Multi-orbit context can reduce layover/shadow blind spots and strengthen SAR evidence quality before promotion decisions. | `backend/sar_unet_worker.py`; `backend/scripts/assemble_seed_archive.py`; `backend/sar_release_manifest.py` | Use Modal GPUs with larger-memory cards for larger patch batches or scene mosaics once the data pipeline matures. | Leinss 2020; current manifest-patch batching path | `Research-only opportunity` | More data plumbing, timing ambiguity, and scientist validation are needed before this becomes a product claim. |
| Add GPU-accelerated calibration or sweep experiments off the public path | The client’s 2017 Himalayan paper shows calibration can become a real bottleneck; GPU sweeps could improve candidate-model quality without hurting UX if the repo reopens that track. | `backend/common/abc_optimizer.py`; `backend/train_model.py`; future Modal worker experiment path if adopted | Use Modal GPUs for offline sweep experiments only; consider clustered or multi-GPU shapes only after a real dataset-size justification exists. | Singh et al. 2017; Modal multi-GPU docs | `Research-only opportunity` | The current active baseline is RF rather than k-NN, so this is an experiment path, not an immediate product change. |

## Customer-Safe Answers

- `What ML methods are we using?`
  The live MVP uses the `surrogate_rf_v1` baseline. TreeSHAP is implemented as the explanation path, but the current active full-grid artifact reports heuristic explanation fallback. The repo also contains `mts_lstm_v1` and `sar_unet` candidate paths that are real, inspectable, and Modal-backed, but still gated.

- `How is Modal.com helping here today?`
  Modal.com is the off-path compute and artifact backbone. It hosts authenticated workers, attaches persistent volumes, and runs remote SAR and sequence-model jobs without forcing those dependencies into the public web app.

- `How is Modal.com helping predictions specifically?`
  Today it helps by producing candidate-model evidence, SAR segmentation artifacts, and reproducible batch ML jobs. It does not yet justify saying that the live public forecast is already generated by a promoted Modal/GPU model.
