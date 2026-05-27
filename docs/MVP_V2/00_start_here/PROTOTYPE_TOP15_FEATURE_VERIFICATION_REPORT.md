# Prototype Top-15 Feature Verification Report

Status: 2026-05-27  
Purpose: demo-prep verification of `PROTOTYPE_TOP15_FEATURES_AND_FUTURE_PLAN.md` and `SCIENTIST_COLLABORATION_PITCH_MVP1_MVP2.md`  
Boundary: this verifies prototype feature surfaces and scientist-demo wording. It does not validate Himalayan operational avalanche accuracy or official warning-service readiness.

## Executive Readout

The top-15 prototype feature claims are substantially supported by repo code, focused tests, and browser checks. The strongest live-demo story is: a hosted, batch-first avalanche decision-support workspace exists; it loads a Colorado Rockies precomputed artifact; it presents map/time/bulletin/masking/uncertainty/share/export workflows; and admin/scientist routes are present with role-gated access.

The main demo risk is freshness and access, not feature absence. On 2026-05-27, the hosted public route showed `PRECOMPUTED BATCH - STALE (72h)` and `last batch 6d ago`. Admin and scientist workflows are implemented and tested, but the browser-visible routes stop at login gates unless demo credentials and seeded scientist data are prepared. Therefore, for the meeting, say "working prototype and co-working workflow" rather than "fresh operational forecast" or "completed scientist validation."

## Verification Evidence

| Evidence Type | Result | Notes |
|---|---|---|
| Build | Pass | `PATH=/Users/sanjayb/.nvm/versions/node/v25.6.0/bin:$PATH npm run build` succeeded. The default Codex-bundled Node failed on Rollup native package loading; use the user-installed Node path for demo checks. |
| Focused tests | Pass | 11 test files / 40 tests passed: admin gate, role gate, bulletin, risk dashboard/IPA, uncertainty, cell evidence, field reports, scientist workbench, daily verification, exports. |
| Local browser `/` | Pass | Rendered Avalanche Hub public workspace with disclaimer, Colorado Rockies region, model/status panel, map, time controls, bulletin, share/export/report/event controls. |
| Hosted browser `/` | Pass with stale data caveat | `https://avalanche-insight-hub.netlify.app/` rendered the same public route and loaded a precomputed Colorado batch, but displayed stale status. |
| Hosted browser `/admin` | Pass as gated route | Rendered admin control lane and Supabase operator sign-in gate. |
| Hosted browser `/scientist` | Pass as gated route | Rendered scientist workspace and Supabase scientist sign-in gate. |
| Computer Use | Partial | Direct Computer Use could not inspect the Codex in-app browser; Chrome was inspected and available. Browser verification is the stronger UI evidence for this task. |

## External Best-Practice Anchors

| Anchor | Why It Matters For The Demo |
|---|---|
| WMO Impact-Based Forecast and Warning Services: https://wmo.int/impact-based-forecast-and-warning-services | Supports the product direction of moving from hazard display to actionable likelihood/severity/impact information, while keeping authority claims separate. |
| EAWS avalanche danger scale: https://www.avalanches.org/standards/avalanche-danger-scale/ | Supports the five-level danger framing used in the UI, with the caveat that this prototype is EAWS-style experimental, not an official EAWS warning product. |
| EAWS avalanche problems: https://www.avalanches.org/standards/avalanche-problems/ | Supports showing avalanche problem types alongside danger level, elevation, aspect, and time-window context. |
| EAWS spatial/temporal scale: https://www.avalanches.org/standards/setting-the-spatial-and-temporal-scale/ | Supports the need for warning regions, elevation/aspect policy, temporal subdivisions, and a fixed reference unit before stronger regional claims. |
| RAvaFcast GMD 2024: https://gmd.copernicus.org/articles/17/7569/2024/ | Supports the future plan: station-level classification, GPxyz-style interpolation, warning-region aggregation, and explicit station-density limitations. |
| NHESS 2022 RF danger-level paper: https://nhess.copernicus.org/articles/22/2031/2022/nhess-22-2031-2022.html | Supports the label-quality message: reviewed/tidy labels can materially change model evaluation, so public bulletins alone are not enough training truth. |

## Table A - Features Working Or Demo-Ready With Benefits To Highlight

| # | Feature | Verified Status | Evidence | Benefit To Highlight To Scientists | Demo Wording |
|---:|---|---|---|---|---|
| 1 | Public avalanche forecast workspace | Working | Hosted and local `/` render forecast map, disclaimer, status panel, bulletin, time controls, selected-cell area, share/export/report/event controls. | Shows that research output can be converted into a usable decision-support surface instead of remaining a notebook. | "This is a working decision-support shell for published forecast artifacts, not an official warning service." |
| 2 | Published batch forecast artifacts | Working, but current hosted batch is stale | Hosted route loaded `forecast-20260504T070406Z`, `PRECOMPUTED BATCH - STALE (72h)`. | Heavy computation stays outside the browser; users inspect published artifacts with provenance and freshness cues. | "The batch publication mechanism works; today it is stale, so we should not call this a fresh forecast." |
| 4 | EAWS-style experimental bulletin | Working | Browser showed danger level, problem type, critical aspects/elevations, morning/afternoon/evening windows, and peak window. | Speaks the language avalanche professionals expect: danger level plus problem, where, and when. | "EAWS-style experimental bulletin framing is implemented; local terminology still needs scientist approval." |
| 5 | Interactive map and time slider | Working | Browser showed Leaflet map, timeline controls, play/reset, hour offset, daypart buttons. | Lets scientists inspect how forecast state changes over time rather than seeing one static score. | "The UI supports map-and-time review of published cells." |
| 7 | Terrain and snow/public eligibility masking | Working | Hosted click showed `GRID STATE`, `APT MASKED`, slope angle, probability, and mask reason. Tests also cover cell evidence wording. | Prevents false low-risk messaging where terrain is outside the avalanche-prone or public-eligible profile. | "Masked terrain is deliberately separated from danger classes to reduce false confidence." |
| 8 | Uncertainty and reduced-confidence cues | Working | Hosted route displayed `STALE`, `REDUCED CONFIDENCE`, `HIGH UNCERTAINTY`, high-uncertainty cell counts. Tests cover uncertainty logic. | Shows scientific honesty: the app can say when evidence is weak, stale, partial, or uncertain. | "The product is designed to surface uncertainty rather than hide it." |
| 12 | Shareable forecast links | Working | Browser click on `SHARE` produced success toast: "Full-state forecast link copied". Code preserves region, hour, selected cell, expert mode, and 3D state. | Enables scientist review sessions where everyone discusses the same forecast state. | "A scientist can send a reviewable stateful link, not just a screenshot." |
| 13 | CSV and JSON forecast export | Working when artifact is loaded | Browser showed CSV/JSON buttons enabled for loaded artifact; focused export-related tests passed. | Makes the prototype auditable: scientists can take the grid data outside the UI for review. | "Exports reflect the currently loaded artifact fields; they are not independent validation." |
| 14 | Admin/operator control and observability | Working as protected route; full dashboard requires admin login | Hosted `/admin` rendered admin lane and operator sign-in gate. Admin gate tests passed. Source includes job controls, model status, source health, evaluation, publication trace surfaces. | Shows governance discipline: operators have a separate release/observability lane from public users. | "The admin lane exists and is role-gated; use demo credentials before showing internals." |
| 15 | Scientist validation and daily verification lane | Working as protected route; full workflow requires scientist login and seeded data | Hosted `/scientist` rendered scientist lane and sign-in gate. Tests passed for scientist workbench, daily verification, paired analytics, and export. | Gives scientists a direct role in adjudicating model-vs-expert disagreement, label quality, and claim impact. | "The scientist workflow is implemented and gated; it needs credentials and demo/real review rows for the live meeting." |

## Table B - Features Partially Working, Not Demo-Ready, Or Needing Prep

| # | Feature | Current Gap | Why It Matters | Plan To Fix Before Demo |
|---:|---|---|---|---|
| 2 | Published batch forecast artifacts | Hosted batch is stale on 2026-05-27 (`last batch 6d ago`, `STALE (72h)`). | A scientist may interpret stale data as weak operational discipline if we call it a current forecast. | Either publish a fresh Colorado technical artifact before the demo or explicitly say "hosted technical proof surface, not a fresh forecast today." |
| 3 | 20x20 grid and 72-hour review pattern | Docs record historic May 8 `20x20` / `400` / `72h` proof, but current visible browser text does not expose `20x20` or `400 ready cells`; it does expose `72h` and timeline review. | The presenter may be challenged if the live UI does not visibly show the exact grid-size claim. | Add a small visible "grid: 20x20 / ready cells / horizon" metadata line, or use a prepared screenshot from the verified May 8 proof pack. |
| 6 | Cell-level risk inspection | Masked selected cells are easy to demonstrate live; non-masked risk-score cells were not easily found in the current hosted artifact during spot checks. | The top-15 wording says selected cells show risk level/probability/drivers; a live demo should include at least one normal cell and one masked cell. | Prepare a known selected-cell link or publish/seed a demo artifact with both normal and masked cells. Keep masked-cell demo as the conservative fallback. |
| 9 | Weather summary and snowpack proxy context | Code supports these fields, but the current browser check did not prove a visible weather/snowpack proxy panel for the loaded artifact. | Scientists will ask whether snowpack/weak-layer context is real or placeholder. | Before demo, identify one artifact/cell with weather summary and snowpack proxy fields, or say this is an artifact-dependent surface awaiting partner-reviewed snowpack features. |
| 10 | Explainability and risk-driver display | Code supports TreeSHAP/fallback risk drivers, but current browser check mainly showed masked-cell details, not a visible active TreeSHAP panel. | Overclaiming active explainability is risky if the loaded artifact lacks verified SHAP metadata. | Demo wording should be "explainability surface exists; active TreeSHAP must be verified per artifact." Prepare a known artifact/cell with driver metadata if available. |
| 11 | Historical events and field-report evidence | Field-report tests pass and the public route has `REPORT` / `SHOW EVENTS`, but current browser check did not verify real event rows or a submitted report against Supabase. | Raw field/event records must not be treated as training truth without governance. | For demo, show UI affordances and offline/queue test evidence. Do not submit live reports unless using a demo project or agreed test row. |
| 14 | Admin dashboard internals | Browser-visible `/admin` is gated; no admin credentials were used in this verification. | Without a signed-in demo account, the audience sees only the gate, not observability internals. | Run `provision_scientist_demo_user.py`/admin credential prep as appropriate, confirm `DEMO_ADMIN_PASSWORD` or admin login, and smoke `/admin` before the meeting. |
| 15 | Scientist workbench internals | Browser-visible scientist routes are gated; full workbench was verified by tests but not live with credentials. | This is central to the co-working pitch; a gate-only live demo is weaker. | Provision scientist demo user, seed synthetic demo-only rows with `seed_scientist_demo_data.py`, then show `/scientist` and `/scientist/daily-verification` with claim-boundary labels visible. |

## Scientist Pitch Claim Cross-Check

| Pitch Claim | Verification Result | Evidence | Safe Benefit Framing |
|---|---|---|---|
| Hosted decision-support MVP exists | Verified | Hosted `/` rendered the public forecast workspace; hosted `/admin` and `/scientist` rendered protected routes. | "The product shell is real and hosted; the current artifact is stale and must not be framed as a fresh operational warning." |
| Scientist review workflow exists | Verified as code/test + gated route | `/scientist` and `/scientist/daily-verification` routes exist; role-gate and workbench tests passed; full browser workflow requires credentials. | "Scientists can be given a separate review lane without giving them broad operator/admin access." |
| Current live scorer remains an explainable RF baseline | Verified from route/status docs and source | Hosted route showed `active scorer surrogate_rf_v1`; `Modal_GPU_ML_Inventory.md` identifies `surrogate_rf_v1` as the active MVP baseline. | "The live MVP is anchored on an inspectable tree baseline, while advanced models remain gated." |
| Modal/GPU is off-path research/candidate compute | Verified from source/docs, not exercised in this run | `Modal_GPU_ML_Inventory.md` maps SAR and MTS-LSTM Modal paths and explicitly states they do not drive current public scoring. | "Modal helps candidate ML and SAR research without making the public route a black-box GPU product." |
| Swiss RAvaFcast research lane exists | Verified as research-only artifact/code | `backend/data/swiss_envidat/swiss_ravafcast_data_manifest.json` exists; `Swiss_Reproduction_Lane.md` records RF4 results and `production_scoring_allowed=false`; tests assert research-only boundaries. | "Swiss work is a reference and discipline check, not Himalayan proof." |
| Himalayan evidence framework exists | Verified as templates/contracts, not real partner evidence | Partner templates exist under `backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates/`; contract code requires `source_ref`, station metadata, D_tidy-style label provenance, and `himalayan_accuracy_claim_allowed=false`. | "The partner handoff is ready to collect reviewed evidence; it does not yet prove local accuracy." |
| SAR/remote-sensing path exists | Verified as shadow/candidate path, not production | Source/docs include SAR worker/training and European/SnowSlide qualification history; production promotion remains blocked. | "Remote sensing is a serious shadow lane, but not an operational detection claim." |

## Demo Script Recommendation

| Order | What To Show | Benefit Message | Safety Phrase |
|---:|---|---|---|
| 1 | Hosted `/` disclaimer and status panel | We make claim boundaries visible before showing maps. | "Decision-support prototype, not an official warning service." |
| 2 | Colorado Rockies map, time slider, bulletin | We can turn batch model output into a map/time/bulletin workspace. | "Colorado is live technical proof; it is not Himalayan accuracy proof." |
| 3 | Click a masked terrain cell | The UI avoids false low-risk messages outside eligible terrain. | "Masked is not low danger; it means this cell is outside the public/terrain profile." |
| 4 | Show reduced confidence / stale cues | The product is built to expose evidence weakness. | "Today’s hosted batch is stale, so do not treat it as a fresh forecast." |
| 5 | Share/export controls | Scientists can review the same state and export grid evidence. | "Exports are artifact evidence, not validation." |
| 6 | `/admin` and `/scientist` gates, then signed-in demo if credentials are prepared | Separation of public, operator, and scientist authority. | "Scientist review informs decisions; it does not automatically promote models." |

## Meeting-Ready Claim Edits

| Risky Line | Safer Line |
|---|---|
| "We have a live avalanche prediction system." | "We have a hosted decision-support prototype that renders published avalanche forecast artifacts with explicit caveats." |
| "The Colorado model proves the Himalayas." | "Colorado proves the web/publication mechanics; Himalayan accuracy requires local reviewed evidence and scientist gates." |
| "Admin and scientist workflows are ready for scientists to use today." | "The admin and scientist routes are implemented and tested; live use requires prepared accounts and seeded or real review rows." |
| "The app provides full operational avalanche detection." | "Remote sensing and advanced detection remain shadow-gated and require separate validation." |
| "The forecast is current." | "The hosted route currently works, but the loaded batch is stale unless we publish a fresh artifact before the demo." |

## Immediate Fix Checklist

| Priority | Action | Owner | Done Criteria |
|---:|---|---|---|
| 1 | Publish or clearly label a fresh/stale Colorado demo artifact | Operator/dev | Hosted `/` shows fresh status, or deck/script explicitly says stale technical proof. |
| 2 | Prepare one normal-cell and one masked-cell demo link | Dev/operator | Links restore selected cells and show risk details without hunting during the meeting. |
| 3 | Prepare admin and scientist demo credentials | Operator | `/admin`, `/scientist`, `/scientist/daily-verification` can be shown beyond the gate. |
| 4 | Seed synthetic scientist demo rows, if no real rows are approved | Operator | Workbench shows rows marked synthetic/demo-only and not training/production evidence. |
| 5 | Add visible grid/horizon metadata if absent | Frontend | UI displays grid size, ready/stale cell counts, and horizon in the public status panel. |
| 6 | Confirm weather/snowpack/explainability artifact fields before claiming them live | ML/dev | A known artifact/cell displays weather summary, snowpack proxy, and/or risk-driver metadata. |
