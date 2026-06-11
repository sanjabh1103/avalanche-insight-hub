# Scientist Onboarding

This guide is for a scientist reviewer using Avalanche Insight Hub independently. The workflow creates review evidence only; it does not promote SAR, MTS-LSTM, public scoring, or operational claims without a separate release decision.

## 1. Sign in

- Open `/scientist`.
- Sign in with an account whose Supabase `app_metadata.roles` contains `scientist`.
- A scientist account must not require the `admin` role.

## 2. Review the queue

- Start with priority 5 cases.
- Priority 5 cases require two distinct reviewers before sign-off.
- A disagreement keeps the case in review and creates an escalation action.

## 3. Open a case

Check the displayed:

- forecast run, forecast hour, row, and column
- model evidence and snowpack proxy
- linked forecast outcomes and field reports, when available
- review boundary and current promotion gates

## 4. Record the structured review

For priority 4 and 5 cases, complete all structured fields:

- EAWS avalanche problem
- label quality verdict
- model error verdict
- terrain/SAR ambiguity
- evidence needed next
- confidence rationale

Free-text notes are still useful, but they do not replace the structured verdict fields.

## 5. Attach references

Use the Reference Library only when a publication directly supports the case reasoning. The reference attachment is evidence context; it is not a claim that the current model has reproduced the publication result.

## 6. Export sign-off evidence

Use:

- `Sign-off MD` for meeting review
- `Sign-off JSON` for audit and downstream analysis
- individual case export for detailed review

The exported packet should include cases, reviews, actions, references, reviewer counts, disagreements, and the claim boundary.

## 7. Daily paired verification

Open `/scientist/daily-verification` to record:

- scientist danger level
- model danger level
- scientist EAWS problem
- model EAWS problem
- observed outcome, if known

This creates a paired scientist-vs-model comparison record. It is comparison evidence only, not public forecast promotion.

## Stop Conditions

Stop and escalate if:

- the displayed evidence is insufficient to decide
- the model appears overconfident in a masked or low-evidence cell
- the case needs field observation, snowpit, SAR/optical review, or partner data
- two reviewers disagree on verdict or claim impact

## Required External Inputs

These cannot be invented:

- scientist meeting outcomes
- signed scientist feedback
- Himalayan event cases
- SASE/DGRE partner data
- field-report observations
- production credential handoff
