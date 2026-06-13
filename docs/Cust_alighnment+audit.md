Customer-Aligned Final Re-Audit Plan
This plan defines a read-only, evidence-grounded re-audit of Avalanche Insight Hub against all discovered customer communications, PRDs, scientist-collaboration docs, and current implementation evidence.

Scope And Ground Rules
Goal: redo the repository audit with customer expectations as the primary lens, then produce a final alignment table scored out of 5 plus a gap-closure implementation strategy with edge cases and boundary conditions.
Non-goal: no source-code edits during the audit; only evidence collection, analysis, and recommendations.
Authority rule: all docs under docs are considered potentially authoritative; conflicts are resolved by recency, explicit customer/scientist intent, and proof-boundary wording.
Evidence rule: every claim must cite actual file paths and line numbers; unverifiable claims will be labeled explicitly.
Maturity calibration: assess as a scientist-validation / decision-support MVP moving toward pilot readiness, not as a certified official warning service.
Customer Communication Capture Plan
Initial high-signal docs already identified:

Source	Why it matters
Cust_comm1.md	Current customer-facing MVP alignment matrix and must-use language.
Cust_comm.md	Updated source variant with May 8 same-day publication wording.
prd_customer.md	Full-pivot SAR + MTS-LSTM PRD and public/data/API contracts.
prd_addendum.md	Adversarial scientific risk recalibration and revised score baseline.
Cust_comm2.md	Customer email pointing to RAvaFcast / EnviDat references and operational automation goal.
CLIENT_MEETING_RUNBOOK.md	Scientist meeting expectations, demo boundaries, and required closeout artifacts.
SCIENTIST_COLLABORATION_PITCH_MVP1_MVP2.md	Sendable scientist-facing email and claim boundaries.
README.md	Current scientist-safe story and explicit do-not-claim list.
docs/MVP_V2/01_scientist_client_pack/*	Scientist onboarding, top feature score sheets, SLA, validation workflow.
docs/MVP_V2/02_letters_outreach_templates/*	Director letter, outreach kit, questionnaire, meeting outcome templates.
docs/MVP_V2/04_european_shadow_evidence/*	European/SAR shadow evidence and transfer-boundary claims.
docs/MVP_V2/06_implementation_evidence/*	Code/test/migration copies used as customer proof artifacts.
docs/MVP/presentation/rendered/*	Customer-send deck sources, transcripts, proof maps, and technology glossary.
Additional discovery steps before final audit:

Search docs for customer, client, email, message, partner, SASE, DGRE, pilot, requirement, expectation, do not claim, must not say.
De-duplicate copied artifact-pack files versus source files.
Build a customer expectation register with one row per distinct expectation.
Preserve direct quotes where they define claim boundaries or acceptance criteria.
Customer Expectation Register Categories
The final report will score each category on a Customer Expectations Alignment Index / 5:

Category	Expected alignment evidence
Hosted public decision-support workspace	/ route, map/timeline/bulletin/risk evidence, disclaimer, share/export/report controls.
Same-day batch publication and freshness proof	forecast_runs, forecast_grids, publishedAt, sameDayPublished, stale/unavailable states, proof artifacts.
Admin/operator transparency	/admin, compute jobs, source health, model status, release gates, benchmark/stability/provenance display.
Scientist co-working and validation	/scientist, daily verification, two-reviewer governance, action ledgers, exportable review artifacts.
Claim honesty and deck readiness	Current-state/future-strategy language, no official-warning overclaim, no SAR/MTS production overclaim.
Groundsource and autonomous evidence governance	News + field reports scope, confidence weighting, training weights, review gates, no social wave-1.
SAR and remote-sensing path	Sentinel/ASF/GEE/SAR U-Net artifacts, mask + geometry handling, shadow/gated status.
MTS-LSTM / sequence-model candidate path	True sequence architecture, feature store, Modal/GPU role, RF surrogate boundary.
Snowpack / weak-layer science	HIM-STRAT-style proxy or partner adapter, weak-layer field taxonomy, boundary honesty.
Class imbalance, calibration, and metrics	PSS, Brier/ECE, Youden thresholding, KMeansSMOTE where appropriate, rare-event controls.
Batch-first architecture and safety	No runtime synthesis claims after cutover; edge functions light; heavy compute offloaded.
Security and pilot readiness	Auth gates, credential boundaries, no demo passwords in repo, RLS, customer-safe admin smoke.
Documentation and handoff quality	README, runbooks, templates, evidence manifest, reproducibility and FAIR-style provenance.
Codebase Verification Plan
Read and cite these implementation areas:

Frontend routes: App.tsx, Index.tsx, AdminPage.tsx, ScientistPage.tsx, ScientistDailyVerificationPage.tsx, ScientistPartnerIntakePage.tsx.
Customer-facing components: AvalancheMap, RiskDashboard, ForecastBulletinBadge, CellEvidenceDrawer, ForecastSidebar, ExportForecast, ShareForecast, FieldReportForm, ScientistValidationWorkbench, AdminDashboard, RoleAccessGate, AdminAccessGate.
Domain libs: gridUtils.ts, forecastArtifacts.ts, forecastBulletins.ts, scientistValidation.ts, partnerEvidenceReadiness.ts, riskNarratives.ts, offlineFieldReports.ts, fieldReportSync.ts, shapLoader.ts.
Supabase edge functions: run-forecast, trigger-job, ingest-event, field-report-enrichment, label-forecast-outcomes, run-evaluation, recent-activity-refresh, ingest-snow-cover, promote-report, _shared/auth.ts.
ML backend: daily_inference.py, train_model.py, modal_worker_app.py, lstm_model.py, models/mts_lstm.py, models/surrogate_rf.py, sar_unet_training.py, sar_unet_worker.py, common/label_governance.py, common/sequence_features.py, common/snowpack_proxy.py, common/sar_*, common/forecast_publication.py.
Schemas/migrations: latest migrations for forecast runs, scientist validation, governance, SAR artifacts, label weighting, cron tokens, RLS.
CI/tests: .github/workflows/*, src/test/*, backend/tests/*, supabase/functions/**/*.test.ts, tests/e2e/*.
External Research Plan
Use current web research to verify best-practice alignment for:

RAvaFcast / EnviDat Swiss three-stage reference from the customer email.
Avalanche SAR segmentation best practices and limitations: Sentinel-1 masks, manual labels, wet/dry snow constraints, revisit timing, region transfer risks.
MTS-LSTM / multi-timescale sequence modelling: true branched sequence models, feature-store requirements, calibration, sequence-space imbalance handling.
Operational warning and impact-based forecasting framing: WMO-style decision-support boundaries and do-not-claim language.
Scientific collaboration and reproducibility: FAIR provenance, Turing Way-style artifact manifests, validation-pilot design.
Security for public edge functions: authenticated job dispatch, service-role isolation, rate limiting, spend caps, RLS posture.
External claims will be clearly separated from repo-verified claims.

Scoring Method
Each customer expectation gets a score:

5.0: fully implemented, verified in code/tests/docs, and claim-safe for customer send.
4.0: substantially implemented; minor proof, freshness, or documentation gaps remain.
3.0: MVP/prototype support exists, but important scientific, security, data, or validation gaps remain.
2.0: mostly planned or shadow/gated; current implementation does not yet satisfy customer expectation.
1.0: not implemented or contradicted by code.
Each row will include:

Customer expectation
Source docs and line references
Current implementation evidence and line references
Alignment index / 5
Gap-analysis reason
Risk if not fixed before customer send
Recommended gap-closure task
Final Deliverable Shape
The final audit document will include:

Executive Summary — customer-readiness grade, top aligned areas, top gaps, and go/no-go recommendation.
Captured Customer Communications Register — all high-signal customer/email/message/PRD docs found under docs.
Customer Expectations Alignment Table — alignment index / 5, reasons, evidence, and gap analysis.
Codebase Re-Audit By Requirement Cluster — not generic architecture-only; each finding mapped to customer impact.
Best-Practice / Scientific Framework Check — current repo vs RAvaFcast, SAR, MTS-LSTM, WMO, FAIR/reproducibility, and security practices.
Detailed Implementation Strategy — gap-plug tasks with edge cases, boundary conditions, acceptance checks, risk, effort, dependencies.
Customer Claim Boundary Matrix — what can be said now, what must be softened, what must not be said.
Open Questions — human decisions needed before final customer send.
Verification Commands To Run During Audit
Read-only or non-mutating checks only unless explicitly approved:

git status --short
git branch --show-current && git rev-list --count main..HEAD
npm run lint
npx tsc -p tsconfig.app.json --noEmit
npx tsc -p tsconfig.lib.json --noEmit
npm run test
npm run build
python -m unittest discover -s backend/tests -p 'test_*.py'
Deno tests for edge functions if local Deno is available
If any check is not run or fails due to missing tools/secrets, the report will say so explicitly.

Immediate Risks Already Noted For Re-Audit
config.toml still sets verify_jwt = false for all listed functions; handler-level auth now exists, so final audit must verify REQUIRE_JOB_AUTH deployment defaults and token propagation rather than judging config alone.
Frontend CI has been strengthened with lint, app typecheck, lib strict typecheck, full tests, and build; backend CI still only pushes on main/master and should be reassessed.
tsconfig.app.json remains non-strict globally, but a separate tsconfig.lib.json appears to be used in CI; final audit should inspect scope and coverage.
eslint.config.js still ignores functions, so edge function linting may remain a gap even with handler tests.
 