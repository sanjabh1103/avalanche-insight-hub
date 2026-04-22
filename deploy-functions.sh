#!/bin/bash
# Deploy all Edge Functions to new Supabase project
# Usage: ./deploy-functions.sh <your-new-project-ref>

PROJECT_REF=$1

if [ -z "$PROJECT_REF" ]; then
  echo "Usage: ./deploy-functions.sh <project-ref>"
  echo "Example: ./deploy-functions.sh abcdefghijklmnopqrst"
  exit 1
fi

echo "Deploying Edge Functions to project: $PROJECT_REF"

# Functions invoked directly from the browser without a signed-in session.
# The app uses the new Supabase publishable key (sb_publishable_*) which is
# NOT a JWT, so these functions must be deployed with --no-verify-jwt or
# invocations will fail with 401 Unauthorized.
PUBLIC_FUNCTIONS=(
  "run-forecast"
  "trigger-job"
)

# Back-office / delegated functions that keep JWT verification.
PRIVATE_FUNCTIONS=(
  "field-report-enrichment"
  "ingest-event"
  "ingest-snow-cover"
  "label-forecast-outcomes"
  "run-evaluation"
  "recent-activity-refresh"
)

echo "Deploying PUBLIC functions..."
supabase functions deploy run-forecast --project-ref "$PROJECT_REF" --no-verify-jwt
supabase functions deploy trigger-job --project-ref "$PROJECT_REF" --no-verify-jwt

echo "Deploying PRIVATE (authenticated) functions..."
for fn in "${PRIVATE_FUNCTIONS[@]}"; do
  echo "Deploying $fn..."
  supabase functions deploy "$fn" --project-ref "$PROJECT_REF"
  if [ $? -eq 0 ]; then
    echo "✓ $fn deployed successfully"
  else
    echo "✗ $fn deployment failed"
  fi
  echo ""
done

echo "Deployment complete!"
