#!/usr/bin/env bash
# Stage the Home Assistant app into dist/ha-app/steward: manifest, Dockerfile, server and web UI.
# Copy that folder into HA's /addons share (Samba or SSH app), then Settings → Apps → App store →
# ⋮ → Check for updates; "Steward" shows up under "Local apps".
#   dev/scripts/build_app.sh           stage only
#   dev/scripts/build_app.sh --docker  also build the image locally, as the Supervisor would
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
out="$root/dist/ha-app/steward"

(cd "$root/frontend" && npm run build --silent)
rm -rf "$out" && mkdir -p "$out"
cp -R "$root/app/." "$out/"
cp "$root/server/pyproject.toml" "$out/"
rsync -a --exclude '__pycache__' "$root/server/steward_server" "$out/"
echo "Staged $out"

if [[ "${1:-}" == "--docker" ]]; then
  docker build -t local/steward-app "$out"
fi
