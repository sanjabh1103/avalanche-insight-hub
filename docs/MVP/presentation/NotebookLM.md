# NotebookLM Deck Prompt Guide

Updated: May 11, 2026

This is a **prompt guide**, not a source file to upload. For each deck, create a separate NotebookLM notebook and upload only that deck's final Markdown source from `docs/MVP/presentation/rendered/`.

Do not upload the generated HTML, PDFs, transcripts, or this guide unless you intentionally want NotebookLM to critique those files. The Markdown deck file is the source of truth.

## Upload Rule

| Deck | Upload this one Markdown file only | Do not upload |
|---:|---|---|
| 1 | `docs/MVP/presentation/rendered/deck1_final.md` | HTML, PDF, transcript, support docs |
| 2 | `docs/MVP/presentation/rendered/deck_challenge_alignment_final.md` | HTML, PDF, transcript, support docs |
| 3 | `docs/MVP/presentation/rendered/deck2_final.md` | HTML, PDF, transcript, support docs |
| 4 | `docs/MVP/presentation/rendered/Tech_deck_final.md` | HTML, PDF, transcript, support docs |
| 5 | `docs/MVP/presentation/rendered/deck_technology_terms_final.md` | HTML, PDF, transcript, support docs |

The rendered PDFs are for your visual review after NotebookLM generates slides. They are not needed as NotebookLM sources.

## Global Prompt Rules

Use these rules inside every deck prompt:

- Create exactly `15` slides or fewer.
- Treat the uploaded Markdown as the only source of truth.
- Preserve every `Current state and future strategy` section.
- Preserve every `Evidence level` label.
- Keep customer-facing wording direct, optimistic, and evidence-bounded.
- Do not add new scientific, operational, regulatory, or model-performance claims.
- Do not convert future strategy into current implementation.
- Expand abbreviations on first use when the slide introduces a technical term.
- Prefer dense but readable scientific visuals over marketing-style slides.
- Use compact tables, evidence chips, heatmaps, system diagrams, and decision ladders.
- Keep every slide readable for a senior avalanche scientist and a customer stakeholder.

## Blocked Claim Rules

Never generate these phrases or equivalent claims:

- production MTS-LSTM
- operational SAR
- official warning service
- real-time retraining
- Modal.com public scorer
- scientist validation complete
- TreeSHAP proven for the active full-grid run
- fully autonomous avalanche warning
- authority-grade forecast
- replace avalanche forecasters

Use these replacements:

- `MTS-LSTM candidate`
- `SAR candidate evidence path`
- `decision-support MVP`
- `same-day full-grid technical publication`
- `Modal.com candidate/off-path compute`
- `TreeSHAP implemented path; current active run uses heuristic fallback`
- `scientist validation remains the next phase`

## Visual Style Rules

Use a modern technical-scientific style:

- deep backgrounds with selective light slides for dense tables
- graphite, slate, deep pine, deep ridge, deep spruce, and technical mist backgrounds
- glacier blue, signal amber, risk amber, signal teal, or circuit lime accents
- small proof-bucket labels on each slide
- no decorative mountain stock imagery unless it explains terrain, runout, or forecast context
- no generic marketing hero slides
- no yellow, pink, beige, playful illustration, or decorative clutter

Each slide should have:

- one short title
- one customer-facing message
- one visual structure
- one visible proof/status label
- one current-state or future-strategy takeaway

## Deck 1 Prompt

Upload: `docs/MVP/presentation/rendered/deck1_final.md`

Notebook name: `Deck 1 - Current MVP Proof And Customer Value`

Prompt:

```text
Create a customer-facing 15-slide technical proof deck from the uploaded Markdown only.

Goal: show what the current hosted Avalanche Insight Hub MVP proves today, why it matters to customers, and which claims remain future strategy.

Audience: senior avalanche scientist, customer stakeholder, and technical reviewer.

Design direction:
- executive technical proof
- deep pine and light ice backgrounds
- glacier blue and signal amber accents
- proof-bucket strip on every slide
- use screenshots only where the Markdown explicitly references them

Content rules:
- preserve the same-day full-grid technical publication boundary
- keep hosted public proof, admin proof, active ML truth, and future strategy separate
- do not strengthen TreeSHAP, SAR, MTS-LSTM, Modal.com, WhiteboxTools, or official-warning claims
- frame the close as a validation decision, not as completed science

Output: 15 slides maximum with concise titles, one message per slide, and visual layouts suitable for direct customer sharing.
```

## Deck 2 Prompt

Upload: `docs/MVP/presentation/rendered/deck_challenge_alignment_final.md`

Notebook name: `Deck 2 - Top 15 Challenge Alignment`

Prompt:

```text
Create a 15-slide scientist-facing challenge alignment deck from the uploaded Markdown only.

Goal: map the top systemic avalanche forecasting challenges to the current MVP response using the revised evidence-gated ratings.

Audience: senior avalanche scientist with deep forecasting experience.

Design direction:
- scientific heatmap and evidence matrix style
- deep ridge and light snow backgrounds
- risk amber, glacier blue, and pine ink accents
- use status chips: tackled, partial, missing, candidate, future strategy

Content rules:
- use the revised ratings in the Markdown, not older inflated ratings
- show what is current, partial, missing, or future strategy
- keep manual collection, sparse AWS, weak-layer, SAR, climate drift, and micro-climate claims bounded
- make the Top 15 challenges readable as a scientist-facing matrix, not a sales ranking

Output: 15 slides maximum with one challenge cluster per slide where possible and a final validation-priority close.
```

## Deck 3 Prompt

Upload: `docs/MVP/presentation/rendered/deck2_final.md`

Notebook name: `Deck 3 - Scientist Validation And Collaboration`

Prompt:

```text
Create a 15-slide scientist collaboration deck from the uploaded Markdown only.

Goal: explain why scientist validation is required, what the scientist team owns, and how the next validation phase should operate.

Audience: senior avalanche scientist, research collaborator, and implementation sponsor.

Design direction:
- collaboration protocol and decision-path style
- deep technical background with light process slides
- signal teal and glacier blue accents
- use validation ladders, benchmark workflows, role maps, and decision cards

Content rules:
- do not present validation as complete
- make scientist authority concrete: benchmark ownership, weak-layer review, SAR qualification, candidate-model gates
- keep timeline and budget directional, not procurement promises
- end with concrete decision options

Output: 15 slides maximum with a clear progression from collaboration rationale to validation execution.
```

## Deck 4 Prompt

Upload: `docs/MVP/presentation/rendered/Tech_deck_final.md`

Notebook name: `Deck 4 - Technical Architecture`

Prompt:

```text
Create a 15-slide technical architecture deck from the uploaded Markdown only.

Goal: explain the current platform architecture, proof boundary, offline batch split, active RF scorer, and future gated architecture.

Audience: technical reviewer, engineering lead, and senior scientist who wants implementation clarity.

Design direction:
- systems blueprint
- deep spruce and light mist backgrounds
- signal teal and circuit lime accents
- use layered architecture diagrams, data-flow maps, and current/partial/candidate/proposed grids

Content rules:
- separate current implementation from candidate/gated and proposed architecture
- show React and Supabase as presentation/storage layers
- show Python/offline batch as the compute direction
- show Random Forest as active scorer
- show MTS-LSTM, SAR, TreeSHAP refresh, PostGIS, and WhiteboxTools as gated or future paths exactly as written

Output: 15 slides maximum with architecture diagrams that do not introduce new claims.
```

## Deck 5 Prompt

Upload: `docs/MVP/presentation/rendered/deck_technology_terms_final.md`

Notebook name: `Deck 5 - Technology Glossary And Future Strategy`

Prompt:

```text
Create a 15-slide technical field-guide deck from the uploaded Markdown only.

Goal: explain the top technology terms in plain English while keeping each term tied to current state, candidate/gated status, or future strategy.

Audience: mixed customer, scientist, and technical stakeholder group.

Design direction:
- technical field guide
- deep slate and light paper backgrounds
- signal teal and risk amber accents
- use term clusters, status tags, compact glossary panels, and release-gate diagrams

Content rules:
- expand abbreviations on first use
- label each term as current, repo/admin verified, candidate/gated, or future strategy
- keep Modal.com as off-path compute
- keep SAR and MTS-LSTM as candidate/gated
- keep standards and interoperability terms as future strategy unless the Markdown says otherwise

Output: 15 slides maximum with terminology grouped by platform layer and proof status.
```

## Per-Deck Review Checklist

After NotebookLM generates a deck, check:

- It used only the uploaded deck Markdown as source.
- It has 15 slides or fewer.
- It did not merge content from other decks.
- It preserved the deck's proof/status boundaries.
- It did not introduce blocked phrases or stronger claims.
- It did not turn future strategy into current state.
- It did not add unsupported numbers, dates, model scores, field validation, official status, or regulatory status.
- It kept each slide readable with one main message.
- It used visual layouts appropriate to the deck type.

## Final Export Review

Use the generated deck visually, then compare against the existing rendered PDF for the same deck only:

| Deck | Existing rendered PDF for visual comparison |
|---:|---|
| 1 | `docs/MVP/presentation/rendered/avalanche-insight-hub-deck-1-credibility.pdf` |
| 2 | `docs/MVP/presentation/rendered/avalanche-insight-hub-deck-2-challenge-alignment.pdf` |
| 3 | `docs/MVP/presentation/rendered/avalanche-insight-hub-deck-3-scientist-validation.pdf` |
| 4 | `docs/MVP/presentation/rendered/avalanche-insight-hub-deck-4-technical-architecture.pdf` |
| 5 | `docs/MVP/presentation/rendered/avalanche-insight-hub-deck-5-technology-glossary.pdf` |

The PDF is a review reference, not a NotebookLM source.

## Speaker Notes

Use [Speaker_Notes_Deckwise.md](Speaker_Notes_Deckwise.md) after the five PDFs are prepared. It contains deck-by-deck speaker notes for all 75 slides, with plain-English explanations, full-form expansions for technical terms, and real-life examples for beginner audiences.

Do not upload the speaker-notes file as a deck source unless you want NotebookLM to generate a narrated presenter script. For slide generation, keep using the single Markdown file listed for each deck above.
