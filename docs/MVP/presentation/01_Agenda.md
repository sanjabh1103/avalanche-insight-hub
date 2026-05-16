# MVP Presentation Agenda

Updated: May 9, 2026

## Session Goal

Use the current MVP source pack to achieve three linked outcomes:

1. establish what the hosted MVP proves now;
2. convert the discussion into scientist-in-the-loop validation and co-development decisions;
3. make the current and future architecture understandable enough for engineering, science, and product stakeholders to challenge it.

## Modular Deck Contract

- Deck 1 is the current MVP proof and customer-value deck.
- Deck 2 is the top-15 challenge alignment deck.
- Deck 3 is the scientist collaboration and validation deck.
- Deck 4 is the technical architecture deck.
- Deck 5 is the technology glossary, release gates, and future-strategy deck.
- Each deck may be rendered independently or merged into a single presentation.
- Each slide should carry a visible proof bucket in notes or slide metadata.

## Recommended Sequence

This order is intentionally scientist-first:

1. problem framing and research lineage
2. current MVP proof on the live website
3. top-15 challenge alignment and current-state response
4. what remains blocked or candidate-gated
5. why scientist co-development is necessary
6. how the current architecture works
7. what the future architecture proposes
8. terminology, release gates, and concrete next-step ask

## Deck Agenda

| Session | Focus | Main outcome |
|---|---|---|
| Deck 1 | Current website, hosted proof, current product value, admin proof, and claim boundaries | Stakeholders understand the MVP as a governed decision-support shell with clear proof limits. |
| Deck 2 | Top 15 systemic avalanche forecasting challenges and current-state MVP alignment | Scientists see exactly where the MVP is strong, partial, or still science-gated. |
| Deck 3 | Scientist role, validation path, benchmark ownership, SAR/MTS-LSTM qualification, and collaboration ask | Scientists see a concrete role in benchmark design, validation authority, and promotion decisions. |
| Deck 4 | Current platform architecture, future core model, offline-batch PRD direction, and architecture gates | Technical stakeholders can separate current implementation from proposed architecture work. |
| Deck 5 | Technical glossary, release gates, proof buckets, and future strategy terms | Mixed technical and customer audiences use the same vocabulary without overclaiming. |

## Deck-Level Pacing

| Deck | Slide clusters | Why the split works |
|---|---|---|
| Deck 1 | `1-4` proof contract and context; `5-9` live MVP proof; `10-12` ML and governance truth; `13-15` value, limits, and conditional-go close | Scientists see the real product before they are asked to believe the future story. |
| Deck 2 | `1-3` evidence contract and data challenges; `4-9` model, physics, compute, and integration alignment; `10-15` remote sensing, drift, trust, priorities, and close | The challenge matrix gets space to be readable without overloading Deck 1. |
| Deck 3 | `1-4` collaboration hook and scientist role; `5-9` benchmark and validation program; `10-15` pilot, requirements, team, budget, and decision ask | The scientist role becomes attractive before the deck turns procedural. |
| Deck 4 | `1-5` current architecture; `6-10` batch, governance, field, and Modal.com lanes; `11-15` future offline-batch architecture and gates | Engineering details stay out of the credibility deck but remain available for technical review. |
| Deck 5 | `1-6` platform and communication terms; `7-12` ML, SAR, Modal.com, and geospatial terms; `13-15` lineage, standards, and release gates | Technical terminology gets clarified without turning earlier decks into a glossary. |

## Live Links To Keep Ready

- Public MVP: `https://avalanche-insight-hub.netlify.app/`
- Admin route: `https://avalanche-insight-hub.netlify.app/admin`
- Source pack root: [docs/MVP/README.md](../README.md)
- Deck 1 final source: [deck1_final.md](rendered/deck1_final.md)
- Deck 2 final source: [deck_challenge_alignment_final.md](rendered/deck_challenge_alignment_final.md)
- Deck 3 final source: [deck2_final.md](rendered/deck2_final.md)
- Deck 4 final source: [Tech_deck_final.md](rendered/Tech_deck_final.md)
- Deck 5 final source: [deck_technology_terms_final.md](rendered/deck_technology_terms_final.md)

## Audience Framing

| Audience | What they will care about most | What to avoid |
|---|---|---|
| Senior avalanche scientists | problem framing, validation discipline, weak-layer realism, data limitations, benchmark ownership | UI-first hype, autonomy-first language, authority-grade claims |
| Product / PM stakeholders | what is demoable now, how to talk about it safely, what gets funded next | research jargon without product consequence |
| Engineering / delivery stakeholders | proof surfaces, deploy boundaries, roadmap phases, requirements, and operational realism | vague `AI later` statements without artifacts |

## Discussion Rules

- Lead with sparse-data scientific difficulty, not the UI.
- Use `Hosted production`, `Repo/admin verified`, and `Artifact/doc proof only` labels in speaker notes.
- Keep `EAWS-style experimental` and `Groundsource-style` wording bounded exactly as already established.
- Do not present MTS-LSTM, SAR, or autonomy as `Active` unless the slide is explicitly marked future or candidate.
- Keep future GPU opportunities separate from current public forecast proof.

## Expected Outputs

- agreement on what can be shown now without overclaim
- agreement on the scientist role in the next phase
- agreement on the pilot or validation work needed after the MVP discussion
- agreement on which architecture paths are current, candidate/gated, or proposed
- a concrete follow-up ask rather than a generic `interesting conversation`
