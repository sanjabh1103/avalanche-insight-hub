# Avalanche Demo Research Appendix

Updated: May 8, 2026

This appendix is intentionally more adversarial than the customer-ready brief. Its job is to pressure-test claims, compare the repo to the strongest prior art, and keep novelty language honest.

For deck generation, use this as `Artifact/doc proof only` unless a specific row points to hosted route or admin proof. It is designed to support cautious wording, not to upgrade candidate paths.

## Adversarial Repo-Vs-Claim Audit

| Claim area | Strong wording that needed downgrade | Adversarial verdict | Current truth layer | Safe wording going forward |
|---|---|---|---|---|
| Groundsource positioning | “World’s first open-source Groundsource-style AI avalanche early-warning system” | Unsupported as a current-state claim. The repo shows inspiration and partial ingest machinery, not avalanche-domain validation. | `repo/admin verified` plus `research-only precedent` | “A governed, Groundsource-style avalanche evidence approach inspired by flood-domain work.” |
| Self-improving evidence loop | “Continuously enhances the dataset” | Too strong for the live demo. The repo has ingest and weighting machinery, but not proven continuous trustworthy autonomy on the public surface. | `repo/admin verified` | “Supports governed evidence enrichment and weighting.” |
| Update cadence | “Rapidly updating” or “real time” | Only partially true. The live product loads the latest published artifact; it is not continuous retraining. | `current live MVP` plus `repo/admin verified` | “Refreshes the latest published batch forecast and shows freshness.” |
| Production model status | “Advanced LSTM / PINN stack is already driving the forecast” | False for the current demo. The MTS-LSTM path is shadow-gated. | `shadow/future science path` | “A candidate shadow path exists and must earn promotion.” |
| SAR operations | “Operational SAR avalanche detection” | Overstated. The repo has SAR-related schema and coverage signaling, but not broad live promoted SAR mapping. | `repo/admin verified` plus `shadow/future science path` | “SAR support is being scaffolded; current public proof is mainly coverage signaling.” |
| Autonomy level | “No or minimal human-observed data required” | Unsupported as a present-state claim. The literature and repo both still lean on limited but important observed inputs. | `research-only precedent` | “Designed to reduce manual dependence, not eliminate the need for truth and validation.” |
| Bulletin equivalence | “EAWS bulletin” | Incorrect. The correct wording is `EAWS-style experimental`. | `current live MVP` | “An EAWS-style experimental bulletin layer.” |
| Authority equivalence | “Operational warning service” | Too strong for the current product. There is no proof of official-authority deployment or dissemination standards. | `future path` | “A decision-support MVP with authority-facing future potential.” |
| Admin proof | “Live admin dashboard proves scientific maturity” | Overstated. Hosted authenticated admin proof succeeded on May 8 and supports operator observability for the active same-day publication, but it does not prove scientific correctness. | `Hosted production` plus `Repo/admin verified` | “The signed-in operator lane exposes source health, provenance, model status, stability, publication state, and benchmark context as governance evidence.” |
| Human replacement | “AI can replace expert avalanche forecasters” | Contradicted by recent benchmark literature. Model support is getting stronger, but expert workflows still matter. | `research-only precedent` | “Model support is approaching operational usefulness as a second opinion.” |

## Client Publication Findings

| Year/paper | Question addressed | Key finding | Challenge surfaced | What it means for our MVP | Confidence (1-5) |
|---|---|---|---|---|---:|
| 2008 ANN paper | Can nonlinear models improve Himalayan avalanche forecasting? | ANN was already being explored as a meaningful upgrade path. | Nonlinearity is important, but not new. | Supports future-model ambition, but not any claim of novelty or live deployment. | 4 |
| 2011 review paper | What broader model families matter? | GIS, AHP, deterministic, statistical, and numerical approaches all have roles. | No single modelling family solves the full problem. | Supports a co-development roadmap that spans product, geospatial, and science layers. | 3 |
| 2015 calibration paper | How should nearest-neighbour inputs be weighted? | Weighting is an optimization problem with multiple optima; ABC improved HSS. | Parameter weighting and calibration are governance problems, not just modelling details. | Supports release gates, benchmark dashboards, and disciplined evaluation. | 5 |
| 2017 GPU paper | Is calibration cost operationally acceptable? | Sequential calibration was slow enough to justify GPU acceleration by roughly 10x. | Heavy compute can break operational usefulness. | Strongly supports the repo’s batch-first, off-path compute strategy. | 5 |
| 2020 HIM-STRAT | Can snowpack parameter simulation improve prediction? | ANN-simulated snowpack parameters plus stability indexing improved prediction, but still depended on observations and snow stratigraphy. | Weak layers and snowpack memory matter, but autonomy is still hard. | Supports future validation investment while limiting current overclaim. | 5 |
| 2025 feature-selection paper | Which features are really significant? | A much smaller feature set can match or beat larger noisy sets. | Feature sprawl is not a virtue. | Validates concise, disciplined feature design and messaging. | 5 |
| 2025 class-imbalance paper | How should rare avalanche events be modelled? | Class balancing plus POD/PSS-sensitive evaluation materially improve the forecasting setup. | Accuracy alone is misleading. | Supports the repo’s governance-first quality narrative. | 5 |

## International Comparison

| Benchmark body | What they proved | How our proposal compares today | Where we are weaker | Where we may differ if fully developed | Distinctness (1-5) |
|---|---|---|---|---|---:|
| Client Himalayan lineage (2008-2025) | ANN, calibration, feature selection, class imbalance, and snowpack-aware thinking are all already part of the client’s research tradition. | The repo aligns well as a product and systems layer around that lineage. | Current validation depth is shallower than the lineage’s strongest science claims. | Could become the productized, governed operational shell around the lineage’s science. | 4 |
| EAWS Matrix and bulletin structure work | Danger-level assessment can be standardized through explicit stability, frequency, and size logic. | The product already uses `EAWS-style experimental` bulletin framing. | It is not an authority warning service and does not yet prove authority-grade consistency. | Could become a stronger structured presentation layer for regional avalanche outputs. | 3 |
| WMO impact-based warning guidance | Hazard communication should move from “what the hazard is” to “what the hazard will do”. | Expert overlays and runout warnings point in this direction. | No current proof of formal impact-based alert dissemination or authority workflows. | Could differentiate the product if consequence-aware outputs are hardened. | 4 |
| Explainable ML danger models (Switzerland) | ML danger models can provide strong second opinions, with SHAP improving transparency. | The repo is philosophically aligned and more productized on the UX side. | Swiss systems have deeper operational validation and stronger forecast infrastructure. | A sparse-data Himalayan adaptation with stronger public UX could become a distinct contribution. | 3 |
| Critical-layer snowpack validation work | Snowpack simulations are useful only when continuously validated against operationally relevant layers and weak points. | The repo currently offers only partial physics-aware signals and future validation intent. | We do not yet have a real-time critical-layer validation suite. | Co-development with scientists could make this a strong next-stage differentiator. | 3 |
| SAR avalanche mapping literature | SAR can materially improve avalanche activity monitoring, but with real limits in timing, visibility, and coverage. | The repo is honest about current SAR limits and has artifact scaffolding. | Live promoted SAR operations are not there yet. | If the SAR pipeline is validated and governed, the product could bridge remote sensing with public decision support better than most papers do. | 4 |

## Paper-Worthiness And Novelty Assessment

| Question | Verdict | Rating (1-5) | Why |
|---|---|---:|---|
| Is there enough here for an independent engineering or systems paper? | Yes. | 4 | The repo plus the customer/problem framing support a paper on governed sparse-data avalanche decision support, especially if the scope is product-plus-validation design. |
| Is there enough here for a Himalayan co-development methods paper? | Potentially, after pilot work. | 4 | The client publication lineage plus the current product shell make a good base for a jointly validated methods or pilot paper. |
| Is the current work already a groundbreaking avalanche science discovery? | No. | 2 | The science components are evolutionary and integrative rather than novel at the level of core avalanche theory or validated forecasting skill. |
| Is the product/integration design itself distinctive? | Yes. | 4 | The repo’s strongest claim is governed integration under sparse-data conditions, not raw model novelty. |
| Is reproducibility currently a strength? | Moderate. | 3 | The repo is open and structured, but live data pipelines, credentials, and validation datasets still limit full external reproducibility. |
| Is external validation currently a weakness? | Yes. | 4 | Several of the most ambitious claims still need scientist-in-the-loop validation and operational benchmarking. |
| Would publication now create risk? | Yes, but manageable. | 3 | A paper submitted too early could expose gaps between roadmap language and demonstrated operational evidence. |

## Pros And Cons Of Independent Publication

| Pro/con | Why it matters | Severity/benefit (1-5) | Mitigation or amplifier |
|---|---|---:|---|
| Pro: It converts demo work into a peer-reviewable asset. | Helps the customer see the engagement as co-developed science and engineering, not just software delivery. | 5 | Stronger if the scientist team becomes co-author or formal reviewer. |
| Pro: It forces disciplined validation language. | Publication pressure discourages inflated product claims. | 4 | Use the proof tiers and keep current-vs-future boundaries explicit. |
| Pro: It improves credibility for grants, pilots, and agency partnerships. | A paper can support future funding and formal collaboration. | 4 | Stronger if linked to pilot benchmarks and documented evaluation. |
| Pro: The open repo improves transparency. | Reproducible artifacts can distinguish the work from slide-only proposals. | 3 | Stronger if demo-safe docs, scripts, and benchmark descriptions are cleaned up. |
| Con: Validation is not yet deep enough for aggressive claims. | Premature publication could invite criticism that the product promises more than it proves. | 5 | Position it as systems/pilot work, not solved avalanche science. |
| Con: Customer IP and collaboration boundaries may be sensitive. | Independent publication can complicate ownership and future commercialization. | 4 | Agree authorship, data rights, and publication scope before drafting. |
| Con: International prior art is strong. | Overclaiming novelty would be easy to challenge. | 4 | Claim integration novelty and sparse-data product design, not global firsts. |
| Con: Public failure modes become easier to scrutinize. | Reviewers will probe weak layers, SAR gaps, and autonomy limits. | 3 | Use those limitations as explicit study boundaries rather than hiding them. |

## What Is Actually Unique

| Potential uniqueness claim | Verdict | Rating (1-5) | Why |
|---|---|---:|---|
| Proof-tier honesty in customer-facing avalanche product language | Genuinely useful and somewhat distinctive. | 4 | Most novelty here is in disciplined product framing: masking, uncertainty, and proof tiers are built into the demo narrative instead of buried in caveats. |
| Governed sparse-data evidence fusion for avalanche records | Distinctive if validated. | 4 | Weighted ingest and dedupe across news plus field reports is stronger than a generic “crowd + AI” story, but still needs live evidence. |
| Batch-first interactive forecast workspace | Distinctive as product packaging. | 4 | Many studies stop at models or bulletins; this repo already packages stateful forecast interaction. |
| APT-gated masked terrain semantics | Distinctive trust design. | 4 | It addresses a real public-safety communication issue that many systems leave implicit. |
| ANN or sequence modelling for avalanche forecasting | Not unique. | 1 | The client lineage and international research already explored ANN and ML-based forecasting paths. |
| SHAP-based explainability for avalanche danger models | Not unique. | 2 | Swiss literature already established SHAP-based explanation value. |
| SAR avalanche detection itself | Not unique. | 1 | The SAR mapping literature is already extensive. |
| Official warning-service equivalence | Not achieved. | 1 | The product is still an experimental decision-support MVP, not an authority-grade warning service. |

## Top 5 Methodology Explorations Against Prior Art

| Methodology | Current repo status | Closest prior art | Why it matters | Distinctness (1-5) |
|---|---|---|---|---:|
| Batch-first interactive forecast workspace | Live public route | Bulletin-centric operational systems and model-support dashboards | Gives the customer something operationally demonstrable before full science closure. | 4 |
| APT-gated masked terrain plus honesty-first semantics | Live public route | Danger maps, ATES-style terrain communication, and conventional bulletin framing | Reduces false confidence in non-avalanche terrain more directly than many public products. | 4 |
| Governed Groundsource-style news plus field-report ingest | Repo/admin verified | Google Groundsource flood pipeline and incomplete avalanche event registries | Targets one of the hardest Himalayan bottlenecks: missing event records. | 4 |
| SHAP-backed explainability embedded in product UX | Live plus repo/admin verified | Perez-Guillen 2025 and related Swiss explainability work | Turns model rationale into something demo-visible rather than research-only. | 3 |
| MTS-LSTM plus SAR plus promotion-gate roadmap | Shadow/future path | Client ANN/HIM-STRAT lineage, Swiss ML support models, SAR mapping studies | The disciplined gating is stronger than a direct “next-gen AI” claim, but the path is still future-facing. | 4 |
