#!/usr/bin/env bash
# Install the ContentSwarm integration into an Orphus agent directory.
set -euo pipefail

ORPHUS_DIR="${ORPHUS_CODING_AGENT_DIR:-$HOME/.orphus/agent}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing ContentSwarm integration into $ORPHUS_DIR"

mkdir -p "$ORPHUS_DIR/skills" "$ORPHUS_DIR/agents" "$ORPHUS_DIR/fleets"

for skill_dir in "$HERE"/skills/*/; do
    cp -r "$skill_dir" "$ORPHUS_DIR/skills/"
done
cp "$HERE/agents/phone-operator.md" "$ORPHUS_DIR/agents/"
cp "$HERE/fleets/contentswarm.fleet.yaml" "$ORPHUS_DIR/fleets/"

echo "Installed:"
echo "  skills:  $(ls "$HERE/skills" | tr '\n' ' ')"
echo "  agent:   phone-operator"
echo "  fleet:   contentswarm"
echo
echo "Next, on this machine:"
echo "  export CONTENTSWARM_API_URL=\"http://<server-ip>:5000/api/v1\""
echo "  export CONTENTSWARM_API_TOKEN=\"<token>\"   # if the server sets one"
echo "  pip install -e \"$(dirname "$HERE")\"        # provides the contentswarm CLI"
echo "  contentswarm status                          # smoke test"
