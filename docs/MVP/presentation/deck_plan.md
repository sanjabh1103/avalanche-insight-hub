# MVP Deck Source Creation Brief

Updated: May 9, 2026

## Summary

Use `docs/MVP` as the canonical Markdown source pack for fresh slide creation. Build from current-state proof, not from rendered transcripts. Keep every slide grounded in one of three proof buckets:

- `Hosted production`
- `Repo/admin verified`
- `Artifact/doc proof only`

The deck set is now organized as a five-deck discussion pack so NotebookLM can stay under the 15-slide-per-deck limit without compressing proof, challenges, validation, architecture, and terminology into the same file.

1. current MVP proof and customer value
2. top 15 avalanche forecasting challenges and MVP alignment
3. scientist validation and collaboration plan
4. technical architecture: current platform and future core model
5. technology glossary, release gates, and future strategy

## Source Inputs

| Deck | Primary source files | Required proof posture |
|---|---|---|
| Deck 1: current MVP proof and customer value | [rendered/deck1_final.md](rendered/deck1_final.md), [02_Deck1_Outline_Draft.md](02_Deck1_Outline_Draft.md), [Scientist_claim_ledger.md](../source/Scientist_claim_ledger.md), [06_Proof_Status_And_Screenshot_Manifest.md](06_Proof_Status_And_Screenshot_Manifest.md) | Lead with `Hosted production`, then separate `Repo/admin verified` and `Artifact/doc proof only` claims. |
| Deck 2: top 15 challenge alignment | [rendered/deck_challenge_alignment_final.md](rendered/deck_challenge_alignment_final.md), [Top_challanges.md](../source/Top_challanges.md), [Reserches.md](../source/Reserches.md), [Demo_research_appendix.md](../source/Demo_research_appendix.md) | Use revised ratings and caveats; do not use inflated draft ratings. |
| Deck 3: scientist validation and collaboration | [rendered/deck2_final.md](rendered/deck2_final.md), [03_Deck2_Outline_Draft.md](03_Deck2_Outline_Draft.md), [Scientist_validation_protocol_v0.md](../source/Scientist_validation_protocol_v0.md), [Scientist_benchmark_pack_v0.md](../source/Scientist_benchmark_pack_v0.md), [Scientist_discussion_framework.md](../source/Scientist_discussion_framework.md) | Treat scientist validation as required next work, not as completed proof. |
| Deck 4: technical architecture | [rendered/Tech_deck_final.md](rendered/Tech_deck_final.md), [08_Deck3_Architecture_Addendum_Outline.md](08_Deck3_Architecture_Addendum_Outline.md), [Technical_Architecture_Current_Platform.md](../source/Technical_Architecture_Current_Platform.md), [Technical_Architecture_Future_Core_Model.md](../source/Technical_Architecture_Future_Core_Model.md), [prd_add3.md](../../prd_add3.md) | Separate current platform, candidate/gated paths, and proposed offline-batch architecture. |
| Deck 5: technology glossary and release gates | [rendered/deck_technology_terms_final.md](rendered/deck_technology_terms_final.md), [Technical_Glossary_And_Acronyms.md](../source/Technical_Glossary_And_Acronyms.md), [Modal_GPU_ML_Inventory.md](../source/Modal_GPU_ML_Inventory.md), [07_Modal_GPU_Evidence_Table.md](07_Modal_GPU_Evidence_Table.md), [Governed_autonomy_evidence_fusion_note.md](../source/Governed_autonomy_evidence_fusion_note.md) | Explain terms with status labels: current, repo/admin verified, candidate/gated, or future strategy. |

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

## Deck 2 Recommended Flow: Top 15 Challenge Alignment

1. challenge alignment contract
2. data collection and observation scarcity
3. occurrence records and autonomous evidence
4. rare events and feature discipline
5. physical processes and weak layers
6. spatial and temporal hazard fusion
7. weighting, calibration, and multiple optima
8. compute bottlenecks and batch delivery
9. data integration and terrain semantics
10. SAR and remote sensing limits
11. climate drift and micro-climate variability
12. trust, explainability, and reviewability
13. customer alignment summary
14. immediate improvement areas
15. discussion close

## Deck 3 Recommended Flow: Scientist Validation

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

## Deck 4 Recommended Flow: Technical Architecture

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

## Deck 5 Recommended Flow: Technology Glossary And Future Strategy

1. technology terms contract
2. published forecast terms
3. public platform terms
4. Supabase and access-control terms
5. offline and field workflow terms
6. avalanche communication terms
7. active model terms
8. explainability terms
9. candidate sequence-model terms
10. SAR and remote-sensing terms
11. Modal.com and GPU terms
12. terrain, runout, and geospatial terms
13. data lineage and synthetic boundary terms
14. standards and interoperability terms
15. proof buckets and release gates

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
- Regenerate rendered transcripts, HTML, and PDFs for all five decks only after the Markdown source pack is final.
