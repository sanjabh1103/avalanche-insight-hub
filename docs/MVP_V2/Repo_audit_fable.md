Avalanche Insight Hub — Repo Audit & Improvement Plan
One-sentence summary: Evidence-based audit of the full repo (frontend, Supabase edge layer, Python ML backend) finding two Critical unauthenticated edge-function exposures and disabled TypeScript strictness as the top risks, with a 4-milestone remediation plan.

Executive Summary
Overall health: C+. The project has an unusually strong testing culture (82 backend test files, 25 frontend test files, Playwright e2e), SHA-pinned GitHub Actions, RLS enabled everywhere, and deep delivery documentation — but it ships two Critical security holes (trigger-job and ingest-event are publicly invokable with verify_jwt = false and write with service-role privileges) and runs a safety-critical UI with TypeScript strict: false. Top 3 risks: (1) anonymous callers can trigger Gemini/Modal-GPU spend and poison the avalanche training dataset; (2) CI gates almost nothing on the frontend (one test file, no lint/typecheck/build); (3) god-files (daily_inference.py 2,300 lines, trigger-job 1,389, Index.tsx 1,340) concentrate correctness risk. Top 3 opportunities: server-side auth on edge functions (small effort, removes both Criticals), turning the existing test suite into an enforced CI gate, and incremental strict-mode adoption. The repo is calibrated as a serious pre-production prototype heading to partner pilots — recommendations match that maturity, not enterprise scale.

Repo Map
Purpose: Open-source avalanche early-warning system — 24h grid forecasts from weather + terrain ML, field-report/news enrichment loop, SAR (Sentinel-1) wet-snow detection, scientist validation workbench.

Stack: React 18 + TypeScript + Vite 7 + Tailwind/shadcn + Leaflet/Three.js frontend; Supabase (PostGIS, RLS, Edge Functions in Deno, pg_cron); Python ML backend (scikit-learn, PyTorch, SHAP, Modal.com GPU workers); GitHub Actions for async training/inference; Netlify deploy.

Architecture flow: GitHub Actions / pg_cron → daily_inference.py + Modal workers → precomputed forecast_runs/forecast_grids in Supabase → run-forecast edge fn (read-only lookup) → Index.tsx renders grids/SHAP/runouts. Enrichment loop: field reports / NewsData+Gemini → trigger-job → ingest-event → avalanche_events → retraining.

Key directories:

src — React app; pages/Index.tsx is the orchestration hub; lib/ holds domain logic (gridUtils, scientistValidation); components/ UI incl. role gates
functions — 11 Deno edge functions; migrations — 46 migrations
backend — training (train_model.py), inference (daily_inference.py), SAR U-Net pipeline, scripts/ (65 ops scripts), tests (82 files)
workflows — 10 workflows (ML pipeline, release gates, CI)
delivery, MVP_V2 — extensive delivery evidence packs
Surprises: four lockfiles committed (package-lock.json, bun.lock, bun.lockb, deno.lock); ad hoc fix SQL (fix_rls_immediate.sql, APPLY_ALL_FIXES.sql) living outside migrations; current branch feature/european-data-shadow-pipeline is 36 commits ahead of main (main stale since 2026-05-16); package.json still named vite_react_shadcn_ts@0.0.0.

Lighter-review areas: internals of daily_inference.py / sar_unet_* (skimmed structurally), the 46 migration bodies, docs content, Playwright spec contents.

Audit Report
Security
S1 — CRITICAL (fact): trigger-job is publicly invokable and dispatches cost-incurring + state-mutating jobs without auth. config.toml:3-4 sets verify_jwt = false; index.ts:633-649 accepts 15 job types from any caller — only evaluate_release requires an admin bearer token (index.ts:303-378). Anonymous callers can trigger daily_enrichment (Gemini spend, index.ts:787), fine_tune, ml_train, retrain_avalanche_model, model_optimization (Modal GPU spend). Consequence: quota burn, cost abuse, and adversarial retraining of a safety-critical model.

S2 — CRITICAL (fact): ingest-event writes avalanche events with service-role privileges, no caller auth. config.toml:13 (verify_jwt = false); index.ts:354-375 parses the body and immediately creates a service-role client — no token check anywhere in the handler. Non-field-report sources (gemini_news, etc.) skip even the field-report-existence check (index.ts:381). Consequence: anyone can inject fake avalanche events into the training/groundtruth dataset (data poisoning of a safety system).

S3 — HIGH (fact): live credentials sit in the working-tree .env (.env:5-17): Gemini API key, NewsData key, Supabase service-role JWT, Modal token id/secret/worker token, and a DB password in a comment (.env:8). The file is untracked (verified via git ls-files) and .gitignore:25 covers it, but .env.netlify, .env.scientist.local, .env.lovable.backup multiply the leak surface. DEMO_ADMIN_PASSWORD="test123" (.env:17) pairs with a pre-filled admin email in the UI (AdminAccessGate.tsx:57) on a live deployment — trivially guessable admin login if that account exists in prod.

S4 — HIGH (fact): no Gemini spend-cap enforcement. incrementGeminiUsage reads gemini_spend_cap but never compares it before calling Gemini (index.ts:21-45, call at :787-804). Combined with S1, an anonymous loop can exhaust the API budget.

S5 — MEDIUM (fact): hardcoded anon JWTs + project ref in committed migrations for pg_cron HTTP calls (supabase/migrations/20260415100000_schedule_foundation_jobs.sql:21-22,44-45,67-68; also 20260416160000_*.sql:86-87, 20260501093000_*.sql:24-25). Anon keys are public by design, but key rotation now requires editing and re-running migrations, and the repo is hard-coupled to project fzheroisjhxnairglelv.

S6 — MEDIUM (judgment): LLM-output-to-database pipeline is injectable. Gemini extracts coordinates/severity from news text and the result is ingested as an event with confidence floor 0.45 (trigger-job/index.ts:816-874). A crafted news article (prompt injection) can fabricate events. Mitigated partially by corroboration_sources metadata; no human-review gate verified.

Healthy: RLS is enabled with sensible policies (public read, service-role write, per-user field_reports) — fix_rls_immediate.sql:9-38. UI role gates use real Supabase auth + app_metadata.roles (RoleAccessGate.tsx:39-43), not client-side passwords.

Architecture & design
A1 — MEDIUM (fact): god files concentrate the core 20%. daily_inference.py 2,300 lines; index.ts, ,389 (15-branch if/else dispatcher, :763-1240); Index.tsx 1,340; AdminDashboard.tsx ~1,310; himalayan_accuracy_contract.py 8,772. Consequence: every change to job orchestration or the main page risks unrelated regressions; review is hard.

A2 — MEDIUM (judgment): dual forecast read-paths (forecast_active_runs vs legacy forecast_grids) live side-by-side in run-forecast/index.ts:120-179 and in gridUtils.ts (legacy-playback shims). Already flagged in your own gap assessment (AVA-ARCH-001). Acceptable transitional state, but the legacy path needs a sunset date.

A3 — LOW (fact): ad hoc SQL outside migrations (APPLY_ALL_FIXES.sql, fix_rls_immediate.sql, enable_rls_all.sql, APPLY_ALL_MIGRATIONS.sql) — schema truth can drift from migrations/.

Code quality
Q1 — HIGH (fact): TypeScript strictness disabled. tsconfig.app.json:16,26 — noImplicitAny: false, strict: false. ESLint disables no-unused-vars (eslint.config.js:23) and excludes functions entirely (eslint.config.js:8). For an app whose output is "should I ski this slope," implicit-any holes in grid/risk math (gridUtils.ts, 723 lines) are a real correctness risk.

Q2 — MEDIUM (fact): swallowed exceptions in the enrichment loop. Per-article catch {} with no logging (trigger-job/index.ts:877-879); reverseGeocode also swallows (:16-18). Failures are counted but undiagnosable.

Q3 — LOW (fact): npm run jobs:* scripts are echo stubs (package.json:16-19) — dead/placeholder commands that mislead.

Testing
T1 — HIGH (fact): CI gates almost none of the frontend. frontend-trust.yml:44-45 runs exactly one test file (risk-narratives.test.ts); no npm run lint, no tsc, no vite build, and the other 24 test files don't run in CI. Backend CI is much better (backend-ci.yml:75-78 runs full unittest discovery).

T2 — MEDIUM (fact): push-triggered CI only fires on main/master (frontend-trust.yml:12-14, backend-ci.yml:12-14) while active work lives on a feature branch 36 commits ahead — recent work has only been CI-tested if PRs were opened (not verified).

T3 — LOW (judgment): no coverage measurement configured in vitest.config.ts or backend CI — can't know if core grid/risk logic is covered.

Healthy: test volume and naming discipline are excellent for this maturity (82 backend + 25 frontend + 3 e2e specs); tests assert behavior (e.g., gate-lock and release-gate tests).

Performance
P1 — LOW (judgment): run-forecast is a read-only precomputed lookup (good design). daily_enrichment does sequential per-article Gemini + Nominatim calls (trigger-job/index.ts:785-880) — fine at 5 articles, would not scale, not worth fixing now. No other hot-path issues identified at this depth.

Dependencies
D1 — MEDIUM (fact): four lockfiles committed (package-lock.json, bun.lock, bun.lockb, deno.lock) — npm vs bun ambiguity means CI (npm ci) and local installs can resolve differently.

D2 — LOW (fact): heavy frontend deps (three.js + react-three, turf, d3-geo, recharts, framer-motion) are all plausibly used; lovable-tagger is a leftover from the Lovable origin. No CVE scan run (not verified).

DevEx & operations
O1 — MEDIUM (fact): main is 3 weeks stale; release flow unclear. Netlify deploys from which branch? (not verifiable from repo). Long-lived divergence undermines the release gates you built.

O2 — LOW (fact): root clutter — screenshots, smoke-test-results.txt, snowslide_mock.zip, generate_synthetic_snowslide.py at repo root.

Documentation
DOC1 — MEDIUM (fact): README is stale and contradicts the code. README.md:5,7 claims Lovable URL + "Production Ready v1.0"; :9 describes the old pg_cron/Gemini loop as primary; :132 says "seven public tables" (46 migrations later); deploy target is now Netlify (netlify.toml). New contributors will be onboarded into the wrong architecture. Strength elsewhere: delivery evidence packs are unusually thorough.

Strengths (preserve these)
SHA-pinned actions with permissions: contents: read everywhere (frontend-trust.yml:23-24,31)
RLS-on-by-default with idempotent policy scripts
Real Supabase auth role gates, no fake client-side auth in UI
Read-only precomputed forecast serving (no synchronous ML in request path)
Backend test discipline incl. release-gate lock tests; reproduction contracts
Lazy-loaded routes, PWA offline field-report sync, honest stale/unavailable UI states
Improvement Strategy
Theme 1: The edge layer trusts the network (Criticals S1, S2, S4, S6)
Target state: every state-mutating or cost-incurring edge function authenticates its caller (JWT verification + role check, or a shared x-job-token for cron/CI callers); spend caps enforced before external API calls. Principle: in a service whose data feeds a safety model, write-paths are security boundaries — verify_jwt = false is only acceptable for pure-read endpoints.

Theme 2: Safety net exists but isn't wired to the gate (T1, T2, Q1)
Target state: CI fails on lint, typecheck, full vitest suite, and build for every PR and every active branch; TS strict mode on for lib first. Principle: tests you don't run are documentation, not protection.

Theme 3: Orchestration is a monolith dispatcher (A1, Q2)
Target state: trigger-job decomposed into per-job handlers behind a typed registry; Index.tsx split into a state hook + layout components. Don't fully rewrite — extract incrementally as each job type is next touched. Principle: match module boundaries to change frequency.

Theme 4: Environment coupling and repo hygiene (S5, D1, A3, O2, DOC1)
Target state: secrets only in platform secret stores; migrations parameterized via Vault/app_settings; one lockfile; ad hoc SQL archived into docs or converted to migrations; README rewritten to match reality.

Explicitly NOT recommended now
No microservice/queue re-architecture of the batch pipeline — the gap assessment (AVA-ARCH-001) already covers the forecast_runs decomposition; finish that, don't add more
No full strict-mode conversion of all 76 components — lib + new files only; UI components convert opportunistically
No dependency slimming (three.js etc.) — real features use them, payoff is low
No backend mypy adoption — 82 tests carry correctness; type-annotating 100k+ lines of Python is poor ROI at this stage
"Done" signals
Zero edge functions with verify_jwt = false that perform writes or spend money
CI fails on lint/typecheck/test/build for frontend PRs; both CI workflows trigger on all PRs regardless of base branch state
gemini_usage >= gemini_spend_cap provably blocks Gemini calls (test exists)
One lockfile; README quick-start works verbatim on a clean machine
No file > 1,500 lines in functions or pages
Task Plan
Milestone 0 — Safety net (before touching auth)
#	Task	Files	Acceptance	Effort	Risk	Deps
0.1	Full frontend CI gate: lint + tsc --noEmit + full vitest + build on all PRs	frontend-trust.yml	CI red on intentional lint/type/test break	S	Low	—
0.2	Add edge-function request-auth tests (characterize current anonymous behavior for trigger-job/ingest-event)	_shared, new test files	Tests document which job types accept anonymous calls today	M	Low	—
0.3	Merge or rebase feature/european-data-shadow-pipeline → main; decide branch strategy	git only	main ≤ 1 day behind active work; Netlify deploy branch documented	S	Med (merge conflicts)	—
Milestone 1 — Critical fixes
#	Task	Files	Acceptance	Effort	Risk	Deps
1.1	Authenticate trigger-job: require admin JWT or x-job-token for ALL job types (reuse existing prepareEvaluateReleaseRequest machinery at index.ts:303)	index.ts, config.toml, cron migrations, GH workflows that call it	Anonymous POST → 401 for every type; cron + Actions callers still work via token	M	High (can break cron/Actions callers — inventory all callers first)	0.2, 0.3
1.2	Authenticate ingest-event + field-report-enrichment (service-to-service token; field-report path may keep user-JWT)	ingest-event/index.ts, field-report-enrichment/index.ts, config.toml	Anonymous POST → 401; trigger-job→ingest-event chain passes token	M	High (same callers)	1.1
1.3	Enforce Gemini spend cap before calls; log per-article failures instead of bare catch {}	trigger-job/index.ts:21-45,763-898	Unit test: usage ≥ cap ⇒ no fetch to Gemini, job result says cap_exceeded	S	Low	—
1.4	Rotate exposed credentials (service-role key, Gemini, NewsData, Modal tokens, DB password) and kill DEMO_ADMIN_PASSWORD=test123 in prod; consolidate .env* files into one example + platform secrets	.env*, Supabase/Netlify/Modal/GH secret stores	Old keys revoked; demo admin uses strong generated password	S	Med (must update all secret stores in lockstep)	—
1.5	Parameterize cron-migration JWTs (use Supabase Vault / current_setting) so rotation doesn't require migration edits	supabase/migrations/20260415100000_*.sql + 2 successors (new migration)	New migration replaces hardcoded headers; cron jobs still fire	M	Med	1.4
Milestone 2 — High-leverage
#	Task	Files	Acceptance	Effort	Risk	Deps
2.1	TS strict mode for lib (separate tsconfig project or strict + targeted excludes); fix fallout	tsconfig.app.json, src/lib/*	tsc passes with strict: true over lib; CI enforces	L	Med	0.1
2.2	Lint edge functions (Deno lint or eslint deno config); re-enable no-unused-vars as warn	eslint.config.js, CI	functions no longer in ignore list; CI runs it	S	Low	0.1
2.3	Decompose trigger-job dispatcher into per-job handler modules with a typed registry	trigger-job	Each job type in its own file; index.ts < 300 lines; existing behavior tests pass	L	Med	1.1
2.4	Split Index.tsx: extract forecast-state hook (useForecastState) + presentational sections	Index.tsx, new hooks	Index.tsx < 500 lines; all 25 vitest files pass	L	Med	0.1
2.5	Single lockfile: delete bun.lock, bun.lockb (CI uses npm); keep deno.lock for functions	repo root	npm ci is the documented + only JS install path	S	Low	—
Milestone 3 — Quality & polish
#	Task	Files	Acceptance	Effort	Risk	Deps
3.1	Rewrite README: current architecture (async precompute, Netlify, GH Actions), real quick-start, remove pg_cron-as-primary and "seven tables" claims	README.md	Clean-machine onboarding works verbatim	M	Low	0.3
3.2	Archive ad hoc SQL (APPLY_ALL_*, fix_rls_*, enable_rls_all) into docs/ops/ with "historical" headers	supabase/*.sql	supabase contains only config.toml, migrations/, functions/, verify_schema.sql	S	Low	—
3.3	Root cleanup: move screenshots/zips/scripts to docs/assets/ & scripts; fix package.json name/version; remove echo-stub jobs:* scripts or implement them	root, package.json	Root contains only config + top-level dirs	S	Low	—
3.4	Add vitest coverage reporting + threshold for lib (e.g., 70%)	vitest.config.ts, CI	Coverage report in CI; threshold enforced	S	Low	0.1
3.5	Add a human-review or corroboration gate for gemini_news events before training_eligible=true	ingest-event/index.ts:340-352	News-sourced events require 2nd source or manual promotion	M	Med	1.2
3.6	Legacy forecast_grids read-path sunset plan (date + telemetry on which path serves traffic)	run-forecast/index.ts, gridUtils.ts	Decision doc + usage counter	M	Low	—
Quick wins (do immediately, all S effort)
0.1 full CI gate — biggest protection-per-hour in the repo
1.3 enforce the spend cap that already exists in the schema
1.4 rotate keys + kill test123
2.5 delete the bun lockfiles
3.2/3.3 SQL + root cleanup
Implementation sketches — top 3
1.1 Authenticate trigger-job. Approach: extend the existing admin-auth helper (prepareEvaluateReleaseRequest, trigger-job/index.ts:303-378) into a general authorizeJobRequest(type, req): accept (a) admin user JWT (roles via app_metadata), or (b) x-job-token matching a JOB_DISPATCH_TOKEN secret for cron/CI. Steps: inventory callers (3 cron migrations, GH workflows ml_pipeline.yml/train-avalanche-model.yml, AdminDashboard UI); add the token to Supabase secrets + GH secrets; update cron migrations (task 1.5) to send the token; gate the handler before the validTypes check; finally flip verify_jwt decision per function. Gotcha: AdminDashboard calls via supabase.functions.invoke with the user's JWT — verify the admin user's app_metadata.roles includes admin in prod before flipping, or you lock yourself out. Ship behind a REQUIRE_JOB_AUTH env flag for one deploy cycle to compare logs.

1.2 Authenticate ingest-event. Approach: same authorizeJobRequest shared helper (move to supabase/functions/_shared/auth.ts). Internal chain (trigger-job → ingest-event via invokeEdgeFunction, trigger-job/index.ts:47-80) should forward the job token in a header rather than the caller's Authorization. Field-report ingestion initiated by users can instead require a valid user JWT and verify field_reports.user_id === auth.uid. Gotcha: field-report-enrichment also calls ingest-event — update both call sites in the same PR; add a contract test for the chain.

0.1 Full frontend CI gate. Approach: replace the single-test step in frontend-trust.yml with four steps: npm run lint, npx tsc -p tsconfig.app.json --noEmit, npx vitest run, npm run build (with dummy VITE_ env like test:e2e:preview already does at package.json:12). Also broaden on.push.branches to ['**'] or add the active feature branch. Gotcha: tsc --noEmit may fail today because the build path uses Vite/SWC without typechecking — run locally first; if there's existing fallout, land the CI gate with tsc as non-blocking (separate job, continue-on-error) and flip it blocking in task 2.1.

Open Questions with responces
Open Questions
Which branch does Netlify deploy from? Determines urgency of the main-branch staleness (task 0.3).--> Mostly the main branch
Is admin@insight-hub.local with test123 an actual account in the production Supabase project? If yes, 1.4 escalates to immediate.-->yes 
What callers invoke trigger-job today besides pg_cron, GH Actions, and AdminDashboard? (Any partner scripts?) Needed before 1.1 to avoid breaking integrations.---Not sure
Is the legacy forecast_grids path still serving real traffic, or can it be sunset this quarter (3.6)? --->not sure . pls heck & decide
Bun vs npm: lockfiles suggest both were used; confirm npm is the sanctioned toolchain before deleting bun artifacts (2.5).--->any 
Target audience timeline: if scientist-partner pilots start soon, Milestone 1 should be completed before any external traffic increase.-->yes