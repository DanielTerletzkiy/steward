# Use Steward in your Home Assistant

Steward has two parts, and your Home Assistant needs both:

- **The app** (Settings → Apps): the Steward server and web UI. It opens in the sidebar and keeps your data.
- **The integration** (`custom_components/steward`): to-do lists, sensors, calendars, actions, and the bridge for AI Task, weather and your appliances.

This guide covers Home Assistant OS and Supervised, which have apps. For HA Container, see [Without apps](#without-apps-ha-container).

## Private repository: what works

| Install route | Private GitHub repository? |
|---|---|
| HACS (custom repository) for the integration | **No.** HACS doesn't support private repositories at all, not even as a custom repository. |
| App store → Repositories, for the app | **Unofficial.** People report that a URL with a token works (`https://USER:TOKEN@github.com/USER/steward`), but it isn't documented and has failed for some. It also needs published images, which Steward doesn't have yet (see [Later](#later-install-from-github)). |
| Copy both over SSH, described below | **Yes.** Nothing is fetched from GitHub; you build on your Mac and copy to Home Assistant. |

So, for now, install from your checkout.

## 1. Prepare SSH access (once)

1. Install the **Terminal & SSH** app from the official app store.
2. In its Configuration tab:
   - add your public key (`cat ~/.ssh/id_ed25519.pub`) under `authorized_keys`;
   - set a port (22) under Network.
3. Start the app.
4. Check from your Mac:

```bash
ssh root@homeassistant.local ls /addons /config
```

Use your HA's IP address if `homeassistant.local` doesn't resolve.

## 2. Copy the app and the integration

Run these from the repository root. Set `HA` to your SSH address first:

```bash
export HA=root@homeassistant.local
```

Build the app folder. This also builds the web UI, so run `npm ci` in `frontend/` once beforehand:

```bash
dev/scripts/build_app.sh
```

Copy the app into HA's local app folder:

```bash
COPYFILE_DISABLE=1 tar -C dist/ha-app -cf - --exclude __pycache__ steward | ssh $HA 'rm -rf /addons/steward && tar -xf - -C /addons'
```

Copy the integration:

```bash
COPYFILE_DISABLE=1 tar -C custom_components -cf - --exclude __pycache__ steward | ssh $HA 'mkdir -p /config/custom_components && rm -rf /config/custom_components/steward && tar -xf - -C /config/custom_components'
```

Restart Home Assistant so it loads the integration:

```bash
ssh $HA ha core restart
```

## 3. Install and connect

1. Open Settings → Apps → **App store**, then ⋮ → **Check for updates**.
2. Under **Local apps**, open **Steward** and click **Install**. HA builds the image on the device, which takes a few minutes on a Raspberry Pi.
3. Leave **Demo data** off; demo data is for looking around, not for real use.
4. Turn on **Show in sidebar**, then click **Start**.
5. Go to Settings → Devices & services. HA shows **Discovered: Steward**; click **Add**. The server announced itself with its token, so nothing else is needed.

Steward now opens from the sidebar, signed in as your HA user. The to-do lists, sensors and calendars appear under the Steward device.

## 4. Set it up for your home

- **AI:** Settings → AI in Steward.
  - The default is **Home Assistant AI Task**: whichever AI integration you set up in HA (e.g. Ollama, OpenAI, Google Generative AI or Anthropic).
  - You can add providers directly instead, with their API keys. Keys stay in Steward and are never shown again.
- **Weather** for outfits: Settings → Weather.
  - Steward uses your HA weather entity, or Open-Meteo at your HA home location.
  - Pick a different entity or location there if needed.
- **LG ThinQ washer:**
  1. Set up the LG ThinQ integration in HA.
  2. In Steward, go to Equipment → add the washer (type *Washer*) → **Home Assistant** card → **Link device**, and pick the ThinQ device.
  3. Choose what happens to the laundry: **Track the laundry bin** (start = in the wash, done = drying), **Ask me when it's done**, or leave it as it is.
  4. Add a chore like "Hang up the laundry" and link it, so it becomes due when the washer finishes.
- **Robot vacuum:** link it the same way. A finished run completes its chore, and Steward can start it and send it to the dock.
- **Receipts:** put REWE eBon PDFs into HA's `/share` folder to import them.
- **Notifications:** Steward fires `steward_appliance_finished` and `steward_appliance_started` in HA. Use them as automation triggers.

## Updating

1. Raise `version` in `app/config.yaml`.
2. Run the build and both copy commands from step 2 again.
3. In HA, open ⋮ → **Check for updates**; the Steward app then offers **Update**. Without a version change, use **Rebuild** on the app page.
4. Restart HA if the integration changed.

Your data stays in the app's `/data` folder through updates. HA backups include it. Make a backup before updating anyway.

## Direct access without the sidebar (optional)

For a wall tablet, or another machine on your network:

1. In the app's Network section, set a host port for `8095/tcp`.
2. In its Configuration tab, set **Home Assistant URL** to the address your browser uses for HA, e.g. `http://homeassistant.local:8123`.
3. Open `http://homeassistant.local:8095` and click **Sign in with Home Assistant**.

## Without apps (HA Container)

1. Run the server as a container next to Home Assistant; `dev/docker-compose.yml` shows how. Set:
   - `STEWARD_HA_URL` to where the container reaches HA;
   - `STEWARD_HA_PUBLIC_URL` to where your browser reaches it;
   - `STEWARD_API_TOKEN` to a long random string.
2. Never set `STEWARD_TRUST_ALL`: it lets anyone on the network in.
3. Copy `custom_components/steward` into HA's `config/custom_components/` and restart HA.
4. Add **Steward** under Settings → Devices & services with the server's address and the token.

## Later: install from GitHub

Installing straight from GitHub ("Add repository" in the app store, plus HACS for the integration) needs two things:

1. **Published images.** A GitHub Actions workflow builds the app image for `amd64` and `aarch64` and pushes it to `ghcr.io`, and `app/config.yaml` names that image. The Supervisor can't build from this repository as it is, because the app's Dockerfile needs the server and the built web UI next to it.
2. **A public repository**, for HACS. A private repository would also need the token URL in the app store and registry credentials for a private image.
