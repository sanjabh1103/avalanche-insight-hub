# MVP V2 Artifact Manifest

Status date: 2026-05-22

This manifest explains what was copied into the MVP V2 hub and how each group should be used. The original source files remain in their existing folders; this folder is a curated client-scientist working pack.

## Folder Map

| Folder | Purpose | Primary Audience | Source Of Truth Note |
|---|---|---|---|
| `00_start_here/` | Meeting runbook, artifact manifest, and first-use navigation | Project owner and meeting facilitator | Curated MVP V2 guidance |
| `01_scientist_client_pack/` | Top20 feature guide, technical feature map, onboarding, completion tracker, RLS/migration verification | Scientist reviewers and project owner | Copied from `docs/learning/`, `docs/MVP/source/`, and `docs/` |
| `02_letters_outreach_templates/` | Director letter, SASE/DGRE outreach, questionnaire, meeting templates, partnership and publication docs | Project owner and partner organization | Sendable drafts need human review before sending |
| `03_post_mvp_decks/` | Post-MVP addendum material for co-working, European shadow evidence, and Modal/GPU role | Scientist meeting audience | Old MVP decks are not rewritten |
| `04_european_shadow_evidence/` | Euro plans, SnowSlide/SAR status, manual-review handoff, transfer boundary | Scientist reviewers and technical reviewers | Shadow validation only, not Himalayan proof |
| `05_modal_gpu_ml_architecture/` | Modal/GPU operating note, ML inventory, RF/SAR methodology, Tier C scaffolding | Technical and scientist reviewers | Modal is off-path validation compute |
| `06_implementation_evidence/` | Reference copies of key source, scripts, migrations, and tests | Technical reviewers | Real executable source remains in `src/`, `backend/`, and `supabase/` |
| `07_demo_assets/` | Selected screenshot evidence for demo preparation | Project owner and presentation reviewer | Verify freshness before external circulation |
| `08_security_ui_github_status/` | Security, UI, and GitHub status note | Project owner and engineering reviewer | Update before any commit, push, or public share |

## Highest-Value Files For The Next Scientist Interaction

| File | Use It For |
|---|---|
| `README.md` | One-page orientation to the MVP V2 hub |
| `00_start_here/CLIENT_MEETING_RUNBOOK.md` | Running the client scientist meeting |
| `01_scientist_client_pack/top20.md` | Scientist-friendly top 20 verification checklist and glossary |
| `01_scientist_client_pack/Top20_features.md` | Detailed technical architecture, stack, APIs, and feature proof map |
| `02_letters_outreach_templates/SASE_DGRE_Director_Letter_Draft.md` | Drafting the director letter |
| `02_letters_outreach_templates/Scientist_pre_meeting_questionnaire.md` | Collecting structured input before the meeting |
| `03_post_mvp_decks/01_Scientist_Coworking_Update.md` | Explaining what changed after the MVP |
| `04_european_shadow_evidence/README.md` | Explaining European evidence as shadow validation only |
| `05_modal_gpu_ml_architecture/Modal_GPU_Scientist_Coworking_Operating_Note.md` | Explaining Modal/GPU usage and boundaries |
| `Remote_Sensing_Operational_Wishlist_Delta.md` | Explaining how the scanned customer wishlist changes scope without authorizing production detection claims |
| `08_security_ui_github_status/UI_GITHUB_SECURITY_STATUS.md` | Deciding whether UI or GitHub action is needed |

## Critical Claim Boundaries

| Topic | Current Status |
|---|---|
| Himalayan scientific proof | Pending real scientist-confirmed or partner-provided cases |
| Synthetic demo data | Allowed for demo only; not training or production evidence |
| European shadow evidence | Benchmark and SAR methodology support; not Himalayan proof |
| Customer remote-sensing wishlist | Product-scope backlog; not operational avalanche/landslide detection proof |
| Modal/GPU | Off-path candidate training, SAR validation, and release evaluation |
| `/scientist` workbench | Co-working and validation surface |
| `/admin` | Admin-only; do not widen for scientist accounts |

## Maintenance Rule

When original files are updated, refresh the corresponding MVP V2 copies before the next scientist or community meeting. Treat this folder as the client-facing pack and the original folders as the engineering source of truth.
