# Scientist Pre-Meeting Questionnaire

Status: prepared template, not yet answered.

Purpose: collect specific scientist decisions before or during the meeting so validation can move from general feedback to actionable case review. Answers should be copied into a dated meeting-outcomes file after the meeting.

## Questions

| # | Question | Expected answer shape | Why it matters |
|---:|---|---|---|
| 1 | What false-alarm rate is acceptable for each danger-level band in the pilot region? | Percent by danger level 1-5 | Sets model-vs-scientist tolerance. |
| 2 | What minimum number of stations or snowpack profiles is required before a region can be considered HIM-STRAT-class for review? | Count and station/profile type | Prevents overclaiming with sparse data. |
| 3 | Which weak-layer signatures are most important for the selected region? | Ranked list; ICSSG codes if available | Drives snowpack feature validation. |
| 4 | What avalanche problem types are most common in the target season? | EAWS problem list with rough percentages | Calibrates problem-type priors. |
| 5 | Which 3-5 historical events from the last five winters must be included in the validation queue? | Event name/date/location/source | Anchors the first real review set. |
| 6 | What is the acceptable delay between event occurrence and validation record creation? | Days | Defines operational review cadence. |
| 7 | What evidence is required before confirming a public-source candidate case as grounded? | Minimum evidence checklist | Protects `himalayas_nepal` queue integrity. |
| 8 | For priority-5 cases, can both reviewers be from the same institution? | yes/no plus condition | Defines two-reviewer governance. |
| 9 | Who can veto or approve a `claim_block` action? | scientist only / operator only / joint | Defines claim governance. |
| 10 | What attribution wording is required for partner data and publications? | Preferred wording | Prevents publication and outreach mistakes. |
| 11 | Which outputs may be published later: case pack, metrics, anonymized data, or none? | Allowed/disallowed list | Sets Zenodo / OSF boundary. |
| 12 | What are the hard no-go conditions for model promotion or public claim upgrades? | Bullet list | Keeps SAR, MTS-LSTM, and public scoring gated. |

## Meeting Capture

- Record unanswered items as `pending_partner_input`.
- Do not infer missing answers from the model or from public-source cases.
- Do not promote candidate rows to grounded Himalayan evidence without explicit scientist confirmation.
