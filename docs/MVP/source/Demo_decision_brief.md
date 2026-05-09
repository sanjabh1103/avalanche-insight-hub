# Avalanche Demo Decision Brief

Updated: May 8, 2026

This is the customer-ready master brief for demo preparation. It separates:

- `current live MVP`
- `repo/admin verified capability`
- `shadow/future science path`
- `research-only precedent`

Locked defaults used in this brief:

- Canonical demo host: `https://avalanche-insight-hub.netlify.app/`
- Customer-safe demo routes: `/` and `/admin`
- Current May 8 public forecast proof: same-day published `72h` full-grid cell artifact for Colorado Rockies with `sameDayPublished=true`, `stale=false`, `forecastRunId=4822ecf8-defa-4479-ac86-cf9eb7cf2f08`, and `publishedAt=2026-05-08T14:31:50.594343+00:00`.
- Current May 8 admin proof: hosted authenticated smoke reached the signed-in observability dashboard, and the refreshed admin screenshot shows the exact active full-grid run id.
- Publication caveat: the May 8 full-grid artifact is `20x20`, has `400` ready cells, `0` stale cells, structured bulletin content, `13` bulletin dayparts, `data_lineage=observed_or_derived_real`, and `synthetic_inputs_present=false`; it is technical publication proof, not final scientist validation.
- Explanation/runout caveat: the active run reports `explainability_mode=heuristic_fallback`, `skipTreeShap=true`, and `runout_method_counts={"alpha_beta_elliptical":7}`. TreeSHAP and WhiteboxTools are credible hardening paths, not stronger active-run proof for this artifact.
- Cost basis: India-lean co-development team with selective specialist support
- Main-deck roadmap lens: use the 3-phase scientist collaboration model in `Scientist_discussion_framework.md`; treat the 5-phase table below as appendix-only productization expansion for deck builds.

Scales used below:

- `Gap rating (1-5)`: `1` = small remaining gap, `5` = large unresolved gap
- `Novelty rating (1-5)`: `1` = established approach, `5` = materially differentiated and not clearly evidenced in prior art
- `Readiness rating (1-5)`: `1` = distant or weakly grounded, `5` = near-term and strongly grounded in current repo truth

Proof tiers used where relevant:

- `Live demo` = visible on the current public route, live admin gate, or the May 8 hosted authenticated admin smoke when explicitly dated
- `Repo/admin verified` = implemented and provable in code or operator surfaces
- `Shadow-gated or config-gated` = present in repo but not active on the public MVP
- `Research-only precedent` = supported by publications or planning direction, not by current repo proof

Scientist-readiness companion artifacts for this brief:

- `docs/MVP/source/Scientist_claim_ledger.md`
- `docs/MVP/source/Scientist_evidence_surface_ledger.md`
- `docs/MVP/source/Governed_autonomy_evidence_fusion_note.md`
- `docs/MVP/source/Scientist_benchmark_pack_v0.md`
- `docs/MVP/source/Scientist_validation_protocol_v0.md`
- `docs/MVP/source/Scientist_meeting_checklist.md`

## Past Research Baseline

| Rank | Research point | Client paper/source | Challenge identified | Solution proposed in literature | Relevance now (1-5) |
|---|---|---|---|---|---:|
| 1 | ANN-based nonlinear avalanche forecasting is already part of the client’s history. | Singh and Ganju 2008 | Linear or rule-based systems miss nonlinear snow-weather interactions. | Use ANN classifiers to learn nonlinear relations from historical snow-meteorological patterns. | 4 |
| 2 | The client lineage has already considered broader modelling families, including GIS and AHP. | GeoSpatial review 2011 | One model family rarely captures the whole operational problem. | Combine statistical, numerical, GIS, and decision-support methods instead of betting on a single paradigm. | 3 |
| 3 | Variable weighting is not a minor tuning detail. | Singh et al. 2015 | Subjective parameter weighting can distort nearest-neighbour forecasts. | Optimize weights using ABC and skill-score-driven search rather than manual tuning. | 5 |
| 4 | Calibration can have multiple plausible optima. | Singh et al. 2015 | Different parameter sets can look good on paper, creating governance ambiguity. | Use repeated optimization and skill-based comparison rather than one-off calibration. | 5 |
| 5 | Compute burden is part of the avalanche-forecasting problem. | Singh et al. 2017 | Calibration and training can be too slow for practical operations. | Use GPU acceleration and keep heavy computation off the interactive user path. | 5 |
| 6 | HIM-STRAT already linked ANN simulation with a snow stability index. | Joshi et al. 2020 | Weather-only systems miss snowpack structure and weak-layer effects. | Simulate snowpack parameters and combine them with a stability index. | 5 |
| 7 | Feature discipline can outperform feature sprawl. | Kaushik 2025 | Too many variables increase noise, cost, and overfitting risk. | Use SVM-RFE to reduce large input sets to the most significant drivers. | 5 |
| 8 | Rare-event imbalance must be treated explicitly. | Kala 2025 | Avalanche days are rare, so naive accuracy can be misleading. | Use class balancing and rare-event metrics such as POD and PSS. | 5 |
| 9 | Missing occurrence records are a first-order weakness. | Kala 2025 | Training and validation degrade when avalanche events are under-recorded. | Improve event capture and evaluate models against richer occurrence evidence. | 5 |
| 10 | Physics-based snowpack simulations add meaningful signal beyond simple snowfall totals. | Mayer 2023 | New-snow sums alone do not capture weak layers or structural instability. | Combine snowpack simulation outputs with probabilistic models. | 5 |
| 11 | Explainability is operationally useful, not cosmetic. | Perez-Guillen 2025 | Black-box model outputs reduce forecaster and user trust. | Use SHAP to expose local and global feature influence for danger-level models. | 4 |
| 12 | Human forecasts still have a small edge over model-only forecasts. | Techel et al. 2025 | Fully automated model-driven systems are not yet clearly superior in operational discrimination. | Integrate models as strong second opinions inside human workflows. | 5 |
| 13 | Snowpack simulations need continuous validation against critical layers. | Herla 2024 | Even strong snowpack models can drift away from operationally relevant weak-layer conditions. | Build validation suites focused on critical layers and real-time checks. | 4 |
| 14 | SAR mapping is powerful but incomplete. | Leinss et al. 2020 | Remote sensing misses some avalanche features, timing precision, and dry-snow conditions. | Use multiorbital SAR and change detection as a complement, not a stand-alone truth engine. | 4 |
| 15 | Structured bulletin logic and impact-based communication matter as much as the raw model. | EAWS Matrix 2025; WMO IBFWS | A strong model still fails operationally if the warning format is inconsistent or unactionable. | Use matrix-based danger framing and impact-oriented communication. | 4 |

## Present MVP Gap Analysis

The table below focuses on the top 15 customer-facing challenges that matter before slide preparation.

| Rank | Challenge/issue | Status | Gap rating (1-5) | How MVP addresses it | Why gap remains | Demo pointers | Website link |
|---|---|---|---:|---|---|---|---|
| 1 | Slow or brittle forecast delivery under heavy compute | `tackled` | 1 | The public app serves a precomputed forecast artifact with ready/partial/stale states and lazy hour loading; May 8 proof is a same-day published `72h`, `20x20`, full-grid cell artifact. | It is fast because it is batch-first, not because heavy science is solved in real time; current proof must be described as technical publication evidence rather than scientist validation closure. | Current published horizon badge, timeline, map load, publication-state notice | [Forecast workspace](https://avalanche-insight-hub.netlify.app/) |
| 2 | Users need a structured forecast, not a raw model console | `tackled` | 2 | The bulletin layer shows danger level, problem framing, elevations, aspects, and time windows. | It is still experimental framing, not an official avalanche warning service product. | Bulletin cards, daypart chips, danger labels | [Forecast workspace](https://avalanche-insight-hub.netlify.app/) |
| 3 | Terrain outside avalanche scope must look out of scope | `tackled` | 1 | APT-gated masking keeps irrelevant terrain visually separate from low-danger terrain. | Snowline and snow-cover eligibility are not fully solved by slope gating alone. | Masked cells, unavailable states, terrain semantics | [Forecast workspace](https://avalanche-insight-hub.netlify.app/) |
| 4 | Uncertainty must be obvious to users | `tackled` | 2 | The public UI surfaces reduced-confidence states, uncertainty counts, and SAR-support caveats. | This is honest uncertainty communication, not a complete probabilistic uncertainty science stack. | Reduced-confidence cues, evidence/coverage language | [Forecast workspace](https://avalanche-insight-hub.netlify.app/) |
| 5 | Teams need one shareable operating picture | `tackled` | 1 | The app supports full-state share links plus CSV/JSON/report actions. | Shared state still depends on the referenced forecast artifact remaining available. | Share, CSV, JSON, Report actions | [Forecast workspace](https://avalanche-insight-hub.netlify.app/) |
| 6 | Hazard needs consequence context for roads and assets | `tackled` | 2 | Expert overlays and runout warnings connect hazard output to roads and mapped assets. | Asset and runout quality still vary by region and data completeness. | Expert mode, overlays, runout warnings | [Forecast workspace](https://avalanche-insight-hub.netlify.app/) |
| 7 | Forecast reasoning must be inspectable | `tackled` | 2 | Operator provenance and explanation surfaces reduce black-box risk; the current active run uses heuristic explanation fallback while TreeSHAP remains the hardening path. | Explainability does not prove correctness, and the current artifact should not be described as TreeSHAP-proven. | Cell inspection, expert controls, model provenance | [Forecast workspace](https://avalanche-insight-hub.netlify.app/) |
| 8 | Sparse-data mountain operation | `partial` | 3 | The repo uses region-wide batch products, Open-Meteo-style forcing, and governed evidence augmentation. | Sparse data are still the biggest science bottleneck, especially for local validation. | Region selector, freshness status, event layer | [Forecast workspace](https://avalanche-insight-hub.netlify.app/) |
| 9 | Autonomous evidence capture with governance | `partial` | 4 | Field reports, news ingest, dedupe, and weighted evidence handling all exist in the repo. | The live demo does not yet prove a complete, continuously trusted autonomy loop. | Report flow, events layer, ingest narrative | [Forecast workspace](https://avalanche-insight-hub.netlify.app/) |
| 10 | Rare-event evaluation and release discipline | `partial` | 2 | The repo exposes evaluation jobs, release evidence, and candidate-model status. | Most of this strength is operator-facing, not directly visible to public users. | Model status surfaces, admin route, version cues | [Admin gate](https://avalanche-insight-hub.netlify.app/admin) |
| 11 | Rapid update cadence from fresh evidence | `partial` | 2 | The product refreshes the active published artifact and exposes freshness plus async jobs; May 8 proof confirms same-day full-grid publication metadata. | The system is not a real-time autonomous retraining platform, and the current full-grid run still needs scientist review before stronger validation language. | Freshness states, current published artifact language | [Forecast workspace](https://avalanche-insight-hub.netlify.app/) |
| 12 | Snowpack memory and weak-layer completeness | `partial` | 4 | Problem framing, snowpack proxies, and future shadow-model hooks point in the right direction. | The MVP is not a validated critical-layer observatory or full snowpack-physics platform. | Problem cards, expert narratives, candidate-model language | [Forecast workspace](https://avalanche-insight-hub.netlify.app/) |
| 13 | Operational SAR support | `partial` | 4 | Coverage and evidence limits are surfaced honestly, and the repo has SAR artifact scaffolding. | The product does not yet prove broad live SAR segmentation and regional operational coverage. | SAR/support caveats, evidence coverage language | [Forecast workspace](https://avalanche-insight-hub.netlify.app/) |
| 14 | Micro-climate and local slope heterogeneity | `missing` | 5 | Regional grids, terrain modifiers, and masking reduce some false precision. | Local heterogeneity remains a hard unsolved science problem without denser truth and validation. | Selected-cell inspection, map vs local reality discussion | [Forecast workspace](https://avalanche-insight-hub.netlify.app/) |
| 15 | Fully autonomous promoted next-gen scorer | `missing` | 5 | The repo contains a shadow-gated MTS-LSTM path and promotion language. | It is not the active public scoring path, and promotion evidence is not yet there. | Candidate-shadow status, admin/model narrative | [Admin gate](https://avalanche-insight-hub.netlify.app/admin) |

## Advanced Technology Propositions

| Technology/method | Where used now | Proof tier | What is genuinely modern here | Prior-art comparison | Novelty rating (1-5) | Caveat |
|---|---|---|---|---|---:|---|
| Batch artifact plus lazy geospatial hydration | Public MVP | `Live demo` | Keeps heavy geospatial forecast payloads interactive without forcing synchronous recompute. | Research systems often publish bulletins or model outputs, but not a customer-facing lazy-hydrated forecast workspace. | 3 | Strong engineering, not a new avalanche science method. |
| APT-gated masked terrain contract | Public MVP | `Live demo` | Treats out-of-scope terrain as masked instead of low risk, which is a trust-forward product choice. | Stronger honesty semantics than many conventional hazard maps or region-only bulletins. | 4 | It still depends on the quality of the underlying terrain gate. |
| EAWS-style bulletin UI with explicit uncertainty | Public MVP | `Live demo` | Blends model output into a public-facing bulletin format while keeping uncertainty visible. | Consistent with European bulletin logic, but not equivalent to an authority warning service. | 3 | The innovation is product packaging, not ownership of the EAWS standard. |
| SHAP-backed cell inspection | Public MVP | `Live demo` | Gives local, inspectable model rationale in a forecast workspace instead of hiding feature effects in backend reports. | Closely aligned with Perez-Guillen 2025, but more productized for interactive review. | 3 | Explainability is meaningful but not unprecedented. |
| PWA offline field-report replay | Repo/admin path | `Repo/admin verified` | Helps collect mountain evidence even under unreliable connectivity with implemented local queueing and replay. | Research papers rarely address field-evidence UX and offline replay directly. | 3 | Useful operationally, but device or deployment smoke is still required before field-reliability claims. |
| Governed autonomous event weighting and deduplication | Repo/admin path | `Repo/admin verified` | Encodes `label_confidence`, `training_weight`, and corroboration logic before evidence is trusted. | Stronger governance layer than most individual avalanche research papers, closer to production data-engineering thinking. | 4 | Needs more live validation before it can be sold as a solved truth engine. |
| Feature-selection and rare-event evaluation discipline | Repo/admin path | `Repo/admin verified` | Aligns the repo with current Himalayan evidence on SVM-RFE and class-imbalance handling. | Scientifically grounded, but the methods themselves are established. | 2 | This is rigor, not novelty. |
| Random-forest baseline and surrogate explanation path | Current scoring and trust path | `Repo/admin verified` | Uses a practical tree-based stack that is explainable and operationally governable. | Very consistent with recent Swiss second-opinion work. | 2 | Reliable and defensible, but not new. |
| 3D voxel and runout consequence review | Public MVP plus expert mode | `Repo/admin verified` | Moves from flat hazard display toward consequence-aware spatial inspection. | Product-oriented rather than a common research-paper deliverable. | 3 | Value depends on runout completeness and region data quality. |
| Earth Engine plus rasterio plus whitebox geospatial processing | Repo/admin path | `Repo/admin verified` | Gives the repo a credible hybrid geospatial processing base for terrain and remote-sensing expansion. | Modern stack choice, but not unique in geospatial engineering. | 3 | Several flows remain gated or unfinished for live operations. |
| SAR coverage and artifact schema foundation | Repo/admin path | `Repo/admin verified` | The schema already anticipates mask assets and derived event geometries, which is better than a vague SAR aspiration. | More concrete than many high-level product plans, but not yet a promoted SAR system. | 3 | Current public proof is mainly coverage signaling, not production detection; data access, label scarcity, dry-snow detectability, revisit limits, and radar shadow or layover remain gating blockers. |
| MTS-LSTM shadow path with promotion gates | Shadow science path | `Shadow-gated or config-gated` | Couples sequence-model ambition to explicit release gates instead of direct marketing. | The combination is directionally modern and consistent with ANN lineage, but not yet proven better than the baseline. | 4 | Not an active public model. |
| Scientist-in-the-loop validation suite and impact-based packaging | Future path | `Research-only precedent` | Ties avalanche ML, validation discipline, and consequence-oriented warning design into one co-development program. | Closer to international best practice than to a finished product today. | 4 | This is roadmap, not delivered capability. |

## Future Path To Full Product

For the main scientist deck, this table is appendix-only. The primary meeting visual should use the 3-phase scientist collaboration model in [Scientist_discussion_framework.md](./Scientist_discussion_framework.md).

These are directional phase budgets, not vendor quotes. Amounts are incremental per phase and assume an India-lean team with selective specialist support.

| Phase | Objective | Key technical actions | Team shape | Timeframe | Approx budget | Value unlocked | Readiness rating (1-5) |
|---|---|---|---|---|---|---|---:|
| 1 | MVP hardening and pilot readiness | Freeze truth-tier language, verify `/` and `/admin` smoke flows, harden report replay, tighten model-status provenance, and package customer-safe demo assets. | 1 full-stack engineer, 1 frontend/map engineer, 1 QA/ops engineer, 0.25 avalanche-science advisor | 0-3 months | INR 25-40 lakh (about USD 30k-48k) | A credible pilot-ready product story without scientific overclaim. | 5 |
| 2 | Scientist-in-the-loop evidence pilot | Add stronger event-review tooling, shared evaluation dashboards, routine label/outcome review, and client-scientist feedback loops. | Phase 1 team plus 1 ML/data engineer and 0.5 geospatial analyst | 3-6 months | INR 40-65 lakh (about USD 48k-78k) | Turns the MVP into a governed co-development platform instead of a one-off demo. | 4 |
| 3 | Remote-sensing and shadow-model pilot | Bootstrap SAR artifact handling, run shadow MTS-LSTM training on GPU, expand evaluation gates, and begin curated local validation. | 1 ML engineer, 1 geospatial/remote-sensing engineer, 1 MLOps engineer, 0.5 scientist review capacity | 6-12 months | INR 75 lakh-1.2 crore (about USD 90k-145k) | Creates real evidence for or against stronger autonomy claims. | 3 |
| 4 | Operational authority-style pilot | Promote only proven shadow paths, add stronger consequence workflows, and shape impact-based dissemination outputs for controlled pilots. | Phase 3 team plus product lead and part-time warning-domain advisor | 12-18 months | INR 1.2-2.0 crore (about USD 145k-240k) | Moves from decision-support MVP toward an authority-facing operational pilot. | 2 |
| 5 | Full productization and publication package | Expand multi-region validation, strengthen reproducibility and documentation, formalize co-developed benchmark packs, and prepare papers or formal pilot reports. | Stable product squad plus dedicated research lead and support for publication/partnership work | 18-24 months | INR 2.0-3.5 crore (about USD 240k-420k) | Makes the platform defensible as a long-term co-developed product rather than a promising prototype. | 2 |

## Decision Synthesis

| Decision area | Ready to demo now | Credible next | Must remain research ambition |
|---|---|---|---|
| Forecast experience | Published-horizon batch workspace, structured bulletin, uncertainty cues, share/export/report | Better consequence workflows and cleaner operator analytics | Real-time self-updating autonomous forecast engine |
| Evidence generation | Public field reports and governed ingest scaffolding | Weighted multi-source event review with scientist oversight | Fully trusted autonomous ground-truth replacement |
| Model stack | Explainable baseline plus release-evidence posture | Shadow-model evaluation with explicit promotion gates | Public claim that MTS-LSTM already outperforms current scoring in production |
| Remote sensing | Honest SAR coverage signaling with explicit qualification blockers | SAR artifact promotion and controlled remote-sensing pilot | Universal SAR truth engine across all regions |
| Warning semantics | `EAWS-style experimental` framing and impact-aware overlays | More formal impact-based alert packaging | Official EAWS or WMO-equivalent warning-service status |
| Customer partnership | Strong co-development narrative backed by the client’s publication lineage | Scientist-in-the-loop pilot and benchmark pack | Claim of finished scientific or operational closure today |

## Publication And Uniqueness Snapshot

| Question | Verdict | Rating (1-5) | Why |
|---|---|---:|---|
| Is this already strong enough for an independent systems or pilot-methods paper? | Yes, with careful scope. | 4 | The combination of open repo, product workflow, sparse-data positioning, and evidence-governed design is paper-worthy if the claim is systems-oriented. |
| Is this already a groundbreaking avalanche science breakthrough? | No. | 2 | The science ingredients draw heavily from prior ANN, snowpack, SAR, and explainability literature, and validation is still incomplete. |
| Is the product/integration story distinct enough to stand out in a customer demo? | Yes. | 4 | The strongest uniqueness lies in the governed, honesty-first integration of forecast UX, evidence ingest, masking, uncertainty, and scientist-team co-development. |
| Is external validation mature enough for aggressive publication claims? | Not yet. | 2 | The current repo truth supports direction and engineering discipline more than completed operational validation. |
| Would co-development with the client scientist team materially improve publishability? | Yes. | 5 | A shared benchmark, validation loop, and operational pilot would convert several current caveats into defendable evidence. |

## Top 5 Methodology Comparison

| Methodology | Closest benchmark | How our proposal differs | Distinctness rating (1-5) | Customer-safe claim |
|---|---|---|---:|---|
| Batch-first interactive forecast workspace | Traditional bulletin and model-support tools | Turns precomputed science output into a shareable, stateful forecast workspace rather than a static forecast product. | 4 | “We already have a usable decision-support front end, not just a model notebook.” |
| APT-gated masked terrain semantics | Standard danger maps and region bulletins | Treats out-of-scope terrain as masked instead of flattening everything into low danger. | 4 | “We designed the public semantics to avoid false confidence.” |
| Governed news plus field-report evidence fusion | Google Groundsource flood methodology | Applies a Groundsource-style idea to avalanche evidence with explicit weighting and dedupe logic. | 4 | “This is a governed avalanche adaptation idea, not transferred avalanche validation from Google.” |
| SHAP-backed cell inspection inside the forecast UX | Perez-Guillen 2025 explainable danger model | Pushes explainability into an interactive product surface rather than a research-only evaluation artifact. | 3 | “We can show forecast rationale at the point of use.” |
| MTS-LSTM plus SAR plus promotion-gate roadmap | Client ANN/HIM-STRAT lineage plus current Swiss ML workflows | Frames next-gen modelling as gated, evidence-driven promotion instead of immediate replacement marketing. | 4 | “The advanced-model path is credible and disciplined, but still future-facing.” |
