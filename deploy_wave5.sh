#!/bin/bash
set -e

echo "=========================================================="
echo " Wave 5 Operational Rollout Execution Script"
echo "=========================================================="

echo "[1/6] Pushing Supabase database migrations (creates sar-masks bucket)..."
supabase db push

echo "[2/6] Configuring Supabase Edge Function admin secrets..."
supabase secrets set ADMIN_USER_EMAILS="sanjabh1103@gmail.com"

echo "[3/6] Deploying Supabase Edge Functions..."
supabase functions deploy trigger-job
supabase functions deploy run-forecast
supabase functions deploy ingest-event

echo "[4/6] Creating synthetic SnowSlide truth archive..."
python3 generate_synthetic_snowslide.py

echo "[5/6] Seeding the synthetic archive into the authoritative registry..."
# Export SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to the python script
export SUPABASE_URL=$(grep VITE_SUPABASE_URL .env | cut -d'"' -f2)
export SUPABASE_SERVICE_ROLE_KEY=$(grep SUPABASE_SERVICE_ROLE_KEY .env | cut -d'"' -f2)

python3 -m backend.scripts.seed_snowslide_truth \
  --source-zip snowslide_mock.zip \
  --set-key snowslide-heldout-v1 \
  --source-version 2026-04-25

echo "[6/6] Materializing the GEE baseline masks for the reference set..."
python3 -m backend.scripts.materialize_release_baseline_masks \
  --reference-set-key snowslide-heldout-v1

echo "=========================================================="
echo " Deployment successful! Modal deploy skipped in this script."
echo " Please run: modal deploy backend/modal_worker_app.py manually if you have your Modal token configured."
echo "=========================================================="
