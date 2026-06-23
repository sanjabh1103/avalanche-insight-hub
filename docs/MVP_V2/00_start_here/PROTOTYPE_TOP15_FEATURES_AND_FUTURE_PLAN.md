# Prototype Website - Top 15 Current Features And Future Plan

Status: 2026-06-21 (claim wording locked)
Purpose: short scientist-facing attachment for first discussion
Boundary: this is a prototype / decision-support summary, not an operational avalanche warning claim

## Locked Claim Wording (Do Not Alter In Demo)

The following phrases are the only approved wording for public-facing claims about the prototype. Any deviation requires scientist review.

- **What it is:** "Hosted decision-support prototype rendering published Colorado technical artifacts."
- **What it is NOT:** "Not an official warning service. Not Himalayan operational accuracy proof."
- **Forecast data:** "Precomputed batch artifacts loaded from storage on demand."
- **Grid metadata:** "20x20 grid with N/h hours loaded out of a H-hour horizon."
- **Explainability:** "TreeSHAP contributions when the surrogate artifact is present; heuristic fallback shown honestly otherwise."
- **Uncertainty:** "Confidence state and uncertainty class are surfaced from the artifact; they are review signals, not guarantees."
- **Share links:** "Shared links preserve review context (region, hour, cell, expert mode, 3D); they do not imply scientific acceptance."
- **Weather summary:** "Weather values are from Open-Meteo with units displayed once; proxy snowpack context is not weak-layer validation."
- **Bulletin:** "EAWS-style experimental bulletin for discussion; not an official avalanche warning."

## How To Frame This Attachment

Avalanche Insight Hub is best presented as a working prototype for scientist-led discussion. It already demonstrates the product direction, evidence surfaces, forecast publication mechanics, and review workflow. It does not yet prove Himalayan operational accuracy, and it is not an official warning service.

The future plan is to move from a Colorado live technical proof and research-only evidence lanes toward a Himalayan pilot only after local partner evidence, scientist validation, release gates, and holdout checks pass.

## Top 15 Features And Future Plans

| # | Current prototype feature | What exists today | Future plan | Claim boundary |
|---:|---|---|---|---|
| 1 | Public avalanche forecast workspace | Public route `/` presents a forecast map, bulletin-style summary, time controls, selected-cell details, share, export, and report workflows. | Convert the same workflow into a Himalayan pilot workspace after local evidence and region wiring pass. | Technical decision-support prototype, not official warning authority. |
| 2 | Published batch forecast artifacts | The website loads precomputed forecast artifacts instead of running heavy computation in the browser. Current proof geography is Colorado Rockies. | Publish Himalayan pilot artifacts only after partner data, validation, and release-gate approval. | Colorado live proof does not prove Himalayan accuracy. |
| 3 | 20x20 grid and 72-hour review pattern | The current proof surface supports grid-cell forecast review and multi-hour navigation. | Extend to locally agreed Himalayan grid size, forecast windows, warning regions, and elevation bands. | Grid display is review evidence, not slope-specific safety advice. |
| 4 | EAWS-style experimental bulletin | The UI presents danger level, avalanche problem, critical elevation/aspect context, and peak-window style information. | Align bulletin fields with scientist-approved local terminology and warning-region policy. | Experimental framing only until approved by scientists. |
| 5 | Interactive map and time slider | Users can inspect map cells across forecast hours and see state changes over time. | Add Himalayan pilot bounds, local basemaps if needed, and region-specific map presets. | Map output must stay caveated until local validation is complete. |
| 6 | Cell-level risk inspection | Selected cells show risk level, probability, hazard, exposure, vulnerability, problem type, model versions, and driver context. | Add scientist-approved thresholds, local features, and disagreement notes from daily verification. | Cell output is a discussion artifact, not field instruction. |
| 7 | Terrain and snow/public eligibility masking | The app distinguishes masked or unavailable terrain from normal danger classes, reducing false low-risk messaging. | Tune terrain masks with Himalayan DEM, elevation, ATES/runout evidence, and local scientist review. | Masking reduces overconfidence but still needs local field validation. |
| 8 | Uncertainty and reduced-confidence cues | The UI surfaces confidence interval, uncertainty class, stale/partial/unavailable states, and reduced-confidence labels where data is weak. | Add calibrated uncertainty from local holdout results and scientist-vs-model disagreement metrics. | Uncertainty is a review signal, not a guarantee. |
| 9 | Weather summary and snowpack proxy context | The risk panel can show weather summary and proxy snowpack context when artifact fields exist. | Replace proxy-level evidence with partner-reviewed snowpack, weak-layer, SNOWPACK/HIM-STRAT-like features where available. | Current proxy context is not weak-layer validation. |
| 10 | Explainability and risk-driver display | The app can display TreeSHAP-style or fallback risk-driver explanations, with artifact-origin caveats. | Tie each live artifact to active explainability metadata and add scientist-facing model reasoning review. | Explanation path must be verified per artifact before claiming active TreeSHAP. |
| 11 | Historical events and field-report evidence | The app supports avalanche event context and field-report workflows, with governance before training use. | Use partner-confirmed Himalayan events and scientist-reviewed field observations as validation evidence. | Raw reports are evidence inputs, not automatic truth. |
| 12 | Shareable forecast links | Users can copy a link preserving region, forecast hour, selected cell, expert mode, and 3D view state. | Use controlled shared links for scientist review sessions and pilot-region walkthroughs. | Shared link proves review context, not scientific acceptance. |
| 13 | CSV and JSON forecast export | Forecast cells, probabilities, uncertainty fields, problem type, and selected evidence can be exported from loaded artifacts. | Extend exports into partner-review packets and audit-ready evidence bundles. | Export reflects loaded artifact fields only. |
| 14 | Admin/operator control and observability | `/admin` supports job controls, model status, source health, evaluation metrics, publication traces, and candidate workflow visibility. | Harden into a release-control cockpit with explicit promotion blocks, source-health attestations, and audit history. | Admin evidence does not equal production approval. |
| 15 | Scientist validation and daily verification lane | `/scientist` and `/scientist/daily-verification` support role-gated review, paired scientist-vs-model comparison, verdicts, notes, and exportable evidence. | Make this the core co-working workflow for Himalayan validation, including D_tidy-style label review, model-disagreement analysis, and release-gate signoff. | Scientist review informs decisions; it does not automatically retrain or promote models. |

## Near-Term Future Plan

| Phase | Practical next step | Output expected |
|---|---|---|
| 1 | First scientist discussion | Confirm whether the prototype direction is worth exploring and which pilot region, if any, is suitable. |
| 2 | Autonomous pipeline activation | Activate news + SAR + weather pipeline for selected Himalayan region. Optional: scientist-reviewed local data can augment the autonomous pipeline if available. |
| 3 | Himalayan research validation | Run local validation only after evidence passes source, license, quality, and leakage checks. |
| 4 | Scientist co-working review | Use the scientist workspace and daily verification lane to classify errors, label quality, and model disagreement. |
| 5 | Release decision | Continue, narrow, pause, or stop based on measured local evidence and named scientist signoff. |

## Safe One-Line Summary

The prototype is strong enough to show a credible decision-support direction and co-working model, but Himalayan operational prediction claims should wait until local reviewed evidence and scientist validation gates pass.
