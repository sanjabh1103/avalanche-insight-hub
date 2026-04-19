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
  "ingest-snow-cover"
  "label-forecast-outcomes"
  "run-evaluation"
  "recent-activity-refresh"
)

for func in "${PUBLIC_FUNCTIONS[@]}"; do
  echo "Deploying $func (public, --no-verify-jwt)..."
  supabase functions deploy "$func" --project-ref "$PROJECT_REF" --no-verify-jwt
  if [ $? -eq 0 ]; then
    echo "✓ $func deployed successfully"
  else
    echo "✗ $func deployment failed"
  fi
  echo ""
done

for func in "${PRIVATE_FUNCTIONS[@]}"; do
  echo "Deploying $func..."
  supabase functions deploy "$func" --project-ref "$PROJECT_REF"
  if [ $? -eq 0 ]; then
    echo "✓ $func deployed successfully"
  else
    echo "✗ $func deployment failed"
  fi
  echo ""
done

echo "Deployment complete!"
