# Customer Communication And Expectation Matrix

Updated: May 5, 2026

This file converts the earlier proposal-and-response narrative into a compact expectation table. It is intentionally strict about separating:

- what the current MVP can truthfully demo now
- what the repo clearly supports in admin or backend paths
- what remains future co-development direction with the client scientist team

Alignment scale:

- `5` = strongly matched by current MVP/repo proof
- `4` = strong fit with visible caveats
- `3` = partial fit
- `2` = weak fit or mostly directional
- `1` = essentially unaddressed

## Top 15 Customer Expectations

| Rank | Expectation | Customer signal | Current MVP proposition | Alignment (1-5) | Demo framing | Risk if overstated |
|---|---|---|---|---:|---|---|
| 1 | Minimize dependence on human-observed data | “Assume there is no historical data or existing research… rethink an autonomous solution that requires no or minimal human-observed data.” | The repo combines public field reports, offline replay, and a `Groundsource-style` news ingest path to reduce exclusive dependence on manual observations. That direction is consistent with the client’s ANN/HIM-STRAT lineage, but the live MVP remains governed decision support. | 3 | “We reduce manual dependence with governed autonomous evidence loops.” | Claiming this replaces snowpack truth would overstate what the repo can actually verify. |
| 2 | Update quickly as recent data flows in | The customer explicitly asked for a rapidly updating system. | The public app refreshes the latest published batch forecast, and the operator lane exposes jobs for ingestion, labeling, and evaluation. | 3 | “The app reloads the latest published forecast artifact and shows freshness.” | Calling this continuous real-time autonomous retraining would be inaccurate. |
| 3 | Be scientifically robust and operationally implementable | The customer wants something that is both rigorous and usable, not a research toy. | The repo combines batch forecasts, bulletin framing, uncertainty signaling, and operator metrics, while the publication lineage shows the client has already explored ANN and snowpack-simulation approaches beyond the current MVP. | 3 | “This is a physics-aware decision-support MVP with clear operational hooks.” | Saying the science stack is fully closed would outrun current proof. |
| 4 | Do not rely on old historical registries as the main moat | The customer pushed back hard on “improving the candle” with legacy data. | The repo emphasizes fresh forecast artifacts and autonomous evidence ingestion rather than only static registries. | 2 | “We augment history with fresh evidence and current forecast state.” | The repo still contains model-training and historical-governance logic; it is not history-free. |
| 5 | Keep outputs transparent and inspectable | The customer repeatedly pushed for trustworthy, explainable outputs. | The app exposes SHAP-style reasoning, per-cell inspection, and operator provenance surfaces. | 4 | “You can inspect why a cell looks dangerous and what confidence cues accompany it.” | Explainability is not the same as correctness. |
| 6 | Communicate uncertainty explicitly | Forecast users need to know when the system is guessing. | The public UI already surfaces reduced-confidence states, uncertainty counts, and SAR-coverage caveats. | 4 | “We show uncertainty as part of the forecast, not as hidden model metadata.” | Hiding these cues would damage trust; overselling them as full uncertainty quantification would also be misleading. |
| 7 | Work in sparse-data mountain regions | The customer wants an approach that does not collapse outside heavily instrumented regions. | The repo uses region-wide batch products, Open-Meteo-driven inputs, and autonomous evidence augmentation. | 3 | “The design targets data-sparse regions better than a station-only workflow.” | That is still not equivalent to dense local instrumentation or perfect coverage. |
| 8 | Use land- and space-based monitoring where helpful | The customer explicitly mentioned land- and space-based monitoring resources. | The repo includes SAR coverage handling, snow-cover refresh jobs, field reports, and news ingestion. | 3 | “We already combine multiple evidence channels and expose when some are thin.” | The SAR path remains constrained and should not be framed as universal operational coverage. |
| 9 | Govern autonomous evidence before it influences trust | The customer wanted autonomy, but not naive autonomy. | The ingest path uses dedupe, `label_confidence`, `training_weight`, and governed field-report linkage. | 4 | “Autonomous evidence is weighted and filtered before it is treated as useful.” | Calling autonomous ingest “self-validating” would be false. |
| 10 | Provide an operational public forecast format | The customer wants something forecasters and field users can actually read and use. | The app already exposes an `EAWS-style experimental` bulletin layer over the batch forecast grid. | 4 | “The public surface behaves like a forecast workspace, not a raw model console.” | It is still experimental and not an official avalanche warning service product. |
| 11 | Show impact on roads, assets, and field operations | The audience includes safety and mobility stakeholders, not just data scientists. | Expert overlays and runout intersection warnings tie hazard output to roads and mapped assets. | 4 | “We can move from abstract risk to consequence-aware review.” | Coverage is only as good as the available runout and OSM data. |
| 12 | Keep the automation maintainable and cloud-friendly | The customer rejected brittle, heavyweight operational complexity. | The repo uses precomputed artifacts, async job triggers, Supabase-backed surfaces, and admin controls. | 4 | “Heavy lifting happens off the critical UI path; the forecast workspace stays responsive.” | This is maintainable relative to synchronous heavy compute, not a claim of zero ops burden. |
| 13 | Show objective model-quality gates before promotion | The customer asked for something better than subjective “latest AI” claims. | The repo tracks PSS/Brier-oriented gates, candidate shadow status, benchmarks, and evaluation jobs. | 4 | “Candidate models are supposed to earn promotion rather than being marketed into it.” | It would be misleading to imply the shadow candidate is already the active public scorer. |
| 14 | Keep current proof and future co-development visibly separate | The customer explicitly challenged hand-wavy innovation language and will likely ask what comes after MVP. | The refreshed docs now separate `Live demo`, `Repo/admin verified`, `Shadow-gated or config-gated`, and future co-development phases with scientist-team involvement. | 3 | “We can show the delivered forecast workspace and separately describe the co-development roadmap.” | Blurring these layers would weaken credibility fast. |
| 15 | Do not borrow Google- or authority-level validation without avalanche proof | The plan explicitly required softening both Groundsource and official-warning comparisons. | The honest proposition is `Groundsource-style` inspiration for avalanche ingest and `EAWS-style experimental` bulletin framing, not avalanche-domain validation or official-authority status. | 2 | “We can cite Google, EAWS, and WMO as reference points, not as proof transfers.” | Claiming Google-equivalent or authority-equivalent validation would be an avoidable overclaim. |

## Communication Rules For Demos

- Lead with the forecast workspace, bulletin framing, uncertainty cues, share/export, reporting, and expert overlays.
- Describe the autonomous ingest path as `Groundsource-style` and governed, not as a solved avalanche truth engine.
- When the autonomy question comes up, cite the 2008-2025 ANN/HIM-STRAT lineage as research continuity, then immediately separate it from the current batch-first MVP.
- Describe the MTS-LSTM path as a candidate shadow path unless promotion gates are actually passed and activated.
- Use `EAWS-style experimental` exactly as written in the app; do not say the product is an official EAWS bulletin.
- Keep “current proof”, “repo/admin capability”, and “future co-development path” visibly separate in every customer-facing artifact.

## How To Answer “What Happens After MVP?”

| Horizon | Honest answer | Why this is the safe framing |
|---|---|---|
| 0-3 months | Harden the current batch-first MVP, verify operator workflows, and align the demo narrative with proof-tier truth. | This is strongly grounded in the current repo and avoids speculative science claims. |
| 3-9 months | Run a scientist-in-the-loop pilot around governed event ingest, evaluation cadence, and validation review. | This fits the customer’s co-development posture without pretending autonomy is already solved. |
| 9-18 months | Expand into remote-sensing promotion, shadow-model evaluation, and stronger consequence workflows if the validation evidence is good enough. | This turns future science into earned roadmap steps rather than premature claims. |
