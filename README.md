# Steward

Household management for Home Assistant: stock, shopping lists, chores, tasks and receipts, built like Music Assistant (a Python server plus a thin HA integration). The plan and decisions are in [PLAN.md](PLAN.md).

## Layout

| Path | What |
|---|---|
| `server/steward_server/` | FastAPI server: REST API under `/api`, events on `/api/ws`, web UI from `static/` |
| `frontend/` | Vue 3 + Vuetify web UI; `npm run build` writes into `server/steward_server/static` |
| `custom_components/steward/` | Home Assistant integration |
| `dev/` | Docker Compose demo (Home Assistant + Steward) and helper scripts |
| `samples/ebons/` | Real REWE eBons for tests (git-ignored, personal data) |

## Run the demo

```bash
cd frontend && npm ci && npm run build && cd ..
docker compose -f dev/docker-compose.yml up -d --build
```

- Home Assistant: http://localhost:8123 (the local test login is in `dev/.env`)
- Steward UI: http://localhost:8095, also in HA's sidebar as "Steward"
- Dashboard: "Household" in HA's sidebar (recreate with `server/.venv/bin/python dev/scripts/dashboard.py <HA access token>`)

The server seeds demo data on an empty database, including the eBons from `samples/ebons/`. Delete `dev/data/` to start over.

In the demo the server runs with `STEWARD_TRUST_ALL=true`, so the sidebar iframe needs no token. Don't use that setting outside localhost; the integration authenticates with `STEWARD_API_TOKEN` (`dev-token` in the demo).

## Develop the server

```bash
cd server
uv sync
uv pip install --no-deps rewe-ebon-parser
STEWARD_DATA_DIR=./data STEWARD_TRUST_ALL=1 STEWARD_SEED_DEMO=1 STEWARD_DEMO_RECEIPTS=../samples/ebons .venv/bin/python -m steward_server.main
```
