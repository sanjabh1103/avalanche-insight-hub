# Supabase Setup Guide - Lovable Project

## Project Details
- **Supabase Project ID**: `rmzipvwqafrxhhuinggf`
- **Supabase URL**: `https://rmzipvwqafrxhhuinggf.supabase.co`
- **Lovable Project**: `https://lovable.dev/projects/449cc2d7-09f8-469d-a41b-e012a283cfb6`

## Current Status

### ✅ Completed in Codebase
1. **FieldReportForm.tsx** - UI validation for lat (-90 to 90) and lng (-180 to 180)
2. **Migration file** - `20260411183000_validate_field_report_coordinates.sql` adds DB constraint
3. **RLS policies** - All tables have policies defined in migrations

### ⚠️ Needs Verification on Live Database
Since this is a Lovable-managed project, the migrations need to be applied via the Lovable SQL Editor.

## Step-by-Step Instructions

### Step 1: Open Lovable SQL Editor
1. Go to your Lovable project: `https://lovable.dev/projects/449cc2d7-09f8-469d-a41b-e012a283cfb6`
2. Navigate to **Database** section
3. Click **SQL Editor** (or "New Query")

### Step 2: Run the Complete Setup Script
1. Open `supabase/complete_setup_check.sql` in your editor
2. Copy the entire contents
3. Paste into Lovable SQL Editor
4. Click **Run**

### Step 3: Interpret Results
The script will output:
- **TABLE RLS STATUS** - Shows if RLS is enabled on each table
- **FIELD_REPORTS CONSTRAINTS** - Shows if coordinate constraint exists
- **RLS POLICIES** - Lists all active policies
- **FINAL RLS STATUS** - Summary with ✅ or ❌ indicators

### Step 4: Fix Any Issues
If any table shows "DISABLED" or constraint is missing:
1. The script automatically attempts to fix RLS (idempotent)
2. The script automatically adds the constraint if missing
3. Re-run to verify fixes applied

## Alternative: Supabase CLI (If You Want Direct Access)

### Prerequisites
1. Get Supabase access token from https://app.supabase.com/account/tokens
2. Run:
```bash
supabase login --token YOUR_TOKEN
supabase link --project-ref rmzipvwqafrxhhuinggf
supabase db push
```

### Note on CLI Access
Lovable projects are typically managed by Lovable, so CLI access may require:
- Database password from Lovable Database settings
- Or requesting Lovable support to apply migrations

## Testing the Fix

### Test Valid Coordinates
1. Open app at `http://localhost:8080` (or deployed URL)
2. Click "Report Avalanche Observation"
3. Enter: Lat `39.5`, Lng `-106.5`
4. Submit - Should succeed

### Test Invalid Latitude
1. Enter: Lat `95`, Lng `-106.5`
2. Submit - Should show: "Invalid latitude. Must be between -90 and 90."

### Test Invalid Longitude
1. Enter: Lat `39.5`, Lng `200`
2. Submit - Should show: "Invalid longitude. Must be between -180 and 180."

## Files Reference

| File | Purpose |
|------|---------|
| `supabase/complete_setup_check.sql` | One script to verify & fix everything |
| `supabase/verify_schema.sql` | Basic schema verification queries |
| `supabase/migrations/20260411183000_validate_field_report_coordinates.sql` | Coordinate constraint migration |
| `src/components/FieldReportForm.tsx` | UI with validation (already fixed) |

## Next Steps After SQL Setup

1. ✅ Run the complete setup script in Lovable
2. ✅ Verify all tables show "ENABLED" for RLS
3. ✅ Verify coordinate constraint exists
4. ✅ Test the field report form with valid/invalid coordinates
5. ✅ Commit any changes to GitHub if needed

## Troubleshooting

### "Cannot connect to database" in SQL Editor
- Refresh Lovable page
- Try again in 30 seconds
- Contact Lovable support if persistent

### Constraint already exists error
- This is fine - the script is idempotent
- Just means the constraint was already applied

### RLS still disabled after script
- Manually toggle RLS in Lovable Database UI
- Or contact Lovable support to apply migrations

## Security Summary

After setup complete:
- ✅ RLS enabled on all 7 tables
- ✅ Policies: Public can read events/forecasts, users can manage own reports
- ✅ Database constraint prevents invalid coordinates
- ✅ UI validation prevents invalid coordinates
- ✅ Service role can manage all tables
