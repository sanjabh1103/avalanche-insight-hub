# Deck QA Summary

Updated: 2026-05-08

## Outputs

- Deck 1 — Credibility: `avalanche-insight-hub-deck-1-credibility.html` and `avalanche-insight-hub-deck-1-credibility.pdf`
  - slide count: `15`
  - pdf pages: `15`
- Deck 2 — Collaboration: `avalanche-insight-hub-deck-2-collaboration.html` and `avalanche-insight-hub-deck-2-collaboration.pdf`
  - slide count: `15`
  - pdf pages: `15`
- Technical Architecture: `avalanche-insight-hub-technical-architecture.html` and `avalanche-insight-hub-technical-architecture.pdf`
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

## Hosted Authenticated Admin Proof

- Fresh hosted-authenticated admin smoke succeeded on May 8, 2026.
- D1-9 uses hosted authenticated admin observability, so no local fallback label is required on that slide for this build.

## Viewport Results

| Deck | Viewport | Pass | Notes |
|---|---|---|---|
| Deck 1 — Credibility | `1920x1080` | pass | no overflow; navigation ok; proof chips visible |
| Deck 1 — Credibility | `1280x720` | pass | no overflow; navigation ok; proof chips visible |
| Deck 1 — Credibility | `768x1024` | pass | no overflow; navigation ok; proof chips visible |
| Deck 1 — Credibility | `390x844` | pass | no overflow; navigation ok; proof chips visible |
| Deck 2 — Collaboration | `1920x1080` | pass | no overflow; navigation ok; proof chips visible |
| Deck 2 — Collaboration | `1280x720` | pass | no overflow; navigation ok; proof chips visible |
| Deck 2 — Collaboration | `768x1024` | pass | no overflow; navigation ok; proof chips visible |
| Deck 2 — Collaboration | `390x844` | pass | no overflow; navigation ok; proof chips visible |
| Technical Architecture | `1920x1080` | pass | no overflow; navigation ok; proof chips visible |
| Technical Architecture | `1280x720` | pass | no overflow; navigation ok; proof chips visible |
| Technical Architecture | `768x1024` | pass | no overflow; navigation ok; proof chips visible |
| Technical Architecture | `390x844` | pass | no overflow; navigation ok; proof chips visible |

## Fallback Decisions Used

- D1-10 through D1-12 use reconstructed tables and diagrams only, never raw admin/doc screenshots.
- D2 uses reconstructed roadmap, validation, and qualification visuals rather than screenshot-heavy slides.
- The hosted admin gate screenshot remains in the bundle as a fallback, but the current deck build uses hosted authenticated admin proof for D1-9.

## Manual QA Follow-Up

- Open all three decks in Google Chrome at `http://127.0.0.1:4380/` and verify first, mid, and final slides with native keyboard navigation.
- If meeting-day hosted auth fails in a later rerun, replace D1-9 authenticated imagery with the gate screenshot or a reconstructed evidence table.
