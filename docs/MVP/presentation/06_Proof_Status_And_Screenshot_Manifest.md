# Proof Status And Screenshot Manifest

Updated: May 8, 2026

This file is the proof and screenshot contract for fresh deck generation. It keeps hosted route proof, authenticated admin proof, repo/admin evidence, and document-only evidence separate.

## Proof Buckets

- `Hosted production`
  - directly visible on `https://avalanche-insight-hub.netlify.app/` or `https://avalanche-insight-hub.netlify.app/admin`
- `Repo/admin verified`
  - implemented and inspectable in source, artifacts, tests, or authenticated operator surfaces, but not necessarily visible to public users
- `Artifact/doc proof only`
  - ledgers, benchmark packs, protocols, source tables, screenshots, and backend artifacts without direct public-route proof

## May 8 Verification Facts

- Hosted `/` and `/admin` returned `HTTP 200` after the May 8 production deploy.
- The deployed public HTML uses Avalanche Insight Hub metadata and the May 8 JS asset hash.
- The hosted `run-forecast` path for Colorado Rockies returned `status=ready`, `stale=false`, `sameDayPublished=true`, `forecastDate=2026-05-08`, `forecastRunId=4822ecf8-defa-4479-ac86-cf9eb7cf2f08`, `publishedAt=2026-05-08T14:31:50.594343+00:00`, and `horizonHours=72`.
- The active May 8 artifact is a full-grid cell publication: `20x20`, `400` ready cells, `0` stale cells, structured bulletin present, `13` dayparts, `data_lineage=observed_or_derived_real`, `publish_eligible=true`, and `synthetic_inputs_present=false`.
- The active May 8 artifact reports `skipTreeShap=true`, `tree_shap_status=heuristic_fallback`, and `explainability_mode=heuristic_fallback`. TreeSHAP remains an implemented explanation path, but it is not the stronger proof claim for this active run.
- Runout evidence in the active artifact uses analytical Alpha-Beta fallback output: `runout_method_counts={"alpha_beta_elliptical":7}`. Do not describe this as operationally qualified WhiteboxTools physics.
- WhiteboxTools runout smoke passed separately on May 8 with `method=alpha_beta_whitebox`; the active public artifact still uses analytical Alpha-Beta fallback because the stronger no-skip publication did not complete.
- A stronger `20x20 / 72h` cell-mode publication with TreeSHAP and physics runout enabled was attempted on May 8 and stopped after it did not complete in the operator window. Keep `4822ecf8-defa-4479-ac86-cf9eb7cf2f08` as the active proof unless a later run supersedes it.
- Hosted authenticated `/admin` smoke succeeded and reached the signed-in observability dashboard on May 8. The refreshed screenshot `2026-05-08_hosted-admin-auth-full-grid-run.png` shows the exact active full-grid run id.
- Live `forecast_active_runs` and `forecast_runs` checks show exactly one active Colorado Rockies row for `4822ecf8-defa-4479-ac86-cf9eb7cf2f08`; the admin summary may count active recent rows across the broader recent-run set.
- Rendered deck QA passed `1920x1080`, `1280x720`, `768x1024`, and `390x844` for the existing rendered decks; regenerate and rerun QA after new deck creation.

## Canonical Screenshot Inventory

| Screenshot | Truth bucket | Recommended use | Required caption or note |
|---|---|---|---|
| [2026-05-08_hosted-public_cell-full-grid-after-refresh.png](rendered/assets/screenshots/2026-05-08_hosted-public_cell-full-grid-after-refresh.png) | `Hosted production` | current public workspace, same-day full-grid cell publication | `Hosted production - same-day full-grid cell publication, May 8, 2026` |
| [2026-05-08_hosted-public_mobile-cell-full-grid-after-refresh.png](rendered/assets/screenshots/2026-05-08_hosted-public_mobile-cell-full-grid-after-refresh.png) | `Hosted production` | mobile current public route proof | `Hosted production mobile - same-day full-grid cell publication, May 8, 2026` |
| [2026-05-08_hosted-admin-auth-full-grid-run.png](rendered/assets/screenshots/2026-05-08_hosted-admin-auth-full-grid-run.png) | `Hosted production` plus `Repo/admin verified` | signed-in admin proof with full active run id visible | `Hosted authenticated admin smoke - full-grid active run id, May 8, 2026` |
| [2026-05-08_hosted-admin-auth-same-day-publication.png](rendered/assets/screenshots/2026-05-08_hosted-admin-auth-same-day-publication.png) | `Hosted production` plus `Repo/admin verified` | signed-in admin publication proof | `Hosted authenticated admin smoke - active same-day forecast run, May 8, 2026` |
| [2026-05-08_hosted-public_same-day-proof.png](rendered/assets/screenshots/2026-05-08_hosted-public_same-day-proof.png) | `Hosted production` | historical rescue publication proof | `Historical hosted production rescue publication proof, May 8, 2026` |
| [2026-05-08_hosted-public_mobile-same-day-proof.png](rendered/assets/screenshots/2026-05-08_hosted-public_mobile-same-day-proof.png) | `Hosted production` | historical mobile rescue proof | `Historical hosted production mobile rescue proof, May 8, 2026` |
| [2026-05-07_hosted-public_workspace.png](rendered/assets/screenshots/2026-05-07_hosted-public_workspace.png) | `Hosted production` | earlier public workspace context, model badge, action controls, full-bulletin visual context | `Hosted production - historical full-workspace context, May 7, 2026` |
| [2026-05-07_hosted-public_mobile-after-deploy.png](rendered/assets/screenshots/2026-05-07_hosted-public_mobile-after-deploy.png) | `Hosted production` | mobile route proof | `Hosted production mobile smoke, May 7, 2026` |
| [2026-05-07_hosted-admin-auth-observability.png](rendered/assets/screenshots/2026-05-07_hosted-admin-auth-observability.png) | `Hosted production` plus `Repo/admin verified` | signed-in admin observability | `Hosted authenticated admin smoke, May 7, 2026` |
| [2026-05-07_hosted-admin-gate.png](rendered/assets/screenshots/2026-05-07_hosted-admin-gate.png) | `Hosted production` | admin route gate fallback | `Hosted admin gate, May 7, 2026` |
| [2026-05-07_hosted-public_share-workflow.png](rendered/assets/screenshots/2026-05-07_hosted-public_share-workflow.png) | `Hosted production` | share workflow proof | `Hosted share workflow, May 7, 2026` |
| [2026-05-07_hosted-public_events-workflow.png](rendered/assets/screenshots/2026-05-07_hosted-public_events-workflow.png) | `Hosted production` | report/events workflow proof | `Hosted report workflow, May 7, 2026` |

Do not reference `rendered/assets/tmp/*.png` in deck-source Markdown.

## Current Proof Status

| Asset or claim | Deck use | Truth bucket | Source | Screenshot rule | Notes |
|---|---|---|---|---|---|
| Public forecast workspace | Deck 1 and Deck 3 | `Hosted production` | Netlify `/`; hosted `run-forecast` response | Prefer May 8 full-grid cell screenshots for current deck rebuild | May 8 proves same-day full-grid cell publication for Colorado Rockies: `20x20`, `72h`, `400` ready, `0` stale, structured bulletin present, and no synthetic inputs. |
| Bulletin wording, masking, and uncertainty cues | Deck 1 | `Hosted production` plus `Repo/admin verified` | Netlify `/`; source ledgers | Use May 8 full-grid screenshots for current public-bulletin proof | Keep `EAWS-style experimental` visible; current full-grid publication is technical/scientist-review-ready evidence, not field-validation closure. |
| Share, export, report, and expert-review actions | Deck 1 | `Hosted production` | Netlify `/`; source ledgers | Use share and events screenshots where useful | Export remains artifact-dependent. |
| Admin route and authenticated observability | Deck 1 and Deck 3 | `Hosted production` plus `Repo/admin verified` | Netlify `/admin`; hosted authenticated smoke | Use hosted admin-auth screenshot for current build; use gate screenshot as fallback | The signed-in dashboard showed source health, decision provenance, model status, model stability, jobs, field reports, evaluation runs, and publication controls. |
| Active RF baseline and explanation gate | Deck 1 and Deck 3 | `Repo/admin verified` | [07_Modal_GPU_Evidence_Table.md](07_Modal_GPU_Evidence_Table.md), [Modal_GPU_ML_Inventory.md](../source/Modal_GPU_ML_Inventory.md) | Use a reconstructed table | The active scorer is the RF baseline. TreeSHAP is implemented, but the current active full-grid artifact reports heuristic explanation fallback. |
| Governed evidence fusion | Deck 1, Deck 2, and Deck 3 | `Repo/admin verified` plus `Artifact/doc proof only` | [Governed_autonomy_evidence_fusion_note.md](../source/Governed_autonomy_evidence_fusion_note.md), [Scientist_evidence_surface_ledger.md](../source/Scientist_evidence_surface_ledger.md) | Use a diagram or source-derived table | Keep `governed evidence fusion` wording exact. |
| Benchmark, stability, and release-gate posture | Deck 1 and Deck 2 | `Repo/admin verified` plus `Artifact/doc proof only` | [Scientist_benchmark_pack_v0.md](../source/Scientist_benchmark_pack_v0.md), [Scientist_validation_protocol_v0.md](../source/Scientist_validation_protocol_v0.md), hosted admin proof if used | Prefer reconstructed tables | Governance evidence does not equal field-validation closure. |
| Architecture addendum | Deck 3 | `Repo/admin verified` plus `Artifact/doc proof only` | [Technical_Architecture_Current_Platform.md](../source/Technical_Architecture_Current_Platform.md), [Technical_Architecture_Future_Core_Model.md](../source/Technical_Architecture_Future_Core_Model.md), [Technical_Glossary_And_Acronyms.md](../source/Technical_Glossary_And_Acronyms.md), [prd_add3.md](../../prd_add3.md) | Diagrams and tables preferred | Separate current, candidate/gated, and proposed architecture states. |

## Pre-Render Checklist

- Use only screenshots from `rendered/assets/screenshots/`.
- Use May 8 full-grid wording only for the Colorado Rockies cell-mode publication unless another region is published and verified.
- For structured bulletin claims, prefer the May 8 full-grid screenshots; use May 7 screenshots only for share/report workflows or historical context.
- Re-run hosted `/` and `/admin` checks before reusing screenshots for a later meeting.
- Re-run hosted authenticated admin smoke before reusing signed-in admin proof for a later meeting.
- Use reconstructed visuals for benchmark, protocol, SAR, MTS-LSTM, and architecture-gate slides unless a screenshot directly proves the statement.
- Regenerate rendered decks after Markdown source changes; do not edit rendered transcripts as source files.
