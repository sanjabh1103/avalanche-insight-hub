#!/usr/bin/env bash
# Run RLS integration tests against local Supabase stack.
#
# Prerequisites:
#   - Docker installed and running
#   - Supabase CLI installed (npm i -g supabase)
#
# Usage:
#   bash scripts/run_rls_integration_tests.sh
#
# This script:
#   1. Starts local Supabase stack (Postgres, Auth, etc.)
#   2. Resets DB to apply all migrations
#   3. Reads service_role and anon keys from supabase status
#   4. Runs RLS integration tests
#   5. Stops Supabase stack on exit

set -euo pipefail

echo "=== RLS Integration Test Runner ==="

if ! command -v supabase &> /dev/null; then
    echo "ERROR: supabase CLI not found. Install with: npm i -g supabase"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo "ERROR: Docker is not running. Start Docker first."
    exit 1
fi

echo "1. Starting Supabase local stack..."
supabase start

echo "2. Resetting database (applying all migrations)..."
supabase db reset

echo "3. Reading API keys..."
STATUS_OUTPUT=$(supabase status)
SUPABASE_URL="http://127.0.0.1:54321"
SERVICE_KEY=$(echo "$STATUS_OUTPUT" | grep -i 'service_role' | head -1 | awk -F': ' '{print $2}' | tr -d '[:space:]')
ANON_KEY=$(echo "$STATUS_OUTPUT" | grep -i 'anon key' | head -1 | awk -F': ' '{print $2}' | tr -d '[:space:]')

if [ -z "$SERVICE_KEY" ] || [ -z "$ANON_KEY" ]; then
    echo "ERROR: Could not extract API keys from supabase status"
    supabase stop
    exit 1
fi

echo "4. Running RLS integration tests..."
export SUPABASE_URL="$SUPABASE_URL"
export SUPABASE_SERVICE_KEY="$SERVICE_KEY"
export SUPABASE_ANON_KEY="$ANON_KEY"

python -m pytest backend/tests/test_rls_integration.py -v --tb=short
TEST_EXIT=$?

echo "5. Stopping Supabase stack..."
supabase stop

exit $TEST_EXIT
