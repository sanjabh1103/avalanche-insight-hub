# MVP Deck Source Creation Brief

Updated: May 8, 2026

## Summary

Use `docs/MVP` as the canonical Markdown source pack for fresh slide creation. Build from current-state proof, not from rendered transcripts. Keep every slide grounded in one of three proof buckets:

- `Hosted production`
- `Repo/admin verified`
- `Artifact/doc proof only`

The deck set can be rebuilt as two decks, three decks, or one combined presentation. The recommended split is:

1. credibility and current MVP proof
2. scientist collaboration and validation path
3. technical architecture addendum

## Source Inputs

| Deck | Primary source files | Required proof posture |
|---|---|---|
| Deck 1: credibility and MVP proof | [02_Deck1_Outline_Draft.md](02_Deck1_Outline_Draft.md), [Scientist_claim_ledger.md](../source/Scientist_claim_ledger.md), [Top20_features.md](../source/Top20_features.md), [Demo_decision_brief.md](../source/Demo_decision_brief.md) | Lead with `Hosted production`, then separate `Repo/admin verified` and `Artifact/doc proof only` claims. |
| Deck 2: collaboration and validation | [03_Deck2_Outline_Draft.md](03_Deck2_Outline_Draft.md), [Scientist_validation_protocol_v0.md](../source/Scientist_validation_protocol_v0.md), [Scientist_benchmark_pack_v0.md](../source/Scientist_benchmark_pack_v0.md), [Scientist_discussion_framework.md](../source/Scientist_discussion_framework.md) | Treat scientist validation as required next work, not as completed proof. |
| Deck 3: architecture addendum | [08_Deck3_Architecture_Addendum_Outline.md](08_Deck3_Architecture_Addendum_Outline.md), [Technical_Architecture_Current_Platform.md](../source/Technical_Architecture_Current_Platform.md), [Technical_Architecture_Future_Core_Model.md](../source/Technical_Architecture_Future_Core_Model.md), [Technical_Glossary_And_Acronyms.md](../source/Technical_Glossary_And_Acronyms.md), [prd_add3.md](../../prd_add3.md) | Separate current platform, candidate/gated paths, and proposed offline-batch architecture. |

## Deck 1 Recommended Flow

1. meeting contract and proof buckets
2. avalanche forecasting difficulty
3. client research lineage
4. research lessons and remaining science gaps
5. hosted public MVP proof
6. batch-first forecast workspace
7. bulletin, uncertainty, and masked terrain
8. share, export, report, and expert-review workflows
9. admin/operator observability
10. current RF baseline, explanation gate, and Modal.com split
11. governed evidence fusion
12. benchmark, stability, and release gates
13. current differentiation
14. blocked claims
15. conditional validation ask

## Deck 2 Recommended Flow

1. why scientist co-development matters
2. why the work is worth scientist time
3. claim/evidence discipline
4. scientist role and decision rights
5. benchmark pack `v0`
6. validation protocol `v0`
7. critical-layer and weak-layer program
8. governed autonomy roadmap
9. SAR qualification path
10. scientist-in-the-loop pilot
11. data and field requirements
12. engineering workstreams
13. team shape and collaboration model
14. timeline, budget, and infrastructure
15. concrete decision options

## Deck 3 Recommended Flow

1. current platform proof boundary
2. current web, Supabase, and artifact-delivery layers
3. current batch compute and publication flow
4. active Random Forest scorer and explanation gate
5. admin governance and release-evidence lane
6. offline field-reporting and evidence ingestion
7. Modal.com candidate compute plane
8. future offline-batch paradigm from the PRD
9. proposed GitHub Actions / lightweight VPS execution model
10. proposed PostGIS, KMeansSMOTE, RFE, and WhiteboxTools extensions
11. current / partial / candidate / proposed classification
12. architecture decisions and next engineering gates

## Claim Rules

- Say `current published batch` and `same-day full-grid cell publication` for the May 8 public proof.
- Keep the validation caveat visible: the May 8 artifact is `20x20`, `72h`, `400` ready cells, `0` stale cells, structured bulletin present, and non-synthetic, but it is not scientist field-validation closure.
- Use stale/fallback wording only when same-day hosted artifact proof is absent.
- Do not say the candidate sequence model is publicly active, SAR is promoted, the product has authority-grade warning standing, or retraining is continuous.
- Use `Modal.com` only for off-path candidate compute and remote worker infrastructure.
- Use hosted screenshots only from `rendered/assets/screenshots/`.

## Verification Before Rendering

- Check every slide against [05_Slide_Evidence_Map.md](05_Slide_Evidence_Map.md).
- Check every screenshot against [06_Proof_Status_And_Screenshot_Manifest.md](06_Proof_Status_And_Screenshot_Manifest.md).
- Run a stale-phrase scan over the Markdown source pack before rendering.
- Regenerate rendered transcripts and deck HTML only after the Markdown source pack is final.
