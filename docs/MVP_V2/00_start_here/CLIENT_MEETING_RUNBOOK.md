# MVP V2 Client Scientist Meeting Runbook

Status date: 2026-05-22

This runbook is the recommended order for using the MVP V2 pack with scientist reviewers, SASE/DGRE stakeholders, and community reviewers. It keeps the discussion focused on what is implemented, what needs expert verification, and what must not be claimed yet.

## Meeting Objective

Use the web app as a scientist co-working and validation system, not as an independent operational warning authority. The meeting should produce:

| Output | What It Means | Where To Record It |
|---|---|---|
| Feature ratings | Scientist ratings for the top 20 features, on a 1-5 scale | `../01_scientist_client_pack/top20.md` |
| Scientific objections | Cases where terminology, evidence, or model behavior is wrong or incomplete | Meeting outcomes template |
| Data commitments | Which pilot region, season, bulletin archive, station data, field reports, and snowpack data can be shared | Director letter and outreach kit |
| Validation actions | Claim downgrade, data remediation, label remediation, benchmark slice, model-gap candidate, or evidence request | Web app action ledger |
| Next meeting scope | Which 3-5 candidate cases and which UI workflows will be checked next | Completion tracker |

## Pre-Meeting Checklist

| Step | Action | Owner | Proof To Carry |
|---:|---|---|---|
| 1 | Confirm meeting date, attendees, and technical contact | Project owner | Calendar invite |
| 2 | Share the Top20 verification guide and pre-meeting questionnaire | Project owner | Sent email and attachments list |
| 3 | Confirm demo credentials out-of-band; never put passwords in email attachments or this repo | Project owner / admin | Local untracked credential note only |
| 4 | Confirm internet, projector, and browser availability | Meeting host | Test opening the hosted site |
| 5 | Pick 3-5 candidate cases for discussion | Scientist lead + project owner | Candidate list with source links |
| 6 | Confirm no one will treat synthetic demo data as training or production evidence | All participants | Verbal agreement and meeting note |

## Recommended 90-Minute Flow

| Time | Segment | What To Show | What To Ask Scientists To Verify | Record This |
|---:|---|---|---|---|
| 0-10 min | Context and proof boundary | `../README.md` and this runbook | Does the proof boundary match how scientists want the system presented? | Accepted / wording change needed |
| 10-25 min | Public forecast experience | Public app, region selector, forecast grid, bulletin-style summary | Are the danger-level language, uncertainty wording, and terrain caveats scientifically acceptable? | Feature ratings and wording objections |
| 25-40 min | Evidence inspection | Cell drawer, weather/snowpack proxy, SAR/residual-shadow warnings, field evidence | What evidence is useful, misleading, or missing before trust is possible? | Missing evidence list |
| 40-55 min | Scientist workbench | `/scientist` validation queue and structured review | Are the structured fields sufficient for a real review? | Field additions or terminology corrections |
| 55-65 min | Daily paired verification | `/scientist/daily-verification` | Does the model-vs-scientist comparison capture the right daily judgment? | Required daily fields |
| 65-75 min | European shadow and Modal compute | Post-MVP deck files and Modal note | Is the European/SAR evidence useful as shadow validation, and is the Himalaya boundary clear? | Accepted / boundary wording changes |
| 75-85 min | Data and partnership ask | Director letter draft, outreach kit, adapter contract | Which data package can be shared first? | Pilot region, winter season, owner |
| 85-90 min | Closeout | Completion tracker and meeting outcomes template | What is blocked before the next technical step? | Action owner and due date |

## Demo Routes

| Route | Who Should Use It | Purpose | Boundary |
|---|---|---|---|
| `/` | Public/scientist reviewers | Inspect forecast map, bulletin-style wording, risk evidence, and export/share behavior | Demonstration and review surface |
| `/scientist` | Scientist or admin role only | Structured case validation, evidence attachments, sign-off export, action ledger | Co-working and validation |
| `/scientist/daily-verification` | Scientist or admin role only | Paired model-vs-scientist daily comparison and analytics | Benchmarking and learning loop |
| `/admin` | Admin role only | Operator controls and internal workflows | Not for scientist-only accounts |

## What To Avoid

| Do Not Say | Safer Wording |
|---|---|
| The app is an official warning service | The app is a validation and decision-support prototype for scientist review |
| European data proves Himalayan accuracy | European data provides shadow benchmark discipline, not Himalayan proof |
| Modal GPU drives the public forecast | Modal supports off-path candidate training, SAR validation, and release evaluation |
| Synthetic data proves the workflow | Synthetic data only demonstrates mechanics and is excluded from training and production claims |
| The model is ready for autonomous retraining | Scientist review creates governed candidates and actions; no automatic promotion |

## Required Closeout Artifacts

| Artifact | Location |
|---|---|
| Meeting outcomes | `../02_letters_outreach_templates/Scientist_meeting_outcomes_TEMPLATE.md` copied to a dated file after meeting |
| Pilot observations | `../02_letters_outreach_templates/Scientist_pilot_observations_TEMPLATE.md` |
| Feature ratings | `../01_scientist_client_pack/top20.md` score sheet |
| Director follow-up | `../02_letters_outreach_templates/SASE_DGRE_Director_Letter_Draft.md` |
| Open actions | Web app action ledger export and `../01_scientist_client_pack/Scientist_Coworking_Completion_Tracker.md` |
