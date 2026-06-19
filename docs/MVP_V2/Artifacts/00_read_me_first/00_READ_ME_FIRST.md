# MVP V2 Artifacts Pack - Read Me First

Status: 2026-05-24

This folder is the curated one-source-of-truth copy pack for the MVP V2 scientist and partner discussion. It copies the current deck outputs, scientist operating documents, partner handoff packet, and workorders into one place without moving the canonical source files.

## Fast Path

| Need | Open | What It Gives You |
|---|---|---|
| First 5-minute orientation | [Scientist and team quick-start FAQ](SCIENTIST_TEAM_QUICK_START_FAQ.md) | Plain-language answers, top simplification model, and next action by role. |
| Executive orientation | [Deck 3 scientist validation PDF](../01_deck_pack/avalanche-insight-hub-deck-3-scientist-validation.pdf) | Scientist co-working story and partner handoff narrative. |
| One-page scientist handout | [Scientist handout](../02_scientist_operating_pack/Scientist_Handout_OnePager.md) | Live/research/blocked split, partner packet inventory, scientist asks. |
| Artifact responsibility table | [Artifact workorder index](../MVP_V2_ARTIFACT_WORKORDER_INDEX.md) | Single table of files, owners, actions, UI status, and claim boundaries. |
| Week-by-week execution | [W0-W13 partner workorder](../04_workorders_and_weekly_execution/MVP_V2_W0_W13_PARTNER_WORKORDER.md) | W0-W13 instructions for Sanjay's team and scientists. |
| Colorado-to-Himalaya readiness | [Colorado-to-Himalaya readiness](COLORADO_TO_HIMALAYA_READINESS.md) | Why Colorado Rockies is live first and what is needed for Himalayan live claims. |
| Partner files to fill | [Partner handoff packet](../03_partner_handoff_packet/) | Blank v3 CSV templates, source manifest, field dictionary, and checksum guide. |

## Claim Boundary

| Claim | Current State |
|---|---|
| Colorado Rockies live technical proof | Yes: hosted public route and `/admin` route have same-day `20x20` / `72h` proof dated 2026-05-08. |
| Himalayan accuracy claim | No: `himalayan_accuracy_claim_allowed=false` until partner evidence, local holdout, scientist review, and release gates pass. |
| Production scoring changes | No: this pack is documentation and handoff material only. |
| SAR operational claim | No: SAR remains shadow-gated. |
| Synthetic rows as evidence | No: synthetic files are isolated in `99_synthetic_smoke_only_DO_NOT_SUBMIT/`. |

## UI Reality Check

The scientist/partner workflow is **not fully UI-driven today**. The current Himalayan partner evidence workflow is file-based:

1. Partners fill CSV templates and `partner_source_manifest_template`.
2. Sanjay's team runs validation/triage scripts.
3. Scientists review outputs and fill review/attestation artifacts.
4. UI support is partial for existing scientist/demo review surfaces, but not a complete partner evidence-entry system.

## Folder Map

| Folder | Purpose |
|---|---|
| `00_read_me_first/` | This guide plus Colorado-to-Himalaya readiness explanation. |
| `01_deck_pack/` | Five refreshed decks in PDF/HTML plus seven transcript Markdown files and QA summary. |
| `02_scientist_operating_pack/` | One-pager, 13-week plan, action list, weekly template, and related MVP V2 context docs. |
| `03_partner_handoff_packet/` | Blank partner templates, field dictionary, source manifest, checksum guide, runbooks, and validation artifacts. |
| `04_workorders_and_weekly_execution/` | W0-W13 practical execution plan. |
| `05_deck_sources_for_traceability/` | Deck source Markdown and build/QA scripts used to regenerate the decks. |
| `99_synthetic_smoke_only_DO_NOT_SUBMIT/` | Synthetic smoke-test fixture and report. Never send as partner evidence. |
