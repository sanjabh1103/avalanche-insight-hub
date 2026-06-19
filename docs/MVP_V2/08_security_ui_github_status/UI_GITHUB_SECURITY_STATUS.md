# UI, Security, And GitHub Status

Status date: 2026-05-22

## UI Change Decision

No UI change is required for the MVP V2 consolidation itself. The current scientist-facing interaction can use the already implemented surfaces:

| Surface | Role In Scientist Meeting | Current Decision |
|---|---|---|
| Public forecast route `/` | Show forecast map, evidence drawer, exports, and public copy boundaries | Use as-is for demo |
| `/scientist` | Scientist-safe validation queue, structured review, sign-off export, action ledger | Use as-is for demo |
| `/scientist/daily-verification` | Model-vs-scientist daily comparison and analytics | Use as-is for demo |
| `/admin` | Admin-only operator route | Keep admin-only |

Recommended optional UI improvement after the next meeting: add a compact "Scientist verification pack" link or help drawer inside `/scientist` that points to the Top20 guide, questionnaire, and reference library. This is not required before the next scientist conversation because the MVP V2 folder already provides those materials externally.

## GitHub Status

No GitHub push was performed as part of this consolidation pass.

Reason:

| Item | Status |
|---|---|
| UI modified in this pass | No |
| MVP V2 docs created locally | Yes |
| Existing worktree | Dirty, with many pre-existing code/docs changes outside this folder |
| Safe push decision | Do not push broad mixed changes until the intended commit set is reviewed |

Recommended GitHub sequence:

| Step | Action |
|---:|---|
| 1 | Run the security checks listed below |
| 2 | Stage only `docs/MVP_V2/` and any intentional source docs that must accompany it |
| 3 | Review `git diff --cached` for secrets and overclaims |
| 4 | Commit the MVP V2 documentation pack separately from UI/code changes |
| 5 | Create a separate UI/code commit only if there are deliberate UI changes to ship |

## Security Boundaries

| Risk | Rule |
|---|---|
| Demo scientist password | Store only in an untracked local env file; do not copy into MVP V2 |
| Supabase service role or secret key | Never commit, paste, or screenshot |
| Screenshots | Review before external circulation; do not include passwords or admin secrets |
| Synthetic data | Keep `training_eligible=false`, `production_eligible=false`, and a visible demo-only claim boundary |
| Candidate Himalayan public-source cases | Keep unconfirmed until scientist review or partner data confirms them |
| European shadow evidence | Do not present as proof of Himalayan accuracy |
| Modal/GPU | Do not present as the live public forecast authority |

## Security Check Commands

Run these before committing or sending the folder externally:

```bash
git diff --check -- "docs/MVP_V2" docs/MVP/source/Top20_features.md
rg -n "SUPABASE_SERVICE_ROLE_KEY|SUPABASE_SECRET_KEY|SCIENTIST_DEMO_PASSWORD|SUPABASE_ACCESS_TOKEN|sbp_|GEMINI_API_KEY=.*|MODAL_WORKER_TOKEN=.*|eyJ[A-Za-z0-9_-]+" "docs/MVP_V2"
rg -n "official warning authority|European data proves Himalayan accuracy|Modal GPU drives public forecast|scientifically proven|production SAR is active|top-3" "docs/MVP_V2"
```

Expected interpretation:

| Result | Meaning |
|---|---|
| Secret variable names only | Acceptable if they are instructions, not values |
| Actual token/password/key values | Block commit and remove immediately |
| Overclaim phrase inside a blocked-claim warning | Acceptable |
| Overclaim phrase as an asserted capability | Block commit and rewrite |

## What To Tell The Scientist Group

The MVP V2 pack is ready as a consolidated review folder. It does not change the web app UI by itself. It supports the next scientist meeting by providing one place for the Top20 verification guide, director letter draft, outreach kit, European shadow evidence, Modal/GPU role, implementation evidence, and security/GitHub status.
