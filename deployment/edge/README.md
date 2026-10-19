# F15: Edge Deployment Mode — Avalanche Insight Hub

Air-gapped Docker Compose profile for Partner Dhruva-3 or similar HPC environments.
Runs entirely without external API calls (no Supabase, no GEE, no Open-Meteo, no USGS).

## Prerequisites

- Docker Engine 24+ and Docker Compose v2+
- Model weights (LSTM, RF, GNN) placed in `data/model_weights/`
- DEM tiles (GeoTIFF) placed in `data/dem/`
- Pre-built frontend in `data/frontend_dist/` (run `npm run build` and copy `dist/`)
- PostgreSQL init SQL in `sql/init/` (schema migrations)
- 8GB+ RAM, 4+ CPU cores recommended

## Quick Start

```bash
# 1. Copy and edit environment
cp .env.edge.example .env.edge
# Edit .env.edge with your passwords and paths

# 2. Prepare data directories
mkdir -p data/{model_weights,dem,sar_cache,artifacts,frontend_dist}
# Place model weights, DEM tiles, and built frontend

# 3. Start core services
docker compose --env-file .env.edge up -d postgres redis

# 4. Run database migrations
docker compose --env-file .env.edge exec backend python -m backend.common.migrations

# 5. Start backend + frontend
docker compose --env-file .env.edge up -d backend frontend

# 6. (Optional) Run local SAR processor
docker compose --env-file .env.edge --profile sar up sar_processor
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_DB` | `avalanche_insight` | Database name |
| `POSTGRES_USER` | `avalanche` | Database user |
| `POSTGRES_PASSWORD` | `changeme_edge` | **CHANGE THIS** — database password |
| `FRONTEND_PORT` | `8080` | Nginx port for frontend |
| `MODEL_WEIGHTS_DIR` | `./data/model_weights` | Host path for model weights |
| `DEM_DIR` | `./data/dem` | Host path for DEM GeoTIFF tiles |
| `SAR_CACHE_DIR` | `./data/sar_cache` | Host path for local SAR scene cache |
| `ARTIFACT_DIR` | `./data/artifacts` | Host path for forecast artifacts |
| `FRONTEND_DIST_DIR` | `./data/frontend_dist` | Host path for built frontend |
| `CONFIG_DIR` | `./config` | Host path for config files |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `BRIER_BLOCK_THRESHOLD` | `0.15` | UQ Brier score publish block threshold |
| `CONFORMAL_ALPHA` | `0.1` | Conformal prediction miscoverage rate |
| `GNN_RUNOUT_ENABLED` | `true` | Enable GNN runout dynamics |
| `CONTINUOUS_LEARNING_ENABLED` | `true` | Enable auto-labeling from new detections |

## Services

| Service | Port | Description |
|---|---|---|
| `postgres` | 5432 | Local PostgreSQL 16 (replaces Supabase) |
| `redis` | 6379 | Redis for async task queue |
| `backend` | — | Python inference engine (runs daily_inference) |
| `frontend` | 8080 | Nginx serving static frontend build |
| `sar_processor` | — | Local SAR processor (optional, `--profile sar`) |

## Fallback Behavior

When `EDGE_MODE=true`, the system:
- Uses local PostgreSQL instead of Supabase REST API
- Loads model weights from `/opt/model_weights/` instead of cloud storage
- Reads DEM tiles from `/opt/dem/` instead of cloud storage
- Uses cached SAR scenes from `/opt/sar_cache/` instead of GEE
- Disables seismic API calls (USGS) — uses cached/manual seismic data
- Disables Open-Meteo API — uses last-known weather or manual input
- GNN runout uses heuristic fallback if no weights loaded
- Brier blocking still active (UQ is computed from model metadata)
- Continuous learning still active (labels stored in local DB)

## Smoke Test

```bash
# Check all services are healthy
docker compose --env-file .env.edge ps

# Check backend can connect to database
docker compose --env-file .env.edge exec backend python -c "
from backend.common.config import load_settings
s = load_settings()
print(f'Edge mode: {s.edge_mode}')
print(f'DB URL: {s.local_db_url}')
print(f'Model weights: {s.local_model_weights_path}')
"

# Check frontend is served
curl -s http://localhost:8080 | head -5

# Run a dry-run inference
docker compose --env-file .env.edge exec backend python -m backend.daily_inference --dry-run --region-key all
```

## Network Isolation

All services run on the `edge_internal` Docker network with `internal: true`
by default, which blocks outbound internet access. During initial setup,
temporarily set `internal: false` in `docker-compose.edge.yml` to pull Docker
images, then switch back to `internal: true` for production air-gapped operation.

## Signed Image Mirroring For Air-Gapped Sites

Production air-gapped deployments should not pull images directly from the
internet. Build or pull images on a connected staging machine, verify/sign them,
mirror them into Harbor, Artifactory, or another private registry, then deploy
only from that registry inside the offline network.

Example connected-side workflow:

```bash
# 1. Set the private registry namespace used inside the air-gapped network.
export EDGE_REGISTRY=registry.edge.local/avalanche
export IMAGE_TAG=$(git rev-parse --short HEAD)

# 2. Build project images and tag them for the private registry.
docker build -t "$EDGE_REGISTRY/backend:$IMAGE_TAG" -f deployment/edge/Dockerfile.backend .

# 3. Mirror third-party base services into the same registry namespace.
#    Frontend is served via nginx:alpine with volume-mounted static files
#    (data/frontend_dist/) — no separate frontend Dockerfile is needed.
skopeo copy docker://nginx:alpine docker://"$EDGE_REGISTRY/nginx:alpine"
skopeo copy docker://postgres:16 docker://"$EDGE_REGISTRY/postgres:16"
skopeo copy docker://redis:7-alpine docker://"$EDGE_REGISTRY/redis:7-alpine"

# 4. Sign images before export or registry sync.
cosign sign --key cosign.key "$EDGE_REGISTRY/backend:$IMAGE_TAG"
cosign sign --key cosign.key "$EDGE_REGISTRY/frontend:$IMAGE_TAG"
cosign sign --key cosign.key "$EDGE_REGISTRY/postgres:16"
cosign sign --key cosign.key "$EDGE_REGISTRY/redis:7-alpine"

# 5. Export image tarballs when registry replication is not available.
docker save \
  "$EDGE_REGISTRY/backend:$IMAGE_TAG" \
  "$EDGE_REGISTRY/frontend:$IMAGE_TAG" \
  "$EDGE_REGISTRY/postgres:16" \
  "$EDGE_REGISTRY/redis:7-alpine" \
  -o avalanche-edge-images.tar
```

Offline-side verification and import:

```bash
# 1. Load the signed image bundle or sync it into the local Harbor/Artifactory mirror.
export EDGE_REGISTRY=registry.edge.local/avalanche
export IMAGE_TAG=<approved-release-tag>
docker load -i avalanche-edge-images.tar

# 2. Verify signatures before Compose starts services.
cosign verify --key cosign.pub "$EDGE_REGISTRY/backend:$IMAGE_TAG"
cosign verify --key cosign.pub "$EDGE_REGISTRY/frontend:$IMAGE_TAG"
cosign verify --key cosign.pub "$EDGE_REGISTRY/postgres:16"
cosign verify --key cosign.pub "$EDGE_REGISTRY/redis:7-alpine"

# 3. Deploy from the private registry tags only.
docker compose --env-file .env.edge -f docker-compose.edge.yml up -d
```

Before deployment, update `docker-compose.edge.yml` image references to private
registry tags or set registry-prefixed image variables in `.env.edge`. Keep
`internal: true`; PAC files or temporary egress exceptions are setup-only tools
and must not be required for steady-state inference.

## Pre-Deployment Checklist

Before deploying to a production air-gapped environment:

- [ ] **Change PostgreSQL password** — override `POSTGRES_PASSWORD` in `.env.edge` (default `changeme_edge` is a placeholder)
- [ ] **Verify `internal: true`** on `edge_internal` network in `docker-compose.edge.yml` (set to `false` only during initial image pull)
- [ ] **Mirror all images** into the approved Harbor/Artifactory/private registry namespace
- [ ] **Verify image signatures offline** with `cosign verify --key cosign.pub ...`
- [ ] **Confirm Compose uses private registry tags only** — no Docker Hub, GHCR, or internet registry references remain
- [ ] **Place model weights** in `data/model_weights/`
- [ ] **Place DEM tiles** in `data/dem/`
- [ ] **Build and place frontend** in `data/frontend_dist/`
- [ ] **Run database migrations** via `docker compose exec backend python -m backend.common.migrations`
- [ ] **Verify smoke test** passes (see Smoke Test section)
- [ ] **Configure audit trail rotation** — set `AUTO_LABEL_AUDIT_MAX_SIZE_MB` if default 10 MB is insufficient

## Cold-Start Sequence

1. Start PostgreSQL and Redis
2. Run database migrations
3. Place model weights in `data/model_weights/`
4. Place DEM tiles in `data/dem/`
5. Build frontend (`npm run build`) and copy `dist/` to `data/frontend_dist/`
6. Start backend and frontend services
7. Run first inference cycle (may use fallback weather/terrain data)
8. Verify forecast output in `data/artifacts/`
