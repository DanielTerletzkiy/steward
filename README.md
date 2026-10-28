# Steward

Household management for Home Assistant, built like Music Assistant: a Python server plus a thin HA integration. It covers:
- stock and shopping
- chores and tasks
- REWE eBons
- equipment with manuals
- a wardrobe with outfit suggestions
- recipes and a meal plan
- scanning by barcode and AI

The plan and decisions are in [PLAN.md](PLAN.md).

## Layout

| Path | What |
|---|---|
| `server/steward_server/` | FastAPI server: REST API under `/api`, events on `/api/ws`, sign-in under `/auth`, web UI from `static/` |
| `frontend/` | Vue 3 + Vuetify web UI; `npm run build` writes into `server/steward_server/static` |
| `custom_components/steward/` | Home Assistant integration |
| `app/`, `repository.yaml` | Home Assistant app (formerly "add-on"): manifest, Dockerfile, translations, docs |
| `dev/` | Docker Compose demo (Home Assistant + Steward) and helper scripts |
| `samples/ebons/` | Real REWE eBons for tests (git-ignored, personal data) |

## Install in your Home Assistant

See [INSTALL.md](INSTALL.md). In short:
1. `dev/scripts/build_app.sh` stages the app in `dist/ha-app/steward`.
2. Copy that folder to HA's `/addons` and `custom_components/steward` to `/config/custom_components`, over SSH.
3. Install **Steward** from **Local apps**.

The app:
- opens in the sidebar through ingress, signed in as your HA user;
- announces itself, so HA shows **Discovered: Steward** and the integration sets up in one click.

`dev/scripts/build_app.sh --docker` also builds the image the way the Supervisor would. HACS and the app store's "Add repository" need published images and a public repository (see INSTALL.md).

## Run the demo (HA Container + Docker)

```bash
cd frontend && npm ci && npm run build && cd ..
docker compose -f dev/docker-compose.yml up -d --build
```

- Home Assistant: http://localhost:8123 (the local test login is in `dev/.env`)
- Steward UI: http://localhost:8095. It asks you to **sign in with Home Assistant** (HA's own OAuth flow); it is also in HA's sidebar as "Steward".
- Dashboard: "Household" in HA's sidebar. Recreate it with `server/.venv/bin/python dev/scripts/dashboard.py <HA access token>`.

On an empty database the server seeds demo data:
- products and stock, including the eBons from `samples/ebons/`
- chores and tasks
- equipment with a sample manual
- clothes with generated pictures
- recipes and a meal plan

Each module seeds only when its own tables are empty. Delete `dev/data/` to start over.

The integration authenticates with `STEWARD_API_TOKEN` (`dev-token` in the demo). `STEWARD_TRUST_ALL=true` still exists for quick local development, but don't use it outside localhost; the app ignores it.

## AI

Open Steward → Settings → AI to choose a provider for each job (scanning groceries, tagging clothes, suggesting outfits):

- **Home Assistant AI Task** (the default when HA offers one): whatever AI you set up in HA, local (Ollama) or cloud. Requests go through the integration; images are handed over through HA's media folder.
- **Direct:** Anthropic Claude, OpenAI, Google Gemini, Ollama, or any OpenAI-compatible endpoint (LM Studio, vLLM, OpenRouter).

Without AI, everything still works: barcodes use Open Food Facts, and outfits come from the rule engine. The AI only adds photo recognition, clothing tags and taste.

## Laundry

- **Wear counts:** every piece has "wears before washing", from its category (t-shirts 1, jeans 6, sweaters 4, …).
- **What happens at the count:**
  - Socks, underwear and t-shirts go into the laundry automatically.
  - Jeans, sweaters and the like ask first: they stop being suggested and appear under "Ready for the wash?" ("To the laundry" / "Still fine"). Each piece can override this.
- **With a washer linked to HA:**
  - Starting it means the laundry bin went in ("washing").
  - Finishing means the clothes are drying. They aren't suggested for 24 h (configurable: right away, 12/24/48 h, or until you mark them dry). A linked dryer finishing marks them dry.
- **Without a linked washer:** the same steps are buttons in the wardrobe.

## Appliances

Link a piece of equipment to a Home Assistant device, or to single entities, in its detail page. Steward then:

- **Shows live status:** run state, remaining time, battery.
- **Recognizes finished runs**, from any of:
  - a vacuum going back to its dock;
  - completion events, such as LG ThinQ's `washing_is_complete`;
  - run-state sensors reaching `end` or `finished`.
- **Reacts per appliance type:**
  - a vacuum run completes its linked chores (e.g. "Vacuum");
  - a washer, dryer or dishwasher makes its chores due (e.g. "Hang up the laundry");
  - a washer moves the laundry bin through washing and drying (see Laundry), or asks you when it's done.
- **Controls vacuums from Steward:** start, pause, dock, locate. Only the linked vacuum entity can be commanded.
- **Fires `steward_appliance_finished` in HA** (with the appliance, the chores and the laundry outcome), for your own notifications.

The demo HA simulates an LG ThinQ washer and a robot vacuum with helpers. Change `input_select.demo_washer_state` or press start on `vacuum.demo_robot` to watch it work.

## Develop the server

```bash
cd server
uv sync
uv pip install --no-deps rewe-ebon-parser
STEWARD_DATA_DIR=./data STEWARD_TRUST_ALL=1 STEWARD_SEED_DEMO=1 STEWARD_DEMO_RECEIPTS=../samples/ebons .venv/bin/python -m steward_server.main
TZ=Europe/Berlin .venv/bin/python -m pytest -q
```
