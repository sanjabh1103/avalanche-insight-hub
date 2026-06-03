# Scientist And Team Quick-Start FAQ

Status: 2026-05-24

Use this file first. The full artifact pack is an evidence archive, not a reading assignment.

## The Simple Reading Model

| Layer | Time | Who Uses It | Read This | Stop When You Can Answer |
|---|---:|---|---|---|
| 1. Quick start | 5-10 min | Sanjay team, scientist lead, partner coordinator | This FAQ | What is live, what is research-only, what is blocked, and who must do what next. |
| 2. Working brief | 30-45 min | Scientist lead, partner data owner, project owner | [Scientist handout](../02_scientist_operating_pack/Scientist_Handout_OnePager.md), [Colorado-to-Himalaya readiness](COLORADO_TO_HIMALAYA_READINESS.md), [W0-W13 workorder](../04_workorders_and_weekly_execution/MVP_V2_W0_W13_PARTNER_WORKORDER.md) | Which files the partner must fill and which claims remain locked. |
| 3. Evidence appendix | As needed | ML/data/geospatial reviewers | [Artifact workorder index](../MVP_V2_ARTIFACT_WORKORDER_INDEX.md), [Partner field dictionary](../03_partner_handoff_packet/partner_field_dictionary.md), CSV templates | The exact schema, source refs, hashes, and validation gates. |

## Top 3 Industry Simplification Ideas

| Idea | What Industry Does | How We Apply It Here |
|---|---|---|
| Progressive disclosure | Show the minimum useful layer first, then reveal detail only when needed. | FAQ first, one-pager second, deep evidence appendix last. Do not ask scientists to read all 100+ files. |
| Role-based action register | Convert documents into owner/action/status rows instead of prose. | The workorder index and W0-W13 plan say who fills which file, when, and what “done” means. |
| FAIR-style evidence archive | Keep data findable, source-linked, reusable, and machine-checkable. | CSV templates, SHA-256 source refs, manifests, validation reports, and release-gate attestations stay in the archive. |

## Basic Questions You Will Be Asked

| Question | Short Answer | Where To Verify |
|---|---|---|
| What technologies were used earlier? | Vite + React + TypeScript frontend; Python backend; Supabase for app data; Netlify hosting; batch forecast artifacts; scikit-learn Random Forest baseline; Modal/GPU only for off-path candidate work. | `package.json`, `backend/daily_inference.py`, `backend/models/surrogate_rf.py`, [Scientist handout](../02_scientist_operating_pack/Scientist_Handout_OnePager.md). |
| What changed with newer technology and this week’s work? | Added scientist review surfaces, daily verification workflow, curated MVP V2 evidence pack, Himalayan v3 partner contract, Swiss RAvaFcast reproduction lane, SAR shadow gates, and claim-lock documentation. | [Artifact workorder index](../MVP_V2_ARTIFACT_WORKORDER_INDEX.md), [Swiss lane](../02_scientist_operating_pack/Swiss_Reproduction_Lane.md). |
| What ML model are we using and why? | The live MVP is still anchored on an explainable tabular Random Forest baseline because it is inspectable, works with structured weather/terrain/snowpack features, supports class-imbalance handling, and fits scientist review. Candidate MTS-LSTM and SAR U-Net paths exist but remain gated. | `backend/models/surrogate_rf.py`, `docs/RF_Methodology_Baseline.md`, deck glossary. |
| What datasets were trained or evaluated and why? | Current local artifacts include a forecast model artifact under `backend/artifacts/20260504T070406Z/`; Swiss EnviDat RF1/RF2 data for RAvaFcast reproduction; Himalayan partner templates are not real training data yet; SAR/SnowSlide work is shadow qualification only. | `backend/artifacts/20260504T070406Z/`, `backend/data/swiss_envidat/`, [Himalayan checkpoint](../02_scientist_operating_pack/Himalayan_PrePartner_Evidence_Finite_Checkpoint.md). |
| Where are datasets stored? | Local generated/research data lives under `backend/data/` and `backend/artifacts/`; partner handoff templates are copied under `docs/MVP_V2/Artifacts/03_partner_handoff_packet/`; synthetic smoke files are isolated under `99_synthetic_smoke_only_DO_NOT_SUBMIT/`. | [Artifact file list](../ARTIFACT_FILE_LIST.txt), [checksum list](../ARTIFACT_SHA256SUMS.txt). |
| How was training/evaluation conducted? | The baseline uses chronological splits, calibration, class-imbalance controls, selected features, and release artifacts. Swiss reproduction uses RF4, GPxyz readiness checks, and aggregation guards. Himalayan accuracy waits for local partner evidence and holdout gates. | `backend/train_model.py`, `backend/models/surrogate_rf.py`, [Swiss lane](../02_scientist_operating_pack/Swiss_Reproduction_Lane.md). |
| Why is this better for avalanche forecasting? | It moves from a demo-only interface toward evidence-governed forecasting: precomputed regional grids, inspectable reasoning, scientist review loops, local data contracts, and explicit release gates. It still does not prove Himalayan accuracy until local evidence passes. | [Colorado-to-Himalaya readiness](COLORADO_TO_HIMALAYA_READINESS.md), [W0-W13 workorder](../04_workorders_and_weekly_execution/MVP_V2_W0_W13_PARTNER_WORKORDER.md). |
| Why Colorado first? | Colorado Rockies is the live technical proof geography because route hosting, grid publication, admin observability, and claim boundaries were already proven there. It is not proof for the Himalayas. | [Colorado-to-Himalaya readiness](COLORADO_TO_HIMALAYA_READINESS.md). |
| What is needed for Himalayas? | Partner source manifest, station X/Y/Z, weather observations, snowpack profiles, D_tidy-grade labels, warning-region polygons, event truth, scientist reviews, independent holdout, and release attestation. | [Partner handoff packet](../03_partner_handoff_packet/), [W0-W13 workorder](../04_workorders_and_weekly_execution/MVP_V2_W0_W13_PARTNER_WORKORDER.md). |
| Can scientists do everything in the UI today? | No. The UI supports partial scientist review and daily verification. The Himalayan partner evidence workflow is still file-based: CSV templates, manifests, hashes, CLI validation, then scientist review. | `src/pages/ScientistPage.tsx`, `src/pages/ScientistDailyVerificationPage.tsx`, [Partner field dictionary](../03_partner_handoff_packet/partner_field_dictionary.md). |
| Should we build a UI FAQ? | Yes, but not before the file workflow is stable. First mirror this FAQ into the `/scientist` route as a compact “What to do first” panel. Later add CSV upload/review only after real partner packages reveal actual failure modes. | Future frontend task; current file is the source text. |
| What should we not say? | Do not say the Himalayas are locally validated, do not say promoted SAR detection exists, do not say synthetic rows are evidence, and do not say partner templates are training data. | [Scientist handout](../02_scientist_operating_pack/Scientist_Handout_OnePager.md). |

## Who Does What Next

| Role | Next Action | File To Use |
|---|---|---|
| Sanjay team | Send only the FAQ, one-pager, Deck 3 PDF, and W0-W13 workorder as the first read-ahead. | This FAQ, [Scientist handout](../02_scientist_operating_pack/Scientist_Handout_OnePager.md), [Deck 3 PDF](../01_deck_pack/avalanche-insight-hub-deck-3-scientist-validation.pdf), [W0-W13 workorder](../04_workorders_and_weekly_execution/MVP_V2_W0_W13_PARTNER_WORKORDER.md). |
| Scientist lead | Confirm local truth standard, priority regions, and what counts as D_tidy-grade review. | [Partner field dictionary](../03_partner_handoff_packet/partner_field_dictionary.md), `danger_labels_and_bulletins.csv`, `scientist_reviews.csv`. |
| Partner data owner | Fill source manifest and the first CSV templates with reviewed real data. | [Partner handoff packet](../03_partner_handoff_packet/). |
| Engineering team | Keep UI claims locked; later add a scientist quick-start panel and partner upload workflow only after real triage outputs stabilize. | `src/pages/ScientistPage.tsx`, `src/pages/ScientistDailyVerificationPage.tsx`. |

## Recommended UI Path

| Stage | UI Addition | Why Not More Yet |
|---|---|---|
| Now | Add a compact `/scientist` quick-start panel using this FAQ. | Low risk; explains what to do without changing evidence intake. |
| After first real partner package | Add triage-status view: missing files, schema blockers, source-ref failures, quality score. | Real package errors will show what fields matter. |
| After two or more partner cycles | Add guided CSV upload and scientist review forms. | Avoid building forms around synthetic assumptions. |

## Source Anchors

- The Turing Way: use a README/index so newcomers can orient quickly.
- GO FAIR: preserve metadata, source references, and machine-actionable evidence.
- GOV.UK Service Manual: start from user needs and keep the service simple.
- Atlassian DACI: document owners, action items, and decision outcomes.
- Google technical writing: write only the knowledge the audience needs to complete the task.
- WMO impact-based warnings: keep the focus on useful, actionable decision support.
