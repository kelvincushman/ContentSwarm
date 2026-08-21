#!/usr/bin/env bash
# Install ContentSwarm as a systemd service on the AI server.
# Run from the repo root as a user with sudo:  ./deploy/install_aiserver.sh
set -euo pipefail

INSTALL_DIR="${CONTENTSWARM_INSTALL_DIR:-/opt/contentswarm}"
ENV_DIR=/etc/contentswarm
SERVICE_USER="${SUDO_USER:-$USER}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== ContentSwarm AI-server install ==="
echo "Repo:    $REPO_ROOT"
echo "Target:  $INSTALL_DIR (service user: $SERVICE_USER)"

# 1. Prerequisites
command -v python3 >/dev/null || { echo "ERROR: python3 not found"; exit 1; }
if ! command -v adb >/dev/null; then
    echo "WARNING: adb not found - install android-tools-adb before controlling phones"
fi

# 2. Copy the application
sudo mkdir -p "$INSTALL_DIR"
sudo rsync -a --delete \
    --exclude .git --exclude venv --exclude __pycache__ \
    "$REPO_ROOT/" "$INSTALL_DIR/"
sudo chown -R "$SERVICE_USER" "$INSTALL_DIR"

# 3. Virtualenv + dependencies
if [ ! -d "$INSTALL_DIR/venv" ]; then
    sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/venv"
fi
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" \
    install -r "$INSTALL_DIR/requirements.txt" -r "$INSTALL_DIR/dashboard/requirements.txt"
# CLI for local use on the server too:
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -e "$INSTALL_DIR"

# 4. Environment file (created once, never overwritten - holds the token)
sudo mkdir -p "$ENV_DIR"
if [ ! -f "$ENV_DIR/env" ]; then
    GENERATED_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
    sudo tee "$ENV_DIR/env" >/dev/null <<EOF
# ContentSwarm server environment - edit and restart the service to apply.
CONTENTSWARM_HOST=0.0.0.0
CONTENTSWARM_PORT=5000
CONTENTSWARM_PHONES_CONFIG=$INSTALL_DIR/phones_config.json
CONTENTSWARM_API_TOKEN=$GENERATED_TOKEN

# Vision model serving the on-phone agent (vLLM/SGLang or a hosted provider):
PHONE_AGENT_BASE_URL=http://localhost:8000/v1
PHONE_AGENT_MODEL=autoglm-phone-9b
PHONE_AGENT_API_KEY=EMPTY
PHONE_AGENT_LANG=en

# Optional local generation:
COMFYUI_URL=http://127.0.0.1:8188
EOF
    sudo chmod 600 "$ENV_DIR/env"
    echo "Wrote $ENV_DIR/env (API token generated - view with: sudo cat $ENV_DIR/env)"
else
    echo "$ENV_DIR/env already exists - left untouched"
fi

# 5. systemd unit
sudo sed "s/^User=%i/User=$SERVICE_USER/" "$REPO_ROOT/deploy/contentswarm.service" \
    | sudo tee /etc/systemd/system/contentswarm.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now contentswarm.service

echo
echo "=== Done ==="
echo "Status:   systemctl status contentswarm"
echo "Logs:     journalctl -u contentswarm -f"
echo "API:      http://<this-server>:5000/api/v1/status"
echo "Next:     edit $INSTALL_DIR/phones_config.json with your phones' ADB addresses,"
echo "          then: sudo systemctl restart contentswarm"
