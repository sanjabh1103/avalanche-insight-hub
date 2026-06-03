# ML-Focused Understand Anything Deck Addendum

Status: 2026-05-29

This addendum reviews the NotebookLM slide-maker draft for the ML-focused
Understand Anything deck. The draft is directionally useful, but it needs a
scientific and product-governance tightening pass before it is treated as the
preferred client/scientist deck language.

The addendum has two purposes:

1. Tighten the deck language so the presentation stays technically impressive
   without overstating scientific certainty.
2. Convert the same review into a web-app and ML implementation backlog that
   moves Avalanche Insight Hub faster toward high-quality Himalayan avalanche
   prediction.

## Claim Boundary

Use these boundaries in every deck, source packet, UI brief, and client
conversation:

- `production_scoring_allowed=false`
- `himalayan_accuracy_claim_allowed=false`
- SAR remains shadow-only until SnowSlide, fresh final holdout, and promotion
  gates pass.
- Swiss and European research improves method discipline; it does not prove
  Himalayan performance.
- The current Himalayan partner evidence workflow is CSV, source-manifest, and
  CLI based, with partial scientist UI support only.
- Deck QA and viewport QA prove presentation quality; they do not prove model
  skill.

## Research Anchors

| Anchor | Why It Matters For The Deck |
|---|---|
| [GMD 2024 RAvaFcast](https://gmd.copernicus.org/articles/17/7569/2024/) | Avalanche danger prediction should be framed as a pipeline: classification, spatial interpolation, and elevation/region aggregation. Station density and GP uncertainty matter. |
| [NHESS 2022 RF danger-level study](https://nhess.copernicus.org/articles/22/2031/2022/) | Raw forecast labels and quality-controlled `D_tidy` labels are different. Himalayan partner labels need provenance, review basis, and evidence references. |
| [EAWS danger scale](https://www.avalanches.org/standards/avalanche-danger-scale/) | The 1-5 danger scale is a shared vocabulary, but local warning regions and interpretation still need evidence and review. |
| [The Cryosphere 2024 SAR mapping](https://tc.copernicus.org/articles/18/2809/2024/) | Sentinel-1 avalanche mapping is valuable but sensitive to transferability, wet snow, small-event misses, shadow, and layover. |
| [AvalCD benchmark](https://arxiv.org/abs/2603.22658) | SAR change-detection benchmarks are useful for method comparison, not automatic public scoring approval. |
| [Avalanche forecast verification scale caveats](https://www.cambridge.org/core/journals/annals-of-glaciology/article/predictions-in-avalanche-forecasting/FA43C586CB1C6A2A8D0840D5A1CA3CB5) | Forecast verification depends on spatial and temporal scale; a map cell must not be read as slope-level safety clearance. |
| [DRDO avalanche warning bulletins](https://www.drdo.gov.in/drdo/en/documents/avalanche-warning-bulletin?page=0) | Himalayan public bulletins are relevant operational context, but not sufficient as quality-controlled training truth without partner review. |
| [Google Nano Banana Pro](https://blog.google/innovation-and-ai/products/nano-banana-pro/) and [Google Workspace rollout](https://workspaceupdates.googleblog.com/2025/11/workspace-nano-banana-pro.html) | Nano Banana Pro is useful for high-quality explanatory diagrams in Slides and NotebookLM, but generated visuals must stay clearly labeled as teaching assets, not evidence. |
| [Gemini API image generation docs](https://ai.google.dev/gemini-api/docs/image-generation) | Current image-generation model names may differ by surface; deck prompts should request Nano Banana Pro where exposed and otherwise use the current available Nano Banana-family image model. |
| Current scikit-learn calibration guidance | Calibration should be evaluated with reliability curves and Brier/ECE-style metrics; isotonic calibration can overfit with too little calibration data. |

## Adversarial Corrections To NotebookLM Slide Maker Output

| # | Improvement / Change | Why It Matters | Slide Priority /5 | Addendum Action |
|---:|---|---|---:|---|
| 1 | Replace "cryptographically enforced data boundary" | The repo has SHA-256 partner checksum workflow, but claim locks are governance and programmatic controls, not cryptographic enforcement. | 5 | Reword as "programmatic claim locks plus checksum-backed source provenance." |
| 2 | Replace "immutable ledger" language | Supabase/Postgres is an auditable operational ledger. Immutability is not proven unless append-only and audit constraints are shown. | 5 | Use "auditable database ledger" and show what is stored, reviewed, and exported. |
| 3 | Make `D_tidy` label quality a headline | Raw forecasts can carry human label noise. Local Himalayan truth needs nowcast, observer, event, or reviewed reanalysis evidence. | 5 | Add a slide/sidebar: "Raw public bulletins are input context, not training truth." |
| 4 | Add spatial-scale caveat | Avalanche verification varies across synoptic, regional, and slope scales. A UI grid can be misread as slope-specific safety advice. | 5 | Add "regional decision support, not slope-specific safety clearance." |
| 5 | Strengthen uncertainty story | Calibrated probabilities and GPxyz should surface uncertainty, not just danger classes. | 5 | Add uncertainty cards: calibration quality, GP posterior uncertainty, SAR scene-transfer uncertainty. |
| 6 | Soften "enterprise" and owl-quote tone | Scientist audiences may read cinematic phrasing as sales language or overclaim. | 4 | Keep executive polish but remove grand claims; make notes evidence-first and source-grounded. |
| 7 | Add UI-not-complete warning | The repo has `/scientist` and `/scientist/daily-verification`, but partner evidence intake is still file/CLI based. | 5 | Add explicit "UI partial today" badge on database, handoff, and roadmap slides. |
| 8 | Add Colorado-to-Himalaya boundary | Colorado is the current live technical proof surface. It is not Himalayan validation. | 5 | Add one callout: "Colorado proves route/publication mechanics; Himalaya needs local evidence gates." |
| 9 | Clarify SAR as shadow-only | SAR evidence is valuable, but heldout gates, precision/F1/FPR floors, and scene transfer remain blockers. | 5 | Keep SAR slide but add FPR/precision/F1 gate language and "fresh final holdout required." |
| 10 | Add source/license governance | Partner data and imagery sharing need source, license, checksum, and review identifiers before external use. | 4 | Add source manifest, checksum, license scope, review ID, and imagery-sharing status to artifact slide. |
| 11 | Add model-vs-scientist verification | Existing daily verification captures paired model/scientist danger levels, but the deck should identify stronger future metrics. | 4 | Add future metric note: discrimination, calibration, outcome-linked skill, false-alarm/miss review, disagreement queue. |
| 12 | Add deck QA vs science QA distinction | NotebookLM, PDF, and viewport checks prove the deck is usable. They do not prove forecast skill. | 5 | Keep Slide 13 but add a visible "presentation QA is not model validation" warning. |
| 13 | Teach the three-stage danger pipeline | Beginners need a stable mental model: classify danger, interpolate across space, then aggregate by elevation and warning region. | 5 | Add a dedicated pipeline explanation and map partner evidence fields to each stage. |
| 14 | Add Nano Banana Pro visual guidance | The slide-maker can create strong visuals, but model names and availability vary across NotebookLM, Slides, and API surfaces. | 4 | Request Nano Banana Pro where exposed, allow the current Nano Banana-family fallback, and keep generated visuals labeled as explanatory. |
| 15 | Use function-specific color palettes | A single cinematic palette makes complex evidence lanes harder to distinguish. | 4 | Assign colors by function: database, classification, interpolation, aggregation, SAR, and governance. |

## Recommended Slide Maker Rewrite Rules

| Draft Pattern To Avoid | Use This Instead | Reason |
|---|---|---|
| "Cryptographically enforced data boundary" | "Programmatic claim locks plus checksum-backed source provenance" | Avoids claiming a security property not demonstrated by the repo. |
| "Immutable ledger" | "Auditable operational database ledger" | Honest about the database role without implying append-only guarantees. |
| "The model output is mathematically correlated to real events" | "Calibration checks whether probabilities match observed frequencies on a valid evaluation set" | More precise and consistent with calibration practice. |
| "Public display guarantees technical pipeline success" | "Public display indicates publication mechanics passed; scientific validation remains separate" | Keeps technical proof separate from scientific proof. |
| "Deploy once local evidence is secured" | "Consider a narrow pilot only after local evidence, holdout metrics, and named release-gate attestation pass" | Prevents automatic promotion language. |
| "Enterprise team aligned" | "Scientist, partner, and engineering team aligned on evidence gates" | Better fit for a scientific stakeholder deck. |
| One polished color palette for all slides | Function-specific palettes for database, classification, interpolation, aggregation, SAR, and governance | Color should encode meaning, not only decoration. |
| "Use latest model" without naming the surface | "Use Nano Banana Pro in NotebookLM/Slides where exposed; otherwise use the current available Nano Banana-family image model" | Avoids stale model-name hard-coding while following current Google surfaces. |

## Visual Model And Pipeline Addendum

The NotebookLM source packet now includes a dedicated beginner pipeline:

```text
classification -> station/cell danger probabilities
GPxyz interpolation -> spatial danger grid + uncertainty
elevation/region aggregation -> warning-region summary
```

Deck visuals should use the best current image-generation option available in
the tool surface. For NotebookLM and Slides, prefer Nano Banana Pro where it is
available. If the Google tool exposes a newer Nano Banana-family model, use the
current available model while keeping the same evidence-bounded prompt.

Use color as a semantic guide:

| Function | Palette Direction | What The Color Should Communicate |
|---|---|---|
| Database and ledger | Luminous azure, crisp platinum, deep graphite | Facts are stored and auditable. |
| Classification | Glacier blue, alpine pine, controlled danger red | Features become danger probabilities. |
| Spatial interpolation | Topographic teal, elevation cyan, contour gray | Predictions move across space with uncertainty. |
| Elevation/region aggregation | Verification green, slate, signal amber | Outputs become reviewed warning-region summaries. |
| SAR shadow lane | Radar green, ice white, graphite, caution amber | Remote-sensing evidence is internal and gated. |
| Governance and handoff | Clean white, slate, verification green, signal amber | Humans, manifests, checksums, and gates control claims. |

## Web-App ML Gap Closure Backlog

| Rank | Gap | Current Repo Evidence | Impact On Objective | Priority /5 | Implementation Plan |
|---:|---|---|---|---:|---|
| 1 | No real Himalayan `D_tidy` evidence yet | Partner CSV templates and contract exist; real reviewed rows are not present. | Blocks any defensible Himalayan accuracy claim. | 5 | Execute partner handoff, require label source, review basis, observer/nowcast/event refs, avalanche regime, timing fields, and holdout split. |
| 2 | Partner evidence intake is not UI-complete | `/scientist` and `/scientist/daily-verification` exist; partner source manifests and ten evidence CSVs remain file/CLI-based. | Slows scientist/partner co-working and increases data-entry friction. | 5 | Add feature-flagged `/scientist/partner-intake` UI for upload, schema validation, checksum display, blocker list, and resubmission status. |
| 3 | GPxyz blocked by station X/Y/Z coverage | Swiss code requires station coordinates; Himalayan station template exists but no reviewed station data is present. | Blocks spatial uncertainty maps and regional interpolation. | 5 | Validate `station_metadata.csv`, compute station count, region count, elevation span, sparse-coverage warnings, then run GPxyz readiness/LOOCV only after coverage passes. |
| 4 | No independent Himalayan holdout metrics | Holdout protocol/templates exist; no local holdout evaluation result is present. | Blocks release-gate and client accuracy claims. | 5 | Pre-register holdout, run leakage audit, produce metric report with per-region/per-class results and named scientist signoff. |
| 5 | Calibration and uncertainty are not fully user-visible | Backend has calibration, Brier, ECE, and uncertainty-related paths; UI only partially exposes uncertainty. | Weakens trust and decision support. | 4 | Add admin/scientist uncertainty panel with calibration bins, Brier/ECE, high-uncertainty cells, GP uncertainty, evidence age, and stale-source flags. |
| 6 | Model-vs-scientist analytics are basic | Daily verification captures paired model/scientist danger levels and confusion matrices. | Needs stronger scientific learning loop. | 4 | Add discrimination metrics, disagreement queues, false-alarm/miss review, outcome-linked skill, and exportable weekly scientist report. |
| 7 | SAR manual/scene review remains unresolved | SAR shadow lane and SnowSlide/AvalCD artifacts exist; SAR remains gated. | Limits remote-sensing value for sparse Himalayan regions. | 4 | Complete component review, classify scene failures, keep SAR shadow-only, then design bounded v9 only if labels are valid and the gap is model-side. |
| 8 | Weak-layer/snowpack model evidence is incomplete | Snowpack proxy and Swiss reproduction exist; local HIM-STRAT/SNOWPACK-style evidence is not supplied. | Weak-layer prediction remains under-evidenced. | 4 | Extend partner contract and reporting for layer depth, grain type, hardness, stability, burial date, persistent slab indicators, and reviewer notes. |
| 9 | Region/live Himalayan wiring is not ready | App routes exist; live proof geography remains Colorado technical proof. | Cannot switch the public story to Himalayan pilot without overclaim. | 4 | Add region config, map bounds, warning polygons, tile/projection checks, and claim-gated pilot region switch after evidence gates pass. |
| 10 | Governance pack is strong but not operationalized in UI | Docs and artifacts are rich; status is spread across docs, CSVs, CLI outputs, and deck pack. | Reviewers may miss blocker state and next action. | 4 | Build compact scientist/admin readiness dashboard showing evidence-group status, blockers, owner, last validation, and claim state. |

## Practical Implementation Sequence

| Phase | Target | Done Criteria | Claim Boundary |
|---:|---|---|---|
| 1 | Add this deck addendum to the operating pack | Addendum is readable as a standalone review and links to source anchors. | Documentation only. |
| 2 | Use addendum to correct NotebookLM slide language | Slide-maker prompt removes unsupported certainty and keeps UI/data gaps explicit. | No stronger scientific claims. |
| 3 | Build partner-intake UI plan | Route, feature flag, accepted files, validation states, and export flow are specified before implementation. | Internal/scientist workflow only. |
| 4 | Execute real partner evidence triage | Real submitted package gets manifest, checksum, schema validation, blocker report, and readiness score. | `himalayan_accuracy_claim_allowed=false` until holdout and release gates pass. |
| 5 | Add uncertainty/readiness dashboard | Scientist/admin can see calibration, uncertainty, source age, evidence completeness, and blockers. | Readiness dashboard only, not public authority. |
| 6 | Run local holdout workflow after evidence is valid | Leakage audit, metric report, scientist review, and release-gate attestation exist. | Only then consider narrow pilot language. |

## Addendum Acceptance Criteria

- The addendum improves the NotebookLM slide-maker output without weakening any claim lock.
- It avoids exact unsafe phrases that could be picked up as unsupported claims.
- It makes UI incompleteness explicit.
- It separates deck QA, structural code evidence, model validation, and release-gate approval.
- It produces a clear backlog for the next web-app/ML implementation phase.

## Recommended Next Prompt For Deck Update

Use this prompt if the slide-maker is asked to regenerate or revise the deck:

```text
Revise the ML-focused Understand Anything deck using the addendum at
docs/MVP_V2/Artifacts/02_scientist_operating_pack/ML_Focused_Understand_Anything_Deck_Addendum.md.

Keep the 15-slide structure. Preserve the database/model/evidence-gate story.
Remove unsupported certainty phrases such as cryptographic enforcement,
immutable ledger, and automatic deployment. Add the D_tidy label-quality
headline, spatial-scale caveat, uncertainty cards, UI-partial warning,
Colorado-to-Himalaya boundary, SAR shadow-only gate language, and deck-QA vs
science-QA distinction.

Do not claim Himalayan performance, public SAR scoring, official warning
status, or production promotion. Use evidence-bounded language only.
```
