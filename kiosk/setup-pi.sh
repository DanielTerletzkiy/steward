#!/usr/bin/env bash
# Steward kitchen terminal: set up a Raspberry Pi (Raspberry Pi OS with desktop) to start Chromium in
# kiosk mode on Steward's kiosk page at boot, and turn the screen off when nobody uses it.
#
# Run it once on the Pi as the desktop user (not with sudo), with the pairing link from
# Steward → Settings → Kitchen terminals:
#
#   curl -fsSL https://github.com/DanielTerletzkiy/steward/releases/latest/download/setup-pi.sh | bash -s -- '<pairing link>'
#
# Instead of the pairing link you can pass the kiosk address (http://<host>:<port>/#/kiosk) and type the
# pairing code on the screen. Options:
#   --dry-run          print what would change, change nothing
#   --blank-after N    turn the screen off after N minutes without input (default 10, 0 = never)
#   --no-autologin     leave the boot behaviour alone
set -euo pipefail

DRY=0
BLANK_MINUTES=10
AUTOLOGIN=1
LINK=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --blank-after) BLANK_MINUTES="${2:?--blank-after needs minutes}"; shift ;;
    --no-autologin) AUTOLOGIN=0 ;;
    -h|--help) echo "Usage: setup-pi.sh [--dry-run] [--blank-after MINUTES] [--no-autologin] <pairing link or kiosk address>"; exit 0 ;;
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

[ -n "$LINK" ] || die "pass the pairing link (or the kiosk address) from Steward → Settings → Kitchen terminals"
[ "$(id -u)" != 0 ] || die "run this as the desktop user, without sudo; it asks for sudo where it needs it"
case "$LINK" in
  http://*|https://*) ;;
  *) die "that doesn't look like an address: $LINK" ;;
esac

# The server's address: everything before /auth/... or /#/...
ORIGIN="${LINK%%/auth/*}"
ORIGIN="${ORIGIN%%/#*}"
ORIGIN="${ORIGIN%/}"
KIOSK_URL="$ORIGIN/#/kiosk"
case "$LINK" in
  */auth/terminal\?code=*) FIRST_URL="$LINK" ;;
  *) FIRST_URL="$KIOSK_URL" ;;
esac

say "Steward at $ORIGIN"
if [ "$DRY" = 0 ] && ! curl -fsS -o /dev/null --max-time 10 "$ORIGIN/"; then
  echo "    Can't reach $ORIGIN/ from this Pi right now. Setting it up anyway; check the address and the app's host port."
fi

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

# --- the launcher -------------------------------------------------------------

CONFIG="$HOME/.config/steward-kiosk"
LAUNCHER="$HOME/.local/bin/steward-kiosk"

say "Kiosk address: $KIOSK_URL"
write_file "$CONFIG/url" 600 <<<"$KIOSK_URL"
# The first start opens the pairing link; it sets the terminal's cookie and lands on the kiosk page.
write_file "$CONFIG/first-url" 600 <<<"$FIRST_URL"

write_file "$LAUNCHER" 755 <<EOF
#!/bin/sh
# Steward kitchen terminal: open the kiosk page full screen, and start Chromium again if it exits.
# Written by setup-pi.sh; the address is in $CONFIG/url.
CONFIG="$CONFIG"
url="\$(cat "\$CONFIG/url")"
if [ -f "\$CONFIG/first-url" ]; then
  url="\$(cat "\$CONFIG/first-url")"
  rm -f "\$CONFIG/first-url"
fi
origin="\${url%%/auth/*}"
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
    "\$url"
  url="\$(cat "\$CONFIG/url")"
  sleep 2
done
EOF

# --- start at login, screen off when idle ---------------------------------------

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
    echo "@$LAUNCHER"
  } | write_file "$AUTOSTART" 644
fi

if [ "$AUTOLOGIN" = 1 ] && command -v raspi-config >/dev/null 2>&1; then
  say "Booting straight into the desktop (auto-login)"
  run sudo raspi-config nonint do_boot_behaviour B4
fi

say "Done. Reboot to start the kitchen terminal:  sudo reboot"
if [ "$FIRST_URL" = "$KIOSK_URL" ]; then
  echo "    The screen asks for a pairing code on first start; create one in Steward → Settings → Kitchen terminals."
else
  echo "    The pairing link works once, for 15 minutes. If it has expired by then, the screen asks for a new code."
fi
echo "    To undo: delete $AUTOSTART and $LAUNCHER, then reboot."
