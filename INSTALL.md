# Use Steward in your Home Assistant

Steward has two parts, and your Home Assistant needs both:

- **The app** (Settings → Apps): the Steward server and web UI. It opens in the sidebar and keeps your data.
- **The integration** (`custom_components/steward`): to-do lists, sensors, calendars, actions, and the bridge for AI Task, weather and your appliances.

Apps exist on Home Assistant OS and Supervised. For HA Container, see [Without apps](#without-apps-ha-container).

| Install route | Works with a private repository? | Updates |
|---|---|---|
| [Manual installation](#manual-installation) from the release zips | **Yes**: you download the zips while signed in to GitHub. | By hand |
| [From GitHub](#install-from-github): app store + HACS | App store: only with workarounds. HACS: **no**, it doesn't support private repositories at all. | In HA |
| [From a checkout](#from-a-checkout-development) over SSH | Yes | By hand |

## Manual installation

You need a way to copy files into Home Assistant. Any of these works:
- the **Samba share** app;
- the **Terminal & SSH** app;
- the **Studio Code Server** app, which can upload files.

### 1. Download

On GitHub, open **Releases** and download both zips of the latest version:
- `steward-app-<version>.zip`, the app;
- `steward-integration-<version>.zip`, the integration.

Each unzips into a folder called `steward`.

### 2. Copy the app

Unzip `steward-app-<version>.zip` and copy the `steward` folder into HA's **`addons`** share, so you get `addons/steward/config.yaml`.

- **Samba:** connect to `\\homeassistant.local\addons` (Windows), or `smb://homeassistant.local/addons` (macOS: Finder → Go → Connect to Server).
- **SSH**, from your computer:

```bash
scp -r steward root@homeassistant.local:/addons/
```

### 3. Copy the integration

Unzip `steward-integration-<version>.zip` and copy that `steward` folder into **`config/custom_components`**, so you get `config/custom_components/steward/manifest.json`. Create `custom_components` if it doesn't exist.

- **Samba:** `\\homeassistant.local\config\custom_components`.
- **SSH:**

```bash
scp -r steward root@homeassistant.local:/config/custom_components/
```

Then restart Home Assistant: Settings → System → ⏻ → **Restart Home Assistant**.

### 4. Install the app

1. Open Settings → Apps → **App store**, then ⋮ → **Check for updates**.
2. Under **Local apps**, open **Steward** and click **Install**. HA builds the image on the device, which takes a few minutes, longer on a Raspberry Pi.
3. Leave **Demo data** off; demo data is for looking around, not for real use.
4. Turn on **Show in sidebar**, then click **Start**.

### 5. Connect the integration

Go to Settings → Devices & services. HA shows **Discovered: Steward**; click **Add**. The app announced itself with its token, so there is nothing to type.

Steward now opens from the sidebar, signed in as your HA user. The to-do lists, sensors and calendars appear under the Steward device. Continue with [Set it up for your home](#set-it-up-for-your-home).

### Updating a manual installation

1. Download the new zips.
2. Replace `addons/steward` and `config/custom_components/steward` with the new folders. Delete the old folders first rather than merging into them.
3. Restart Home Assistant.
4. In the app store, ⋮ → **Check for updates**. Steward then offers **Update**, which rebuilds it.

Your data stays in the app's `/data` folder through updates. HA backups include it; make a backup before updating anyway.

## Install from GitHub

Once a release exists, Home Assistant can install and update both parts from the repository itself.

**The app:**
1. Settings → Apps → App store → ⋮ → **Repositories**.
2. Add `https://github.com/DanielTerletzkiy/steward`.
3. Install **Steward**.

HA pulls the ready-made image from `ghcr.io/danielterletzkiy/{amd64,aarch64}-steward`, so nothing is built on the device.

**The integration:**
1. HACS → ⋮ → **Custom repositories**.
2. Add `https://github.com/DanielTerletzkiy/steward` as type **Integration**.
3. Download **Steward** and restart HA.

Then continue with [step 5](#5-connect-the-integration).

**While the repository is private:**
- **HACS:** can't use it. Copy the integration manually (step 3 above).
- **App store:** can't read a private repository on its own. People report that a token in the URL works, but this isn't documented: `https://USER:TOKEN@github.com/DanielTerletzkiy/steward`. Use a fine-grained token with read-only *Contents* access to this repository only.
- **Images:** the images on ghcr.io are private too, so HA can't pull them. Either:
  - make the packages public: GitHub → your profile → Packages → `amd64-steward` / `aarch64-steward` → Package settings → Change visibility; or
  - give HA a login: app store → ⋮ → **Registries** → add `ghcr.io` with your GitHub user and a classic token with `read:packages`. This needs Advanced mode in your user profile.

The simplest choice is manual installation until the repository is public.

## Set it up for your home

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
- **Storage locations:** Settings → Storage locations. Add Fridge, Freezer, Pantry and so on. Then pick a usual place for each product.
- **Receipts:** upload eBon PDFs, or let Steward fetch them from your mailbox:
  1. Settings → Receipts from email → **Gmail**.
  2. Create an app password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords). This needs 2-step verification on the Google account.
  3. Enter your address and the app password, then **Test connection**.
  4. Turn on **Check the mailbox regularly** and **Save**.

  If your eBons skip the inbox (a filter or label), set the folder to `[Gmail]/All Mail`, or `[Gmail]/Alle Nachrichten` with Gmail in German.
- **Notifications:** Steward fires `steward_appliance_finished` and `steward_appliance_started` in HA. Use them as automation triggers.

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
3. Copy the integration into HA's `config/custom_components/` as in [step 3](#3-copy-the-integration) and restart HA.
4. Add **Steward** under Settings → Devices & services with the server's address and the token.

## From a checkout (development)

To try changes before a release, build on your computer and copy over SSH. This needs:
- the **Terminal & SSH** app, with your public key under `authorized_keys` and a port set under Network;
- `npm ci` run once in `frontend/`.

From the repository root:

```bash
export HA=root@homeassistant.local
```

```bash
dev/scripts/build_app.sh
```

```bash
COPYFILE_DISABLE=1 tar -C dist/ha-app -cf - --exclude __pycache__ steward | ssh $HA 'rm -rf /addons/steward && tar -xf - -C /addons'
```

```bash
COPYFILE_DISABLE=1 tar -C custom_components -cf - --exclude __pycache__ steward | ssh $HA 'mkdir -p /config/custom_components && rm -rf /config/custom_components/steward && tar -xf - -C /config/custom_components'
```

```bash
ssh $HA ha core restart
```

Then install or **Rebuild** Steward under Local apps.

`build_app.sh` drops the `image:` line from the app's manifest, so HA builds the copied app on the device instead of pulling the published image.

## Releasing a new version

1. Set the same version in `app/config.yaml` and `custom_components/steward/manifest.json`.
2. Commit, then tag and push:

```bash
git tag v0.2.0 && git push origin master v0.2.0
```

The **Release** workflow then:
- checks that the versions match the tag;
- builds the images for `amd64` and `aarch64` and pushes them to ghcr.io;
- creates the GitHub release with both zips.

HA offers the update as soon as it sees the new version in `app/config.yaml`, which can be before the images finish building (about 10 minutes). So push the tag together with the version change.
