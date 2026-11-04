#!/usr/bin/env bash
# Steward kitchen terminal: set up a Raspberry Pi (Raspberry Pi OS with desktop) to start Chromium in
# kiosk mode on Steward's kiosk page at boot, allow the camera for Steward, run the helper that pairs
# Bluetooth scanners, and turn the screen off when nobody uses it.
#
# Run it on the Pi as the desktop user (not with sudo), with the pairing link from
# Steward → Settings → Kitchen terminals:
#
#   curl -fsSL https://github.com/DanielTerletzkiy/steward/releases/latest/download/setup-pi.sh | bash -s -- '<pairing link>'
#
# The script pairs the terminal itself and keeps its key in ~/.config/steward-kiosk/key, so the terminal
# stays paired whatever happens to the browser. Run it again without a link to update an existing setup.
# Instead of the pairing link you can pass the kiosk address (http://<host>:<port>/#/kiosk) and type the
# pairing code on the screen (then the Bluetooth helper has no key until you run it with a link). Options:
#   --dry-run          print what would change, change nothing
#   --blank-after N    turn the screen off after N minutes without input (default 10, 0 = never)
#   --no-autologin     leave the boot behaviour alone
set -euo pipefail

DRY=0
BLANK_MINUTES=10
AUTOLOGIN=1
LINK=""
RELEASE="https://github.com/DanielTerletzkiy/steward/releases/latest/download"

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --blank-after) BLANK_MINUTES="${2:?--blank-after needs minutes}"; shift ;;
    --no-autologin) AUTOLOGIN=0 ;;
    -h|--help) echo "Usage: setup-pi.sh [--dry-run] [--blank-after MINUTES] [--no-autologin] [pairing link or kiosk address]"; exit 0 ;;
    -*) echo "Unknown option: $1" >&2; exit 2 ;;
    *) LINK="$1" ;;
  esac
  shift
done

die() { echo "setup-pi: $*" >&2; exit 1; }
say() { echo "==> $*"; }
run() {
  if [ "$DRY" = 1 ]; then echo "+ $*"; else "$@"; fi
}
write_file() { # path, mode; content on stdin
  local path="$1" mode="$2" content
  content="$(cat)"
  if [ "$DRY" = 1 ]; then
    printf -- '--- would write %s:\n%s\n---\n' "$path" "$content"
    return
  fi
  mkdir -p "$(dirname "$path")"
  printf '%s\n' "$content" > "$path"
  chmod "$mode" "$path"
}
sudo_write() { # path; content on stdin (for files outside the home directory)
  local path="$1" content
  content="$(cat)"
  if [ "$DRY" = 1 ]; then
    printf -- '--- would write (sudo) %s:\n%s\n---\n' "$path" "$content"
    return
  fi
  sudo mkdir -p "$(dirname "$path")"
  printf '%s\n' "$content" | sudo tee "$path" > /dev/null
}

[ "$(id -u)" != 0 ] || die "run this as the desktop user, without sudo; it asks for sudo where it needs it"

CONFIG="$HOME/.config/steward-kiosk"
LAUNCHER="$HOME/.local/bin/steward-kiosk"
AGENT="$HOME/.local/bin/steward-kiosk-agent"

if [ -z "$LINK" ]; then
  [ -f "$CONFIG/url" ] || die "pass the pairing link (or the kiosk address) from Steward → Settings → Kitchen terminals"
  LINK="$(cat "$CONFIG/url")"
  say "Updating the existing setup"
fi
case "$LINK" in
  http://*|https://*) ;;
  *) die "that doesn't look like an address: $LINK" ;;
esac

# The server's address: everything before /auth/... or /#/...
ORIGIN="${LINK%%/auth/*}"
ORIGIN="${ORIGIN%%/#*}"
ORIGIN="${ORIGIN%/}"
KIOSK_URL="$ORIGIN/#/kiosk"

say "Steward at $ORIGIN"
if [ "$DRY" = 0 ] && ! curl -fsS -o /dev/null --max-time 10 "$ORIGIN/"; then
  echo "    Can't reach $ORIGIN/ from this Pi right now. Setting it up anyway; check the address and the app's host port."
fi

# --- pairing: trade the code for the terminal's key ---------------------------------

case "$LINK" in
  */auth/terminal\?code=*)
    CODE="${LINK##*code=}"
    CODE="${CODE%%&*}"
    say "Pairing this terminal"
    if [ "$DRY" = 1 ]; then
      echo "+ curl -X POST $ORIGIN/auth/terminal/redeem (code $CODE)"
    else
      ANSWER="$(curl -fsS --max-time 15 -X POST -H 'Content-Type: application/json' \
        -d "{\"code\": \"$CODE\"}" "$ORIGIN/auth/terminal/redeem")" \
        || die "pairing failed: the code is wrong or expired. Create a new one in Steward → Settings → Kitchen terminals."
      KEY="$(printf '%s' "$ANSWER" | python3 -c 'import json, sys; print(json.load(sys.stdin)["key"])')"
      write_file "$CONFIG/key" 600 <<<"$KEY"
    fi
    ;;
esac
[ "$DRY" = 1 ] || [ -f "$CONFIG/key" ] || echo "    No pairing link given: type the pairing code on the screen. The Bluetooth helper needs the link; run this again with one to set it up."

# --- packages ---------------------------------------------------------------

if [ -d /etc/xdg/labwc ] || command -v labwc >/dev/null 2>&1; then
  SESSION=labwc
elif [ -d /etc/xdg/lxsession ]; then
  SESSION=x11
else
  die "no supported desktop found. Use Raspberry Pi OS with desktop (labwc, the default since late 2024, or the older X11 desktop)."
fi
say "Desktop session: $SESSION"

CHROMIUM="$(command -v chromium || command -v chromium-browser || true)"
PACKAGES=()
[ -n "$CHROMIUM" ] || PACKAGES+=(chromium)
command -v python3 >/dev/null 2>&1 || PACKAGES+=(python3)
command -v bluetoothctl >/dev/null 2>&1 || PACKAGES+=(bluez)
if [ "$SESSION" = labwc ]; then
  command -v swayidle >/dev/null 2>&1 || PACKAGES+=(swayidle)
  command -v wlopm >/dev/null 2>&1 || PACKAGES+=(wlopm)
else
  command -v unclutter >/dev/null 2>&1 || PACKAGES+=(unclutter)
fi
if [ ${#PACKAGES[@]} -gt 0 ]; then
  say "Installing ${PACKAGES[*]}"
  run sudo apt-get update
  run sudo apt-get install -y "${PACKAGES[@]}"
fi
CHROMIUM="$(command -v chromium || command -v chromium-browser || echo chromium)"

# --- Chromium policy: camera and wake lock for Steward over http:// --------------------------
# Browsers only allow the camera (and keeping the screen on) on secure pages. This treats Steward's
# address as secure and allows its camera without a prompt; nothing else changes.

say "Allowing the camera for $ORIGIN"
sudo_write /etc/chromium/policies/managed/steward-kiosk.json <<EOF
{
  "OverrideSecurityRestrictionsOnInsecureOrigin": ["$ORIGIN"],
  "VideoCaptureAllowedUrls": ["$ORIGIN"]
}
EOF

# --- Bluetooth: on, and usable by this user (for the helper) ---------------------------------

say "Turning Bluetooth on"
run sudo rfkill unblock bluetooth || true
run sudo systemctl enable --now bluetooth || true
id -nG | grep -qw bluetooth || run sudo usermod -aG bluetooth "$USER"

# --- the helper and the launcher -----------------------------------------------------

say "Installing the Bluetooth helper"
# Run from a checkout: the helper next to this script. Piped from the release: download it.
HERE=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  HERE="$(dirname "${BASH_SOURCE[0]}")"
fi
if [ -n "$HERE" ] && [ -f "$HERE/steward-kiosk-agent" ]; then
  run mkdir -p "$(dirname "$AGENT")"
  run install -m 755 "$HERE/steward-kiosk-agent" "$AGENT"
else
  run mkdir -p "$(dirname "$AGENT")"
  run curl -fsSL -o "$AGENT" "$RELEASE/steward-kiosk-agent"
  run chmod 755 "$AGENT"
fi

say "Kiosk address: $KIOSK_URL"
write_file "$CONFIG/url" 600 <<<"$KIOSK_URL"
[ ! -f "$CONFIG/first-url" ] || run rm -f "$CONFIG/first-url" # left by 0.3.0

write_file "$LAUNCHER" 755 <<EOF
#!/bin/sh
# Steward kitchen terminal: open the kiosk page full screen, and start Chromium again if it exits.
# Written by setup-pi.sh; the address is in $CONFIG/url, the terminal's key in $CONFIG/key.
CONFIG="$CONFIG"
page() {
  url="\$(cat "\$CONFIG/url")"
  # The key goes in the URL fragment, which the browser never sends to a server; the page keeps it
  # and signs in with it whenever the browser has lost its cookie.
  if [ -f "\$CONFIG/key" ]; then url="\$url?key=\$(cat "\$CONFIG/key")"; fi
  echo "\$url"
}
origin="\$(cat "\$CONFIG/url")"
origin="\${origin%%/#*}"
# Wait up to two minutes for the network and Steward after boot.
i=0
while [ \$i -lt 60 ] && ! curl -fsS -o /dev/null --max-time 2 "\$origin/"; do
  sleep 2
  i=\$((i + 1))
done
# A crash or power cut must not leave a "restore pages?" bubble on the screen.
prefs="\$HOME/.config/chromium/Default/Preferences"
[ -f "\$prefs" ] && sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/; s/"exited_cleanly":false/"exited_cleanly":true/' "\$prefs"
while true; do
  "$CHROMIUM" --kiosk --noerrdialogs --disable-infobars --disable-session-crashed-bubble \\
    --autoplay-policy=no-user-gesture-required --check-for-update-interval=31536000 \\
    --disable-features=Translate --overscroll-history-navigation=0 --password-store=basic \\
    "\$(page)"
  sleep 2
done
EOF

# --- start at login, screen off when idle ---------------------------------------

AGENT_LOOP="sh -c 'while true; do python3 $AGENT; sleep 5; done'"
BLANK_SECONDS=$((BLANK_MINUTES * 60))
if [ "$SESSION" = labwc ]; then
  AUTOSTART="$HOME/.config/labwc/autostart"
  # The user's autostart replaces the system one, so there is no panel or desktop: only the kiosk.
  if [ -f "$AUTOSTART" ] && ! grep -q steward-kiosk "$AUTOSTART"; then
    run cp "$AUTOSTART" "$AUTOSTART.before-steward"
    say "Saved your previous labwc autostart as $AUTOSTART.before-steward"
  fi
  {
    echo "# Steward kitchen terminal (setup-pi.sh). Remove this file to get the normal desktop back."
    if [ "$BLANK_MINUTES" -gt 0 ]; then
      echo "swayidle -w timeout $BLANK_SECONDS 'wlopm --off \\*' resume 'wlopm --on \\*' &"
    fi
    echo "$AGENT_LOOP &"
    echo "$LAUNCHER &"
  } | write_file "$AUTOSTART" 644
else
  AUTOSTART="$HOME/.config/lxsession/LXDE-pi/autostart"
  {
    echo "# Steward kitchen terminal (setup-pi.sh). Remove this file to get the normal desktop back."
    if [ "$BLANK_MINUTES" -gt 0 ]; then
      echo "@xset s $BLANK_SECONDS $BLANK_SECONDS"
      echo "@xset +dpms"
      echo "@xset dpms $BLANK_SECONDS $BLANK_SECONDS $BLANK_SECONDS"
    else
      echo "@xset s off"
      echo "@xset -dpms"
    fi
    echo "@unclutter -idle 3"
    echo "@$AGENT_LOOP"
    echo "@$LAUNCHER"
  } | write_file "$AUTOSTART" 644
fi

if [ "$AUTOLOGIN" = 1 ] && command -v raspi-config >/dev/null 2>&1; then
  say "Booting straight into the desktop (auto-login)"
  run sudo raspi-config nonint do_boot_behaviour B4
fi

say "Done. Reboot to start the kitchen terminal:  sudo reboot"
if [ ! -f "$CONFIG/key" ]; then
  echo "    The screen asks for a pairing code on first start; create one in Steward → Settings → Kitchen terminals."
fi
echo "    To undo: delete $AUTOSTART, $LAUNCHER and $AGENT, then reboot."
