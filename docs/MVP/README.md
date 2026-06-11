# MVP Markdown Source Pack

Updated: May 9, 2026

This folder is the slide-source workspace for the Avalanche Insight Hub MVP decks. Treat the Markdown files here as the source of truth for deck generation, presenter notes, proof chips, and screenshot selection.

## Structure

- `source/`
  - current-state research, customer, claim, architecture, glossary, validation, and governance source files
- `presentation/`
  - deck agenda, deck outlines, appendix references, evidence map, proof manifest, Modal.com evidence table, and architecture addendum outline
- `presentation/rendered/assets/screenshots/`
  - canonical hosted-route PNGs for deck builds

## Proof Buckets

Use these proof buckets consistently in slide bodies, captions, and speaker notes:

- `Hosted production`
  - directly visible on `https://avalanche-insight-hub.netlify.app/` or `https://avalanche-insight-hub.netlify.app/admin`
- `Repo/admin verified`
  - implemented and inspectable in source, artifacts, tests, or authenticated operator surfaces, but not necessarily public-route visible
- `Artifact/doc proof only`
  - source ledgers, protocols, benchmark packs, research notes, screenshots, and internal artifacts that support discussion but are not direct live-route proof

## Current Hosted Proof Boundary

- Hosted `/` and `/admin` returned `HTTP 200` on May 8, 2026 after the production deploy.
- Hosted public proof now includes a Colorado Rockies same-day full-grid cell publication: `status=ready`, `stale=false`, `sameDayPublished=true`, `forecastDate=2026-05-08`, `publishedAt=2026-05-08T14:31:50.594343+00:00`, and `horizonHours=72`.
- The active May 8 run is `4822ecf8-defa-4479-ac86-cf9eb7cf2f08`: `20x20` grid, `400` ready cells, `0` stale cells, structured bulletin present, `13` bulletin dayparts, `data_lineage=observed_or_derived_real`, and `synthetic_inputs_present=false`.
- The active run uses heuristic explanation fallback (`skipTreeShap=true`, `tree_shap_status=heuristic_fallback`) and analytical Alpha-Beta fallback runout (`runout_method_counts={"alpha_beta_elliptical":7}`). TreeSHAP and WhiteboxTools remain implemented or smoke-proven hardening paths, not stronger active-run claims.
- Hosted authenticated `/admin` smoke succeeded on May 8, 2026 and proves the observability lane. The refreshed admin screenshot shows the exact active full-grid run id.
- The production metadata uses Avalanche Insight Hub branding.

## Canonical Screenshots

Use only the PNGs in `presentation/rendered/assets/screenshots/` as deck-source references:

| Screenshot | Use |
|---|---|
| `2026-05-08_hosted-public_cell-full-grid-after-refresh.png` | hosted public workspace, same-day full-grid cell publication |
| `2026-05-08_hosted-public_mobile-cell-full-grid-after-refresh.png` | hosted mobile public route, same-day full-grid cell publication |
| `2026-05-08_hosted-admin-auth-full-grid-run.png` | hosted authenticated admin proof with full active run id visible |
| `2026-05-08_hosted-admin-auth-same-day-publication.png` | hosted authenticated admin publication proof |
| `2026-05-08_hosted-public_same-day-proof.png` | historical same-day rescue publication proof |
| `2026-05-08_hosted-public_mobile-same-day-proof.png` | historical mobile rescue publication proof |
| `2026-05-07_hosted-public_workspace.png` | hosted public workspace, full-bulletin/model-badge context and action controls from earlier proof |
| `2026-05-07_hosted-public_mobile-after-deploy.png` | hosted mobile public route proof |
| `2026-05-07_hosted-admin-auth-observability.png` | hosted authenticated admin observability proof |
| `2026-05-07_hosted-admin-gate.png` | hosted admin gate fallback proof |
| `2026-05-07_hosted-public_share-workflow.png` | hosted share workflow proof |
| `2026-05-07_hosted-public_events-workflow.png` | hosted events/report workflow proof |

Do not use `presentation/rendered/assets/tmp/*.png` in fresh deck-source Markdown.

## Five-Deck Discussion Pack

| Order | Deck name | Final Markdown source | Primary purpose |
|---:|---|---|---|
| 1 | Current MVP Proof And Customer Value | [deck1_final.md](presentation/rendered/deck1_final.md) | Hosted proof, current product value, admin proof, ML truth, and claim boundaries. |
| 2 | Top 15 Avalanche Forecasting Challenges And MVP Alignment | [deck_challenge_alignment_final.md](presentation/rendered/deck_challenge_alignment_final.md) | Evidence-gated challenge alignment using revised ratings from the current source pack. |
| 3 | Scientist Validation And Collaboration Plan | [deck2_final.md](presentation/rendered/deck2_final.md) | Scientist role, benchmark pack, validation protocol, workstreams, and decision options. |
| 4 | Technical Architecture: Current Platform And Future Core Model | [Tech_deck_final.md](presentation/rendered/Tech_deck_final.md) | Current architecture, offline-batch split, RF scorer, candidate paths, and proposed architecture gates. |
| 5 | Technology Glossary, Release Gates, And Future Strategy | [deck_technology_terms_final.md](presentation/rendered/deck_technology_terms_final.md) | Plain-English technology terms with current, candidate/gated, and future-strategy labels. |

Each deck is capped at 15 slides for NotebookLM and rendered-deck generation.

## Post-MVP Addendum Pack

The five rendered MVP decks above are frozen as historical May MVP discussion artifacts. Do not silently rewrite their rendered Markdown, transcripts, or PDFs for the scientist co-working phase unless a new meeting-specific deck generation task is opened.

Use the post-MVP addendum sources for the next scientist-facing update:

| Addendum | Source | Purpose |
|---|---|---|
| Scientist co-working update | [01_Scientist_Coworking_Update.md](presentation/post_mvp/01_Scientist_Coworking_Update.md) | Role separation, validation workbench, review governance, daily verification, and remaining external proof needs. |
| European shadow and SAR status | [02_European_Shadow_And_SAR_Status.md](presentation/post_mvp/02_European_Shadow_And_SAR_Status.md) | European shadow evidence pack, SnowSlide v8 status, SAR blockers, and Himalaya transfer boundary. |
| Modal.com / GPU compute role | [03_Modal_GPU_Compute_Role.md](presentation/post_mvp/03_Modal_GPU_Compute_Role.md) | Off-path candidate training, SAR shadow segmentation, release evaluation, and scientist promotion gates. |

## Recommended Source Order

1. Start with [01_Agenda.md](presentation/01_Agenda.md) to choose the deck flow.
2. Use the five final rendered Markdown sources listed above as the direct NotebookLM deck inputs.
3. Use [02_Deck1_Outline_Draft.md](presentation/02_Deck1_Outline_Draft.md), [03_Deck2_Outline_Draft.md](presentation/03_Deck2_Outline_Draft.md), and [08_Deck3_Architecture_Addendum_Outline.md](presentation/08_Deck3_Architecture_Addendum_Outline.md) as supporting outline inputs.
4. Validate proof buckets and screenshots through [06_Proof_Status_And_Screenshot_Manifest.md](presentation/06_Proof_Status_And_Screenshot_Manifest.md).
5. Validate slide claims through [05_Slide_Evidence_Map.md](presentation/05_Slide_Evidence_Map.md).
6. Pull citations and external grounding from [04_Appendix_References_Quotes.md](presentation/04_Appendix_References_Quotes.md) and [Reserches.md](source/Reserches.md).
7. Use [Technical_Architecture_Current_Platform.md](source/Technical_Architecture_Current_Platform.md), [Technical_Architecture_Future_Core_Model.md](source/Technical_Architecture_Future_Core_Model.md), and [Technical_Glossary_And_Acronyms.md](source/Technical_Glossary_And_Acronyms.md) for architecture and terminology backup.

## Source Boundaries

- Current public MVP claims must stay tied to hosted route proof.
- Admin claims must state whether they are hosted-authenticated proof or repo/admin proof.
- Candidate MTS-LSTM, SAR, WhiteboxTools runout, and future GitHub Actions / lightweight VPS architecture must remain gated or proposed unless a current artifact proves promotion.
- The rendered deck transcripts are outputs. Regenerate them after source updates; do not treat them as source Markdown.
