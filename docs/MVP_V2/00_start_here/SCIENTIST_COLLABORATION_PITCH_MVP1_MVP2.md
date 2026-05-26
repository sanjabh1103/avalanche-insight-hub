# Scientist Collaboration Pitch - MVP Phase 1 And MVP V2

Status: 2026-05-26
Purpose: humble scientist-facing email draft plus concise attachment note
Scope: responds jointly to `docs/MVP/Cust_comm1.md` and `docs/MVP_V2/Cust_comm2.md`

## Short Email Body

Dear Sir,

Thank you for sharing the Himalayan avalanche publications earlier and, more recently, the Swiss RAvaFcast / EnviDat papers and repository links. We have studied them with respect for the scientific work already done by your team over many years.

Our intent is not to replace that experience or present a finished operational claim. This is an initial consulting proposal and a basis for discussion. We have used your references to prepare a modest, evidence-governed decision-support prototype and to understand what would be required for a Himalayan data-driven pipeline. We would be grateful for your team’s review, corrections, and suggestions on whether this direction is useful.

In the first phase, we prepared a hosted avalanche decision-support MVP with a public forecast workspace, admin/operator lane, batch forecast publication, uncertainty cues, terrain masking, bulletin-style display, and share/export/report workflows. This was aligned with the operational challenges highlighted in the Himalayan literature, including sparse observations, manual snowpack burden, class imbalance, black-box trust, spatial-temporal display, uncertainty communication, and heavy-compute bottlenecks.

In MVP V2, we examined the Swiss RAvaFcast / EnviDat material. We downloaded and validated the Swiss RF1/RF2 data, reproduced an initial Stage-1 RF4 research signal, and prepared a Himalayan partner-evidence framework. The main learning is that Swiss-style automation is a useful reference model, but Himalayan deployment would require local reviewed evidence, scientist-defined truth standards, and a jointly agreed validation process.

At this stage, we are not requesting a large data handover or a binding commitment. If you find the direction worth exploring, we would request only a short review discussion to understand your priorities, preferred pilot region, and the type of local evidence your team would consider acceptable for validation. Detailed templates and technical artifacts can be shared later only if your team wishes to proceed.

I have attached a short note and a compact Excel workbook summarising progress, current boundaries, and a possible three-month exploratory co-development structure. We remain fully open to modifying the approach based on your team’s guidance.

With regards,
Sanjay

---

## 1. Positioning For The Scientist Team

| Point | Scientist-facing wording |
|---|---|
| Tone | Exploratory, respectful, and collaborative. |
| Status | Initial consulting pitch, not a binding proposal and not a completed operational claim. |
| Relationship to past work | Builds on the scientist team’s prior Himalayan work; does not replace or judge it. |
| What we seek now | Review, criticism, guidance, and whether a small co-development pilot is worth exploring. |
| What we avoid now | Large upfront demands, premature deployment claims, or implying that imported Swiss/Colorado evidence validates Himalayan forecasting. |

## 2. What Has Been Prepared So Far

| Area | Plain-English summary | Boundary |
|---|---|---|
| Hosted decision-support MVP | Public forecast workspace, admin/operator lane, batch forecast publication, uncertainty cues, terrain masking, and bulletin-style display. | Technical proof and decision-support surface; not authority-grade validation. |
| Scientist review workflow | Scientist workspace and daily verification route for comparing model output with expert judgement. | Partial UI support; not a complete partner evidence portal yet. |
| Explainable baseline model | Current live scorer remains an explainable Random Forest baseline. | Practical and inspectable; advanced models remain gated. |
| Modal.com / GPU research lane | Modal-backed GPU paths exist for candidate MTS-LSTM and SAR workflows. | Off-path research/candidate use only; not the public scorer. |
| Swiss RAvaFcast research lane | Swiss EnviDat RF1/RF2 data downloaded and validated; Stage-1 RF4 research signal reproduced; GPxyz blocked pending station coordinates. | Research-only reference, not Himalayan proof. |
| Himalayan evidence framework | Partner field dictionary and templates for station, weather, snowpack, labels, events, terrain, remote sensing, reviews, and holdout evidence. | Ready to share if the scientist team asks for templates after discussion. |

## 3. How It Relates To The Challenges In The Papers

| Challenge from the literature | What the platform currently does | What still needs scientist input |
|---|---|---|
| Sparse observations | Uses batch forecast grids, station metadata planning, and GPxyz readiness checks. | Which stations and regions are reliable enough for a pilot. |
| Manual snowpack burden | Adds field-report and scientist-review workflows. | What snowpack/profile variables are locally trusted. |
| Rare avalanche events | Uses rare-event-aware metrics and class-imbalance controls. | What false-alarm and missed-event tolerance is acceptable. |
| Weak layers and snowpack memory | Provides snowpack/weak-layer evidence templates. | Local weak-layer definitions and case review. |
| Black-box trust | Keeps Random Forest baseline explainable and reviewable. | Scientist review of model reasoning and failure cases. |
| Spatial-temporal presentation | Shows risk over map and time, with bulletin-style framing. | Local warning-region and elevation-band policy. |
| Remote sensing promise | SAR path exists as a shadow-gated candidate. | Whether and how SAR scenes should be validated locally. |

## 4. Technology Summary

| Technology / method | Why it was used | Current interpretation |
|---|---|---|
| React + Vite + TypeScript | Fast web interface for maps, bulletins, review, and admin workflows. | Product surface. |
| Supabase | Database, authentication, and artifact storage. | Operational data layer. |
| Python batch pipeline | Keeps heavy processing outside the browser. | Forecast generation and evidence preparation. |
| Random Forest | Interpretable tabular baseline for weather, terrain, and snowpack features. | Current live baseline. |
| Calibration, chronological splits, rare-event controls | Reduces misleading accuracy and probability overconfidence. | Validation discipline. |
| Modal.com / GPU | Runs heavier candidate training and SAR research workflows off-path. | Research and candidate evidence, not public scoring. |
| RAvaFcast-style RF4 + GPxyz + aggregation | Mirrors the Swiss three-stage reference direction. | Research lane awaiting Himalayan data. |

## 5. Current State In Clear Terms

| Statement | Current answer |
|---|---|
| Is the website live? | Yes, as a technical decision-support MVP. |
| Is it a Himalayan operational validation? | No. Local reviewed Himalayan evidence is still required. |
| Is Swiss RAvaFcast studied? | Yes, and partially reproduced as a research reference. |
| Is SAR promoted into operational detection? | No. It remains a shadow-gated research path. |
| Is GPU used? | Yes, for off-path candidate workflows, not as the current public scorer. |
| Is the next step a large data demand? | No. The next step should be a respectful review discussion first. |

## 6. Suggested Next Step

If the scientist team is open to exploring this direction, we suggest a short review discussion with three modest aims:

1. Confirm whether the prototype direction is scientifically useful.
2. Identify one or two possible pilot regions or use cases.
3. Agree what local evidence would be required before any stronger claim is made.

Detailed templates, data dictionaries, and weekly workorders are ready, but they should be shared only after the team confirms that such a pilot is worth considering.

## 7. Possible Three-Month Exploration, If Invited

| Month | Possible focus | Decision point |
|---|---|---|
| Month 1 | Understand available local evidence, source permissions, and pilot region options. | Is there enough reviewed local evidence for a pilot? |
| Month 2 | Run a limited research validation using agreed data and scientist review. | Does the direction show enough signal to continue? |
| Month 3 | Review results, limitations, and next-stage scope. | Continue, narrow, pause, or stop. |

## 8. What We Would Ask Initially

Only after the scientist team agrees to explore further:

| Initial ask | Why |
|---|---|
| One scientist point of contact and one data point of contact | To avoid fragmented communication. |
| One or two suggested pilot regions | To keep the discussion concrete. |
| Guidance on what your team considers reliable validation evidence | To avoid imposing an external definition of truth. |

The detailed data templates can be supplied later when requested.

## 9. Suggested Attachments For The First Email

Keep the first email light:

1. This short note.
2. The compact Excel progress workbook.

Do not attach the full artifact archive or all CSV templates in the first outreach email. Those can be provided once the scientist team asks for the working model or data templates.

## 10. Evidence Anchors

- `docs/MVP/Cust_comm1.md`
- `docs/MVP_V2/Cust_comm2.md`
- `docs/MVP/source/Top_challanges.md`
- `docs/MVP/presentation/rendered/avalanche-insight-hub-deck-2-challenge-alignment-transcript.md`
- `docs/MVP_V2/Artifacts/02_scientist_operating_pack/Swiss_Reproduction_Lane.md`
- `docs/MVP_V2/Artifacts/03_partner_handoff_packet/partner_field_dictionary.md`
- NHESS 2022: https://nhess.copernicus.org/articles/22/2031/2022/
- GMD 2024 RAvaFcast: https://gmd.copernicus.org/articles/17/7569/2024/
- WMO impact-based forecasting: https://wmo.int/impact-based-forecast-and-warning-services
- FAIR data principles: https://www.go-fair.org/fair-principles/
