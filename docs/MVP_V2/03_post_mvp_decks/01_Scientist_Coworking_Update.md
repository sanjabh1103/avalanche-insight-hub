# Post-MVP Addendum 1: Scientist Co-Working Update

Status date: 2026-05-21

This is a post-MVP addendum source. It does not replace the five May MVP decks or their rendered transcripts.

## Purpose

Give scientists and internal reviewers a compact update on what changed after the MVP discussion pack:

- scientist-safe route and workbench
- structured EAWS review fields
- action ledger and two-reviewer governance
- daily model-vs-scientist verification
- synthetic demo flow
- public-source candidate queue for meeting confirmation
- remaining external blockers

## Current Scientist Co-Working Surface

| Capability | Current state | Boundary |
|---|---|---|
| `/scientist` route | Scientist and admin roles can access the validation queue. | Does not grant admin access to scientists. |
| Review workbench | Structured review fields, evidence refs, action queue, sign-off export. | Reviews are governance evidence, not automatic retraining or promotion. |
| Daily verification | Captures and summarizes scientist-vs-model paired comparison rows. | Comparison evidence only; not public warning authority. |
| Public-source candidate queue | `himalayas_real_candidate` cases are staged for confirmation. | Not grounded Himalayan evidence until scientist-confirmed. |
| Synthetic demo queue | End-to-end smoke data exists for training scientists. | Synthetic demo rows are excluded from training and public promotion. |

## Meeting Flow

1. Open the scientist route with the demo scientist account.
2. Review one synthetic demo case to explain the workflow.
3. Review 3-5 `himalayas_real_candidate` rows and record confirm/reject decisions.
4. Capture answers in `docs/MVP/source/Scientist_pre_meeting_questionnaire.md`.
5. Export the sign-off packet.
6. Convert confirmed candidates into the grounded Himalayan queue only after explicit scientist approval.

## Open Decisions

- Which pilot region should SASE / DGRE or the scientist team select?
- Which 20-30 historical events are acceptable for the first grounded queue?
- Which partner data can be used for benchmark-only vs training-eligible workflows?
- Which claims should remain blocked after the first scientist review?

## Safe Summary Line

The platform is now ready for a structured scientist pilot, but scientific closure still depends on real scientist verdicts and partner-confirmed Himalayan data.
