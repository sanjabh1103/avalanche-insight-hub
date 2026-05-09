# Appendix: References And Supporting Notes

Updated: May 7, 2026

This appendix lists the official standards pages, primary papers, and evidence framing used in the two presentations. It is intended to support the discussion without turning the slides into a literature review.

## Evidence Framing Used In The Decks

| Label | Meaning |
|---|---|
| `Live platform` | Directly visible on the hosted Avalanche Insight Hub platform as reviewed on May 7, 2026. |
| `Validated internal evidence` | Evidence reviewed from authenticated platform surfaces, benchmark tables, stability summaries, manifests, and curated internal analysis. |
| `Research next phase` | Work that is structurally planned and scientifically relevant, but still requires further qualification, validation, or benchmark ownership. |

## Current Official And Primary Sources

These are the external references that should anchor the presentation whenever a standards or literature reference is needed.

| Topic | Current official or primary source | Why it matters to the deck | Link or DOI | Accessed |
|---|---|---|---|---|
| EAWS Matrix | EAWS standards page | Grounds the structured bulletin and danger-assessment framing in the current official reference. | [EAWS Matrix](https://www.avalanches.org/standards/eaws-matrix/) | `2026-05-07` |
| EAWS Workflow | EAWS workflow page | Grounds the multi-problem, stability-frequency-size workflow logic. | [EAWS Workflow](https://www.avalanches.org/standards/workflow-to-determine-the-avalanche-danger-level/) | `2026-05-07` |
| WMO impact-based guidance | WMO IBFWS page plus WMO guidelines | Grounds consequence-aware communication without implying authority transfer. | [WMO IBFWS](https://wmo.int/impact-based-forecast-and-warning-services), [WMO Guidelines PDF](https://etrp.wmo.int/pluginfile.php/16270/mod_resource/content/0/wmo_1150_en.pdf) | `2026-05-07` |
| Avalanche ML explainability | NHESS 2025 paper | Grounds the `second opinion` framing and the persistent weak-layer caution. | [doi:10.5194/nhess-25-1331-2025](https://doi.org/10.5194/nhess-25-1331-2025) | `2026-05-07` |
| Critical-layer validation | NHESS 2024 paper | Grounds the claim that snowpack simulation support still needs operational validation and scientist review. | [doi:10.5194/nhess-24-2727-2024](https://doi.org/10.5194/nhess-24-2727-2024) | `2026-05-07` |
| SAR mapping limitations | NHESS 2020 and TC 2021 | Grounds the SAR qualification caveats: dry-snow misses, timing loss, and geometric limits. | [doi:10.5194/nhess-20-1783-2020](https://doi.org/10.5194/nhess-20-1783-2020), [TC 2021](https://tc.copernicus.org/articles/15/983/2021/) | `2026-05-07` |

## Safe Quote Bank

Use these mostly in speaker notes or sparingly on slides. Keep each quote subordinate to the live platform review, the validated internal evidence, and the research-next-phase boundaries.

| Source | Exact short quote | Suggested use | Link or DOI | Accessed |
|---|---|---|---|---|
| EAWS Matrix | “snowpack stability, frequency distribution of snowpack stability and avalanche size” | Supports the structured bulletin and danger-assessment framing. | [EAWS Matrix](https://www.avalanches.org/standards/eaws-matrix/) | `2026-05-07` |
| EAWS Workflow | “All relevant avalanche problems must be considered” | Supports the slide about why avalanche forecasting cannot be reduced to one score. | [EAWS Workflow](https://www.avalanches.org/standards/workflow-to-determine-the-avalanche-danger-level/) | `2026-05-07` |
| WMO IBFWS | “WHAT THE WEATHER WILL DO” | Supports consequence-aware communication rather than model-only narration. | [WMO IBFWS](https://wmo.int/impact-based-forecast-and-warning-services) | `2026-05-07` |
| NHESS 2025 | “transparent ‘second opinions’” | Supports the bounded role of machine learning in the presentation. | [doi:10.5194/nhess-25-1331-2025](https://doi.org/10.5194/nhess-25-1331-2025) | `2026-05-07` |
| NHESS 2024 | “valuable starting point for targeted field observations” | Supports the claim that critical-layer support is useful but not self-validating. | [doi:10.5194/nhess-24-2727-2024](https://doi.org/10.5194/nhess-24-2727-2024) | `2026-05-07` |
| NHESS 2020 | “many dry-snow avalanches were missed” | Supports the SAR dry-snow detectability caveat. | [doi:10.5194/nhess-20-1783-2020](https://doi.org/10.5194/nhess-20-1783-2020) | `2026-05-07` |

## Research Lineage References

| Publication | Why it matters | Best use in the decks |
|---|---|---|
| 2008 ANN paper | Shows nonlinear avalanche forecasting is already part of the client’s history. | Deck 1 slides `3-4` |
| 2015 calibration and weighting paper | Supports the calibration ambiguity, weighting discipline, and release-gate story. | Deck 1 slide `4`; Deck 2 slide `8` |
| 2017 GPU acceleration paper | Supports the claim that heavy compute belongs off the critical user path. | Deck 1 slides `10-12`; Deck 2 slide `14` |
| 2020 HIM-STRAT | Supports the snowpack-memory and weak-layer relevance story. | Deck 1 slide `4`; Deck 2 slide `7` |
| 2025 feature-selection paper | Supports feature discipline over feature sprawl. | Deck 1 slide `4`; Deck 2 slide `12` |
| 2025 class-imbalance paper | Supports rare-event evaluation, benchmark discipline, and release gates. | Deck 1 slide `4`; Deck 2 slides `5-8` |

## Citation Rules

- Put most external references in speaker notes, not on dense slides.
- Use quotes only when they strengthen one specific point; otherwise paraphrase and keep the link in notes.
- Keep every statement anchored to one of the three visible evidence labels: `Live platform`, `Validated internal evidence`, or `Research next phase`.
- Do not present candidate-model pathways, future GPU opportunities, or qualification hypotheses as current live-platform proof.
- Keep horizon wording route-derived and never hard-code `72h` unless the current hosted screenshot visibly proves it.
- If a slide stands on platform review or validated internal evidence alone, prefer that over unnecessary literature density.
