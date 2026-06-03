# MVP V2 Next Actions

Status date: 2026-05-22

## Before Sending To Scientists

| Priority | Action | Owner | Completion Proof |
|---:|---|---|---|
| P0 | Review `../02_letters_outreach_templates/SASE_DGRE_Director_Letter_Draft.md` for names, dates, and addressees | Project owner | Final letter draft |
| P0 | Confirm demo credentials out-of-band and keep them out of git | Project owner / admin | Untracked local credential note |
| P0 | Choose whether the first review uses synthetic demo cases, public-source candidate cases, or both | Project owner + scientist lead | Meeting agenda |
| P0 | Send `../02_letters_outreach_templates/Scientist_pre_meeting_questionnaire.md` before the meeting | Project owner | Sent email |
| P0 | Review `../Remote_Sensing_Operational_Wishlist_Delta.md` and decide whether the customer expects detection maps, danger ratings, or both | Project owner + scientist lead | Meeting note separating danger-rating and detection-map asks |
| P1 | Refresh screenshots if the hosted UI changed after the current screenshots were captured | Engineering | New screenshot set |
| P1 | Decide whether to create a short addendum deck from `../03_post_mvp_decks/` | Project owner | Deck decision |
| P1 | Run the security checks in `../08_security_ui_github_status/UI_GITHUB_SECURITY_STATUS.md` | Engineering | Clean check output |
| P2 | Create a separate documentation commit for `docs/MVP_V2/` after review | Engineering | Git commit hash |

## During The Scientist Meeting

| Priority | Action | Record In |
|---:|---|---|
| P0 | Ask scientists to rate the Top20 features | `../01_scientist_client_pack/top20.md` |
| P0 | Capture terminology or wording objections | Meeting outcomes file |
| P0 | Confirm no-go conditions for production promotion | Meeting outcomes file |
| P0 | Confirm minimum pilot data package | Director letter follow-up |
| P0 | Confirm whether landslide detection is in-scope for a future lane or only a conceptual analogy | Meeting outcomes file |
| P1 | Review 3-5 candidate cases | Web app validation queue and meeting notes |
| P1 | Open action ledger rows for missing evidence or label ambiguity | Web app action ledger |

## After The Meeting

| Priority | Action | Boundary |
|---:|---|---|
| P0 | Create dated meeting outcomes from the template | Do not fabricate absent answers |
| P0 | Promote only scientist-confirmed candidates to grounded queue | Do not promote public-source candidates automatically |
| P1 | Update completion tracker with repo, live, and external-proof status | Keep claim boundaries explicit |
| P1 | Prepare next data-integration plan for partner-provided snowpack/HIM-STRAT data | Adapter contract first, implementation second |
| P1 | Prepare station metadata request with `station_id`, `latitude`, `longitude`, and `elevation_m` for RAvaFcast GPxyz | Required before full Swiss-style spatial interpolation |
| P2 | Decide whether UI needs an in-app help link to this pack | Optional after scientist feedback |
