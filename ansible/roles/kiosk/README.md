# Role `danielterletzkiy.steward.kiosk`

Turns a Raspberry Pi into Steward's kitchen terminal:
- **Installs the Steward Kiosk app:** the `steward-kiosk` .deb from Steward's GitHub release, checked against the release's `SHA256SUMS`.
- **Pairs it with Steward**, with a pairing code, if the Pi has no valid key yet.
- **Starts it full screen** when the desktop starts, logged in automatically.
- **Sets up Bluetooth**, so scanners can be paired from the kiosk screen.

The app shows Steward's kiosk page, pairs Bluetooth scanners and turns the screen off when nobody uses it. It switches to a new version by itself after an upgrade and applies new settings without a restart, so the role has nothing to restart.

## Requirements

- **The Pi:** Raspberry Pi OS (64-bit) with desktop, Bookworm or Trixie (a Pi 4, 400 or 5).
  - `dpkg --print-architecture` must say `arm64`.
  - Plain Debian (arm64 or amd64) with a desktop works too.
- **Steward:** it needs a direct address. In the Steward app's Network settings, set a host port for `8095/tcp`.
- **The controller:** ansible-core 2.15 or newer. Run the play with `become: true`.

## Variables

| Variable | Default | |
|---|---|---|
| `steward_kiosk_url` | required | Steward's address as the Pi reaches it, e.g. `http://homeassistant.local:8095` |
| `steward_kiosk_user` | required | the desktop user that runs the kiosk |
| `steward_kiosk_pairing_code` | `""` | a pairing code from Steward → Settings → Kitchen terminals; used only while the Pi has no valid key |
| `steward_kiosk_version` | `latest` | the release to install, e.g. `0.5.0` |
| `steward_kiosk_deb_file` | `""` | a .deb on the controller to install instead (offline installations, tests) |
| `steward_kiosk_repository` | `DanielTerletzkiy/steward` | where releases come from |
| `steward_kiosk_session` | `kiosk` | `kiosk`: the desktop starts only the app. `desktop`: the normal desktop with the app on top |
| `steward_kiosk_autologin` | `true` | boot into the desktop logged in, with raspi-config (skipped without it) |
| `steward_kiosk_bluetooth` | `true` | BlueZ on and unblocked, the user in the `bluetooth` group |
| `steward_kiosk_screen_off` | `true` | screen off when the kiosk page goes dark (never during a recipe) |
| `steward_kiosk_zoom` | `1.0` | page zoom, e.g. `1.25` on a small screen with a high resolution |
| `steward_kiosk_reboot` | `false` | reboot when a change needs it; otherwise the play says so |

The argument spec (`meta/argument_specs.yml`) checks these when the role starts. `ansible-doc -t role danielterletzkiy.steward.kiosk` shows them.

## Pairing

The app keeps the terminal's key in `~/.config/steward-kiosk/key`. On every run, the role first asks Steward whether that key still works:
- **It works:** nothing happens, so `steward_kiosk_pairing_code` may stay in the inventory or be passed with `-e`.
- **There is no key, or the terminal was removed in Steward:** the role trades the pairing code for a new key. Without a code it says so, and the kiosk screen asks for one.
- **Steward doesn't answer:** the key is kept.

A code works once, for 15 minutes: Steward → Settings → Kitchen terminals → **Add terminal**, or **Pair a new device** for an existing one.

## What it changes on the Pi

- **Packages:**
  - `steward-kiosk` (from the release);
  - GStreamer's camera plugins;
  - `wlopm` on labwc, or `x11-xserver-utils` on X11, for switching the screen;
  - `bluez` and `rfkill`.
- **App settings:** `~/.config/steward-kiosk/config.toml`, marked as managed by Ansible. The app's own setup screen then says that its changes don't last.
- **Session:**
  - `kiosk`: the user's labwc autostart (`~/.config/labwc/autostart`; on X11, `~/.config/lxsession/LXDE-pi/autostart`) starts only the app. The file it replaces is kept as a backup.
  - `desktop`: `~/.config/autostart/steward-kiosk.desktop`.
- **System settings:**
  - the boot behaviour "desktop, logged in automatically", via `raspi-config nonint do_boot_behaviour B4`;
  - the user joins the `bluetooth` group.
- **Removes 0.4.0's `setup-pi.sh` setup:**
  - `~/.local/bin/steward-kiosk` and `steward-kiosk-agent`;
  - its autostart;
  - `/etc/chromium/policies/managed/steward-kiosk.json`;
  - `~/.config/steward-kiosk/url`.
  - The key stays, so a Pi paired with 0.4.0 needs no new code.

## Examples

**First run:**

```bash
ansible-playbook kitchen.yml -e steward_kiosk_pairing_code=ABCD-EFGH
```

**Pinned version, normal desktop, automatic reboot:**

```yaml
- hosts: kitchen
  become: true
  roles:
    - role: danielterletzkiy.steward.kiosk
      vars:
        steward_kiosk_url: http://192.168.1.10:8095
        steward_kiosk_user: kitchen
        steward_kiosk_version: "0.5.0"
        steward_kiosk_session: desktop
        steward_kiosk_reboot: true
```

## On the Pi

- **Log:** `~/.local/state/steward-kiosk/kiosk.log`.
- **Page console:** start `STEWARD_KIOSK_DEBUG=1 steward-kiosk` to get the page's console in the log as well.
- **Blank or white window:** some GPU drivers need `WEBKIT_DISABLE_DMABUF_RENDERER=1`. Put it in front of `steward-kiosk` in the autostart file.

## Testing

Molecule runs the role in a Debian Bookworm container dressed up as Raspberry Pi OS: a fake raspi-config and the leftovers from 0.4.0. From `roles/kiosk`:

```bash
MOLECULE_STEWARD_KIOSK_DEB=/path/to/steward-kiosk_0.5.0_amd64.deb molecule test
```

**Testing pairing too:** also set the following, pointing at a running Steward.
- `MOLECULE_STEWARD_URL`: Steward's address as the container reaches it.
- `MOLECULE_STEWARD_NETWORK`: the Docker network Steward is on.
- `MOLECULE_STEWARD_PAIRING_CODE`: a fresh pairing code.
