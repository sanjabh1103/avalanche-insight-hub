# Scientist Validation Protocol v0

Updated: May 8, 2026

This protocol is the minimum scientist-in-the-loop review loop the current MVP can support honestly. It ties the meeting discussion back to current release gates, artifact evidence, and the product’s existing operator/public split.

## Review Principles

- Validation authority stays with scientist and operator review, not with model rhetoric.
- Public language must stay downstream of proving artifacts and review outcomes.
- Any gate failure should downgrade claims immediately rather than being explained away.

## Event-Label Review

| Item | Reviewer | Evidence required | Pass condition | Revert / block condition |
|---|---|---|---|---|
| Label confidence assignment | ML/data + scientist | `label_confidence`, source metadata, governed label snapshot | Confidence assignment is interpretable and consistent with source quality. | Confidence path is opaque, contradictory, or weak without explanation. |
| Training weight assignment | ML/data + scientist | `training_weight`, source weights, corroboration, decay, training-reason penalties | Weighting logic matches intended governance behavior and bounded trust. | Weak or audit-only evidence is silently behaving like core evidence. |
| Field-report linkage | Operator + scientist | Field-report intake, linked event rows, governance labels | Field reports can be traced into the governed evidence path. | Report intake exists but cannot be reconciled to event governance. |

## Critical-Layer Review

| Question | Current status | Required scientist action | Blocking rule |
|---|---|---|---|
| Are current snowpack proxies sufficient to support stronger claims? | No. Proxy wording is explicit, but critical-layer closure is not proven. | Define the minimum critical-layer benchmark slices and failure cases. | No claim may imply critical-layer validation until this review exists. |
| Are weak-layer blind spots acceptable for current messaging? | Only as an explicit limitation. | Review whether current caveats are strong enough for the meeting. | If the caveat language is too soft, downgrade the relevant statements immediately. |
| What scientist review cadence is needed for future promotion decisions? | Not yet defined. | Establish a review cadence and sign-off expectation. | Candidate promotion remains blocked without this cadence. |

## Weak-Layer And Runout Validation Checklist

This checklist is intentionally a validation workstream, not a public-scoring claim.

| Review item | Current evidence | Required scientist / field action | Acceptance condition | Claim boundary |
|---|---|---|---|---|
| Weak-layer taxonomy | Snowpack proxies and current caveat language | Define accepted weak-layer classes, required field labels, and failure examples. | Reviewers can map field observations to the taxonomy without ambiguity. | No statement may imply weak-layer validation until reviewed cases exist. |
| Snowpack proxy adequacy | `snowpack_proxy_v1` and source-health summaries | Compare proxy outputs with scientist-selected known weak-layer cases. | Proxy limitations and useful ranges are documented. | Proxy evidence remains decision-support context, not a confirmed weak-layer diagnosis. |
| Alpha-Beta / Whitebox runout smoke | `runout_physics_smoke.yml` or local smoke JSON | Review runout paths against known events, terrain traps, roads, and assets. | Smoke artifact passes and at least one reviewed case is accepted as plausible. | Runout remains exploratory until case review passes. |
| False-positive / false-negative review | Forecast cells, runout overlays, and event labels | Select examples where the MVP over-warns or under-warns. | Failure cases are linked to model, data, or terrain causes. | Failure cases must be carried into deck limitations and release gates. |
| Masked-terrain behavior | Public mask and unavailable-cell semantics | Confirm whether masked cells are visually and textually distinct enough. | A scientist can identify why a cell is withheld. | Masked cells must not be colored or exported as normal low risk. |

## Benchmark Acceptance

| Artifact or proof | Reviewer | Acceptance requirement |
|---|---|---|
| Public route smoke | Product + scientist | Public surface must show reduced-confidence and masked-terrain semantics without authority drift. |
| Admin route smoke | Operator + scientist | Admin must reflect freshest publication/model rows and expose provenance, stability, and benchmark state clearly. |
| Runtime benchmark report | Backend + scientist | Runtime traces must be reproducible and clearly labeled as operational observability, not field validation. |
| Stability summary | ML/data + scientist | Stability classification, seed count, and threshold drift must be visible and interpreted conservatively. |
| Evaluation contract tests | Backend + scientist | Labeling / slice contracts must pass before evaluation wording is reused. |

## Candidate Model Promotion Review

Promotion review should follow the existing repo gates rather than a new ad hoc process.

| Gate | Current source of truth | Current expected rule | Review implication |
|---|---|---|---|
| `pss_gate_passed` | `dynamic_model_candidate.gates` | Candidate must clear baseline quality threshold. | Necessary but not sufficient. |
| `shadow_quality_gate_passed` | `dynamic_model_candidate.gates` | Candidate must beat or match the relevant baseline quality rule. | If false, candidate remains blocked. |
| `sar_release_gate_passed` | `dynamic_model_candidate.gates` | SAR release artifact must exist and pass. | If false, no SAR-strengthened claim is allowed. |
| `sar_volume_gate_passed` | `dynamic_model_candidate.gates` | Promoted SAR event/region/scene thresholds must be met. | If false, evidence volume remains too thin for promotion. |
| `ready_for_activation` | `dynamic_model_candidate.ready_for_activation` | Only true when all required upstream gates are satisfied. | If false, the candidate remains a candidate. |

## Blocked-Claim Escalation Path

1. Detect the drift.
   Trigger: a doc, UI string, or meeting script implies more than the proving artifact allows.
2. Map it to the ledger.
   Use `docs/MVP/source/Scientist_claim_ledger.md` and `docs/MVP/source/Scientist_evidence_surface_ledger.md`.
3. Check the gate.
   Confirm whether the necessary route, artifact, or test actually exists and is current.
4. Downgrade immediately if the gate is missing.
   Replace with the safe phrasing from the claim ledger.
5. Escalate only if a real new artifact exists.
   If new proof exists, attach it explicitly and re-review the wording.

## Scientist Sign-Off Checkpoints

| Checkpoint | Required artifact | Outcome |
|---|---|---|
| Checkpoint 1: Claim-state review | Completed claim ledger | Meeting script is bounded to safe phrasing. |
| Checkpoint 2: Evidence-surface review | Evidence surface ledger + hosted route smoke | Scientist can see where proof lives and where it does not. |
| Checkpoint 3: Governance review | Autonomy evidence fusion note | Autonomy language is limited to governed evidence fusion. |
| Checkpoint 4: Benchmark-pack review | `Scientist_benchmark_pack_v0.md` | Benchmark discussion starts from current artifact truth. |
| Checkpoint 5: Promotion review | Current candidate gates + admin view | Candidate-path statements remain blocked unless gates are satisfied. |

## Gate Failure Rule

If any of the following fail after the meeting or during sprint verification, the related claim must revert:

- hosted route smoke fails;
- admin freshness is wrong;
- benchmark harness cannot reproduce the cited summary;
- backend / frontend / Deno contract tests fail;
- candidate gate or SAR gate language drifts beyond current artifacts.

The default action is downgrade, not explanation.
