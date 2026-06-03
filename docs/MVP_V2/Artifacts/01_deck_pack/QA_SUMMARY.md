# Deck QA Summary

Updated: 2026-05-28

## Outputs

- Deck 1 — Credibility: `avalanche-insight-hub-deck-1-credibility.html` and `avalanche-insight-hub-deck-1-credibility.pdf`
  - slide count: `15`
  - pdf pages: `15`
- Deck 2 — Challenge Alignment: `avalanche-insight-hub-deck-2-challenge-alignment.html` and `avalanche-insight-hub-deck-2-challenge-alignment.pdf`
  - slide count: `15`
  - pdf pages: `15`
- Deck 3 — Collaboration: `avalanche-insight-hub-deck-3-scientist-validation.html` and `avalanche-insight-hub-deck-3-scientist-validation.pdf`
  - slide count: `15`
  - pdf pages: `15`
- Deck 4 — Technical Architecture: `avalanche-insight-hub-deck-4-technical-architecture.html` and `avalanche-insight-hub-deck-4-technical-architecture.pdf`
  - slide count: `15`
  - pdf pages: `15`
- Deck 5 — Technology Glossary: `avalanche-insight-hub-deck-5-technology-glossary.html` and `avalanche-insight-hub-deck-5-technology-glossary.pdf`
  - slide count: `15`
  - pdf pages: `15`
- Deck 6 — ML Understanding: `avalanche-insight-hub-deck-6-ml-understanding.html` and `avalanche-insight-hub-deck-6-ml-understanding.pdf`
  - slide count: `15`
  - pdf pages: `15`

## Screenshot Inventory

| File | Evidence label | Use |
|---|---|---|
| `2026-05-08_hosted-public_cell-full-grid-after-refresh.png` | `Live platform` | D1-5 hero and D1-6 full-grid publication proof |
| `2026-05-08_hosted-public_mobile-cell-full-grid-after-refresh.png` | `Live platform` | Mobile full-grid proof for the MVP readiness record |
| `2026-05-08_hosted-admin-auth-full-grid-run.png` | `Live platform` | D1-9 and Technical Deck hosted-auth admin full run-id proof |
| `2026-05-07_hosted-public_workspace.png` | `Live platform` | Full-workspace context and bulletin visual reference |
| `2026-05-07_hosted-public_share-workflow.png` | `Live platform` | D1-8 workflow state |
| `2026-05-07_hosted-public_events-workflow.png` | `Live platform` | Optional alternate workflow crop if needed |
| `2026-05-07_hosted-admin-gate.png` | `Live platform` | Fallback gate view if hosted-auth screenshots are unavailable |
| `ua-structural-overview.png` | `Technical evidence` | D6 structural graph overview: 10 ML/backend layers |
| `ua-domain-overview.png` | `Technical evidence` | D6 domain graph overview: domains, flows, and steps |
| `ua-active-rf-layer.png` | `Technical evidence` | D6 active Random Forest forecast pipeline layer |
| `ua-mts-lstm-layer.png` | `Technical evidence` | D6 MTS-LSTM candidate model layer |
| `ua-sar-shadow-layer.png` | `Technical evidence` | D6 SAR shadow segmentation lane |
| `ua-swiss-ravafcast-layer.png` | `Technical evidence` | D6 Swiss RAvaFcast research lane |
| `ua-himalayan-evidence-layer.png` | `Technical evidence` | D6 Himalayan partner evidence contract lane |
| `ua-evaluation-governance-layer.png` | `Technical evidence` | D6 evaluation, publication, and release governance layer |
| `ua-modal-compute-layer.png` | `Technical evidence` | D6 Modal and remote compute orchestration layer |
| `ua-tests-ci-layer.png` | `Technical evidence` | D6 tests and CI gates layer |
| `ua-backend-support-layer.png` | `Technical evidence` | D6 backend support and shared infrastructure layer |

## Hosted Authenticated Admin Proof

- Fresh hosted-authenticated admin smoke succeeded on May 8, 2026.
- D1-9 and Technical Deck slide 8 use hosted authenticated admin observability, so no local fallback label is required on those slides for this build.

## Viewport Results

| Deck | Viewport | Pass | Notes |
|---|---|---|---|
| Deck 1 — Credibility | `1920x1080` | pass | no overflow; navigation ok; proof chips visible |
| Deck 1 — Credibility | `1280x720` | pass | no overflow; navigation ok; proof chips visible |
| Deck 1 — Credibility | `768x1024` | pass | no overflow; navigation ok; proof chips visible |
| Deck 1 — Credibility | `390x844` | pass | no overflow; navigation ok; proof chips visible |
| Deck 2 — Challenge Alignment | `1920x1080` | pass | no overflow; navigation ok; proof chips visible |
| Deck 2 — Challenge Alignment | `1280x720` | pass | no overflow; navigation ok; proof chips visible |
| Deck 2 — Challenge Alignment | `768x1024` | pass | no overflow; navigation ok; proof chips visible |
| Deck 2 — Challenge Alignment | `390x844` | pass | no overflow; navigation ok; proof chips visible |
| Deck 3 — Collaboration | `1920x1080` | pass | no overflow; navigation ok; proof chips visible |
| Deck 3 — Collaboration | `1280x720` | pass | no overflow; navigation ok; proof chips visible |
| Deck 3 — Collaboration | `768x1024` | pass | no overflow; navigation ok; proof chips visible |
| Deck 3 — Collaboration | `390x844` | pass | no overflow; navigation ok; proof chips visible |
| Deck 4 — Technical Architecture | `1920x1080` | pass | no overflow; navigation ok; proof chips visible |
| Deck 4 — Technical Architecture | `1280x720` | pass | no overflow; navigation ok; proof chips visible |
| Deck 4 — Technical Architecture | `768x1024` | pass | no overflow; navigation ok; proof chips visible |
| Deck 4 — Technical Architecture | `390x844` | pass | no overflow; navigation ok; proof chips visible |
| Deck 5 — Technology Glossary | `1920x1080` | pass | no overflow; navigation ok; proof chips visible |
| Deck 5 — Technology Glossary | `1280x720` | pass | no overflow; navigation ok; proof chips visible |
| Deck 5 — Technology Glossary | `768x1024` | pass | no overflow; navigation ok; proof chips visible |
| Deck 5 — Technology Glossary | `390x844` | pass | no overflow; navigation ok; proof chips visible |
| Deck 6 — ML Understanding | `1920x1080` | pass | no overflow; navigation ok; proof chips visible |
| Deck 6 — ML Understanding | `1280x720` | pass | no overflow; navigation ok; proof chips visible |
| Deck 6 — ML Understanding | `768x1024` | pass | no overflow; navigation ok; proof chips visible |
| Deck 6 — ML Understanding | `390x844` | pass | no overflow; navigation ok; proof chips visible |

## Fallback Decisions Used

- D1-10 through D1-12 use reconstructed tables and diagrams only, never raw admin/doc screenshots.
- D3 uses reconstructed roadmap, validation, and qualification visuals rather than screenshot-heavy slides.
- D2 uses the strict challenge ratings from `Top_challanges.md`, not the inflated Gemini draft ratings.
- D5 uses proof-bucket labels for current, repo/admin verified, candidate/gated, and future-strategy terms.
- The hosted admin gate screenshot remains in the bundle as a fallback, but the current deck build uses hosted authenticated admin proof for D1-9 and Technical Deck slide 8.

## Manual QA Follow-Up

- Open all six decks in Google Chrome at `http://127.0.0.1:4380/` and verify first, mid, and final slides with native keyboard navigation.
- If meeting-day hosted auth fails in a later rerun, replace D1-9 authenticated imagery with the gate screenshot or a reconstructed evidence table.
