# Draft Customer Response - MVP Phase 1 And MVP V2 Progress

Status: 2026-05-26  
Purpose: short customer email plus Word-attachment-ready progress note  
Scope: responds jointly to `docs/MVP/Cust_comm1.md` and `docs/MVP_V2/Cust_comm2.md`

## Short Email Body

Dear Sir,

Thank you for the earlier Himalayan avalanche publications and the newer Swiss RAvaFcast / EnviDat references. We reviewed both sets of inputs and used them to shape Avalanche Insight Hub in two linked phases.

In Phase 1, we built and validated a hosted avalanche decision-support MVP: public forecast workspace, admin/operator lane, batch forecast publication, uncertainty cues, terrain masking, bulletin-style display, share/export/report workflows, and candidate-model governance. This directly addresses the core operational challenges from the first set of papers: sparse observations, manual snowpack burden, class imbalance, black-box trust, spatial-temporal presentation, uncertainty communication, and heavy-compute bottlenecks.

In MVP V2, we extended the work toward a data-driven Himalayan co-development pathway. We studied the Swiss RAvaFcast and EnviDat material, downloaded and validated the Swiss RF1/RF2 data, reproduced a Stage-1 RF4 research signal, built partner evidence templates for Himalayan data intake, and created a 13-week scientist-in-the-loop pilot plan. The important finding is that Swiss-style automation is feasible as a design pattern, but Himalayan operational validation now needs local reviewed data, not only public bulletins.

The website today is therefore ready as a governed decision-support and validation platform. It is not yet a locally validated Himalayan warning-authority claim or deployed regional accuracy claim. The next step we propose is a 3-month co-development pilot with your scientist and data teams, where we jointly ingest reviewed Himalayan station, snowpack, danger-label, event, terrain, and holdout data; run validation gates; and decide what can responsibly move from research to operational pilot.

Attached is a concise progress note, current-state summary, and the exact inputs we request from your side for the pilot.

Best regards,  
Sanjay

---

## 1. What We Have Built Across Both Phases

| Area | What Exists Now | Why It Matters For The Customer |
|---|---|---|
| Hosted forecast workspace | Public route with map, forecast timeline, bulletin-style cards, uncertainty cues, terrain masking, and export/share/report actions. | Turns model output into something operators and non-technical stakeholders can inspect. |
| Admin/operator lane | Authenticated `/admin` route with publication and model-governance evidence surfaces. | Keeps operational claims tied to dated proof instead of verbal assurance. |
| Batch-first publication | Forecasts are prepared upstream and served as published artifacts. | Keeps the website responsive even when weather, terrain, snowpack, and model processing are heavy. |
| Explainable baseline model | Current live scorer remains an explainable Random Forest baseline. | Practical for sparse tabular avalanche data and easier for scientists to challenge than a black-box model. |
| Rare-event controls | Class-imbalance handling, chronological evaluation, PSS/Brier-style gates, calibration, and feature discipline exist in the backend. | Avoids over-trusting raw accuracy when dangerous avalanche days are rare. |
| Scientist review surfaces | Scientist workspace and daily verification workflow exist, with partial UI support for model-vs-scientist comparison. | Creates a co-working loop instead of treating the model as final truth. |
| Modal.com / GPU lane | Modal-backed candidate training and SAR workflows exist off the public path. | Enables heavier ML and remote-sensing experiments without slowing or overclaiming the public website. |
| SAR shadow lane | SAR U-Net and bi-temporal SAR candidate paths exist, but remain gated. | Adds a future route for weather-independent avalanche activity evidence, while avoiding premature operational claims. |
| Swiss RAvaFcast research lane | EnviDat RF1/RF2 downloaded, validated, and used for Stage-1 RF4 reproduction; GPxyz blocked pending station coordinates. | Converts the customer-supplied Swiss papers into a concrete reference implementation and identifies the data gaps. |
| Himalayan partner evidence contract | Templates and field dictionary for station metadata, weather, snowpack, danger labels, polygons, events, remote sensing, scientist reviews, and independent holdout. | Gives the partner a precise, machine-checkable way to supply local data for validation. |

## 2. How This Addresses The Top Forecasting Challenges

| Customer Challenge | Current Response | Status |
|---|---|---|
| Sparse and discontinuous observation networks | Batch forecast grid, snowpack proxies, station metadata requirement, and GPxyz readiness checks. | Meaningful progress; local station data still needed. |
| Dangerous manual snowpack work | Field-report and scientist-review workflows augment manual observation. | Partial; cannot replace field truth. |
| Incomplete avalanche occurrence records | Partner templates require historical events, source refs, confidence, and review status. | Ready for intake; real Himalayan rows needed. |
| Rare-event class imbalance | Random Forest path includes class weighting / KMeansSMOTE controls and rare-event metrics. | Strong technical foundation. |
| Weak layers and snowpack memory | Snowpack profile template asks for layer, grain, hardness, and stability features. | Data contract ready; local reviewed profiles needed. |
| Feature sprawl and overfitting | Feature discipline, feature/parity audits, and leakage guards are implemented in the research lanes. | Good current control. |
| Spatial and temporal hazard fusion | Public UI combines grid, time slider, daypart bulletin, and terrain masking. | Strong current user-facing capability. |
| Uncertainty communication | UI and docs separate live proof, research-only work, candidate paths, and blocked claims. | Strong governance posture. |
| Black-box trust | Random Forest baseline, explanation path, scientist review, and operator provenance reduce black-box risk. | Meaningful progress; active artifact currently uses fallback explanation. |
| Remote sensing promise and limits | SAR path exists but is explicitly shadow-gated. | Correctly cautious; not operational yet. |

## 3. Technologies Used And Why

| Technology / Method | Why We Used It | Current State |
|---|---|---|
| React + Vite + TypeScript | Fast, maintainable web app for map, bulletin, review, and admin workflows. | Live app surface exists. |
| Supabase Postgres, Auth, Storage | Structured database, access control, and artifact storage. | Used for app data and workflow surfaces. |
| Python batch pipeline | Keeps heavy forecast generation outside the browser. | Core backend path. |
| Random Forest baseline | Interpretable tabular model suitable for weather, terrain, and snowpack features. | Current live baseline. |
| KMeansSMOTE / class weighting / rare-event metrics | Helps avoid misleading accuracy on rare avalanche days. | Implemented in baseline methodology. |
| Calibration and chronological splits | Reduces probability overconfidence and avoids random time leakage. | Implemented in model pipeline. |
| Modal.com and GPUs | Runs heavier candidate-model and SAR workloads off-path. | Candidate/research use only, not live public scorer. |
| SAR U-Net / Swin U-Net candidate paths | Future remote-sensing route for avalanche activity mapping. | Shadow-gated. |
| RAvaFcast-style RF4 + GPxyz + aggregation | Directly follows the Swiss three-stage concept from the customer-supplied papers. | Stage 1 implemented; Stage 2 blocked pending coordinates; Stage 3 baseline implemented. |
| FAIR-style manifests and SHA-256 source refs | Makes partner data auditable, reusable, and leakage-checkable. | Implemented in partner handoff packet. |

## 4. What We Learned From The New Swiss Papers

| Paper / Reference | Key Lesson | How We Used It |
|---|---|---|
| NHESS 2022 dry-snow danger-level prediction | Raw forecast labels and quality-controlled `D_tidy` labels are not the same. Random Forest is a credible baseline, but label provenance matters. | We now require label source, review basis, nowcast/observer evidence, and scientist review before treating labels as training truth. |
| GMD 2024 RAvaFcast three-stage pipeline | Operational regional forecasting can be framed as: station danger classification, GPxyz spatial interpolation, and warning-region / elevation aggregation. | We built a Swiss reproduction lane and Himalayan templates for station X/Y/Z, warning polygons, refined aggregation, and holdout validation. |
| EnviDat weather-snowpack-danger dataset | Data-driven reproduction requires exact schemas, source manifests, and checksum-traceable files. | We downloaded RF1/RF2, validated the rows, and recorded data manifests locally. |
| Himalayan publications from Phase 1 | Himalayan conditions need local terrain, snowpack, station, and event evidence; imported results are not enough. | We kept Colorado and Swiss evidence as technical/research proof, not Himalayan accuracy proof. |

## 5. Current State In Plain Language

| Claim | Safe To Say Now? | Exact Framing |
|---|---|---|
| Website is live | Yes | The app has hosted public and admin surfaces and a Colorado Rockies technical publication proof. |
| It can support scientist review | Yes | Scientist review and daily verification surfaces exist, with partial UI support. |
| It can ingest Himalayan partner evidence today | Partly | Templates and validation scripts exist; full UI intake is not yet built. |
| It establishes Himalayan regional accuracy | No | Local reviewed Himalayan data and holdout gates are still pending. |
| Swiss RAvaFcast was studied and partially reproduced | Yes | Stage-1 RF4 reproduction signal exists; full parity needs station coordinates and warning-region polygons. |
| Promoted SAR detection exists | No | SAR remains a shadow-gated research path. |
| GPU/Modal drives public forecast today | No | Modal/GPU is used for off-path candidate workflows, not the current public scorer. |
| Production promotion is ready | No | Production promotion requires local holdout metrics and scientist release attestation. |

## 6. Pending Items

| Pending Item | Why It Matters | Owner Needed |
|---|---|---|
| Himalayan station metadata with latitude, longitude, elevation | Required for GPxyz-style spatial interpolation. | Partner data team + geospatial reviewer. |
| Quality-controlled danger labels | Avoids training on raw public bulletin noise. | Scientist lead + partner forecasters. |
| Weather and snowpack observation rows | Required for local feature generation. | Partner weather/snowpack team. |
| Warning-region polygons and elevation policy | Required for region-level forecasts and aggregation. | Partner GIS team. |
| Historical avalanche event truth | Required for false-positive / false-negative review. | Scientist lead + field observers. |
| Independent holdout set | Required before any local Himalayan accuracy claim. | Scientist lead + holdout auditor. |
| Release-gate attestation | Required before moving from research/pilot to stronger claims. | Named scientist approver. |
| UI region wiring for Himalayas | Required for public Himalayan pilot display after evidence gates pass. | Product/dev team. |

## 7. What We Need From Your Side For A 3-Month Co-Development Pilot

| Input Needed | Requested Format | Why We Need It |
|---|---|---|
| Named scientist lead and data contact | Names, roles, email, decision authority. | To keep weekly review and approvals clear. |
| Three priority Himalayan pilot regions | Region names, approximate boundaries, operational relevance. | To avoid building a generic system with no local focus. |
| Station metadata | CSV with station id, latitude, longitude, elevation, active dates, source ref. | Needed for spatial interpolation and data-quality checks. |
| Weather observations | CSV with timestamped temperature, precipitation, snowfall, snow depth, wind fields. | Needed for local feature generation. |
| Snowpack / weak-layer evidence | CSV with snowpack profile fields, stability indicators, and review notes. | Needed because weak layers and snowpack memory are central to avalanche risk. |
| Danger labels / bulletins | CSV with reviewed danger levels, validity windows, elevation/aspect policy, label source, review basis. | Needed for `D_tidy`-grade training and validation. |
| Warning-region polygons | GIS geometry or CSV/GeoJSON references with CRS and validity dates. | Needed for regional forecast aggregation and map display. |
| Historical avalanche events | Event location/time/elevation/aspect/problem/outcome/confidence/source. | Needed for error analysis and holdout validation. |
| Remote-sensing validation scenes, if available | Scene id, sensor, acquisition date, preprocessing level, truth/event refs. | Useful for future SAR validation, still shadow-gated. |
| Independent holdout definition | Region/date/source refs kept separate from training and threshold selection. | Required before any Himalayan accuracy claim. |
| License and sharing scope | What may be used for internal research, presentation, training, external display, or deployment. | Prevents misuse of restricted data. |
| Success criteria | Acceptable metrics, false-alarm tolerance, update cadence, operational constraints. | Lets us evaluate against the customer’s real decision needs. |

## 8. Proposed 3-Month Pilot Plan

| Month | Goal | Outputs | Decision Gate |
|---|---|---|---|
| Month 1 | Evidence intake and governance | Source manifest, station metadata, weather/snowpack rows, reviewed labels, first validation report. | Are the data sufficient and legally usable for a local pilot? |
| Month 2 | Model and spatial validation | RF4 feasibility spike, GPxyz readiness, aggregation policy, weak-layer review, first error analysis. | Is there enough evidence to run a meaningful local holdout? |
| Month 3 | Holdout, review, and pilot decision | Pre-registered holdout, leakage audit, metric report, scientist review, release-gate decision. | Continue, narrow scope, request more data, or stop. |

## 9. Suggested Attachment Bundle

Send only these initially, not the full artifact archive:

1. This response note.
2. `docs/MVP_V2/Artifacts/00_read_me_first/SCIENTIST_TEAM_QUICK_START_FAQ.md`
3. `docs/MVP_V2/Artifacts/02_scientist_operating_pack/Scientist_Handout_OnePager.md`
4. `docs/MVP_V2/Artifacts/04_workorders_and_weekly_execution/MVP_V2_W0_W13_PARTNER_WORKORDER.md`
5. `docs/MVP_V2/Artifacts/03_partner_handoff_packet/partner_field_dictionary.md`
6. The ten blank CSV templates from `docs/MVP_V2/Artifacts/03_partner_handoff_packet/`

## 10. Final Position

The work is now strong enough for a serious co-development discussion. It should be framed as:

> Avalanche Insight Hub is a live, governed avalanche decision-support platform with a clear path to Himalayan validation. It has already converted the customer’s scientific direction into a working website, model-governance architecture, Swiss RAvaFcast research reproduction, and partner data-intake packet. The remaining step is not more presentation material; it is local reviewed Himalayan evidence and a 3-month scientist-led validation pilot.

## Research And Evidence Anchors

- Customer communication 1: `docs/MVP/Cust_comm1.md`
- Customer communication 2: `docs/MVP_V2/Cust_comm2.md`
- Challenge evidence: `docs/MVP/source/Top_challanges.md`
- Challenge deck transcript: `docs/MVP/presentation/rendered/avalanche-insight-hub-deck-2-challenge-alignment-transcript.md`
- Swiss reproduction status: `docs/MVP_V2/Artifacts/02_scientist_operating_pack/Swiss_Reproduction_Lane.md`
- Partner field dictionary: `docs/MVP_V2/Artifacts/03_partner_handoff_packet/partner_field_dictionary.md`
- NHESS 2022: https://nhess.copernicus.org/articles/22/2031/2022/
- GMD 2024 RAvaFcast: https://gmd.copernicus.org/articles/17/7569/2024/
- WMO impact-based forecasting: https://wmo.int/impact-based-forecast-and-warning-services
- FAIR data principles: https://www.go-fair.org/fair-principles/
