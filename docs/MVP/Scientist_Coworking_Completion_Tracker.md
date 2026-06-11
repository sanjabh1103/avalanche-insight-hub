# Scientist Co-Working Completion Tracker

Status date: 2026-05-22

Status language:

- **Repo implemented** means the code, document, script, or template exists in the repository.
- **Local/live smoke verified** means a local or live-environment check has been run, but it may depend on ignored credentials or current deployment state.
- **External proof pending** means the item cannot be scientifically closed until a real scientist, partner, or public repository action confirms it.

## Tier A

| Item | Status | Evidence | Remaining blocker |
|---|---|---|---|
| Scientist-safe route | Repo implemented; local/live smoke verified | `/scientist`, `RoleAccessGate`; static live route smoke; credentialed smoke depends on ignored scientist credentials | Ongoing real-user pilot and credentialed rerun before meeting |
| Onboarding pack | Complete | `docs/Scientist_Onboarding.md` | Add screenshots after live smoke |
| Meeting outcomes template | Complete locally | `Scientist_meeting_outcomes_TEMPLATE.md` | Real meeting notes required |
| Pilot observations template | Complete locally | `Scientist_pilot_observations_TEMPLATE.md` | Real unaided pilot required |
| EAWS structured fields | Complete | review fields and migration | Real scientist usage |
| Reference library | Complete | workbench panel and review evidence refs | Real scientist usage |
| Linked reality evidence | Complete | cell drawer fetch + case evidence | Real source rows required |
| Grounded Himalayan queue | Complete with blocker | `--region-key himalayas_nepal` returns not-enough-grounded-cases | Real Himalayan artifacts required |
| Synthetic demo queue | Repo implemented; demo-only boundary enforced | `demo_himalayas_synthetic` seed script; rows must carry `training_eligible=false`, `production_eligible=false`, `claim_boundary=synthetic_demo_not_scientific_evidence` | Excluded from scientific evidence and production promotion |
| Public-source candidate queue | Complete locally | `seed_publication_candidate_cases.py`; dry-run pack `/private/tmp/himalayas-real-candidate-case-pack.json` | Scientist confirmation required before any row becomes grounded evidence |
| Pre-meeting questionnaire | Complete locally | `docs/MVP/source/Scientist_pre_meeting_questionnaire.md` | Scientist answers required |
| Outreach kit | Complete locally | `docs/SASE_DGRE_Outreach_Kit.md` | Human send and partner reply required |

## Tier B

| Item | Status | Evidence | Remaining blocker |
|---|---|---|---|
| Action ledger | Complete | `scientist_validation_actions` | Real review actions |
| Action closure queue | Complete | workbench status control | Real action closure |
| Two-reviewer governance | Complete | priority 5 rule + disagreement status | Real second reviewer |
| Reviewer agreement export | Complete | exact agreement plus Cohen's kappa with insufficiency reasons | Real paired reviews |
| Daily paired verification | Repo implemented; targeted tests passing | `/scientist/daily-verification`; analytics and export summary; targeted Vitest passes | Real pilot records |
| SLA doc | Complete | `docs/Scientist_Coworking_SLA.md` | Scientist acceptance |
| SASE/DGRE brief | Complete | `docs/SASE_DGRE_Partnership_Brief.md` | Partner response/data access |
| Credentialed demo review/export | Local/live smoke verified in prior run; repo cannot expose credentials | Scientist-only account workflow and redacted export script exist; `.env.scientist.local` is ignored | Rerun with current scientist credentials before meeting; real scientist verdict still required |

## Tier C Infrastructure

| Item | Status | Evidence | Remaining blocker |
|---|---|---|---|
| SNOWPACK / HIM-STRAT adapter | Infrastructure complete | `docs/SNOWPACK_HIMSTRAT_Partner_Data_Adapter.md` | Partner data access |
| Zenodo / OSF readiness | Infrastructure complete | `docs/Zenodo_OSF_Publication_Readiness.md` | Approval and upload |
| Hindi / Nepali i18n scaffold | Infrastructure complete | `src/lib/avalancheCopyI18n.ts` | Full translation review |
| Tablet offline mode | Infrastructure complete | offline queue test | Offline tiles and field pilot |
| SAR FCN baseline | Infrastructure complete | `docs/SAR_FCN_Baseline_Evaluation_Plan.md` | Held-out FCN execution |
| RF methodology baseline | Infrastructure complete | `generate_rf_methodology_report.py` | Generate against final release artifact |
| Open peer-review register | Infrastructure complete | `docs/Open_Peer_Review.md` | GitHub / OSF admin approval and public links |
| European Shadow Evidence Pack | Indexed, shadow-only | `docs/superpowers/plans/Euro_plans/README.md` | SnowSlide worksheet completion and fresh-final holdout before SAR promotion |
| Post-MVP deck addendum | Complete locally | `docs/MVP/presentation/post_mvp/` | Render only if a new meeting deck is requested |
| Modal scientist co-working role | Documented, off-path | `docs/Modal_GPU_Scientist_Coworking_Operating_Note.md` | No production promotion without scientist and benchmark gates |
| Migration/RLS verification | Repo documented | `docs/Scientist_Coworking_Migration_RLS_Verification.md` | Run SQL verification against live Supabase after migrations are applied |

## External / Not Fabricated

- Signed scientist feedback
- Himalayan event outcomes not present in source data
- SASE/DGRE partner commitments
- Real credential handoff outside this machine
- Tier C scientific proof beyond infrastructure
- Any use of synthetic data for training, public scoring, production SAR, or operational warning authority
