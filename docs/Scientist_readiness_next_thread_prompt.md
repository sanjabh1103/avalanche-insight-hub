# Scientist Readiness Next-Thread Implementation Prompt

Updated: May 5, 2026

Use the prompt below as the starting brief for the next development thread. It is intentionally aggressive for a 4-day sprint, but it is bounded by current repo truth, live proof, and existing release gates.

```md
/Users/sanjayb/avalanche-insight-hub

You are working in the Avalanche Insight Hub repo. This is an implementation thread, not a brainstorming thread.

Follow the repo `AGENTS.md` workflow strictly:
- choose the single best `@agent` or `@skill`
- research first
- plan quickly from repo truth
- then implement
- verify before claiming success

## Mission

Strengthen the MVP before the scientist discussion in the next 4 days.

This is not an autonomy-first pitch. Treat the product as:
- a governed decision-support MVP
- an honesty-first sparse-data operational shell
- a scientist-in-the-loop co-development platform

The objective is to improve scientist-readiness by raising the credibility of what we can already prove, packaging the evidence better, and tightening the validation story without pretending we have completed the long-horizon science.

## Current Rating Targets

Treat these as the explicit sprint targets:

| Workstream | Current | Target for this sprint | Notes |
|---|---:|---:|---|
| Claim-state hardening | 2 | 4 | Must complete |
| Evidence-surface verification | 2 | 4 | Must complete |
| Governed autonomy reframing | 2 | 4 | Must complete |
| Scientist benchmark pack | 1 | 3 | `v0` only before meeting |
| Validation protocol | 1 | 3 | `v0` only before meeting |
| Shadow-path qualification | 1 | 1-2 | Do not force promotion; only improve evidence visibility if real artifacts exist |

Do not chase impossible 4-day outcomes:
- promoted `MTS-LSTM` activation
- `authoritative SAR`
- official-warning-service equivalence
- full critical-layer science closure
- fake benchmark uplift

## Non-Negotiable Truth Rules

Preserve the current proof-tier taxonomy exactly:
- `Live demo`
- `Repo/admin verified`
- `Shadow-gated or config-gated`

Preserve the current claim-state taxonomy exactly:
- `Exploratory`
- `Candidate`
- `Conditionally available`
- `Active`
- `Unavailable`

Hard guardrails:
- do not upgrade `Groundsource-style` beyond flood-domain inspiration
- do not upgrade `EAWS-style experimental` into official EAWS equivalence
- do not call `MTS-LSTM`, SAR, or autonomy `Active` without the proving artifact required by `docs/OPERATOR_ROLLOUT_QA.md`
- do not use “real-time”, “authoritative”, “operational warning service”, “fully autonomous avalanche AI”, or “production MTS-LSTM” unless the artifact gate is satisfied
- do not add new public routes
- do not do schema redesign unless absolutely required by an existing blocked UI or test
- do not invent benchmark math or validation claims that are not grounded in current artifacts/tests

## Repo Truth You Must Reuse

Use these existing artifacts and components as the foundation instead of inventing a new framework:

### Core docs
- `docs/Scientist_discussion_framework.md`
- `docs/Demo_decision_brief.md`
- `docs/Demo_research_appendix.md`
- `docs/Cust_comm.md`
- `docs/OPERATOR_ROLLOUT_QA.md`
- `docs/delivery/AVA-ARCH-001/ADVERSARIAL_VERIFICATION_REPORT_2026-05-03.md`
- `docs/delivery/AVA-ARCH-001/CHALLENGE_PROGRESS_MATRIX.md`

### Live proof routes
- `https://avalanche-insight-hub.netlify.app/`
- `https://avalanche-insight-hub.netlify.app/admin`

### Existing evidence objects
- `forecast_grids`
- `forecast_runs.model_metadata.source_health`
- `forecast_runs.model_metadata.decision_provenance`
- `model_status.dynamic_model_candidate`
- `model_status.latest_benchmark_summary`
- `model_status.stability_summary`
- `model_status.autonomous_evidence_summary`
- `backend/artifacts/20260504T070406Z/inference_manifest.json`

### Likely code surfaces
- `src/components/ModelStatusBadge.tsx`
- `src/components/AdminDashboard.tsx`
- `src/components/ForecastBulletinBadge.tsx`
- `src/components/FieldReportForm.tsx`
- `src/pages/Index.tsx`
- `backend/common/audit_metadata.py`
- `backend/scripts/run_pipeline_benchmarks.py`

## Required Deliverables

Create or update the following artifacts. Use these names unless you discover a strong repo-local naming conflict:

1. `docs/Scientist_claim_ledger.md`
- A claim-by-claim scientist-demo ledger.
- Columns:
  - `Statement`
  - `Claim state`
  - `Proof tier`
  - `Proving artifact or route`
  - `Blocked phrasing`
  - `Safe phrasing`
  - `Owner`
  - `Status`

2. `docs/Scientist_evidence_surface_ledger.md`
- A route-and-artifact proof ledger.
- Cover:
  - forecast workspace
  - bulletin semantics
  - masking
  - uncertainty cues
  - share/export/report
  - field-report flow
  - model status
  - admin observability
- Columns:
  - `Capability`
  - `Current proof`
  - `Route or artifact`
  - `Observed limitation`
  - `Scientist-safe wording`
  - `Gap severity (1-5)`

3. `docs/Governed_autonomy_evidence_fusion_note.md`
- A short internal note that reframes “autonomy” into governed evidence fusion.
- It must explain:
  - `label_confidence`
  - `training_weight`
  - source weighting
  - dedupe limits
  - where autonomy helps
  - where autonomy stops and scientist/human review is required
- Include a required failure taxonomy table:
  - missing-event risk
  - false-positive extraction
  - corroboration mismatch
  - weak-layer blindness
  - stale source dominance
  - regional transfer failure

4. `docs/Scientist_benchmark_pack_v0.md`
- A scientist-facing benchmark pack built from existing repo evidence.
- Required sections:
  - benchmark purpose
  - what this benchmark can and cannot prove
  - case inventory
  - region slices
  - failure slices
  - critical-layer questions
  - acceptance criteria
  - known blind spots
- Use existing tests, artifacts, and current docs. Do not imply fresh field validation.

5. `docs/Scientist_validation_protocol_v0.md`
- A scientist-in-the-loop review protocol.
- Required sections:
  - event-label review
  - critical-layer review
  - benchmark acceptance
  - candidate model promotion review
  - blocked-claim escalation path
  - scientist sign-off checkpoints

6. Update these existing docs for consistency if needed:
- `docs/Scientist_discussion_framework.md`
- `docs/Demo_decision_brief.md`
- `docs/Cust_comm.md`
- `docs/Demo_research_appendix.md` only if you need to anchor new internal evidence references

## Required Workstreams

### Workstream 1: Claim-State Hardening

Build the claim ledger by mapping every scientist-demo statement to:
- claim state
- proof tier
- proving artifact or route
- blocked phrasing
- safe phrasing

Minimum source set:
- `docs/Scientist_discussion_framework.md`
- `docs/Demo_decision_brief.md`
- `docs/Cust_comm.md`
- `docs/OPERATOR_ROLLOUT_QA.md`

Also reconcile against the release communication gate in `docs/OPERATOR_ROLLOUT_QA.md`, especially:
- `production MTS-LSTM`
- `authoritative SAR`
- `operational whitebox runout`
- `zero-history learning`
- `fully autonomous avalanche AI`

### Workstream 2: Evidence-Surface Verification

Verify the current proof on `/` and `/admin`.

Produce the evidence ledger using:
- live route smoke
- repo code
- current stored artifacts
- existing test coverage

Do not settle for doc claims if code or live proof is stronger or weaker.

Required evidence anchors:
- `forecast_grids`
- `source_health`
- `decision_provenance`
- `dynamic_model_candidate`
- `latest_benchmark_summary`
- `stability_summary`
- `autonomous_evidence_summary`
- `backend/artifacts/20260504T070406Z/inference_manifest.json`

If an existing public/admin component can surface this proof more clearly in 4 days, make the change.

### Workstream 3: Governed Autonomy Reframing

Replace vague autonomy language with a scientist-safe evidence-fusion framing.

This must:
- explain why autonomy is currently a governed candidate, not a finished outcome
- connect ingest and weighting logic to known sparse-data challenges
- separate evidence enrichment from truth generation
- spell out the exact boundaries where scientist review is still needed

Required concrete anchor points:
- `label_confidence`
- `training_weight`
- dedupe logic
- event governance
- promotion gates
- weak-layer and local-heterogeneity blind spots

### Workstream 4: Scientist Benchmark Pack v0

Build a pre-meeting benchmark pack from current repo truth.

This is not a research paper. It is a scientist discussion starter.

It must reuse existing evidence such as:
- adversarial verification report
- challenge progress matrix
- current backend tests
- model-status summaries
- inference manifest
- benchmark harness outputs

It must explicitly include:
- what is validated by tests and artifacts
- what is only bounded honesty or operator observability
- where critical-layer and snowpack questions remain open

### Workstream 5: Scientist Validation Protocol v0

Draft the review protocol that the scientist team could adopt immediately after the MVP discussion.

It must show:
- what gets reviewed
- who reviews it
- what evidence is required for promotion
- what remains blocked without scientist sign-off
- what claims must revert if a gate later fails

This should tie directly to existing release communication gates and promotion logic.

## Selective Implementation Allowance

Limited code changes are allowed only where they materially improve scientist trust in the next 4 days.

Allowed:
- strengthen `/admin` evidence visibility
- surface benchmark, stability, provenance, and evidence summaries more clearly in existing components
- harden scientist-safe copy in existing public/admin surfaces
- add or tighten tests around those surfaces
- improve artifact naming or summary rendering if it helps proof inspection

Forbidden:
- new public routes
- large schema redesigns
- model-promotion theater
- fake benchmark math
- deep SAR or MTS-LSTM activation work unless artifacts genuinely clear the gates
- new marketing claims that outrun the release communication gate

## Four-Day Execution Order

### Day 1
- Freeze truth and build the claim ledger.
- Audit current copy against release communication gates.
- Inventory exact proving artifacts and blocked claims.
- Re-verify `/` and `/admin`.

### Day 2
- Strengthen existing public/admin evidence surfacing.
- Tighten wording in scientist-facing and operator-facing surfaces.
- Make the model-status/admin plane visibly support the claims already in the docs.

### Day 3
- Build `Scientist_benchmark_pack_v0.md`.
- Build `Scientist_validation_protocol_v0.md`.
- Write `Governed_autonomy_evidence_fusion_note.md`.

### Day 4
- Run verification.
- Produce a final scientist-meeting checklist with:
  - what can be said
  - what needs caveats
  - what must not be said
- Rehearse the final proof chain against `/` and `/admin`.

## External Grounding You Must Respect

Use these as framing constraints, not as borrowed validation:

### EAWS
- EAWS standards and the EAWS Matrix were updated in June 2025.
- They reinforce structured avalanche bulletin logic around:
  - snowpack stability
  - frequency
  - avalanche size
- Use them to justify disciplined bulletin structure, not AI novelty.
- References:
  - `https://www.avalanches.org/standards/`
  - `https://www.avalanches.org/standards/eaws-matrix/`
  - `https://www.avalanches.org/standards/workflow-to-determine-the-avalanche-danger-level/`

### WMO
- WMO impact-based guidance requires consequence-oriented communication, partner-agency coordination, and clear “who / what / when / where / why” messaging.
- Use this to reinforce consequence-aware framing and scientist partnership.
- Do not imply WMO-grade authority status.
- References:
  - `https://wmo.int/impact-based-forecast-and-warning-services`
  - `https://etrp.wmo.int/pluginfile.php/16270/mod_resource/content/0/wmo_1150_en.pdf`

### Recent avalanche ML literature
- Recent work still supports “transparent second opinion” more than expert replacement.
- Persistent weak layers remain a known weakness.
- Use this to keep autonomy and novelty claims disciplined.
- Reference:
  - `https://nhess.copernicus.org/articles/25/1331/2025/`

## Verification Requirements

Do not report success until these checks are run.

### Route proof
- smoke `/` and `/admin` with browser tooling

### Frontend
- `npm run build`
- targeted tests for:
  - bulletin
  - admin
  - model-status
  - field-report surfaces

### Backend
- targeted pytest for:
  - audit metadata
  - label governance
  - model status
  - benchmark summaries
  - publish guards
  - daily inference

### Deno
- `label-forecast-outcomes`
- `run-evaluation`
- shared evaluation metadata tests

### Documentation consistency
- no phrase upgraded past its proving artifact
- no `Groundsource-style` drift
- no `EAWS-style experimental` drift
- no blocked claim labeled `Active`

## Final Output Required From This Thread

When done, report in this order:

1. `What was implemented`
- list new docs created
- list existing docs updated
- list code surfaces changed

2. `What ratings improved`
- show `current -> new`
- tie each improvement to an artifact or verification outcome

3. `What remains blocked`
- especially critical-layer closure, promoted MTS-LSTM, authoritative SAR, and authority-grade warning posture

4. `Verification run`
- list exact checks executed
- list anything not run

5. `Scientist-meeting safe line`
- 5-10 bullets for what the user can now safely say in the meeting

Make reasonable assumptions and execute. Do not stop at planning.
```
