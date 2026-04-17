# Operator Rollout QA — Unified PRD v2.0

Step-by-step QA playbook to transition the platform from **cold-start** (`f1_score=0`)
to a **fully functioning scientific instrument**. Each step is independently
verifiable and independently revertable.

Repo: `sanjabh1103/avalanche-insight-hub` · Supabase ref: `fzheroisjhxnairglelv`

Legend: `🧑 operator action` · `🤖 automated check` · `✅ pass criterion`

---

## Step 1 — Activate Topographic Physics (Challenges 4 & 11)

Switch Alpha-Beta runout from rectangular fallback → true gravity-driven flow.

### 1.1 Prerequisites
- `git-lfs` installed: `git lfs install` (once per machine).
- OpenTopography API key: https://portal.opentopography.org/ (free).
  ```bash
  export OPENTOPOGRAPHY_API_KEY=...
  ```

### 1.2 🧑 Download + commit the 8 regional SRTM DEMs
```bash
# From repo root
python -m backend.scripts.download_region_dems      # ~120 MB total
git add .gitattributes backend/data/dem/*.tif backend/data/dem/README.md
git commit -m "data(dem): bundle SRTM 30m per region for Alpha-Beta runout"
git push origin main
```

### 1.3 🧑 Flip the physics flag on the next infer run
```bash
gh workflow run ml_pipeline.yml \
  -f mode=infer \
  -f run_physics_runout=true
```

### 1.4 🤖 Verification queries (Supabase SQL editor)
```sql
-- Most recent infer run should now record physics-mode metadata
SELECT model_metadata->>'run_physics_runout'   AS physics_flag,
       model_metadata->>'runout_method_sample' AS method,
       updated_at
FROM   forecast_grids
ORDER  BY updated_at DESC
LIMIT  5;
```
✅ `physics_flag = 'true'` AND at least one row's `runout_polygons[*].method` is
`'alpha_beta_whitebox'` or `'alpha_beta_elliptical'` (analytical fallback).

### 1.5 🤖 Frontend sanity
Open the deployed app → AvalancheMap → any region. Runout overlays should be
**elongated / irregular polygons** (not axis-aligned rectangles).

---

## Step 2 — Ignite the Satellite Oracle (Challenge 3)

Enable autonomous Sentinel-1 SAR wet-snow ingestion.

### 2.1 🧑 Add two repository secrets
GitHub → Settings → Secrets and variables → Actions → **New repository secret**.

| Name | Value |
|---|---|
| `GEE_SERVICE_ACCOUNT_EMAIL` | `xyz@project.iam.gserviceaccount.com` |
| `GEE_SERVICE_ACCOUNT_JSON`  | *(paste full JSON key file contents)* |

Or via CLI (recommended — avoids UI copy-paste errors):
```bash
gh secret set GEE_SERVICE_ACCOUNT_EMAIL -R sanjabh1103/avalanche-insight-hub \
  -b "xyz@project.iam.gserviceaccount.com"

gh secret set GEE_SERVICE_ACCOUNT_JSON -R sanjabh1103/avalanche-insight-hub \
  < /path/to/gee-service-account.json
```

### 2.2 🧑 Manual dry-run
```bash
gh workflow run ml_pipeline.yml -f mode=gee
gh run list --workflow=ml_pipeline.yml -L 3
gh run watch   # interactive
```

### 2.3 🤖 Verification
- GitHub Actions log contains: `[gee_extractor] processed N Sentinel-1 scenes`
- Supabase row count check:
  ```sql
  SELECT count(*), max(created_at)
  FROM   avalanche_events
  WHERE  source = 'gee_sar';
  ```
  ✅ Count increases after weekly Monday 03:00 UTC run.

### 2.4 Rollback
Delete either secret → the job self-skips (`exit 0`), legacy state preserved.

---

## Step 3 — Prime the ML Ground Truth Engine (Challenges 5, 12, 13)

Gate training on verified high-severity events and retrain once data is sufficient.

### 3.1 🧑 Tag severe events as training-eligible (Supabase SQL editor)
```sql
-- Only severity ≥3 release-zone events poison training the least
UPDATE public.avalanche_events
   SET training_eligible = TRUE
 WHERE severity >= 3
   AND training_eligible_reason IS DISTINCT FROM 'gemini_deposit_zone';

-- Audit current usable count
SELECT count(*) AS eligible
FROM   public.avalanche_events
WHERE  training_eligible = TRUE
  AND  severity >= 3;
```
✅ `eligible ≥ 30` before moving to 3.2. Below that, KMeansSMOTE(k=5) cannot
oversample safely — `train_model.py` will exit 2 at the PSS gate.

### 3.2 🧑 Dispatch a real training run
```bash
gh workflow run ml_pipeline.yml \
  -f mode=train \
  -f pss_floor=0.45
gh run watch
```

### 3.3 🤖 Verification
```sql
SELECT status, pss_score, f1_score, trained_at, notes
FROM   public.model_status
ORDER  BY trained_at DESC
LIMIT  5;
```
✅ Latest row: `status = 'ready'`, `pss_score ≥ 0.45`, `f1_score > 0`,
`notes` no longer contains `"cold-start"`.

### 3.4 Cold-start escape hatch
If data is still thin, run once with `pss_floor=0.0` to publish a baseline
artifact; never ship below 0.45 to production users.

---

## Step 4 — Verify the Offline Field Agent (Challenge 1)

Prove the PWA Background Sync queue survives zero-connectivity field reports.

### 4.1 🧑 Desktop QA (Chrome DevTools)
1. Open deployed URL in Chrome → DevTools → **Application** tab.
2. **Service Workers** panel: confirm `sw.js` is **activated and running**.
3. **Network** tab → throttling dropdown → **Offline**.
4. Submit an Avalanche Field Report with lat=28.0, lng=86.25, severity=3.
5. UI must show the toast: *"Saved offline — will sync when reconnected"*.
6. DevTools → Application → **Background Sync** → queue
   `ingest-event-queue` contains ≥1 pending request.
7. Switch throttling back to **Online**.
8. Within 30 s, queue drains; row appears in Supabase:
   ```sql
   SELECT id, region_name, severity, source, created_at
   FROM   public.avalanche_events
   ORDER  BY created_at DESC
   LIMIT  3;
   ```
   ✅ New row with `source = 'field_report'`.

### 4.2 🧑 Mobile QA (real device)
1. Install PWA via Chrome/Safari "Add to Home Screen".
2. Enable **Airplane Mode**.
3. Submit report → observe offline banner.
4. Disable Airplane Mode → background sync replays within 60 s.
5. Confirm row via 4.1 step 8.

### 4.3 Automated regression (Playwright, optional)
```bash
npx playwright test tests/pwa-offline.spec.ts
```
If the spec doesn't exist yet, add it using the `webapp-testing` skill pattern:
`page.context().setOffline(true)` → submit → `setOffline(false)` → assert row.

---

## Cross-cutting QA — Run before declaring "Done"

### Build & type safety
```bash
npm ci
npm run build
npx tsc --noEmit
npm test
```

### Python lint
```bash
python -m py_compile backend/*.py backend/common/*.py backend/scripts/*.py
```

### Database sanity
```sql
-- 1. Source governance enforced
SELECT source, count(*) FROM avalanche_events GROUP BY source ORDER BY 2 DESC;
-- Every row should match the CHECK allow-list (no NULLs, no unknown values).

-- 2. training_eligible backfill healthy
SELECT training_eligible, training_eligible_reason, count(*)
FROM   avalanche_events GROUP BY 1, 2 ORDER BY 3 DESC;

-- 3. Forecast grid freshness
SELECT region_key, hazard_type, forecast_date, horizon_hours, updated_at
FROM   forecast_grids
ORDER  BY updated_at DESC LIMIT 10;

-- 4. Model readiness
SELECT * FROM model_status ORDER BY trained_at DESC LIMIT 1;
```

### GitHub Actions smoke
```bash
gh run list --workflow=ml_pipeline.yml -L 10
# Most recent train + infer must both be "completed success".
```

### Secrets audit (must all exist before full activation)
```bash
gh secret list -R sanjabh1103/avalanche-insight-hub
```
Required set:

- [x] `SUPABASE_URL`
- [x] `SUPABASE_SERVICE_ROLE_KEY`
- [ ] `GEE_SERVICE_ACCOUNT_EMAIL` *(Step 2)*
- [ ] `GEE_SERVICE_ACCOUNT_JSON` *(Step 2)*
- [ ] `GEMINI_API_KEY` *(optional — enables ingest-event deposit-zone classifier)*
- [ ] `OPENTOPOGRAPHY_API_KEY` *(only needed locally for Step 1.2)*

---

## Acceptance snapshot

The rollout is **Done** when **all** of these are simultaneously true:

1. `model_status.pss_score ≥ 0.45` AND `f1_score > 0` on the latest row.
2. `forecast_grids.model_metadata->>'run_physics_runout' = 'true'` on the
   latest row AND at least one non-rectangular polygon is present.
3. `avalanche_events` contains rows with `source = 'gee_sar'` created in the
   last 7 days.
4. A field report submitted offline reaches Supabase automatically once the
   device reconnects.
5. Frontend grey-voxel rule fires iff `confidence_upper − confidence_lower > 0.30`.
6. `npm run build && npx tsc --noEmit && npm test` all green on `main`.

No shipped UI (share links, CSV/JSON export, admin panel, historical events
toggle, realtime field reports) has regressed.
