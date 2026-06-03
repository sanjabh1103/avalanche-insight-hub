# Scientist Co-Working SLA

This SLA governs a 3-9 month scientist validation pilot. It is a working agreement, not a scientific certification.

## Cadence

- Weekly review session: 60 minutes
- Async validation target: 5 cases per scientist per week
- Priority 5 case first response: 24 hours
- Priority 5 case decision target: 7 days
- Disagreement escalation review: next weekly session or earlier if claim-impact is `block`

## Roles

| Role | Responsibility |
|---|---|
| Scientist reviewer | Structured case review, daily paired verification, evidence-needed flags |
| Second reviewer | Independent priority 5 review and disagreement resolution |
| Operator | Queue hygiene, action assignment, claim-boundary enforcement |
| ML owner | Benchmark slices, model-gap candidate triage, retraining-candidate export |
| Data owner | Field-report, outcome-label, and source-lineage remediation |

## Non-Automation Rule

Scientist reviews can create governed actions. They must not automatically:

- retrain a model
- promote SAR or MTS-LSTM
- change public scoring
- change public copy
- certify top-3 or operational-warning claims

## Exit Criteria For Tier B

- At least 20 grounded Himalayan cases reviewed
- At least 5 priority 5 cases with two-reviewer sign-off
- All open claim-block actions resolved or explicitly accepted
- Daily paired verification export created for at least 10 region-days
- Scientist pilot observations recorded
