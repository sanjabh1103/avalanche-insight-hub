#!/bin/bash
set -e

ANON_KEY=$(grep "^SUPABASE_ANON_KEY=" .env | cut -d= -f2- | tr -d '"')
SR_KEY=$(grep "^SUPABASE_SERVICE_ROLE_KEY=" .env | cut -d= -f2- | tr -d '"')
URL="https://fzheroisjhxnairglelv.supabase.co/functions/v1"

echo "=== 1. Netlify Frontend ==="
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://avalanche-insight-hub.netlify.app

echo ""
echo "=== 2. run-forecast ==="
curl -s -X POST "$URL/run-forecast" \
  -H "Authorization: Bearer $ANON_KEY" \
  -H "Content-Type: application/json" \
  -d '{"bbox":[45.8,6.8,46.0,7.0],"hours":1}' | head -c 500
echo ""

echo ""
echo "=== 3. trigger-job ==="
curl -s -X POST "$URL/trigger-job" \
  -H "Authorization: Bearer $ANON_KEY" \
  -H "Content-Type: application/json" \
  -d '{"type":"daily_enrichment","region_name":"Chamonix"}' | head -c 500
echo ""

echo ""
echo "=== 4. field-report-enrichment (fixed auth) ==="
curl -s -X POST "$URL/field-report-enrichment" \
  -H "Authorization: Bearer $SR_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"fieldReportId\":\"smoke-test-$(date +%s)\",\"lat\":45.9,\"lng\":6.9,\"description\":\"Smoke test\"}" | head -c 500
echo ""

echo ""
echo "=== 5. ingest-event ==="
curl -s -X POST "$URL/ingest-event" \
  -H "Authorization: Bearer $SR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"lat":45.9,"lng":6.9,"description":"Smoke test","source":"field_report"}' | head -c 500
echo ""

echo ""
echo "=== 6. run-evaluation ==="
curl -s -X POST "$URL/run-evaluation" \
  -H "Authorization: Bearer $SR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"hazard_type":"avalanche"}' | head -c 500
echo ""

echo ""
echo "=== 7. label-forecast-outcomes ==="
curl -s -X POST "$URL/label-forecast-outcomes" \
  -H "Authorization: Bearer $SR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"forecast_id":"00000000-0000-0000-0000-000000000000","days_back":7}' | head -c 500
echo ""

echo ""
echo "=== 8. ingest-snow-cover ==="
curl -s -X POST "$URL/ingest-snow-cover" \
  -H "Authorization: Bearer $SR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"region_name":"Chamonix","bbox":[45.8,6.8,46.0,7.0]}' | head -c 500
echo ""

echo ""
echo "=== 9. recent-activity-refresh ==="
curl -s -X POST "$URL/recent-activity-refresh" \
  -H "Authorization: Bearer $SR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"region_name":"Chamonix","window_days":7}' | head -c 500
echo ""

echo ""
echo "=== Done ==="
