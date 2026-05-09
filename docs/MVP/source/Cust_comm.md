# Customer Communication And MVP Alignment

Updated: May 8, 2026

This document is the current customer-facing alignment source for the MVP deck set. It separates the current state of the platform from the future strategy so customer discussions can stay optimistic, precise, and actionable.

## Current Customer Position

The current platform is ready for customer alignment and scientist validation planning. It demonstrates a hosted avalanche decision-support workspace, a governed operator lane, published-batch forecast delivery, experimental bulletin framing, uncertainty cues, masking semantics, share/report/export controls, and candidate-model governance surfaces.

The strongest customer message is:

> Avalanche Insight Hub is a current-state decision-support MVP with a clear future strategy for scientific validation, same-day publication hardening, governed autonomous evidence, and candidate model promotion.

Position the platform as an experimental decision-support MVP with a concrete path toward stronger operational claims. The next few days should focus on closing presentation-readiness gaps and tightening live proof around forecast freshness, authenticated admin evidence, and export/report workflow screenshots.

## Customer-Ready Claim Matrix

| Customer question | Current state | Future strategy | Readiness (1-5) |
|---|---|---|---:|
| Can users inspect avalanche risk on a hosted route? | Yes. The hosted public route shows a forecast workspace with map, publication state, timeline, controls, and uncertainty-aware copy. | Use the latest hosted screenshots in all decks and capture full-bulletin proof when the larger artifact is available. | 4 |
| Is the published forecast current enough for operational language? | The current hosted proof is same-day full-grid technical publication evidence for Colorado Rockies, with freshness explicitly labeled. | Automate same-day proof capture for each demo cycle and complete scientist validation review on selected cases. | 4 |
| Is the system transparent to operators? | Yes. The admin route exposes source health, publication runs, decision provenance, model status, stability, benchmark, and gate language. | Keep a repeatable credentialed smoke test and attach dated evidence before customer distribution. | 4 |
| Is the active model claim bounded? | Yes. Public scoring is framed around the explainable baseline, with MTS-LSTM and SAR treated as candidate/gated paths. | Promote candidate paths only after benchmark, held-out, stability, and scientist review gates pass. | 4 |
| Does the product reduce dependence on manual observations? | Partly. The repo supports governed field-report and autonomous-evidence paths, but these are decision-support inputs. | Expand governed ingestion, confidence weighting, scientist review, and evaluation feedback loops. | 3 |
| Can the customer understand what happens next? | Yes, if decks use current-state/future-strategy language and avoid internal proof jargon. | Present the next phase as same-day artifact hardening, validation pilot, SAR qualification, and candidate-model promotion. | 4 |

## Product And Engineering Improvement Areas

| Priority | Area | Why it matters | Current action | Future strategy |
|---:|---|---|---|---|
| 5 | Same-day forecast publication | Customer confidence depends on seeing a current batch rather than a dated fallback. | May 8 hosted proof now shows same-day full-grid publication with `sameDayPublished=true`, `20x20`, `72h`, and no synthetic inputs. | Automate full-grid same-day publication and proof capture for every demo cycle. |
| 5 | Credentialed admin smoke | Operator claims need dated, repeatable proof. | Admin route and observability surfaces exist; proof must stay dated. | Add one-command hosted admin smoke capture before every customer send. |
| 5 | Rendered deck QA | Customer-send decks should be free of source notes, overflow, and internal wording. | Final deck Markdown is being converted to direct customer language. | Re-render and run viewport checks at desktop, tablet, and mobile sizes. |
| 4 | Export/report/share workflow proof | These controls are useful only when artifact availability is clear. | Export disabled state explains artifact dependency. | Capture export/share/report screenshots after same-day artifact repair. |
| 4 | GPU and Modal.com access | GPU is valuable for SAR and MTS-LSTM candidates while still separate from public-scorer proof. | Modal.com remains off-path candidate infrastructure. | Stabilize worker credentials, held-out artifacts, and promotion reports before claiming acceleration value. |
| 4 | SAR qualification | SAR can improve remote-sensing coverage but can be overclaimed quickly. | SAR is presented as candidate/gated. | Secure data access, labels, revisit-aware evaluation, dry-snow limitations, and region-specific qualification. |
| 4 | Benchmark and release gates | Promotion requires objective quality gates. | PSS/Brier/stability/benchmark language exists in admin and docs. | Tie every candidate promotion to scientist-approved slices and field-validation outcomes. |
| 3 | Weak-layer science | Weak layers are central to avalanche risk and remain open beyond UX. | Decks identify this as an open validation workstream. | Add taxonomy, field labels, snowpack proxy refinement, and failure-case review. |
| 3 | Runout physics validation | Consequence overlays strengthen the product, but need terrain/field validation. | Runout is artifact-backed and bounded as exploratory where needed. | Validate Alpha-Beta/Whitebox outputs against known events and road/asset intersections. |
| 3 | Offline batch-processing split | Keeping heavy math off the live route improves maintainability. | Architecture docs and tech deck describe the split. | Formalize GitHub Actions or lightweight VPS runs with freshness and failure alerts. |

## Presentation Deck Improvement Areas

| Priority | Deck area | Customer-facing fix | Acceptance check |
|---:|---|---|---|
| 5 | Deck tone | Use “current state” and “future strategy”; remove internal authoring notes and defensive wording. | Final deck files read as customer-facing material. |
| 5 | Proof clarity | Use evidence levels without turning the deck into an internal QA report. | Each major claim maps to hosted production, repo/admin verified, or artifact/doc support. |
| 5 | First three slides | Make the customer immediately understand why the MVP exists, what works now, and what comes next. | Slides 1-3 can stand alone as an executive summary. |
| 4 | Screenshot use | Use canonical May 8 full-grid hosted screenshots for publication and bulletin proof. Use May 7 screenshots only for share/report flows or historical context not captured in the current full-grid screenshots. | All screenshot paths resolve locally and point to `docs/MVP/presentation/rendered/assets/screenshots/`. |
| 4 | Future strategy | Make next actions specific: same-day publication, validation pilot, SAR qualification, MTS-LSTM promotion, runout validation. | Every deck includes named future workstreams and promotion gates. |
| 4 | Mobile/overflow readiness | Customer decks should render cleanly across standard viewports. | Re-render and inspect `1920x1080`, `1280x720`, `768x1024`, and `390x844`. |
| 3 | Technical depth | Architecture deck should be readable by scientist, developer, and non-technical stakeholder. | Keep diagrams clear; avoid unexplained acronyms unless defined in glossary. |

## Customer Language To Use

| Instead of | Use |
|---|---|
| Fresh forecast claim without dated proof | Current published batch, with `sameDayPublished` and `publishedAt` evidence |
| Production MTS-LSTM | Candidate MTS-LSTM path with release gates |
| Operational SAR | SAR qualification path |
| Official warning service | Experimental decision-support workspace |
| Real-time retraining | Batch-first publication with future automated refresh |
| Generic trust language | Current-state boundaries and future promotion strategy |

## Immediate Readiness Loop

1. Refresh same-day/publication proof or keep latest-published wording.
2. Run credentialed hosted admin smoke and record the dated evidence.
3. Re-render Deck 1, Deck 2, and the Technical Architecture deck from the updated Markdown.
4. Run deck viewport QA and fix overflow before customer send.
5. Run targeted frontend tests and production build.
6. Capture fresh public/admin screenshots after any hosted deployment.

## Customer Close

The customer ask is a structured validation partnership rather than unconditional production adoption. The most useful next decision is whether to run a scoped validation pilot that tests the current MVP against scientist-approved cases and defines the gates for SAR, MTS-LSTM, same-day publication, and operational expansion.
