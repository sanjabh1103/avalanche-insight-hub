# Scientist Discussion Gate Framework

Updated: May 7, 2026

This is an internal-prep gate review, not a customer-facing sales note. Its purpose is to answer three questions in one place:

1. Is the last three weeks of work worth taking to the scientist now?
2. If not, what exactly must be fixed before that discussion?
3. What future proposition would be compelling enough to convert the MVP meeting into immediate co-development interest?

Front-page recommendation:

- `No-go` if the MVP is framed as advanced autonomous avalanche science.
- `Conditional go` only if the discussion is framed as:
  - governed decision-support MVP,
  - honest sparse-data product shell,
  - scientist-in-the-loop co-development opportunity.

Taxonomies used in this framework:

- Proof tiers:
  - `Live demo`
  - `Repo/admin verified`
  - `Shadow-gated or config-gated`
  - `Research-only precedent`
- Claim states:
  - `Exploratory`
  - `Candidate`
  - `Conditionally available`
  - `Active`
  - `Unavailable`

Readiness rating used below:

- `1` = weak or not defensible in scientist discussion
- `3` = partially defensible with clear caveats
- `5` = strongly defensible today

Evidence spine reused here:

- `docs/MVP/source/Demo_decision_brief.md`
- `docs/MVP/source/Demo_research_appendix.md`
- `docs/MVP/source/Cust_comm.md`
- `docs/OPERATOR_ROLLOUT_QA.md`

Canonical live proof routes for this framework:

- `https://avalanche-insight-hub.netlify.app/`
- `https://avalanche-insight-hub.netlify.app/admin`

Companion artifacts prepared for this sprint:

- `docs/MVP/source/Scientist_claim_ledger.md`
- `docs/MVP/source/Scientist_evidence_surface_ledger.md`
- `docs/MVP/source/Governed_autonomy_evidence_fusion_note.md`
- `docs/MVP/source/Scientist_benchmark_pack_v0.md`
- `docs/MVP/source/Scientist_validation_protocol_v0.md`
- `docs/MVP/source/Scientist_meeting_checklist.md`

Use these as the bounded source of truth for meeting phrasing, proof anchors, and blocked-claim handling.

Main-deck roadmap rule:

- Use the 3-phase model in Section 5 as the primary `D2-14` visual.
- Treat the 5-phase productization table in `Demo_decision_brief.md` as appendix-only expansion for slide work.

## 1. Executive Gate Verdict

| Question | Verdict | Why | Evidence anchors | Risk if ignored |
|---|---|---|---|---|
| Is the last three weeks of work worth taking to the scientist now? | `Conditional go` | Yes, if the meeting is positioned around governed decision support, proof-tier honesty, and co-development opportunity rather than finished autonomy. | `docs/MVP/source/Demo_decision_brief.md` decision synthesis; `docs/MVP/source/Cust_comm.md` expectations 3, 10, 13, 14, 15; live route `/` | Scientist trust will drop quickly if the discussion sounds like autonomy-first marketing. |
| Can we pitch this as advanced autonomous avalanche science already delivered? | `No-go` | No. The current repo does not support `Active` claims for public MTS-LSTM scoring, promoted SAR, authority-grade warning status, or fully autonomous truth generation. | `docs/MVP/source/Demo_research_appendix.md` repo-vs-claim audit; `docs/OPERATOR_ROLLOUT_QA.md` release communication gate; hosted `/admin` proof | A senior scientist will correctly read this as overclaiming and may disengage from the rest of the proposal. |
| Is there a scientifically respectable discussion worth having now? | `Yes` | The strongest current value is a disciplined operational shell: batch-first forecast delivery, masking honesty, uncertainty communication, explainability, and governance posture. | `docs/MVP/source/Demo_decision_brief.md` present MVP gap analysis and top-5 methodology comparison; route `/`; `src/pages/Index.tsx` behavior contract | If this is hidden behind weak AI language, the actual operational strengths may be missed. |
| Can this discussion plausibly lead to immediate co-development interest? | `Yes, with the right framing` | Experienced scientists are more likely to engage around benchmark ownership, validation authority, and critical-layer review loops than around UI novelty alone. | `docs/MVP/source/Demo_decision_brief.md` future path and publication snapshot; `docs/MVP/source/Demo_research_appendix.md` publication pros/cons | Without a concrete scientist role, the meeting can degrade into a one-way demo instead of a partnership discussion. |

| Discussion lane | Status | Why |
|---|---|---|
| `Present now` | `Allowed` | These items are either `Active` on the live public route or `Conditionally available` with strong repo/admin proof and safe wording. |
| `Present only with caveat` | `Allowed with strict wording` | These items are useful for the conversation, but only as governed direction, gated capability, or co-development hooks. |
| `Do not present yet` | `Blocked` | These items lack the proof artifacts required by `docs/OPERATOR_ROLLOUT_QA.md` or remain `Shadow-gated or config-gated` / `Research-only precedent`. |

## 2. Compelling Propositions Worth Taking To The Scientist Now

Only propositions that survive the gate are listed here.

| Rank | Proposition | Claim state | Proof tier | What is actually unique | Why a 40-year scientist should care | What proves it | Safe presentation language | Priority (1-5) |
|---|---|---|---|---|---|---|---|---:|
| 1 | Batch-first interactive forecast workspace | `Active` | `Live demo` | The distinct part is not ML novelty; it is an operationally usable, stateful forecast workspace built around published artifacts and shareable context. | It shows the team can already turn science output into a usable operational surface instead of just another model notebook. | Route `/`; current published horizon badge; `forecast_grids` runtime path; `docs/MVP/source/Demo_decision_brief.md` present gap rank 1 | “We already have a usable decision-support shell for published forecast artifacts.” | 5 |
| 2 | APT-gated masked terrain semantics | `Active` | `Live demo` | The unique piece is honesty-first hazard communication: out-of-scope terrain is masked rather than flattened into low danger. | It respects scientific uncertainty and terrain relevance instead of faking universal precision. | Route `/`; `src/pages/Index.tsx`; `docs/MVP/source/Demo_research_appendix.md` uniqueness table | “We designed the public semantics to avoid false confidence outside avalanche-prone terrain.” | 5 |
| 3 | Uncertainty-forward bulletin framing | `Active` | `Live demo` | The distinctive value is explicit uncertainty in a public-facing bulletin UX, not a hidden admin metric. | Senior scientists know trust is lost when uncertainty is buried or cosmetically softened. | Route `/`; `EAWS-style experimental` bulletin layer; `docs/MVP/source/Cust_comm.md` expectations 6 and 10 | “The bulletin layer is intentionally explicit about reduced confidence and evidence limits.” | 5 |
| 4 | SHAP-backed inspection and provenance | `Active` | `Live demo` | SHAP is not unique by itself; the differentiator is productized local inspection at the point of use. | It shows the team values traceability and reasoning, which is essential for scientist review and co-development. | Route `/`; cell inspection and provenance surfaces; `docs/MVP/source/Demo_decision_brief.md` advanced technology rows | “We can inspect forecast rationale cell by cell instead of presenting a black-box score.” | 4 |
| 5 | Consequence-aware overlays and runout context | `Conditionally available` | `Repo/admin verified` | The unique aspect is connecting hazard output to roads, assets, and runout consequence review in the same working surface. | Scientists with long operational experience tend to care about consequence workflows, not just abstract hazard maps. | Route `/` expert mode; runout and overlay UI; `docs/MVP/source/Cust_comm.md` expectation 11 | “We can move from hazard display toward consequence-aware review, though data quality still varies by region.” | 4 |
| 6 | Release-gated model-governance posture | `Conditionally available` | `Repo/admin verified` | The distinct part is governance discipline: candidate models are not marketed as active until release artifacts say so. | It signals seriousness about validation and promotion thresholds rather than novelty theater. | `docs/OPERATOR_ROLLOUT_QA.md`; `/admin` gate; `model_status.dynamic_model_candidate`; `run_evaluation`; `label_forecast_outcomes` | “Candidate models must earn activation through explicit gates; they are not treated as production by default.” | 5 |
| 7 | Governed field-report plus news-ingest direction | `Candidate` | `Repo/admin verified` | News ingestion is not unique by itself; the interesting part is governed multi-source evidence weighting under sparse-data conditions. | It addresses one of the hardest Himalayan problems: missing event records, but in a way that still respects evidence quality. | `backend/news_ingest.py`; `ingest-event`; field-report flow on `/`; `label_confidence` and `training_weight` references in current docs | “We are building a governed evidence-fusion path to improve occurrence capture, not claiming solved avalanche truth generation.” | 4 |
| 8 | Open, inspectable co-development stack | `Conditionally available` | `Repo/admin verified` | The unique value is not the tools themselves, but that the whole product is auditable and can support shared scientific ownership. | Experienced scientists are more likely to engage when they can inspect assumptions, artifacts, and limits directly and hold benchmark or release-gate authority. | Open repo structure; `docs/MVP/source/Demo_decision_brief.md` publication snapshot; `docs/MVP/source/Top20_features.md` open stack row | “This is a stack that your scientist team can inspect, challenge, and help evolve rather than a sealed vendor black box.” | 4 |

## 3. Why This Is Not Ready Yet

This section is ordered by meeting risk, not engineering convenience.

| Rank | Gap | Why it blocks a scientist discussion | Current rating | Target rating | Delta | Missing artifact or proof | Implementation details | Requirements | Timeline |
|---|---|---|---:|---:|---:|---|---|---|---|
| 1 | No validated critical-layer or snowpack review loop | Senior scientists will immediately ask how weak layers and snowpack structure are being validated against real conditions. | 1 | 4 | +3 | Critical-layer validation pack with benchmark cases, acceptance thresholds, and recurring `run_evaluation` slices reviewed by scientists | Build a scientist-facing validation pack that ties forecast outputs to critical-layer and snowpack review cases instead of proxy-only claims. | Benchmark dataset, review protocol, scientist sign-off cadence | `2-6 weeks` |
| 2 | No promoted next-gen scorer | The repo cannot truthfully claim advanced model activation; the current dynamic path is still blocked. | 1 | 4 | +3 | `model_status.dynamic_model_candidate.ready_for_activation=true` plus active model version change and benchmark evidence | Keep the MTS-LSTM path framed as candidate until promotion gates are passed and visible in model-status artifacts. | Promotion criteria, benchmark runs, admin evidence surfaces | `6-12 weeks` |
| 3 | SAR is not promoted or validated | Remote sensing will attract scrutiny from experienced scientists; coverage signaling is not the same as validated SAR qualification. | 1 | 3 | +2 | Successful `authoritative_release_gate.json` or equivalent held-out validation proof; quality summary tied to regional use case | Move SAR from “coverage and schema” to “validated candidate” through held-out evaluation and explicit promotion artifacts. | Labeled reference set, validation run, artifact publication | `6-12 weeks` |
| 4 | Sparse-data autonomy is still only partial | The customer’s autonomy ask is central, and the current MVP only partially addresses it. | 2 | 4 | +2 | Governed evidence benchmark showing uplift from field reports plus news ingest, with error analysis and acceptance rules | Tighten the story from “autonomous” to “governed candidate autonomy” and back it with measured evidence-capture improvement. | Event-quality rubric, before/after ingest comparison, failure taxonomy | `2-6 weeks` |
| 5 | No authority-grade warning-service standing | Scientists will distinguish a useful MVP from an official warning-service workflow immediately. | 1 | 3 | +2 | Controlled pilot dissemination rules, responsibility boundaries, and consequence-review workflow artifacts | Keep the product framed as decision support until alert packaging, accountability, and operational review flows are defined. | Pilot operating model, dissemination boundary, role definition | `6-12 weeks` |
| 6 | Local heterogeneity is still unresolved | Micro-climate and local slope variability remain obvious scientific weaknesses if asked directly. | 1 | 3 | +2 | Regional benchmark pack showing where grid outputs hold and where local review is still required | Produce a scientist-safe limitation map rather than pretending local heterogeneity is solved. | Region-specific test cases, limitation notes, benchmark slices | `2-6 weeks` |
| 7 | Future-path science is not yet converted into shared benchmark evidence | Without a benchmark pack, the future proposition stays conceptual instead of collaborative. | 2 | 4 | +2 | Shared benchmark pack, scientist review protocol, and pilot acceptance criteria | Turn the roadmap into an evidence program that gives the scientist team ownership over evaluation and promotion. | Benchmark governance, acceptance rubric, co-review cadence | `0-2 weeks` to define, `2-6 weeks` to populate |

## 4. Gap Closure Plan For Pre-Scientist Readiness

| Workstream | Exact fix | Expected rating lift | Proof artifact required | Owner type | Duration | Dependency |
|---|---|---|---|---|---|---|
| Claim-state hardening | Align every demo phrase and note to `Exploratory` / `Candidate` / `Conditionally available` / `Active` / `Unavailable` before any scientist meeting. | `2 -> 4 (+2)` | Updated internal speaking notes and gate checklist mapped to `docs/OPERATOR_ROLLOUT_QA.md` | Product/PM plus technical lead | `0-2 weeks` | None |
| Evidence-surface verification | Verify what the operator lane truly proves today and document the exact proving artifacts for every allowed claim. | `2 -> 4 (+2)` | Route-level proof list, model-status evidence list, benchmark artifact checklist | Full-stack engineer plus QA/ops | `0-2 weeks` | Claim-state hardening |
| Governed autonomy reframing | Tighten the autonomy story to “governed candidate evidence fusion” and add explicit error modes and caveats. | `2 -> 4 (+2)` | Evidence-fusion note with `label_confidence`, `training_weight`, and failure taxonomy | ML/data engineer plus product lead | `2-6 weeks` | Evidence-surface verification |
| Scientist benchmark pack | Produce a first benchmark pack for review: regional cases, failure slices, critical-layer questions, and acceptance criteria. | `1 -> 4 (+3)` | `benchmark_pack_v1` with case list, slice metrics, and review rubric | ML/data engineer plus avalanche-science advisor | `2-6 weeks` | Governed autonomy reframing |
| Validation protocol | Define the scientist-in-the-loop review loop for critical layers, event labels, and model promotion. | `1 -> 4 (+3)` | `scientist_validation_protocol_v1` or equivalent signed internal protocol | Avalanche-science advisor plus technical lead | `2-6 weeks` | Scientist benchmark pack |
| Shadow-path qualification | Keep MTS-LSTM and SAR as candidate paths until release gates and benchmark deltas justify promotion. | `1 -> 3 (+2)` | `authoritative_release_gate.json`, benchmark summaries, `dynamic_model_candidate.ready_for_activation=true` when earned | ML engineer plus MLOps | `6-12 weeks` | Validation protocol |

## 5. Future Proposition Compelling Enough For Immediate Co-Development

This section is written for the “what happens after MVP?” part of the discussion. The scientist-facing attraction should be benchmark ownership, validation authority, and publishable pilot design, not algorithm theater.

| Phase | Ideal state | Features unlocked | Scientist role | Technical work | Current rating | Target rating | Delta | Timeline | Approx budget | Why it becomes compelling |
|---|---|---|---|---|---:|---:|---:|---|---|---|
| Phase 1: MVP hardening | A disciplined, honest decision-support MVP with locked claim states and reproducible evidence surfaces | Trusted demo posture, clearer governance, stronger operator provenance, benchmark-ready packaging | Review scope, challenge claims, define first validation questions | Harden claim states, verify `/` and `/admin`, formalize proof artifacts, package benchmark intake | 2 | 4 | +2 | `0-3 months` | INR `25-40 lakh` | It shows respect for scientific rigor before asking for deeper collaboration. |
| Phase 2: Scientist-in-the-loop pilot | A governed pilot where scientists own or co-own benchmark cases, acceptance thresholds, and review loops | Critical-layer review cadence, event-quality governance, candidate autonomy evaluation, first regional benchmark pack | Own benchmark design, validate cases, set promotion criteria, co-review failures | Build benchmark pack, validation protocol, shared review workflow, stronger event-review tooling, expanded `run_evaluation` cadence | 2 | 5 | +3 | `3-9 months` | INR `40-90 lakh` | This turns the scientists from demo audience into validation authorities and co-designers. |
| Phase 3: Productization and validation expansion | A defensible co-developed product path with qualified remote sensing, stronger model promotion discipline, and publishable pilot evidence | Qualified SAR candidate, stronger shadow-model promotion path, multi-region benchmark expansion, publishable pilot package | Co-author methods, approve qualification gates, shape regional expansion priorities | Remote-sensing qualification, shadow-model benchmarking, multi-region benchmark expansion, publication-ready documentation | 1 | 4 | +3 | `9-18 months` | INR `1.2-3.0 crore` | It offers the scientists a meaningful long-term research-and-product program rather than a one-off advisory role. |

## 6. Step-By-Step Discussion Flow

Use this exact sequence in the meeting prep.

| Step | Objective | What to show | What to say | What not to say | Exit criterion |
|---|---|---|---|---|---|
| 1 | Establish the real problem and why sparse-data avalanche forecasting remains hard | One short challenge summary from `docs/MVP/source/Demo_decision_brief.md` plus the top challenge rows from `docs/MVP/source/Top_challanges.md` | “We are not assuming avalanche forecasting is a solved ML problem; we are starting from the real sparse-data and validation bottlenecks.” | Do not open with product UI or “AI breakthrough” language. | The scientist agrees the problem framing is serious and grounded. |
| 2 | Show what the MVP truthfully proves now | Route `/`, current published horizon badge, bulletin framing, masking, uncertainty cues, share/export/report, expert overlays | “Here is what the current product genuinely proves as a decision-support shell.” | Do not imply production autonomy, authority-grade warning status, or promoted SAR. | The scientist can see current proof without overclaim. |
| 3 | Show what is promising but still gated | Candidate-model language, admin/model governance posture, governed ingest direction, research appendix caveats | “These are credible candidate directions, but they are not active claims yet.” | Do not say active public MTS-LSTM, authoritative SAR, fully autonomous avalanche AI, or zero-history learning. | The boundary between current and future is understood. |
| 4 | Show why scientist involvement is necessary, not decorative | Gaps table and validation needs: critical layers, benchmark ownership, local heterogeneity, SAR qualification | “The next step is not more pitch polish; it is scientist-owned validation and benchmark design.” | Do not present the scientist team as passive validators of a finished solution. | The scientist role becomes concrete and respected. |
| 5 | Propose the immediate co-development path | Three-phase future proposition table | “If this is interesting, the next phase is a scientist-in-the-loop pilot with explicit benchmark ownership and release criteria.” | Do not jump directly to 18-month autonomy or publication promises. | There is a clear near-term collaboration structure to react to. |
| 6 | Close on the benchmark and pilot ask | A short ask: benchmark pack, validation protocol, review cadence, first pilot questions | “The immediate ask is to help define the benchmark pack and validation protocol that would determine what earns promotion.” | Do not close on generic enthusiasm or vague future funding alone. | The meeting ends with a concrete follow-up artifact or review commitment. |

## Non-Negotiable Guardrails

- Do not recommend a hard “yes” scientist pitch.
- Do not present `Groundsource-style` as avalanche validation.
- Do not present `EAWS-style experimental` as official warning-service equivalence.
- Do not present MTS-LSTM, SAR, or autonomy as `Active` unless the proving artifact exists.
- Do not rank algorithm novelty above validation discipline and operational honesty.
- For every “present now” item, include the exact proving artifact or route.
- For every blocked item, include the proof artifact that would unlock it.

## Bottom Line

The last three weeks of work are worth taking to the scientist only if the team resists the temptation to sell autonomy-first novelty. The strongest immediate proposition is narrower and better:

- a working decision-support shell,
- an honesty-first operational semantics layer,
- a governance-aware evidence path,
- and a clear invitation for scientists to own the next validation frontier.
