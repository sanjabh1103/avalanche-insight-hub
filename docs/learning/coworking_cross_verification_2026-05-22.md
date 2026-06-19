# Scientist Co-Working Cross-Verification Report

Status date: 2026-05-22

This report cross-checks the implementation and documentation work created during the scientist co-working, European shadow evidence, Modal.com, and Top20 learning passes. It is a repo-grounded audit, not a scientific validation certificate.

## Adversarial Verdict Matrix

| Area checked | Repo-grounded verdict | Rating /5 | Evidence | Residual blocker |
|---|---:|---:|---|---|
| Scientist-safe access | Implemented | 4 | `/scientist`, `RoleAccessGate`, admin gate remains admin-only | Real scientist pilot still needed |
| Structured scientist review fields | Implemented | 4 | EAWS problem, label quality, model error, terrain/SAR ambiguity, evidence-needed-next | Real reviewer calibration needed |
| Action ledger and closure loop | Implemented | 4 | `scientist_validation_actions`, action status updates, sign-off exports | Real action closure needed |
| Two-reviewer governance | Implemented | 4 | Priority-5 two-reviewer rule and disagreement queue | Real second reviewer needed |
| Cohen kappa and exact agreement | Implemented with guardrails | 4 | `calculateReviewAgreement()` returns kappa or explicit insufficiency reason | Needs enough paired real reviews |
| Daily paired verification | Implemented | 4 | `/scientist/daily-verification`, analytics, export summary | Needs pilot region-day records |
| Synthetic demo segregation | Implemented | 5 | `demo_himalayas_synthetic`, `training_eligible=false`, `production_eligible=false` | Must remain excluded from claims |
| Public-source Himalayan candidates | Implemented as candidate-only | 4 | `himalayas_real_candidate`, not `himalayas_nepal`; unconfirmed source rows only | Scientist confirmation required |
| Grounded Himalayan queue | Correctly blocked | 3 | `himalayas_nepal` requires forecast/outcome/field-report rows | Partner/scientist data required |
| European shadow pack | Correctly shadow-only | 4 | `docs/superpowers/plans/Euro_plans/README.md` | SnowSlide worksheet and fresh-final holdout |
| Modal.com role | Correctly off-path | 4 | Modal note and post-MVP addendum state candidate/shadow compute only | No production promotion without gates |
| Post-MVP deck handling | Correctly separated | 4 | Addendum pack under `docs/MVP/presentation/post_mvp/` | Render only if new deck is requested |
| Top20 scientist learning guide | Implemented and checked | 4 | `docs/learning/top20.md`, 20 features, 30 terms, 22 steps | Needs scientist readability review |
| Director-letter preparation | Drafted | 4 | `docs/SASE_DGRE_Director_Letter_Draft.md` | Human addressee/date approval and actual sending |
| Frontend verification harness | Fixed | 4 | Export-only test now mocks Supabase client; targeted Vitest exits cleanly | Keep Supabase IO tests separate from pure export tests |
| Migration/RLS deployment confidence | Documented | 4 | `docs/Scientist_Coworking_Migration_RLS_Verification.md` | Live database verification when credentials are available |

## Fixed During This Audit

| Gap found | Fix applied | Verification |
|---|---|---|
| Scientist validation auth error mentioned admin only | Changed error text to "scientist or admin reviewer" | `tsc --noEmit` passed |
| Sign-off Markdown export did not include full review/action details | Added per-case review, attached-reference, and governed-action sections | Added focused test assertions |
| Top20 guide did not force claim-boundary inspection in case review step | Updated step 17 to record claim boundary and synthetic/candidate/grounded status | Row-count and record-this checks passed |
| New Top20 guide date was stale | Updated status date to `2026-05-22` | Static grep confirmed |
| Frontend Vitest exited nonzero because export-only tests imported the real Supabase client | Mocked the Supabase client in `src/test/scientist-validation-export.test.ts` so pure export tests do not initialize auth storage | Targeted Vitest now passes: 6 files, 16 tests |
| Completion tracker risked treating local/live credential proof as repo proof | Split status wording into repo-complete, live-smoke, and external-proof boundaries | Tracker now flags credentialed reruns and real scientist verdicts separately |
| Scientist learning guide lacked a single printable score sheet | Added a 1-5 reviewer score sheet and Matrix caution notes | Top20 remains a learning guide, not an operational claim |
| Director-letter areas were listed but not drafted | Added a sendable director-letter draft with explicit proof boundaries and data ask | Requires human addressee, date, and sending approval |

## Residual Blockers Not Falsely Closed

| Blocker | Why it remains open | Next action |
|---|---|---|
| Real scientist verdicts and meeting outcomes | Cannot be fabricated from repo work | Conduct meeting and fill dated outcome file |
| Real grounded Himalayan forecast/outcome/field-report rows | Current public-source rows are candidate-only | Ask partner for 20-30 confirmed cases and bulletin archive |
| SnowSlide v8 manual-review result | Owner/date exist, but worksheet result is not complete | Complete worksheet, then run resolver |
| SNOWPACK / HIM-STRAT partner data | Adapter exists but partner rows are not present | Use adapter contract in SASE/DGRE request |
| Zenodo / OSF public upload | Readiness checklist exists, no public link | Publish only after approval |
| Signed SASE/DGRE commitments | Outreach kit is prepared, not sent/signed | Send director letter and track reply |
| Production SAR or model promotion | Current evidence is shadow/candidate only | Require benchmark, scientist, and release gates |

## Standards Cross-Check

| Standard / source | How this repo now uses it |
|---|---|
| EAWS Avalanche Problems | Structured review options use new snow, wind slab, persistent weak layers, wet snow, gliding snow, plus optional cornices/no distinct problem. |
| EAWS Matrix | Daily verification and Top20 learning guide frame danger-level review around stability, frequency, and avalanche size. |
| EAWS Matrix operational testing, NHESS 2026 | Added caution that the Matrix supports consistency and transparency, but wet/gliding cases and expert-assessed inputs need special review care. |
| WMO impact-based warning services | Director-letter and Top20 verification ask scientists to review consequence and action usefulness, not only model scores. |
| Techel et al. 2025 | Daily paired verification supports model-vs-scientist comparison rather than autonomous truth claims. |
| Perez-Guillen et al. 2025 | SHAP / explanation language is framed as transparent second-opinion evidence. |
| Modal.com docs | Modal.com is documented as serverless off-path compute for candidate training, SAR shadow runs, and release evaluation. |

## Current Verification Evidence

| Check | Result |
|---|---|
| Backend scientist/co-working tests | `17 passed` |
| TypeScript type check | `./node_modules/.bin/tsc --noEmit --pretty false` passed |
| Markdown/static diff check | `git diff --check` passed |
| Top20 row count | 20 feature rows, 30 glossary rows, 22 verification steps |
| Candidate pack safety check | 11 rows, all `training_eligible=false`, `production_eligible=false`, `grounded_himalayan_evidence=false` |
| Credential file hygiene | `.env.scientist.local` exists locally and is ignored by `*.env*` |
| Frontend Vitest | Targeted scientist/access tests passed: 6 files, 16 tests |
| Frontend build | `npm run build` passed |
| Live static route smoke | `/`, `/scientist`, and `/scientist/daily-verification` returned HTTP 200; live chunks reference scientist pages |
| Migration/RLS note | Migration order and final-policy verification SQL documented |

## Next Decision Points

| Decision | Recommended default |
|---|---|
| Should the director letter be drafted now? | Yes, draft from `docs/learning/top20.md`, outreach kit, SLA, and partnership brief. |
| Should old MVP decks be rewritten? | No, keep frozen; use post-MVP addendum. |
| Should candidate public-source cases be promoted? | No, only after scientist confirmation. |
| Should synthetic rows be used for training or claims? | No, demo-only forever unless deleted. |
| Should Modal.com runs change public scoring? | No, only after explicit promotion gates. |
