#!/bin/bash
# Install a user timer. The server must already be configured and running.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
python=${CONTENTSWARM_PYTHON:-$repo/.venv/bin/python}
[[ -x "$python" ]] || { echo "Set CONTENTSWARM_PYTHON to the installed Python environment" >&2; exit 1; }
unit_dir="$HOME/.config/systemd/user"
mkdir -p "$unit_dir" "$HOME/.local/bin"
# Paths are encoded by Python for systemd's quoted ExecStart syntax.
"$python" - "$repo" "$python" "$unit_dir" <<'PY'
import json, pathlib, sys, shutil
repo, python, units = sys.argv[1:]
command = " ".join(json.dumps(x.replace('%', '%%').replace('$', '$$')) for x in (python, repo + '/social_worker.py'))
pathlib.Path(units, 'contentswarm-social.service').write_text('''[Unit]
Description=Prepare due ContentSwarm social drafts
After=omarchy-contentswarm.service
[Service]
Type=oneshot
EnvironmentFile=-%h/.config/contentswarm/social.env
Environment=CONTENTSWARM_KEYRING=1
Environment=CONTENTSWARM_API_URL=http://127.0.0.1:5055/api/v1
Environment="CONTENTSWARM_BRAIN_BIN=''' + (shutil.which('claude') or 'claude').replace('%', '%%') + '''"
ExecStart=''' + command + '''
TimeoutStartSec=600
UMask=0077
''')
PY
cp "$repo/deploy/contentswarm-social.timer" "$unit_dir/contentswarm-social.timer"
systemctl --user daemon-reload
systemctl --user enable --now contentswarm-social.timer
echo "Timer installed. Configure the worker credentials and URL before scheduling drafts."
