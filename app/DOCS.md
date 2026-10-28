# Steward

Household management for Home Assistant: stock and shopping lists, chores and tasks, REWE eBons,
equipment with manuals, and a wardrobe with outfit suggestions.

## After installing

1. Start the app. "Steward" appears in the sidebar; it opens signed in as your Home Assistant user.
2. Home Assistant shows **Discovered: Steward** under Settings → Devices & services. Add it to get the
   to-do lists, sensors, calendars, actions and the outfit picture.
3. In Steward, open **Settings → AI** to choose which AI handles scanning, clothing tags and outfits.
   By default Steward uses Home Assistant's AI Task, i.e. whatever AI you set up in Home Assistant
   (local through Ollama, or OpenAI, Anthropic, Google). You can also add providers directly.

## Options

- **Demo data**: fills an empty database with example data to look around. Turn it off and delete
  the data (uninstall, or remove the app's data) before real use.
- **Home Assistant URL**: only needed if you open Steward directly on its port instead of through the
  sidebar. Enter the address your browser uses for Home Assistant; Steward then offers
  "Sign in with Home Assistant".

## Data and backups

Everything lives in the app's `/data` folder (one SQLite database plus photos and manuals), which
Home Assistant backups include. Receipts can be imported from `/share`.
