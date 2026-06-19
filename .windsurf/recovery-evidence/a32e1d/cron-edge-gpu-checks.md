# Cron, Edge, and GPU Claim Checks

Status date: 2026-06-18

## Cron

Inventory command:

```bash
supabase db query --linked --file scripts/supabase_migration_inventory.sql
```

Result:

- All expected cron jobs are active.
- Cron commands use `private.get_supabase_url()`.
- Cron commands do not target old project `fzheroisjhxnairglelv`.
- `private.get_supabase_url()` resolves to `cyjqvqwpdgluivjoxcfl`.
- `private.get_job_dispatch_token()` returns present health status.
- `private.get_supabase_apikey()` returns present health status.

Cron auth material was installed through Supabase Vault:

- `job_dispatch_token`
- `anon_key`

No secret values are recorded in this evidence pack.

## Edge Auth

Smoke target: `trigger-job` with `static_precompute`

Observed:

- Missing authorization token: HTTP 401
- Valid job dispatch token: HTTP 200
- Valid request created a `compute_jobs` row with simulated result `{ "simulated": true, "regionsComputed": 12 }`

This proves the background-job auth path rejects anonymous calls and accepts the narrow job-token path needed by cron.

## Modal/GPU

GitHub Actions and Supabase Edge secret listings show Modal-related secret names
exist for the new project/repository. Secret values were not printed.

- `MODAL_TOKEN_ID`
- `MODAL_TOKEN_SECRET`
- `MODAL_WORKER_TOKEN`
- `MODAL_WORKER_URL`

Local ASGI import smoke:

```bash
PYTHONPATH=. .venv/bin/python - <<'PY'
from backend.modal_worker_app import create_fastapi_app
expected = {'/health','/sar-segment','/train-sar-unet','/train-mtslstm','/infer-mtslstm','/evaluate-release'}
app = create_fastapi_app()
routes = {getattr(route, 'path', None) for route in app.routes}
missing = sorted(expected - routes)
print({'modal_app_import': 'ok', 'expected_routes_present': not missing, 'missing': missing, 'route_count': len(routes)})
if missing:
    raise SystemExit(1)
PY
```

Observed:

- `modal_app_import`: ok
- `expected_routes_present`: true
- `missing`: []
- `route_count`: 13 after the `/health` route addition

Follow-up code check on 2026-06-19:

- `/health` was added as a non-mutating ASGI route.
- The health payload reports Modal runtime status plus configured GPU function
  names without launching GPU work or returning secrets.
- Unit coverage now asserts `/health` exists and reports GPU-backed remote
  functions: `sar_segment_remote`, `train_sar_unet_remote`,
  `evaluate_sar_checkpoint_remote`, and `train_mts_lstm_remote`.
- `.github/workflows/backend-ci.yml` expects `/health` in its Modal import
  smoke.

GitHub deployment history:

- Latest checked deployment run:
  `https://github.com/sanjabh1103/avalanche-insight-hub/actions/runs/25589982702`
- Run date: 2026-05-09
- Conclusion: success
- The log recorded the deployed ASGI worker URL and the expected remote
  functions.

Live route probe on 2026-06-18:

- `/`: HTTP 404, Modal workspace disabled
- `/sar-segment`: HTTP 404, Modal workspace disabled
- `/train-sar-unet`: HTTP 404, Modal workspace disabled
- `/train-mtslstm`: HTTP 404, Modal workspace disabled
- `/infer-mtslstm`: HTTP 404, Modal workspace disabled
- `/evaluate-release`: HTTP 404, Modal workspace disabled

No authorization token was sent and no GPU/training job was launched.

Live health probe on 2026-06-19:

```bash
set -a
source .env
set +a
.venv/bin/python scripts/modal_worker_health_check.py
```

Observed:

- `/health`: HTTP 404
- Error text: `modal-http: workspace ... is disabled`
- No authorization token was sent and no GPU/training job was launched.

Redeploy and live health restoration on 2026-06-19:

- Commit: `4763d71 fix: restore modal health and all-region recovery gates`
- Workflow run:
  `https://github.com/sanjabh1103/avalanche-insight-hub/actions/runs/27808891166`
- Result: success
- Canonical endpoint:
  `https://sanjabh11--avalanche-modal-worker-worker-api.modal.run`
- Health check:

```bash
MODAL_WORKER_URL='https://sanjabh11--avalanche-modal-worker-worker-api.modal.run' \
.venv/bin/python scripts/modal_worker_health_check.py
```

Observed:

- HTTP 200
- `ok=true`
- `missing_routes=[]`
- `missing_gpu_functions=[]`
- No authorization token was sent and no GPU/training job was launched.

This proves the Modal worker ASGI app and expected candidate routes exist in the
repo and are currently reachable through the public Modal endpoint. It does not
prove a SAR/MTS-LSTM model is scientifically promoted or that GPU drives public
forecast scoring. The demo claim remains bounded:

Modal/GPU is implemented as an off-path candidate compute plane. It is not part of the current live public scorer proof.

Do not claim SAR U-Net, MTS-LSTM, or GPU drives the public forecast unless the
relevant dispatch workflow runs successfully and a separate release gate is run.
