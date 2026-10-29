# Steward: plan v3

*v3, 2026-10-28. Decisions settled; a first demo is running (see "Status").*

## Decisions (v3)

- **Name:** Steward, HA domain `steward`.
- **Install target:** HA OS, so Steward ships as an HA app with an ingress sidebar panel. Plain Docker stays possible for HA Container installs.
- **AI providers:** HA's AI Task (covers any AI already set up in HA, including local models through HA's Ollama integration), plus direct Ollama, OpenAI, Anthropic (Claude) and Google (Gemini). The provider is chosen per job, e.g. local for scanning, cloud for outfits.
- **People:** HA `person` entities are the household. The integration mirrors them into Steward (id, name, linked HA user, picture, presence); new people get their own chore list and sensors automatically, and removed people are kept in history. One person today, more later without migration.
- **Order:** the default in section 8.
- **Grocy import:** not needed (no existing Grocy). Dropped from the roadmap, as is the Grocy API compatibility layer.
- **eBons:** five real eBons are in `samples/ebons/` (git-ignored). The MIT `rewe-ebon-parser` reads all five correctly: item sums match the totals, REWE Bonus and non-Bonus layouts both work. Observed: names are upper case, umlauts transliterated (`ERDNUESSE`), cut to 16 characters (`KR.BUTTERBAGUETT`); deposit lines follow their drink; bottle returns are negative lines; the same text can mean two products (`ZERO CHERRY` as cans and as 6×1,5 l); no weighed goods yet in the sample.

## Status (2026-10-28)

Runs locally (`docker compose -f dev/docker-compose.yml up -d`), plus an installable HA app (`dev/scripts/build_app.sh`).

**Server**
- Stock ledger, shopping lists, chores with schedules and assignment, tasks.
- REWE eBon import with alias and fuzzy matching.
- Equipment with photos, manual PDFs (full-text search with page numbers), warranty, consumables and chores.
- Appliances linked to HA devices or entities: live status, finished runs (vacuum docking, LG ThinQ completion events, run-state sensors), chores completed or made due, laundry prompt, vacuum commands.
- Wardrobe: clothes with photos and qualities, wear and laundry tracking, outfits, style profiles.
- Outfit engine: rules, then AI, then the rules check again. Weather comes from the HA weather entity, with Open-Meteo as a fallback.
- AI provider layer: HA AI Task through the integration, Anthropic, OpenAI, Gemini, Ollama, OpenAI-compatible. One provider per job.
- Scanning: local barcodes, then Open Food Facts (cached), GS1 codes with expiry dates, AI photo recognition.
- Recipes: website import (schema.org), "can I cook it" against stock, cook, missing items to the list.
- Meal plan.
- "Sign in with Home Assistant" for direct access; ingress identity in the app; Supervisor discovery.
- Kitchen terminals (0.3.0): a paired kiosk page for a Raspberry Pi with a USB scanner, limited to stock and scanning; Pi setup script.

**Integration**
- To-do lists, sensors, calendars (chores, due dates, tasks, warranties, meal plan).
- Today's outfit as a sensor and image per person.
- Buttons, and actions for stock, chores, wardrobe, scanning, recipes and manuals.
- Answers the server's AI Task and weather requests.

**Not yet**
- Alembic (new columns are added automatically for now).
- Published multi-arch images and CI.
- Batteries, custom fields and lists, labels and printing, IMAP intake.
- ESPHome scan station, Assist intents and LLM tools, blueprints.
- AI quality is untested: no provider credentials were available while building.

## TL;DR

- **What:** all of Grocy (stock, shopping lists, recipes, meal plan, chores, tasks, batteries, equipment, calendar, custom fields and lists, labels) rebuilt as a Home Assistant **app + integration**, the way Music Assistant does it. No PHP.
- **Shape:** a Python server that runs as an HA app (HA's name for add-ons since 2026.2) or as plain Docker. It hosts its own web UI, which shows up in the HA sidebar. A thin integration turns it into entities, actions, voice intents and LLM tools.
- **Beyond Grocy:**
  1. Scanning: barcode first, then an AI vision model for loose items, best-before dates, category and storage place.
  2. Receipts: REWE eBons are read from your mailbox and matched to real products, so every trip shows what you paid for what.
  3. Wardrobe: photograph your clothes once. Every morning the AI puts an outfit together from what is clean, based on the weather forecast, your calendar and your taste.
- **HA-native twists:** chores go to HA people and can complete themselves from device signals (dishwasher, robot vacuum, waste calendar). Batteries are linked to HA devices. Tasks and chores show up as HA to-do lists. Appliance manuals answer questions through Assist.
- **Stack:** Python 3.13 · FastAPI · SQLite (SQLAlchemy + Alembic) · Vue 3 + Vuetify · Lit cards. AI goes through HA's AI Task by default; Anthropic, OpenAI-compatible endpoints (including Ollama) and Gemini can be called directly.
- **Order:** foundation → stock & shopping → chores, tasks & batteries → AI + scanning → wardrobe → receipts → recipes & meal plan → equipment and the rest of Grocy. Every phase ships something usable, and the order is yours to change.
- **Needs your call:** section 12.

## What it should feel like

- 7:00: "6–11 °C, rain from 16:00. Grey merino sweater, dark jeans, rain jacket, leather boots", with a picture of the outfit and the buttons *Wear this* · *Another one*.
- The dishwasher finishes, and "empty the dishwasher" goes to whoever has done it least.
- You get home from REWE. The eBon is already in: "Trip 47,12 € · 21 of 24 lines matched · 3 to check". The scan station beeps through the bag; for the chicken, your phone asks for one photo of the date.
- 19:00, as you get home: "Your turn: the Gelbe Tonne goes out tonight (pickup tomorrow)". You tap *Done*.
- "Okay Nabu, wie entkalke ich die Kaffeemaschine?" The answer comes from the manual you uploaded, with the page number.
- You swap the battery in a Zigbee sensor. The swap is logged and one CR2032 leaves stock.

## 1. Goals and principles

**Goals**

1. Everything Grocy does, for the whole household, not just the kitchen.
2. Native in HA: sidebar panel with your HA login, UI in your HA theme, entities and voice that behave like built-ins.
3. Little typing: barcodes, AI and receipt matching do the data entry; you confirm.
4. Know what things cost: per-item prices for every trip.
5. Get dressed without thinking: outfits that fit the weather, the day and your taste.

**Principles**

- **HA does what HA already does.** Users, people, presence, notifications, voice, calendar UI and automations stay in HA. Our modules plug into them instead of rebuilding them.
- **Modular.** Every module can be switched off, like Grocy's feature flags, and its screens and HA entities go with it.
- **Confirm, don't type.** AI and matching propose, you confirm with one tap. Nothing low-confidence is saved silently.
- **Rules first, AI second.** Hard constraints live in code: only clean clothes, a waterproof layer when rain is likely, receipt lines that add up to the total. The AI only chooses among options that already pass them, and its answer is checked against the rules again. (In one published outfit experiment an LLM suggested T-shirt and shorts for a cold day.)
- **Offline core, AI as an accelerator.** Barcodes, the local catalog, the Open Food Facts cache, learned receipt aliases, chores and the rule part of the outfit engine all work without AI.
- **Every stock change is a ledger entry.** Append-only transactions that record who, how (scan, receipt, voice, automation) and what they link to (receipt line, recipe, chore). Undo, history, statistics and learning all read from it.
- **Thin integration, boring server.** Logic lives in the server; the integration only maps it into HA.

**Not planned:** hosting for several households, nutrition tracking, online ordering, a native mobile app (the PWA and the HA companion app cover phones).

## 2. Architecture

### 2.1 Why an app plus an integration, not just an integration

Fridge Assistant, a HACS project from July 2026, puts everything inside HA. That is the easiest install, but for this scope it is the wrong place:

- **Dependencies.** PDF parsing, image processing, background removal, barcode decoding, AI SDKs and fuzzy matching would all be installed into HA's own Python environment, which pins its own versions. An HA upgrade could break us, or we could break HA.
- **Long-running work.** Watching a mailbox, calling AI models, removing photo backgrounds and looking up products keep running through HA restarts, and a bug in our code can't stall HA's event loop.
- **A real app UI** with its own release cycle, also usable on a kitchen tablet outside HA.
- **A path into HA core.** Core only accepts integrations that talk to an external service through a PyPI client library. This is that shape; Music Assistant, Z-Wave JS and ESPHome all work this way.
- **Runs anywhere:** as an HA app, as Docker next to HA Container, or on another machine near a GPU.

The price is two parts that must be released together. One monorepo with one version number, an API version check and a Repair issue on mismatch take care of that.

### 2.2 Overview

```
  Phone · tablet · browser      voice · LLM agents · automations · ESPHome station
         │ sidebar panel (ingress)                     │
         ▼                                             ▼
┌──────────────────────────────── Home Assistant ────────────────────────────────┐
│ steward integration: todo · calendar · sensor · image · select · event         │
│                      button · actions · Assist intents · LLM tools             │
│ also used: AI Task · weather · calendars · cameras · people · zones · areas    │
└────────▲─────────────────────────────────────┬─────────────────────────────────┘
         │ HA API: AI Task, weather,           │ WebSocket: commands + live events
         │ cameras, notify, registries         │ (ingress also proxies the web UI)
         │                                     ▼
┌────────┴─────────────── Steward server (HA app or plain Docker) ───────────────┐
│ modules: stock · shopping · recipes · meal plan · chores · tasks               │
│          batteries · equipment · custom lists · wardrobe · receipts            │
│ shared: AI providers · photos · HA bridge · scheduler · custom fields          │
│         labels · search · scan pipeline · receipt matcher · outfit engine      │
│ REST + WebSocket API · web UI (Vue PWA) · SQLite + photos in /data             │
└──────────────┬───────────────────┬────────────────────┬────────────────────────┘
               ▼                   ▼                    ▲
        Open Food Facts   Open-Meteo (trips)    IMAP (REWE eBons)
```

| Part | What it is | Shipped as |
|---|---|---|
| server | Modules, shared services, REST + WebSocket API, background jobs; serves the web UI | Docker image: HA app or standalone |
| frontend | Vue PWA (section 4.9) | Built into the server image |
| integration | HA custom component, domain `steward` | HACS first, built to core standards |
| client, models | Python libraries shared by server and integration | PyPI |
| cards | A few Lovelace cards: expiring soon, chores, outfit of the day, product tile with ± buttons | Bundled with the integration, registered automatically |
| esphome | YAML package for a barcode scan station | ESPHome remote package from GitHub |
| blueprints | Ready-made automations (sections 4.2 and 4.7) | Importable from GitHub |

### 2.3 How the parts talk

- **Integration → server:** one WebSocket that carries commands and live events. Entities update by push, not polling.
- **Server → HA:** HA's API, for AI Task, weather forecasts, calendars, camera snapshots, notifications and reading people, zones, areas and devices. As an HA app it uses the Supervisor token, so there is nothing to set up. Standalone, you paste a long-lived token.
- **Browser → server:** REST and WebSocket, through HA ingress (the sidebar panel) or directly on a port for standalone setups and kiosks.
- **Discovery and pairing:** the app announces itself to HA together with a generated API token, so HA shows "Discovered: Steward" and pairing takes one click. Standalone Docker is found via zeroconf (`_steward._tcp`) or by URL.
- **Versions:** the server reports its API version. The integration refuses incompatible versions and raises a Repair issue that says what to update.

### 2.4 Where it runs

| Your HA install | Server | UI |
|---|---|---|
| HA OS | HA app from our app repository | Sidebar panel via ingress, signed in as your HA user |
| HA Container | `docker compose` next to HA | Direct URL with "Sign in with Home Assistant", or an HA webpage dashboard |

HA deprecated the Supervised and Core install methods in 2025, so they are not targeted. Images are built for amd64 and aarch64.

### 2.5 Sign-in and permissions

- **Sidebar:** the Supervisor passes the logged-in HA user to the app in `X-Remote-User-Id` / `-Name` / `-Display-Name` headers and strips any that a client tries to send. We trust them only on requests from the ingress proxy. There is no second login, and every change is recorded with the HA user who made it.
- **Direct access:** "Sign in with Home Assistant" through HA's own OAuth flow, so there are no extra passwords.
- **Integration and scripts:** API tokens.
- **Permissions:** Grocy-style per-user permissions on top of HA users. For example, kids can tick off chores but can't edit the catalog.

### 2.6 Modules

The server is a modular monolith: one process, one database, one UI. Each module brings its own API routes, UI section, HA entities and LLM tools, and can be switched off.

| Module | Covers | Grocy equivalent |
|---|---|---|
| Stock & shopping | Products, locations, units, barcodes, stock ledger, shopping lists | Stock, shopping list |
| Kitchen | Recipes, meal plan | Recipes, meal plan |
| Chores | Schedules, assignment, tracking | Chores |
| Tasks | To-dos with categories, due dates, assignees | Tasks |
| Batteries | Charge cycles and swaps | Batteries |
| Equipment | Appliances, manuals, warranty, consumables | Equipment |
| Custom lists | Your own object types: books, wine, tools | Userentities |
| Wardrobe | Clothes, outfits, laundry | (new) |
| Receipts & money | eBons, prices, spending | Price tracking, stock reports (extended) |

**Shared services:** sign-in and permissions; photos and files (thumbnails, background removal); AI providers; the HA bridge (people, areas, zones, devices, weather, calendars, notifications); scheduler; search; custom fields; labels and printing; calendar feed.

## 3. Tech stack

| Layer | Choice | Why | Considered instead |
|---|---|---|---|
| Server | Python 3.13+, asyncio | Same language as HA, so server and integration share models; the best libraries for PDFs, images, barcodes, AI and fuzzy matching; Music Assistant precedent | Node/TypeScript (the integration must be Python anyway, so models would exist twice); Go or Rust (great binaries, weak AI and PDF libraries) |
| Web framework | FastAPI | Async, WebSockets, OpenAPI for free, which gives a typed TS client and API docs | aiohttp with a homegrown command bus (Music Assistant's choice, more plumbing); Django (sync-first, heavy) |
| API models | Pydantic v2 in a shared package | One schema for server, client and OpenAPI | mashumaro dataclasses (lighter and used by Music Assistant, but a second schema) |
| Database | SQLite (WAL) + SQLAlchemy 2 async + Alembic | Household-sized data; one file in `/data` that HA backups include; no extra container | Postgres (no gain at this size) |
| Search | SQLite FTS5 over products, notes, custom lists and manual text | Manual Q&A without a vector database | A vector database (not needed at this size) |
| Background jobs | In-process asyncio scheduler | Chore schedules, mailbox watch, expiry checks, lookups, morning outfits | Celery + Redis (overkill) |
| Images | Pillow with WebP thumbnails; rembg (MIT) for background removal on clothing photos, model downloaded on first use | Clean closet photos and outfit collages, all local | Cloud background-removal APIs |
| Barcodes | zxing-cpp on the server; BarcodeDetector with a zxing-wasm fallback in the browser | EAN/UPC, QR and DataMatrix, including GS1 data such as expiry dates in 2D codes; our own QR labels | pyzbar (no DataMatrix), QuaggaJS (1D only) |
| Product data | Open Food Facts and Open Products Facts, cached locally | Free, good German coverage, photos and nutrition | Paid EAN databases |
| Weather | HA weather entities (`weather.get_forecasts`); Open-Meteo for trips and standalone installs | Uses the forecast you already have in HA; Open-Meteo needs no key | |
| Receipts | pdfplumber + a port of the MIT `rewe-ebon-parser`; aioimaplib for IMAP | eBons are text PDFs, and that parser already knows the PAYBACK and REWE Bonus layouts | Depending on the package (its packaging pulls in dev tools, and it is small enough to vendor with credit) |
| Matching | rapidfuzz + abbreviation rules + an assignment solver; embeddings later if needed | Fast, deterministic, explainable | Embeddings first (needs a model; premature) |
| AI | Provider interface: HA AI Task (default), Anthropic SDK, OpenAI-compatible (Ollama, LM Studio, vLLM, OpenRouter), Gemini; JSON-schema output everywhere | Reuses your HA AI setup; models are swappable | One hard-wired vendor |
| Printing | PDF label sheets (browser print), label-printer webhook like Grocy's, ESC/POS for thermal printers | Grocy parity | |
| Frontend | Vue 3 + TypeScript + Vite + Vuetify 3 (Material 3), PWA | Music Assistant runs this stack inside HA ingress; strong mobile components (bottom sheets, image grids, tables, date pickers); Material looks at home next to HA | React + shadcn (equally fine if you prefer it); Lit for everything (too thin for a full app) |
| Lovelace cards | Lit web components | HA's own stack, tiny | |
| Integration | Custom component built to HA's integration quality scale; `steward-client` on PyPI | Keeps the door to HA core open | |
| Packaging | Multi-arch Docker (Debian slim) on GHCR; HA app repository; ESPHome package; blueprints | Prebuilt wheels for the native libraries are most reliable on glibc | Alpine (musl) |
| Tooling | uv, ruff, mypy, pytest + pytest-homeassistant-custom-component, Vitest, Playwright; dev container with HA, the server and a test IMAP server | | |

Wardrowbe, an MIT-licensed self-hosted wardrobe app, uses the same backend stack (FastAPI, async SQLAlchemy, Pydantic), which is a useful sanity check for the wardrobe module.

## 4. Features

### 4.1 Grocy parity

Everything is ported. "Plus" marks where it also gets an HA-native twist. Phases refer to section 8.

| Grocy feature | Plan | Phase |
|---|---|---|
| Products, product groups, presets, locations, quantity units and conversions, barcodes (several per product, with pack sizes) | Port | 1 |
| Parent products ("Milch" → "ja! H-Milch 3,5 % 1 l") | Port; key for receipt matching and recipes | 1 |
| Stock: purchase, consume, open, spoil, transfer, inventory; first-expiring-first-out; best-before vs use-by; opened, frozen and thawed shelf-life rules; move on open; tare weights; quick consume; journal with undo | Port, as the transaction ledger | 1 |
| Min stock → shopping list | Port, plus consumption forecasting later | 1 |
| Shopping lists (several), grouped by store layout, list → stock | Port, plus each list is an HA to-do | 1 |
| Barcode lookup (Open Food Facts, plugins) | Port | 1 |
| Chores: manual, dynamic ("n days after last done"), daily, weekly, monthly, yearly and adaptive schedules; rollover; date-only tracking; assignment (none, fixed, who did least, random, rotation); consume a product on completion; skip, reschedule, undo; journal | Port, plus HA twists (4.2) | 2 |
| Tasks: categories, due dates, assignees | Port, plus each category is an HA to-do | 2 |
| Batteries: charge interval, last charged, cycles, journal | Port, plus HA device links (4.2) | 2 |
| Calendar with iCal feed | Port: HA calendar entities plus an iCal link | 1, 2, 6 |
| Recipes: ingredients and groups, nesting, servings, "can I make it", due score, consume, "produces product", costs and calories | Port, plus import from URL or photo | 6 |
| Meal plan: sections; recipes, products or notes; missing ingredients → shopping list | Port, plus an HA calendar | 6 |
| Price tracking, stores, stock reports (spending) | Port; prices come from receipts automatically | 5 |
| Equipment: manuals, notes | Port, plus HA device link, warranty, consumables, manual Q&A (4.3) | 7 |
| Userfields: custom fields on any object | Port | 7 |
| Userentities: your own object types and lists | Port as "custom lists" | 7 |
| Grocycode labels, label printer, thermal printer for the shopping list | Port | 7 |
| Users with granular permissions | Port on top of HA users | 0 (roles), 7 (granular) |
| Feature flags | Port: every module can be switched off | 0 |
| Night mode, custom CSS | Replaced by HA theme sync (light and dark follow HA) | 0 |
| REST API with Swagger | Own REST + WebSocket API with OpenAPI docs; a Grocy-compatible subset is optional | 0, later |
| Grocy Android app, Barcode Buddy | Covered by the PWA and our own scanning; Grocy API compatibility is optional | later |

### 4.2 Chores, tasks and batteries

**Chores.** Everything in the table above, plus:

- Assignees are HA people. Each person gets an HA to-do list of their due chores, and ticking one off tracks it.
- Reminders go to the assigned person, preferably once they are home, with *Done* · *Snooze* · *Reassign* buttons.
- "Who did least" can count only the people who are at home.
- Device signals set due dates or complete chores, through blueprints we ship:
  - dishwasher finished → "empty the dishwasher" is due
  - robot vacuum finished → "vacuum" is done
  - window open for 10+ minutes → "lüften" is done
  - soil moisture low → "water the plants" is due
  - filter runtime or a filter-life sensor → "replace the filter" is due
  - waste collection calendar (e.g. the Waste Collection Schedule integration) → "Gelbe Tonne rausstellen" is due the evening before pickup
  - NFC tag on the appliance → tap = done
- Optional points and a weekly leaderboard, for households with kids or flatmates.

**Tasks.** Grocy's tasks: categories, due dates, assignees, notes. Each category is an HA to-do list, so HA's built-in voice intents already work ("Füge Steuererklärung zu den Aufgaben hinzu").

**Batteries.**

- Grocy's charge-cycle tracking for anything: remotes, smoke detectors, power tools.
- Linked to HA devices where possible. When a battery sensor jumps from low to about 100 %, the swap is logged and one battery of the right type leaves stock. A low battery puts that type on the shopping list if stock is short.

### 4.3 Equipment, custom fields, custom lists, labels

- **Equipment:** appliances and devices with manuals (PDF), notes, photos, custom fields, a linked HA device, purchase date, price and receipt, warranty end (with a reminder before it runs out), consumables from stock (water filter, descaler, vacuum bags) and chores (descale every 3 months).
- **Manual Q&A:** manual PDFs are indexed for full-text search. Ask Assist "wie entkalke ich die Kaffeemaschine?" and the LLM tool finds the passage and cites the page.
- **Custom fields** (Grocy's userfields): text, number, date, checkbox, list, link, file and picture fields on any object; shown in lists; settable through the API and HA actions.
- **Custom lists** (Grocy's userentities): your own object types, such as books, wine, board games or tools, with custom fields and photos, each with its own menu entry.
- **Labels and printing:** QR labels for stock entries, chores, batteries, equipment and containers. Scanning one does the right thing: consume that entry, track that chore, open that manual. Print through the browser (PDF label sheets) or a label-printer webhook, as Grocy does. The shopping list can go to a thermal (ESC/POS) printer, also as Grocy does.

### 4.4 Wardrobe and outfits

**Adding clothes**

- Photograph each piece on a hanger or flat on the floor. The background is removed locally (rembg), so the closet looks like a catalog and outfits can be shown as collages.
- The AI suggests the details, and you confirm or fix them:
  - type and layer: base, mid, outer, bottom, shoes, accessory
  - colors, pattern, material
  - warmth (1–5) and the temperature range it suits
  - rain protection (none, water-resistant, waterproof) and wind protection
  - formality (1–5) and uses: home wear, comfort, going out, work, sport, formal
  - seasons: summer, winter, in between
- An optional second photo of the care label adds the material mix and washing symbols.
- Bulk mode: one piece after the other, a few seconds each.
- Your own details too: brand, size, fit, condition, price (gives cost per wear), favorite, owner (HA person).

**State and laundry**

- Each piece is clean, worn (n times), in the wash, at the tailor, lent out, or stored for the season.
- "Wears before washing" per piece or type (underwear 1, jeans 5). Pieces that reach it move to the laundry basket automatically.
- When the washing machine finishes (HA), you get "Mark the basket as clean?". Later: suggestions for full loads that go together (same temperature, similar colors).

**Outfit engine** (rules first, AI second)

1. **Context:** today's forecast from your HA weather entity (feels-like range over the hours you are out, rain probability, wind, UV); your HA calendar (office, gym, wedding); home-office day or not; or an occasion you pick.
2. **Rules:** only clean pieces you own; warmth matches the feels-like temperature; a waterproof outer layer and shoes when rain is likely; formality matches the occasion; nothing worn in the last few days.
3. **AI:** picks 1–3 complete outfits from that shortlist using your style profile (your taste in your own words, plus likes and dislikes learned from feedback) and color and style harmony, optionally looking at the photos. It explains in one line ("rain from 16:00, so the rain jacket").
4. **Check:** every outfit goes through the rules again. No T-shirt and shorts at 4 °C.
5. **Feedback:** *Wear this* logs the wear; you can swap one piece; thumbs down takes a reason ("too warm", "don't like these together"). All of it shapes the next suggestions.

**In Home Assistant:** an outfit image and sensor per person; a morning notification with the picture and *Wear this* · *Another one*; "Was soll ich heute anziehen?"; `steward.suggest_outfit` with response data for scripts; a rain nudge when you leave home without a rain layer; laundry from the washing machine.

**Extras:**

- Packing lists for trips: destination forecast from Open-Meteo, outfits per day, and the packing list as an HA to-do list.
- Insights: pieces not worn in 6 months (donate?), cost per wear, gaps such as "no waterproof shoes".
- Everyone in the household gets their own wardrobe and style profile.

### 4.5 Smart scanning

**Inputs**, in any combination:

1. Phone or tablet in the web UI: live barcode scanning and photos. Best camera, autofocus.
2. Barcode scanners: the ESPHome scan station (section 6), or any USB/Bluetooth scanner paired with the kitchen tablet (the UI treats fast keystroke bursts as scans).
3. Any HA camera entity (ESPHome camera, USB webcam via go2rtc), triggered by a button or an automation.
4. Photo upload, or share-to from the phone's gallery.

**Pipeline**

1. **Decode codes locally.** Free and instant: EAN/UPC, QR, DataMatrix, and our own labels. GS1 2D codes can carry the expiry date and lot number. GS1's "Sunrise 2027" push is bringing them to more products, and those need no date reading at all.
2. **Find the product.** Local barcode table, then Open Food Facts / Open Products Facts (cached), otherwise a new-product draft with name, brand, pack size, photo and nutrition.
3. **AI, only when needed.**
   - No barcode (fruit, vegetables, bakery, loose goods): identify it, matching against your own catalog first.
   - Dates: tell "mindestens haltbar bis" (best before) from "zu verbrauchen bis" (use by); read "EXP 03/27" and dot-matrix prints; ask for a close-up when unsure.
   - New products: suggest category, storage location, shelf life (closed, opened, frozen) and a "don't freeze" flag.
4. **Confirm.** One pre-filled card per item, one tap to accept. Known products above a confidence threshold can be saved automatically (your setting).
5. **Learn.** Corrections are kept (barcode ↔ product, preferred location, shelf life), so the same item never asks twice.

**Modes:** purchase (default), consume, open, spoil, inventory count, add to shopping list, look up. Switch them in the UI, with the `select` entity, with buttons on the scan station, or by scanning a printed mode barcode (the Barcode Buddy trick).

**AI result** (JSON schema): `items[]: {name, brand, barcode?, quantity, unit, due_date?, due_type, date_text_seen, category, storage, confidence}`.

**Experimental:** a fridge camera takes a snapshot when the door closes, and the AI compares it with stock and suggests "the yogurt seems gone, mark it as eaten?". Suggestions only.

### 4.6 REWE eBons: trips, prices, stock

**What we're dealing with.** REWE emails each eBon as a PDF to the address on your REWE account (only that one) when you scan the REWE app at checkout. Past ones stay under "Meine Einkäufe". The PDF contains text, not an image, so it parses reliably. The lines are abbreviated, though (`JA! H-MILCH 3,5%`, `BIO BANANE`, `0,532 kg x 2,99 EUR/kg`), and there is no barcode.

**Getting them in**

- Mailbox watch over IMAP: read-only, one folder (a mail rule moves eBons there), REWE sender only. Processed messages are tracked on our side, and nothing in your mailbox changes.
- Also: upload, a watched folder (`/share/steward/inbox`), and an HA action. Later: photos of paper receipts from any store, read by the AI into the same format.
- Backfill: import all past eBons once. That gives you price history right away and a head start on matching.
- Mail providers that only allow OAuth for IMAP (Microsoft accounts, for example) need OAuth support, which comes later, or a forwarding rule to a mailbox with app passwords (Gmail, GMX, web.de, Posteo).

**Parsing.** pdfplumber plus a port of the MIT-licensed `rewe-ebon-parser`, which already handles both the PAYBACK and the REWE Bonus layouts. It covers item lines, quantity lines (`2 Stk x 1,29`), weighed goods, Pfand and Leergut, discounts and coupons, tax classes, total, payment, REWE Bonus credit, store and timestamp. Tests use your real eBons with personal data removed. If a new layout breaks the parser, the AI extracts the receipt instead and we flag it.

**Matching**, cheapest step first:

1. **Learned alias.** The same line text at the same chain, confirmed before, is a match. After a few weeks this resolves most lines.
2. **Text similarity.** Normalize case and brand prefixes (`JA!`, `REWE BIO`, `REWE BESTE WAHL`), expand known abbreviations, fuzzy-match against product names, aliases and Open Food Facts names, and use numbers and units (`3,5%`, `500G`; a per-kg price means loose produce).
3. **Trip context.** Items you scanned in around the receipt time are the likeliest candidates. A plausible price (close to the last one) and matching quantities (2 Stk and 2 scans) add evidence. All lines and scans are matched as one assignment problem (Hungarian algorithm), not greedily line by line.
4. **AI tie-breaker.** One call per receipt with the unresolved lines and their best candidates, plus "new product". It returns choices with confidence and, for new products, a clean name and category (`JA! SCHLAGSAHNE` becomes "ja! Schlagsahne 30 %, 200 ml" in Milchprodukte).
5. **Review.** The receipt is shown with each line marked auto, suggested or unknown. Confirming a line teaches the alias and records the price.

**Two flows**

- **Scan first:** you scan while unpacking; the receipt arrives later and fills in the prices.
- **Receipt first:** nothing was scanned; the receipt becomes a one-tap "put away" list with default shelf lives, and you only photograph the dates of perishables.

Either way, bought products are ticked off the shopping list. Non-food lines (detergent, batteries, toilet paper) land in stock too, which feeds batteries and equipment consumables.

**Money:** a trip view (what was paid for what), price history per product and store (normalized to €/kg and €/l), spending per month and category, Pfand balance, coupon and Bonus savings, price-increase alerts, and HA sensors for monthly spending and the last trip.

### 4.7 Home Assistant surface

**Entities** (only for modules that are switched on)

| Platform | Entities |
|---|---|
| `todo` | Shopping lists; task categories; each person's due chores; trip packing lists. "Add milk to the shopping list" works with Assist out of the box. |
| `calendar` | Due dates, chores, tasks, batteries, meal plan |
| `sensor` | Stock: expiring, expired, below min stock, stock value. Money: spending, last trip, food waste. Chores, tasks and batteries due or overdue, per person. Warranties ending. Wardrobe: today's outfit per person, pieces in the laundry. Opt-in per-product sensors ("Kaffeebohnen: 0,4 kg"). |
| `image` | Today's outfit per person, as a collage of the piece photos |
| `select` | Scanner mode |
| `event` | Scans, stock changes ("ran out of X"), receipts, chores done or overdue, outfit suggested |
| `button` | Add missing products to the shopping list; check the mailbox now; new outfit; laundry done |

**Actions** (all with UI selectors and translations)

- Stock: `steward.purchase`, `.consume`, `.open`, `.spoil`, `.transfer`, `.inventory`
- Input: `steward.scan` (code, mode, source), `.recognize` (camera entity or image → AI result), `.import_receipt`
- Household: `steward.execute_chore`, `.skip_chore`, `.complete_task`, `.track_battery`
- Kitchen: `steward.add_to_shopping_list`, `.complete_meal`
- Wardrobe: `steward.suggest_outfit`, `.wear_outfit`, `.laundry_done`
- Queries that return data, for scripts and LLMs: `steward.get_stock`, `.find_product`, `.get_expiring`, `.get_chores`, `.suggest_recipes`, `.search_manuals`

**Voice and LLMs**

- Assist intents with German and English sentences: "Haben wir noch Eier?", "Was läuft diese Woche ab?", "Wer ist mit Staubsaugen dran?", "Ich habe den Müll rausgebracht", "Was soll ich heute anziehen?", "Wie entkalke ich die Kaffeemaschine?", "Was kann ich heute kochen?"
- An `llm.py` platform adds `steward__*` tools to HA's built-in Assist LLM API, so any LLM conversation agent (OpenAI, Gemini, Anthropic, Ollama) can read and update everything above. HA's MCP server integration should pass the same tools on to external MCP clients.

**Blueprints we ship**

- Morning digest per person: food that expires today, chores due, today's outfit. One notification instead of five.
- Store reminder: entering a store's zone with items on the list sends you the list.
- Battery swap detection (4.2) and the chore triggers listed there.
- Laundry: the washing machine finishes, so you're asked to mark the basket as clean.
- Rain nudge: you leave home, rain is likely, and today's outfit has no rain layer.

**Housekeeping:** config flow with discovery, options flow, diagnostics, Repair issues (version mismatch, mailbox login failing, AI unavailable), translations, long-term statistics for the money sensors.

### 4.8 More features I'd add

| Feature | Why | Effort | Phase |
|---|---|---|---|
| Receipt-first stocking | Most data entry disappears | M | 5 |
| Food-waste tracking (€ and items thrown away) | Grocy records spoilage but never shows it back | S | 5 |
| "Use it up" recipe suggestions | Ranks recipes by what expires soonest | M | 6 |
| Leftovers and freezer portions with short shelf lives and QR labels | Tracks what actually goes bad | S | 6 |
| Consumption forecast ("Kaffee reicht noch ~3 Tage") | Smarter than a fixed min stock; feeds the list | M | 8 |
| Store-zone reminders, list sorted in your walking order per store | The list shows up at the store, in order | S | 8 |
| Mirror the shopping list to any HA to-do list (e.g. Bring!) | The household keeps its usual list app | S | 8 |
| Kitchen kiosk mode for a wall tablet | Scanner-first, big buttons | S | 8 |
| Kitchen scale (ESPHome HX711) | Coffee, flour, pet food by weight, with tare | M | later |
| Grocy API compatibility subset | Keep using the Grocy Android app or Barcode Buddy | L | later |

### 4.9 UI

Grocy's main problem is its UI, so this gets real attention.

- Mobile first. Scan and confirm on one screen. Undo snackbars instead of "are you sure?" dialogs. Photos everywhere: products, clothes, equipment.
- Follows your HA theme and dark mode: inside the sidebar panel, the page reads HA's theme variables.
- Screens: Today (expiring food, chores due, your outfit, last trip) · Stock · Scan · Shopping · Receipts and trips · Recipes and meal plan · Chores and tasks · Batteries · Equipment · Wardrobe (closet grid, outfit of the day, laundry, insights) · Custom lists · Insights (spending, waste, prices) · Settings.
- English first, with German as a translation (language switch in the app; `?lang=de` also works).

## 5. Data model (sketch)

```
catalog   product(name, brand, parent_id, group, default_location, stock_unit, min_stock,
                  due_type[best_before|use_by], due_days, due_days_opened, due_days_frozen,
                  due_days_thawed, no_freeze, tare_weight, off_code, image, nutrition,
                  expose_to_ha)
          barcode(code, product_id, unit_id, amount)        -- several per product, pack sizes
          unit · unit_conversion(product_id?, from, to, factor)
          location(name, is_freezer, ha_area_id)            -- "Kühlschrank" in area Küche
          store(name, chain, address, ha_zone_id)
stock     stock_entry(product_id, amount, location_id, due_date, opened_at, frozen_at,
                      purchased_at, unit_price, store_id)   -- what is on the shelf now
          stock_txn(type, product_id, entry_id, amount, at, actor, source,
                    receipt_line_id?, scan_id?, recipe_id?, chore_id?, undoes?)  -- append-only
shopping  shopping_list(name, ha_entity_id)
          shopping_item(list_id, product_id?, text, amount, unit, done, sort_key)
routines  chore(name, schedule_type[manual|dynamic|daily|weekly|monthly|yearly|adaptive],
                schedule_config, start_date, rollover, track_date_only,
                assignment[none|fixed|least_done|random|rotation], assignees[HA person ids],
                consumes_product_id?, consume_amount, points) · chore_log(done_at, by, skipped)
          task(name, notes, due_date, category_id, assignee, done_at)
          task_category(name, ha_entity_id)
          battery(name, ha_device_id?, battery_product_id, charge_interval_days) · battery_log
assets    asset(kind[equipment|garment|custom], name, photos[], location_id, ha_device_id?,
                purchased_at, price, receipt_id?, warranty_until, condition, status)
          equipment(asset_id, manuals[], consumables[product ids], chores[ids])
          custom_list(name, icon)                           -- Grocy userentities
          custom_field(object_type, name, type, options, show_in_lists) · custom_value
          label(code, target_type, target_id)              -- our QR codes
wardrobe  garment(asset_id, owner, type, layer, colors[], pattern, materials[], warmth,
                  temp_range, rain, wind, formality, uses[], seasons[], care, wears_per_wash,
                  state[clean|worn|laundry|repair|lent|stored], wears_since_wash,
                  wear_count, last_worn)
          outfit(owner, date, garments[], source[ai|manual], weather, occasion, rating, worn)
          style_profile(owner, description, likes[], dislikes[], rules[])
receipts  receipt(store_id, at, total, payment, source, file, external_id, status)
          receipt_line(receipt_id, idx, raw_text, qty, unit, unit_price, total, tax_class,
                       kind[item|pfand|leergut|discount], product_id?, confidence, method)
          receipt_alias(chain, normalized_text, product_id, hits, confirmed)
          price_observation(product_id, store_id, at, unit_price, pack_price, source)
kitchen   recipe · recipe_ingredient(product_id, amount, unit, group, optional)
          meal_plan_entry(date, slot, recipe|product|note, servings, done)
scanning  scan(at, device, mode, image, codes, ai_result, outcome, corrections)
```

Amounts are decimals, not floats. Every table carries created and updated timestamps and the acting HA user. Custom fields work on every object type.

## 6. Hardware

| Tier | Hardware | Good for | Limits |
|---|---|---|---|
| 0 | Your phone or a kitchen tablet (web UI / PWA) | Everything: groceries, dates, produce, clothes | Browsers only allow the camera over HTTPS (Nabu Casa or your own TLS) |
| 1a | USB or Bluetooth barcode scanner paired with the tablet (~20–40 €) | Fast barcode scans, no setup | Barcodes only |
| 1b | ESPHome scan station: ESP32 + GM861S (or GM65/GM67) UART module, mode buttons, buzzer/LED, optional small display (~25–40 €) | Always-on scanner on the counter, with feedback on the device | Barcodes only: the module decodes internally and never hands over an image |
| 2 | Camera station: any HA camera entity above a spot on the counter | Produce, dates | ESP32 cameras (fixed focus, 2–5 MP) struggle with small date prints; a USB autofocus webcam via go2rtc is much better |
| + | NFC tags | Tap to complete chores or open manuals | |
| + | Label printer (webhook) or thermal receipt printer (ESC/POS) | Labels; printed shopping list | |
| + | Load cell (ESPHome HX711) | Weighed goods | Later |

Clothes need no hardware: phone photos against a plain wall or floor are enough. Background removal runs on the server and takes several seconds per photo on a Raspberry Pi-class machine.

The ESPHome station fires an `esphome.steward_scan` event in HA with the code and the mode. The integration forwards it and answers through an action on the device ("✓ Milch +1", or an error beep). We ship the YAML as a remote ESPHome package.

**Recommendation:** start with the phone, add the ESPHome barcode station as the always-there kitchen device, and treat the camera station as an experiment.

## 7. AI: providers, privacy, cost

**Routes**

1. **Home Assistant AI Task (default).** The server sends photos and a JSON schema to `ai_task.generate_data`, which supports image attachments and structured output (HA 2025.8+). It uses whichever AI provider you configured in HA, so our app needs no keys. Photos reach it as media: the app saves them under HA's media folder, and camera entities are passed directly. A standalone install shares that folder or uses a direct provider.
2. **Direct providers,** for standalone installs or tuning: Anthropic (official SDK), OpenAI-compatible endpoints (Ollama, LM Studio, vLLM, OpenRouter), Google Gemini.
3. **Local.** An open-weight vision model on Ollama works, but needs a GPU or an Apple Silicon machine. An HA Green or a Raspberry Pi can't run one at a usable speed.

**What the AI is used for:** product photos, dates, receipt tie-breaks, tagging clothes, choosing outfits, answering from manuals, importing recipes. Everything else is plain code.

**What leaves the house** (with a cloud model): product photos, receipt line texts, clothing photos (photograph clothes on a hanger, not on you), manual passages. No names, payment data or addresses. With a local model, nothing.

**Cost with Claude at October 2026 list prices** (rough):

| Call | Tokens in / out | Claude Haiku 5.5 | Claude Sonnet 5.5 |
|---|---|---|---|
| Product photo (~1 MP image + prompt, JSON out) | ~2k / ~0.5k | ≈ $0.0005 | ≈ $0.009 |
| Receipt matching (unresolved lines + candidates) | ~3k / ~1k | ≈ $0.001 | ≈ $0.016 |
| Tagging one garment (photo + care label) | ~2k / ~0.4k | ≈ $0.0004 | ≈ $0.008 |
| Daily outfit (~60 shortlisted pieces with thumbnails) | ~9k / ~0.6k | ≈ $0.0012 | ≈ $0.024 |
| One month (150 scans, 10 receipts, 30 outfits) | | ≈ $0.11 | ≈ $2.25 |
| Wardrobe setup, once (200 pieces) | | ≈ $0.08 | ≈ $1.60 |

At household volume the cost doesn't matter; the real choice is privacy versus accuracy. Before picking defaults we build small eval sets (about 50 of your product photos, about 30 of your clothes, a few outfit scenarios) and compare providers on them.

## 8. Roadmap

| Phase | Delivers | Done when |
|---|---|---|
| 0 · Foundation | Monorepo, CI; server with database, migrations, sign-in, roles and module switches; shared photo, scheduler and HA bridge services (people, areas, devices, weather, calendars); UI shell in your HA theme; HA app packaging; integration with discovery; dev environment (HA + server + test mail server) | You install the app on HA OS, HA discovers it, and the sidebar panel opens as your HA user |
| 1 · Stock & shopping | Catalog (products, parents, units, locations, barcodes), stock ledger with undo, due dates, shopping lists as HA to-dos, min stock → list, Open Food Facts, phone barcode scanning, core entities and actions, German and English | You run the kitchen on it for a week without Grocy |
| 2 · Chores, tasks, batteries | All schedule and assignment types, per-person to-do lists and reminders, calendars, battery tracking with HA device links, device-driven chore blueprints, NFC, points | Chores reach the right person, and at least two complete themselves from device signals |
| 3 · AI + smart scanning | AI provider layer (AI Task + direct providers), eval sets, recognition (produce, dates, new products), scan modes, ESPHome station, camera entities, GS1 codes | Unpacking a full bag takes about 2 minutes, dates included |
| 4 · Wardrobe | Clothes onboarding with background removal and AI tagging, laundry states, outfit engine, morning notification, outfit image entity, voice, packing lists | You wear the suggested outfit on most days (counted by *Wear this*) |
| 5 · Receipts & money | IMAP intake, eBon parser with golden-file tests, matcher, review screen, receipt-first flow, price history, spending and waste insights and sensors, backfill | 90 %+ of lines match automatically after a month |
| 6 · Kitchen | Recipes (import from URL or photo, "can I cook it", due score, consume, leftovers), meal plan with calendar and list generation, "use it up" | "What can I cook tonight?" is answered from real stock |
| 7 · Equipment and the rest of Grocy | Equipment with manuals, manual Q&A, warranty and consumables; custom fields; custom lists; labels and printing; granular permissions; Grocy API subset if wanted | Everything Grocy does is covered, and Grocy can be switched off |
| 8 · Extras | Forecasting, store reminders, list mirroring, kiosk mode (done in 0.3.0), kitchen scale | |

Phases 4 to 7 don't depend on each other: receipts and recipes need phase 1, and the wardrobe needs the AI layer from phase 3. If you want the wardrobe sooner, the AI layer simply moves up with it.

## 9. Repository layout

One monorepo with one version number. It doubles as a HACS repository and an HA app repository.

```
hass-grocy/                        (rename once the name is settled)
├── server/steward_server/
│   ├── core/                      sign-in, photos, AI providers, HA bridge, scheduler,
│   │                              search, custom fields, labels
│   └── modules/                   stock, shopping, kitchen, chores, tasks, batteries,
│                                  equipment, custom_lists, wardrobe, receipts
├── models/                        steward_models: shared Pydantic schemas
├── client/                        steward_client: async client for the integration (PyPI)
├── frontend/                      Vue 3 PWA, built into the server image
├── cards/                         Lit Lovelace cards
├── custom_components/steward/   HA integration (HACS installs it from here)
├── app/                           HA app: config.yaml, Dockerfile, translations, icon
├── repository.yaml                makes the repo an HA app repository
├── esphome/                       scan-station package
├── blueprints/
└── docs/
```

## 10. Risks

| Risk | Mitigation |
|---|---|
| Scope roughly doubled: all of Grocy plus scanning, receipts and a wardrobe | Phases that each ship; modules can be switched off; the foundation is built for modules from day one |
| Receipt abbreviations too cryptic | Alias learning, trip context, review screen. The goal is "confirm", not "no touch" |
| Date reading fails on curved or embossed prints | Dates are always confirmed; close-up retake; per-product default shelf life; GS1 2D codes over time |
| Outfit AI ignores the weather | Rules before and after the AI; feedback loop |
| Photos make HA backups bigger | WebP at a sensible size, thumbnails, caches excluded from backups |
| Background removal is heavy on a Pi (a model of roughly 100–200 MB, several seconds per photo) | Optional, downloaded on first use, runs only when adding clothes |
| Phone camera needs HTTPS (camera access inside the companion apps still to verify in phase 1) | Works via Nabu Casa or HA with TLS; barcode scanners and ESPHome don't need it |
| REWE changes the eBon layout (it did when PAYBACK became REWE Bonus) | Golden-file tests, versioned parser, AI fallback with a warning |
| Server and integration drift apart | Monorepo, one version, API version check, Repair issue |
| HA platform churn (add-ons became apps, developer docs moved) | Follow the developer docs; keep the integration small |
| Open Food Facts rate limits and license | Local cache, identifying User-Agent, ODbL attribution |
| Maintenance for a one-person project | Boring stack, thin integration, tests from day one |

## 11. Prior art

| Project | What it is | Takeaway |
|---|---|---|
| Grocy 4.6 (PHP) | The feature reference | Port concepts, not code |
| custom-components/grocy | HACS integration for Grocy | Entity and action ideas |
| Music Assistant | Server + HA app + core integration | The architecture template |
| Fridge Assistant (HACS, July 2026) | Everything inside HA; AI shelf-life estimates; labels. Early stage | There is demand; the in-HA approach caps the scope |
| EverShelf (PHP, MIT) | Self-hosted AI pantry: receipt-photo OCR, Bring! sync, scales; HA only for alerts | Good feature ideas; PHP again |
| Wardrowbe (Python, MIT) | Self-hosted AI wardrobe: AI tagging, rembg, weather-aware suggestions, wash tracking, family support; no HA integration | Closest to the wardrobe idea, same backend stack; borrow ideas |
| Libre Closet (AGPL-3.0) | Self-hosted closet organizer without AI | Catalog and outfit-builder ideas |
| rewe-ebon-parser (Python, MIT) | REWE eBon PDF to JSON | Port it into our parser |
| Waste Collection Schedule (HACS) | Waste pickup dates as HA calendars | Feeds the trash chores |
| Barcode Buddy | Scanner modes for Grocy | Mode barcodes |
| Mealie, Tandoor | Recipe managers | Possible import sources for recipes |

## 12. Decisions

All answered; see "Decisions (v3)" at the top.

## Sources

- Grocy features: https://grocy.info/
- Add-ons renamed to apps: https://frenck.dev/renaming-home-assistant-add-ons-to-apps/
- HA deprecates the Core and Supervised installs: https://home-assistant.io/blog/2025/05/22/deprecating-core-and-supervised-installation-methods-and-32-bit-systems/
- AI Task `generate_data`: https://www.home-assistant.io/actions/ai_task.generate_data/
- LLM API and `llm.py` tools: https://contributors.home-assistant.io/core/internals/llm-api/
- Supervisor ingress user headers: https://github.com/home-assistant/supervisor/blob/main/supervisor/api/ingress.py
- REWE eBon: https://www.rewe.de/service/ebon
- rewe-ebon-parser: https://pypi.org/project/rewe-ebon-parser/ and https://github.com/e-kotov/rewe-ebon-parser
- Fridge Assistant: https://community.home-assistant.io/t/introducing-fridge-assistant-how-i-order-my-freezer-with-ai-and-labels-inside-home-assistant-with-a-custom-integration/1018193
- EverShelf: https://github.com/dadaloop82/EverShelf
- Wardrowbe: https://github.com/Anyesh/wardrowbe
- Libre Closet: https://github.com/lazztech/Libre-Closet
- Outfit LLM ignoring the weather (Hackaday): https://hackaday.com/tag/wardrobe
- Waste Collection Schedule: https://github.com/mampfes/hacs_waste_collection_schedule
- ESPHome barcode scanner feeding Mealie: https://community.home-assistant.io/t/esp32-barcode-scanner-mealie-shopping-list/1013946
- Claude prices: Anthropic API list prices as of October 2026
