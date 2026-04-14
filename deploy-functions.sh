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

FUNCTIONS=(
  "run-forecast"
  "trigger-job"
  "field-report-enrichment"
  "ingest-snow-cover"
  "label-forecast-outcomes"
  "run-evaluation"
  "recent-activity-refresh"
)

for func in "${FUNCTIONS[@]}"; do
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
