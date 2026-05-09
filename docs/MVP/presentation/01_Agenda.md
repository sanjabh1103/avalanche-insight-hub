# MVP Presentation Agenda

Updated: May 7, 2026

## Session Goal

Use the current MVP source pack to achieve three linked outcomes:

1. establish what the hosted MVP proves now;
2. convert the discussion into scientist-in-the-loop validation and co-development decisions;
3. make the current and future architecture understandable enough for engineering, science, and product stakeholders to challenge it.

## Modular Deck Contract

- Deck 1 is the credibility and current MVP proof deck.
- Deck 2 is the scientist collaboration and validation deck.
- Deck 3 is the architecture addendum deck.
- Each deck may be rendered independently or merged into a single presentation.
- Each slide should carry a visible proof bucket in notes or slide metadata.

## Recommended Sequence

This order is intentionally scientist-first:

1. problem framing and research lineage
2. current MVP proof on the live website
3. what is genuinely unique now
4. what remains blocked
5. why scientist co-development is necessary
6. how the current architecture works
7. what the future architecture proposes
8. roadmap, budget, and concrete next-step ask

## Deck Agenda

| Session | Focus | Main outcome |
|---|---|---|
| Deck 1 | Current website, research lineage, hosted proof, current uniqueness, and blocked claims | Stakeholders understand the MVP as a governed decision-support shell with clear proof limits. |
| Deck 2 | Scientist role, validation path, benchmark ownership, SAR/MTS-LSTM qualification, and collaboration ask | Scientists see a concrete role in benchmark design, validation authority, and promotion decisions. |
| Deck 3 | Current platform architecture, future core model, offline-batch PRD direction, and architecture gates | Technical stakeholders can separate current implementation from proposed architecture work. |

## Deck-Level Pacing

| Deck | Slide clusters | Why the split works |
|---|---|---|
| Deck 1 | `1-4` problem and lineage; `5-9` live MVP proof; `10-12` ML and governance truth; `13-15` uniqueness, limits, and conditional-go close | Scientists see the real product before they are asked to believe the future story. |
| Deck 2 | `1-4` collaboration hook and scientist role; `5-9` benchmark and validation program; `10-15` pilot, requirements, team, budget, and decision ask | The scientist role becomes attractive before the deck turns procedural. |
| Deck 3 | `1-4` current architecture; `5-7` governance and compute lanes; `8-12` future offline-batch architecture and gates | Engineering details stay out of the credibility deck but remain available for technical review. |

## Live Links To Keep Ready

- Public MVP: `https://avalanche-insight-hub.netlify.app/`
- Admin route: `https://avalanche-insight-hub.netlify.app/admin`
- Source pack root: [docs/MVP/README.md](../README.md)

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
