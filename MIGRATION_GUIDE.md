# Migration Guide: Lovable → Own Supabase + Netlify

## Why Migrate?
- Full ownership of your Supabase project
- No dependency on Lovable's GitHub sync
- Can deploy Edge Functions anytime via CLI
- No monthly credit limits

## Prerequisites
- Supabase account (free tier works)
- Netlify account (free tier works)
- Supabase CLI installed: `npm install -g supabase`

---

## Step 1: Create New Supabase Project

1. Go to https://supabase.com/dashboard
2. Click "New Project"
3. Name it `avalanche-insight-hub` (or your preference)
4. Choose region closest to your users
5. **Save these values:**
   - Project ID (e.g., `abcdefghijklmnopqrst`)
   - Project URL (e.g., `https://abcdefghijklmnopqrst.supabase.co`)
   - Anon/Publishable Key (starts with `eyJ...`)
   - Service Role Key (keep secret!)

---

## Step 2: Apply Database Migrations

1. In new Supabase dashboard → **SQL Editor**
2. Run `supabase/APPLY_ALL_MIGRATIONS.sql` (copy/paste entire file)
3. Run `supabase/migrations/20260411193000_schedule_daily_enrichment.sql`
4. Verify: Check that all tables appear in **Database → Tables**

---

## Step 3: Deploy Edge Functions

### Option A: Automated Script
```bash
# Login to Supabase
supabase login

# Run deployment script
./deploy-functions.sh YOUR_PROJECT_REF
```

### Option B: Manual Deployment
```bash
supabase login

# Deploy each function
supabase functions deploy run-forecast --project-ref YOUR_PROJECT_REF
supabase functions deploy trigger-job --project-ref YOUR_PROJECT_REF
supabase functions deploy field-report-enrichment --project-ref YOUR_PROJECT_REF
supabase functions deploy ingest-snow-cover --project-ref YOUR_PROJECT_REF
supabase functions deploy label-forecast-outcomes --project-ref YOUR_PROJECT_REF
supabase functions deploy run-evaluation --project-ref YOUR_PROJECT_REF
supabase functions deploy recent-activity-refresh --project-ref YOUR_PROJECT_REF
```

Verify in Supabase Dashboard → **Edge Functions** (all 7 should appear)

---

## Step 4: Deploy Frontend to Netlify

### Option A: GitHub-Connected (Recommended)
1. Go to https://app.netlify.com/
2. "Add new site" → "Import from GitHub"
3. Select `sanjabh1103/avalanche-insight-hub`
4. Build settings:
   - Build command: `npm run build`
   - Publish directory: `dist`
5. Click **Deploy**

### Option B: Netlify CLI
```bash
npm install -g netlify-cli
netlify login
netlify init  # Create & configure new site
netlify deploy --prod
```

---

## Step 5: Configure Environment Variables

### In Netlify Dashboard → Site Settings → Environment Variables:

| Variable | Value |
|----------|-------|
| `VITE_SUPABASE_URL` | `https://YOUR_NEW_PROJECT_REF.supabase.co` |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | `YOUR_NEW_ANON_KEY` |

### In GitHub Secrets (for model training workflow):

| Secret | Value |
|--------|-------|
| `SUPABASE_SERVICE_ROLE_KEY` | `YOUR_NEW_SERVICE_ROLE_KEY` |

---

## Step 6: Update Local Development

Create/Update `.env.local`:
```
VITE_SUPABASE_URL=https://YOUR_NEW_PROJECT_REF.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=YOUR_NEW_ANON_KEY
```

---

## Verification Checklist

- [ ] All 7 Edge Functions deployed in Supabase
- [ ] Database tables created (19 tables)
- [ ] Frontend deployed on Netlify
- [ ] Environment variables set
- [ ] Test forecast generation works
- [ ] Test field report submission works
- [ ] Cron job scheduled (daily enrichment)

---

## Post-Migration: Cleanup

1. **Lovable Project**: You can keep it as backup or delete it
2. **Old Supabase Project**: Keep until migration verified, then delete
3. **Update DNS**: If you have custom domain, point to Netlify

---

## Support

If issues arise during migration:
- Check Supabase Edge Functions logs in Dashboard
- Verify environment variables are set correctly
- Test locally first with `npm run dev`
