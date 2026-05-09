# Avalanche Demo Research Pack — Research Base

Updated: May 7, 2026

This file is the research base behind the demo-decision pack. It keeps the evidence tied to the repo questions that matter most:

- what the client has already researched in the Himalaya
- what recent international avalanche work now proves or cautions
- which parts of our MVP are well aligned, only partially aligned, or still ahead of the evidence

Deck-source note: use this file for research lineage, customer-science context, and blocked-claim grounding. It does not prove current hosted functionality on its own.

## Anchor Papers

| Paper | Region | Main problem | Key findings | Customer implication | Link |
|---|---|---|---|---|---|
| Kaushik et al. (2025), *Selection of Significant Features for Snow Avalanche Forecasting* | Bandipore-Gurez, Indian Himalaya | Too many noisy or redundant inputs can slow learning and hurt generalization. | SVM-RFE reduced a 40-feature set to roughly 7-15 meaningful features; rainfall, fresh snow, seasonal snow, temperature, wind, sunshine, and 2-3 day lag effects mattered most. | A credible avalanche MVP should not market feature sprawl as sophistication. Tight feature discipline is a strength, not a weakness. | https://doi.org/10.1007/s10666-025-10061-x |
| Kala et al. (2025), *Addressing class imbalance in avalanche forecasting* | Two Indian Himalayan regions | Avalanche days are rare, and naive classifiers overfit the majority non-avalanche class. | Class-balancing techniques improved POD and PSS; the paper also stresses that incomplete occurrence records are one reason imbalance is so damaging. | Customers need to hear about governance, detection rates, and failure modes, not just headline accuracy. | https://doi.org/10.1016/j.coldregions.2024.104411 |
| Mayer et al. (2023), *Prediction of natural dry-snow avalanche activity using physics-based snowpack simulations* | Swiss Alps | New snow alone is not enough; weak layers and snow stratigraphy matter. | Physics-based snowpack simulations outperformed a simple 3 d new-snow benchmark, and the combined signal performed best. | A usable avalanche product needs some physics-aware framing; pure weather or pure media mining is not enough. | https://nhess.copernicus.org/articles/23/3445/2023/ |

## Client Publication Lineage (2008–2025)

| Paper | Region | Main contribution | Why it still matters now | Link |
|---|---|---|---|---|
| Singh and Ganju (2008), *Artificial Neural Networks for Snow Avalanche Forecasting in Indian Himalaya* | Chowkibal-Tangdhar, Indian Himalaya | Explored ANN as a nonlinear upgrade around older nearest-neighbour-style Himalayan forecasting. | Shows that autonomous or nonlinear modeling is a long-running client direction, but not proof that the repo's current shadow-model path is live. | [Local PDF](</Users/sanjayb/avalanche-insight-hub/docs/publications/2008 _ 12th IACMAG__F08.pdf>) |
| *Emerging Trends in Snow Avalanche Modeling* (2011 review) | Review paper with Himalayan relevance | Surveyed broader modelling families, including deterministic, statistical, numerical, GIS, and AHP-style approaches. | Useful as lineage evidence that the client's research line was already wider than one model family, but not strong enough for narrow benchmark claims. | [Local PDF](</Users/sanjayb/avalanche-insight-hub/docs/publications/2011 _ GeoSpatial World Forum.pdf>) |
| Singh et al. (2015), *Calibration of nearest neighbors model for avalanche forecasting* | Two Indian Himalayan regions | Showed that weighting snow-meteorological variables is an optimization problem with multiple optima; ABC improved Heidke skill score. | Strengthens the case that subjective weighting, calibration ambiguity, and governance are not abstract issues in Himalayan forecasting. | [Local PDF](</Users/sanjayb/avalanche-insight-hub/docs/publications/2015 _ 1-s2.0-S0165232X14001694-main.pdf>); https://doi.org/10.1016/j.coldregions.2014.09.009 |
| Singh et al. (2017), *A novel approach to accelerate calibration process of a k-nearest neighbours classifier using GPU* | Indian Himalayan calibration workflow | Showed that repeated k-NN calibration required thousands of HSS evaluations, took over 400 minutes sequentially, and benefited from roughly 10x GPU acceleration. | Supports the MVP's batch-first posture and the claim that heavy calibration and compute should stay off the critical user path. | [Local PDF](</Users/sanjayb/avalanche-insight-hub/docs/publications/2017 _ 1-s2.0-S0743731517300096-main.pdf>); https://doi.org/10.1016/j.jpdc.2017.01.003 |
| Joshi et al. (2020), *HIM-STRAT* | North-West Himalaya | Combined ANN-based simulation of snowpack parameters with a snow stability index for avalanche prediction. | Strengthens the snowpack-memory argument while also showing that the client's strongest Himalayan ANN lineage still depended on weather and snow stratigraphy observations. | [Local PDF](</Users/sanjayb/avalanche-insight-hub/docs/publications/2020 _ 10.1007_s11069-020-04032-6 _ HIM-STRAT.pdf>); https://doi.org/10.1007/s11069-020-04032-6 |
| Kaushik et al. (2025), *Selection of Significant Features for Snow Avalanche Forecasting* | Bandipore-Gurez, Indian Himalaya | Demonstrated modern feature selection discipline in the same client-domain context. | Reinforces that the strongest near-term science opportunity is disciplined features plus governed evaluation, not feature sprawl. | [Local PDF](</Users/sanjayb/avalanche-insight-hub/docs/publications/2025 _ 10.1007_s10666-025-10061-x.pdf>); https://doi.org/10.1007/s10666-025-10061-x |
| Kala et al. (2025), *Addressing class imbalance in avalanche forecasting* | Two Indian Himalayan regions | Quantified the importance of class balancing, POD, and PSS in the client's domain. | Confirms that rare-event evaluation must stay central in every customer-facing claim about model quality. | [Local PDF](</Users/sanjayb/avalanche-insight-hub/docs/publications/2025 _ manish kala _ crst.pdf>); https://doi.org/10.1016/j.coldregions.2024.104411 |

## Top 15 Synthesized Research Takeaways

| Rank | Research takeaway | Main source(s) | Why it matters to the current MVP |
|---|---|---|---|
| 1 | Sparse observations are still the core autonomy bottleneck. | Kala 2025; Joshi et al. 2020; Herla 2024 | The MVP can reduce manual dependence, but it should not claim it has eliminated ground-truth scarcity. |
| 2 | Nonlinear avalanche modeling is not new in this client context. | Singh and Ganju 2008 | The repo's shadow LSTM path is directionally consistent with the client's research history, not a sudden scientific breakthrough. |
| 3 | The client's research lineage has never been limited to one model family. | GeoSpatial review 2011 | Supports a broad co-development conversation spanning GIS, statistical, and physics-aware methods. |
| 4 | Variable weighting is a genuine optimization problem, not a tuning footnote. | Singh et al. 2015 | Reinforces the need for release gates and defensible evaluation rather than subjective parameter choice. |
| 5 | Calibration ambiguity can produce multiple plausible optima. | Singh et al. 2015 | Weakens any claim that one scoring chain is obviously correct without rolling evaluation. |
| 6 | Heavy calibration and training cost are part of the avalanche-forecasting problem. | Singh et al. 2017 | Justifies batch-first delivery and off-path compute rather than synchronous user-triggered science runs. |
| 7 | Weak layers and snowpack memory matter more than simple snowfall totals. | Mayer 2023; Joshi et al. 2020 | Any future autonomy story must still address snowpack structure and persistent weak layers. |
| 8 | Feature discipline beats feature sprawl. | Kaushik 2025 | Makes concise feature engineering a strength, not a missing piece. |
| 9 | Class imbalance must be handled with rare-event-aware metrics. | Kala 2025 | Supports PSS, Brier, ECE, and POD-style evaluation language over generic accuracy claims. |
| 10 | Missing avalanche-occurrence records weaken both training and validation. | Kala 2025; Groundsource blog 2026 | Strengthens the case for governed ingest, but also for caution in any autonomy claim. |
| 11 | Explainability is now practical enough to be operationally useful. | Perez-Guillen 2025 | Validates the repo's SHAP-first trust posture. |
| 12 | Model-based forecasts are approaching, but not surpassing, human operational usefulness. | Techel et al. 2025 | Supports a "second opinion plus operator workflow" story rather than a forecaster-replacement story. |
| 13 | Snowpack simulations help, but should not run unvalidated as stand-alone truth. | Herla 2024 | Strengthens the case for a future scientist-in-the-loop validation suite. |
| 14 | SAR mapping is a useful complement, not a solved universal truth source. | Leinss et al. 2020 | Supports coverage signaling and future remote-sensing work, but weakens overclaiming around current SAR maturity. |
| 15 | Bulletin structure and impact framing matter as much as raw model skill. | EAWS Matrix 2025; WMO IBFWS | Supports the repo's bulletin-layer, consequence-aware, honesty-first UX direction. |

## Cross-Paper Themes

| Cross-paper theme | Evidence summary | Why it matters to our MVP |
|---|---|---|
| Observation scarcity is still the core bottleneck | Kaushik and Kala both describe sparse, delayed, or dangerous observation pipelines; Herla and Mayer show why richer physical state still matters. | Autonomous ingest helps, but the MVP should not pretend it has solved snow-truth collection. |
| Rare-event handling is non-negotiable | Kala shows why POD, PSS, balanced accuracy, and class-balancing matter more than raw accuracy for avalanche forecasting. | Repo claims should focus on governed evaluation loops, not generic “AI accuracy” language. |
| Feature discipline beats feature sprawl | Kaushik shows that carefully selected 7-15 features can match or beat a much larger input set. | The MVP should frame optimization and selection as rigor, not as missing sophistication. |
| Snowpack memory and weak layers matter | Mayer and HIM-STRAT both show that snowpack structure materially changes forecast quality. | Snowpack proxies, runout logic, and shadow-model gating are directionally correct, but the repo should not oversell them as finished science. |
| Operational Himalayan forecasting has long been constrained by calibration burden, compute cost, and observation dependence | The 2015 paper shows multiple optima in NN calibration, the 2017 paper shows calibration cost severe enough to require GPU acceleration, and HIM-STRAT still depended on weather plus snow stratigraphy inputs. | This supports the repo's batch-first and operator-governed posture and cautions against selling full autonomy as already solved. |
| Human-plus-model workflows remain the international norm | Recent Swiss and Canadian work shows model support getting stronger, but still inside expert workflows and validation loops. | The strongest honest product story is "decision support with governance", not "AI replaces avalanche forecasters". |
| Explainability has to be part of the product | The more operational a model becomes, the more important it is to show why a slope or daypart is dangerous. | SHAP, problem framing, and operator provenance are not “nice to have”; they are trust infrastructure. |
| Impact communication and accepted warning structure matter | EAWS and WMO both show that structured, actionable warning communication is part of system quality, not a cosmetic wrapper. | Batch artifacts, bulletin formatting, consequence overlays, and future alert packaging are real product requirements. |
| Remote sensing is useful, but incomplete | SAR mapping studies show strong complement value but also real limits around timing, visibility, and dry-snow detection. | The repo is right to surface coverage caveats; it would be wrong to claim solved SAR operations. |

## International Benchmarks And External Validation

| Source | What it adds | Why it matters to our MVP | Link |
|---|---|---|---|
| Perez-Guillen et al. (2025), *Assessing the performance and explainability of an avalanche danger forecast model* | Shows that a data-driven avalanche model can function as a reliable second opinion and that SHAP can reduce the black-box problem. | Supports the repo’s explainability and operator-provenance posture, but also reinforces that such models complement rather than replace forecasters. | https://nhess.copernicus.org/articles/25/1331/2025/index.html |
| Latosuo et al. (ISSW 2024), *Users' awareness and response to uncertainty information in public avalanche forecasts* | Found that explicit uncertainty statements change user decisions and can increase trust in forecast centers. | Validates the repo’s reduced-confidence, uncertainty, and evidence-quality messaging. | https://arc.lib.montana.edu/snow-science/item/3360 |
| Techel et al. (2025), *Can model-based avalanche forecasts match the discriminatory skill of human danger-level forecasts?* | Shows that model-driven forecasts are approaching operational usefulness, but human forecasts still retain a small edge. | Weakens any aggressive “fully autonomous forecaster replacement” narrative. | https://nhess.copernicus.org/articles/25/3333/2025/ |
| Herla et al. (2024), *A large-scale validation of snowpack simulations in support of avalanche forecasting focusing on critical layers* | Shows that snowpack simulations can be valuable, but are not yet reliable enough to generate forecasts on their own without validation suites. | Supports a future scientist-in-the-loop validation path and cautions against overclaiming physics completeness. | https://nhess.copernicus.org/articles/24/2727/2024/nhess-24-2727-2024.html |
| Leinss et al. (2020), *Snow avalanche detection and mapping in multitemporal and multiorbital radar images* | Shows that radar mapping can be operationally helpful but still misses parts of avalanches, timing precision, and some dry-snow signals. | Supports remote-sensing ambition while keeping current SAR claims conservative. | https://nhess.copernicus.org/articles/20/1783/2020/index.html |
| EAWS Matrix (updated 06/2025) | Defines a more objective, standardized way to determine avalanche danger levels from stability, frequency distribution, and avalanche size. | Supports the repo’s `EAWS-style experimental` framing, but does not justify claiming official EAWS equivalence. | https://www.avalanches.org/standards/eaws-matrix/ |
| WMO impact-based forecast and warning services guidance | Emphasizes moving from hazard-only statements to actionable impact communication. | Validates the direction of consequence overlays and future alert packaging, but not current operational-authority status. | https://wmo.int/impact-based-forecast-and-warning-services |
| Google Research blog (2026), *Introducing Groundsource* | Introduces a Gemini-based flood methodology that turns global news into structured historical disaster data and explicitly notes that the method may be adaptable to other hazards. | Useful as inspiration for a `Groundsource-style` avalanche ingest loop, but it is flood-domain validation, not avalanche-domain validation. | https://research.google/blog/introducing-groundsource-turning-news-reports-into-data-with-gemini/ |

## Source Shorthand Used In The Other Docs

- `Kaushik 2025` = feature selection and redundancy discipline in the Indian Himalaya
- `Kala 2025` = class imbalance, rare-event evaluation, and occurrence-record gaps
- `Mayer 2023` = physics-based snowpack simulations and weak-layer importance
- `Singh and Ganju 2008` = early ANN lineage in Himalayan avalanche forecasting
- `GeoSpatial review 2011` = review-level survey of broader avalanche model families, including GIS/AHP approaches
- `Singh et al. 2015` = k-NN calibration, weighting burden, multiple optima, and HSS-focused tuning
- `Singh et al. 2017` = GPU acceleration for expensive k-NN calibration workflows
- `Joshi et al. 2020` = HIM-STRAT snowpack parameter simulation plus stability-index-driven Himalayan prediction
- `Perez-Guillen 2025` = explainability and data-driven avalanche danger forecasting
- `Techel et al. 2025` = human-vs-model discriminatory skill benchmark from Switzerland
- `Herla 2024` = critical-layer simulation validation and the need for real-time validation suites
- `Leinss et al. 2020` = SAR avalanche mapping value and limitations
- `ISSW Uncertainty 2024` = explicit uncertainty communication improves trust and affects behavior
- `EAWS Matrix 2025` = accepted matrix logic for danger-scale and bulletin framing
- `WMO IBFWS` = impact-based warning communication benchmark
- `Groundsource blog 2026` = flood-domain news-to-data methodology, relevant only as inspiration
