# Role Demarcation Charter — Scientist Co-Development Model

Status: 2026-06-24
Purpose: Define exact responsibilities, permissions, and boundaries between the development team and DRDO scientist team during the co-development pilot.
Boundary: This charter is binding for the duration of the scientist validation pilot. Changes require written agreement from both parties.

---

## 1. Core Principles

1. **Scientists hold authority over model promotion** — no model is promoted to production without scientist sign-off
2. **Scientists create quality-controlled labels (D_tidy)** — the development team does not create training labels
3. **The development team maintains infrastructure and code** — scientists do not write or deploy code
4. **Non-automation rule** — scientist reviews never automatically retrain, promote, or change public scoring
5. **Two-reviewer governance** — priority 5 cases require two independent scientist reviews
6. **Claim boundaries are hardcoded** — no operational claim is made without local evidence + scientist sign-off

---

## 2. Role Responsibility Assignment Matrix (RACI)

| Task / Responsibility | Our Team (Dev/MLOps) | Scientist Team (DRDO) | Both | Neither |
|---|---|---|---|---|
| **Platform hosting & infrastructure** | **R, A, C, I** | I | | |
| **ML model training & calibration** | **R, A, C** | C | | |
| **Model promotion / release gates** | C | **R, A** | | |
| **Forecast artifact publication** | **R, A, C** | I | | |
| **Quality-controlled label creation (D_tidy)** | I | **R, A, C** | | |
| **Snowpack profile data collection** | I | **R, A, C** | | |
| **Station metadata provision** | I | **R, A, C** | | |
| **Historical avalanche event records** | I | **R, A, C** | | |
| **Pilot region selection** | C | **R, A** | | |
| **Warning-region polygon definition** | I | **R, A, C** | | |
| **Scientist validation case review** | C | **R, A, C** | | |
| **Daily paired verification** | C | **R, A, C** | | |
| **SAR scene validation & ground truth** | C | **R, A, C** | | |
| **Public copy / claim boundary approval** | C | **R, A** | | |
| **Security & credential management** | **R, A, C, I** | I | | |
| **Bug fixes & code maintenance** | **R, A, C** | I | | |
| **Co-working SLA enforcement** | C | C | **R, A** | |
| **Meeting outcomes documentation** | C | C | **R, A** | |

*R = Responsible, A = Accountable, C = Consulted, I = Informed*

---

## 3. Access & Permissions Matrix

| Route / System | Public | Scientist Role | Admin Role | Our Team |
|---|---|---|---|---|
| `/` (public forecast workspace) | Read | Read | Read | Read |
| `/scientist` (validation workbench) | Blocked | **Read/Write** | Read | Read (debug) |
| `/scientist/daily-verification` | Blocked | **Read/Write** | Read | Read (debug) |
| `/admin` (observability dashboard) | Blocked | Blocked | **Read/Write** | **Read/Write** |
| Supabase database (public schema) | Read via API | Read via API | Read/Write | **Full access** |
| Supabase storage (forecast artifacts) | Read | Read | Read/Write | **Full access** |
| GitHub repository | Read (if public) | Read (if shared) | Read | **Read/Write** |
| Modal GPU workers | N/A | N/A | Trigger | **Full access** |
| Model training pipeline | N/A | Review only | Trigger | **Execute** |
| Model promotion gates | N/A | **Approve/Reject** | **Approve/Reject** | Propose only |
| Public copy / claim wording | N/A | **Approve/Reject** | Propose | Propose |

---

## 4. Non-Automation Rules (Locked)

These rules are enforced in code and cannot be overridden by configuration:

| Rule | Enforcement | Code Evidence |
|---|---|---|
| Scientist reviews must not automatically retrain a model | No review → training trigger path exists in code | `src/components/ScientistValidationWorkbench.tsx` |
| Scientist reviews must not automatically promote SAR or MTS-LSTM | `SAR_UNET_PROMOTED=false`, `shadow_mode_active=True` hardcoded | `backend/sar_unet_worker.py`, `backend/models/mts_lstm.py` |
| Scientist reviews must not automatically change public scoring | Publication requires separate operator action | `backend/common/forecast_publication.py` |
| Scientist reviews must not automatically change public copy | No review → UI copy mutation path exists | N/A — no such path |
| No Himalayan accuracy claim without local evidence + scientist signoff | `himalayan_accuracy_claim_allowed=false` hardcoded | `src/lib/partnerEvidenceReadiness.ts` |

---

## 5. Escalation Paths

| Situation | Escalation Path | Timeline |
|---|---|---|
| Two reviewers disagree on priority 5 case | Weekly session or earlier if claim-impact is `block` | ≤ 7 days |
| Model appears overconfident in masked/low-evidence cell | Stop and escalate to scientist review | Immediate |
| Case needs field observation or snowpit data | Escalate to partner data owner | Next data cycle |
| Security incident (credential leak, unauthorized access) | Our team rotates credentials, notifies scientist team | ≤ 24 hours |
| Forecast freshness > 24 hours | Operator investigates batch pipeline, switches to "stale" wording | ≤ 12 hours |
| Scientist identifies fundamental model flaw | Pause promotion pipeline, document in action ledger, schedule review | ≤ 48 hours |

---

## 6. SLA Summary

| Parameter | Value |
|---|---|
| Review cadence | Weekly review sessions + async validation |
| Async validation target | 5 cases/week minimum |
| Priority 5 case response | ≤ 48 hours |
| Escalation response | ≤ 24 hours |
| Meeting frequency | Weekly during active pilot |
| Pilot duration | 3-9 months |

**Full SLA document:** `docs/MVP_V2/01_scientist_client_pack/Scientist_Coworking_SLA.md`

---

## 7. Exit Criteria

The pilot is considered complete when:

1. Minimum 30 Himalayan cases reviewed by scientists
2. All priority 5 cases have two-reviewer sign-off
3. Claim-block actions are resolved
4. Scientist team provides written feedback on model utility
5. Both parties agree on next-phase scope (operational pilot or termination)

---

## 8. Data Handling & Confidentiality

| Data Type | Handling |
|---|---|
| Partner-provided station data | Stored in Supabase with RLS; scientist/admin access only |
| Partner-provided event records | Governed by partner evidence contract; license scope required |
| Scientist review notes | Exportable as MD/JSON; stored in scientist validation tables |
| Model predictions | Public forecast artifacts are public; candidate model outputs are admin-only |
| Security credentials | Managed by development team only; never shared with scientists |

---

## 9. What Scientists Will Never Be Asked To Do

- Write or deploy code
- Manage infrastructure (Supabase, Netlify, Modal, GitHub Actions)
- Fix bugs or debug the platform
- Manage security credentials
- Create public-facing copy without review
- Approve their own model promotion (two-reviewer rule)

---

## 10. What the Development Team Will Never Do

- Create quality-controlled training labels without scientist input
- Promote a model to production without scientist sign-off
- Change public claim wording without scientist approval
- Use synthetic data as evidence for operational claims
- Override the `himalayan_accuracy_claim_allowed=false` lock without local evidence
- Automatically trigger model retraining from scientist reviews
