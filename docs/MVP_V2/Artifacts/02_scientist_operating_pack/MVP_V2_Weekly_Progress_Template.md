# MVP V2 — Weekly Progress Note Template

Fill this template every Friday by 17:00 IST during the 13-week pilot. Filed copies go in `docs/Scientist_Coworking_Completion_Tracker.md`.

---

## Header

- **Week:** N of 13
- **Date range:** YYYY-MM-DD → YYYY-MM-DD
- **Filed by:** <name + role (PL / SL / PR / ML / GS / HA / OP)>
- **Filed at:** YYYY-MM-DD HH:MM IST
- **Filed against:** `MVP_V2_13_Week_Pilot_Plan.md` Week N
- **Pilot contract reaffirmed:** `production_scoring_allowed = false`, `himalayan_accuracy_claim_allowed = false`

---

## 1. Acceptance Gate Status For This Week

| Acceptance criterion (from 13-week plan) | Status | Evidence pointer | Owner |
|---|---|---|---|
| <criterion 1> | `pass` / `partial` / `fail` / `not_attempted` | <artifact path or hash> | <role> |
| <criterion 2> | … | … | … |

If any criterion is `fail` or `partial`, list the corrective action and the target close week below.

---

## 2. Deliverables Produced This Week

| Deliverable | Path | SHA-256 (if applicable) | Tier (0/1/2) | Lane tag |
|---|---|---|---|---|
| <name> | <path under repo> | <hash> | <0/1/2> | `Hosted production` / `Repo/admin verified` / `Artifact/doc proof only` / `Candidate/gated` / `Research-only` |

---

## 3. Action List Closures

| Action ID (`MVP_V2_Action_List.md`) | Previous status | New status | Closed-by | Closed-at |
|---|---|---|---|---|
| Bx | pending | done | <role> | YYYY-MM-DD |

---

## 4. Blockers Opened This Week

| Blocker | Triggered by | Severity (1=trivial, 5=stop-the-pilot) | Owner | Target unblock week |
|---|---|---|---|---|
| <name> | <action ID or external dep> | <1–5> | <role> | <week N> |

---

## 5. Blockers Closed This Week

| Blocker | Resolution | Closed-by | Closed-at |
|---|---|---|---|
| <name> | <one-paragraph resolution> | <role> | YYYY-MM-DD |

---

## 6. Scientist Decisions Recorded

| Decision | Made by | At | Reasoning (≤2 sentences) | Effect on plan |
|---|---|---|---|---|
| `extend` / `narrow` / `block` / `terminate` / `proceed` | <SL or named approver> | YYYY-MM-DD | <text> | <which weeks change> |

---

## 7. Evidence-Lane Compliance

For each statement in this note, confirm the evidence lane is tagged. List any statement that could not be tagged and the reason.

- Untagged statements: `<list or "none">`

---

## 8. Claim Discipline Reaffirmation

Confirm by initials (SL + PL):

- [ ] No production-scoring authorization is implied by anything in this week's work.
- [ ] No Himalayan accuracy claim is implied by anything in this week's work.
- [ ] No SAR promotion is implied by anything in this week's work.
- [ ] No raw bulletin was treated as `D_tidy`-grade training truth.
- [ ] No synthetic fixture was sent as evidence.
- [ ] No Week-9 protocol floor was weakened (only relevant from Week 9 onward).

---

## 9. Risks Surfaced

| Risk | Likelihood (L/M/H) | Impact (L/M/H) | Mitigation pointer |
|---|---|---|---|
| <name> | <L/M/H> | <L/M/H> | <action ID or new mitigation> |

---

## 10. Next Week — Top 5 Actions

| Rank | Action ID (from Action List) | Owner | Acceptance check |
|---|---|---|---|
| 1 | … | … | … |
| 2 | … | … | … |
| 3 | … | … | … |
| 4 | … | … | … |
| 5 | … | … | … |

---

## 11. Cumulative Quality Score Snapshot (Weeks 5 onward)

| Region | Score (/100) | Δ from last week | First blocker |
|---|---|---|---|
| <region 1> | NN | ±N | <first failing rubric entry> |
| <region 2> | NN | ±N | <…> |

---

## 12. Customer-Facing Summary (≤3 sentences)

Write this only after sections 1–11 are filled. It is the line item that will be shared with the SASE/DGRE partner liaison.

> <≤3 sentences, evidence-lane-tagged, no overclaim>

---

## 13. File Hashes For This Note

| File | SHA-256 |
|---|---|
| This note | <hash captured at file commit> |
| Pilot plan in effect (`MVP_V2_13_Week_Pilot_Plan.md`) | <hash> |
| Action list in effect (`MVP_V2_Action_List.md`) | <hash> |
| Co-working SLA (`docs/Scientist_Coworking_SLA.md`) | <hash> |
