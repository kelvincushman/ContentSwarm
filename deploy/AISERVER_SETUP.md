# AI Server Setup

The mobile console now requires its separate `CONTENTSWARM_CONSOLE_TOKEN` for sign-in, including
legacy dashboard routes and Socket.IO. Agents keep sending bearer headers;
browser sessions last eight hours and expire on restart. Set
`CONTENTSWARM_STATE_DIR` to a private writable directory for the durable reply
queue (default `~/.local/state/contentswarm`). Use HTTPS for remote browser access.
New installs generate both credentials. Existing installs must add a distinct
random `CONTENTSWARM_CONSOLE_TOKEN` to the private service environment before
using the GUI. Only the API token belongs in an agent environment. Review
decisions require an owner console session and CSRF token.
See [console setup](../dashboard/CONSOLE.md).
Server startup now fails without `CONTENTSWARM_API_TOKEN`. Browser cookies are
Secure by default; terminate HTTPS at a reverse proxy for remote use. Only a
loopback-bound local HTTP service may set `CONTENTSWARM_COOKIE_SECURE=0`.

Existing installations must change `CONTENTSWARM_HOST=0.0.0.0` to
`CONTENTSWARM_HOST=127.0.0.1` in `/etc/contentswarm/env`. For remote access, put
an HTTPS reverse proxy on the same server and set `CONTENTSWARM_TRUST_PROXY=1`.
For example, Caddy with a domain pointing at this server:

```caddyfile
contentswarm.example.com {
    reverse_proxy 127.0.0.1:5000
}
```

[Caddy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy) terminates HTTPS and sets the forwarded scheme; keep Secure cookies
enabled (the default). Alternatively, use an SSH tunnel to the loopback service
and `CONTENTSWARM_COOKIE_SECURE=0` for the local HTTP browser endpoint. The
installer prepares the service; configure the proxy or tunnel before remote use.

How to run ContentSwarm on your home AI server so Orphus (running there or on
any machine that can reach it — e.g. over your LAN, or remotely via Netbird)
can drive the phone fleet.

```
Orphus ── contentswarm CLI ──HTTP:5000──▶ AI server
                                            ├─ contentswarm.service (API + dashboard)
                                            ├─ vLLM/SGLang AutoGLM-9B (GPU, :8000)
                                            └─ adb ──TCP:5555──▶ phones on the LAN
```

## 1. Install ContentSwarm

```bash
git clone https://github.com/kelvincushman/ContentSwarm
cd ContentSwarm
./deploy/install_aiserver.sh
```

This copies the app to `/opt/contentswarm`, creates a venv, generates an API
token into `/etc/contentswarm/env` (mode 600), and enables the
`contentswarm` systemd service on port 5000.

```bash
systemctl status contentswarm
curl -s -H "Authorization: Bearer $(sudo grep CONTENTSWARM_API_TOKEN /etc/contentswarm/env | cut -d= -f2)" \
  http://localhost:5000/api/v1/status
```

## 2. Enroll the phones (ADB over TCP)

On each phone: enable Developer Options → USB debugging, connect once via USB,
then:

```bash
adb tcpip 5555
adb connect <phone-lan-ip>:5555
```

Edit `/opt/contentswarm/phones_config.json` with each phone's
`<ip>:5555` address and a name (`phone_01` …), then:

```bash
sudo systemctl restart contentswarm
export CONTENTSWARM_API_URL="http://127.0.0.1:5000/api/v1"
export CONTENTSWARM_API_TOKEN="$(sudo sed -n 's/^CONTENTSWARM_API_TOKEN=//p' /etc/contentswarm/env)"
contentswarm discover   # adds authorized ADB devices and persists phones_config.json
contentswarm phones     # all enrolled phones with connection status
```

Phones need the [ADB Keyboard APK](https://github.com/senzhk/ADBKeyBoard)
installed for text input (`adb install ADBKeyboard.apk`).

### Flow storage

Learned flows (the exact-press recordings made by `contentswarm learn`) are
stored as JSON under the directory named by `CONTENTSWARM_FLOWS_DIR` in
`/etc/contentswarm/env` (installer default: `/opt/contentswarm/flows`). The
API reads this at request time, so moving the directory just needs the env
var updated and `sudo systemctl restart contentswarm`. Back this directory up
— it is the fleet's learned knowledge.

## 3. Vision model (GPU)

The on-phone agent needs an AutoGLM-compatible vision model at
`PHONE_AGENT_BASE_URL`. Either point `/etc/contentswarm/env` at a hosted
provider (z.ai, Novita, Parasail — see the main README), or serve locally on
the GPU with vLLM:

```bash
pip install vllm
```

`/etc/systemd/system/vllm.service`:

```ini
[Unit]
Description=vLLM AutoGLM-9B vision model
After=network-online.target

[Service]
ExecStart=/usr/bin/env vllm serve zai-org/autoglm-phone-9b-multilingual \
    --served-model-name autoglm-phone-9b --port 8000
Restart=on-failure
User=YOUR_USER

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now vllm
```

## 4. Point Orphus at the server

On the machine running Orphus, use the HTTPS proxy address configured above.
For direct local use or an SSH tunnel, use its loopback HTTP endpoint instead.

```bash
./orphus/install.sh                      # installs skills/agent/fleet into ~/.orphus/agent/
pip install -e /path/to/ContentSwarm     # provides the contentswarm CLI

export CONTENTSWARM_API_URL="https://<server-domain>/api/v1"
export CONTENTSWARM_API_TOKEN="<token from /etc/contentswarm/env>"
contentswarm status                      # smoke test
```

Use these exports only in the current shell session. For persistent agent
services, load the token from a keyring or an owner-only service environment
file; do not copy the literal secret into a shared or unprotected shell profile.
See `orphus/README.md` for using the `phone-operator` agent and the
`contentswarm` fleet.

## 5. Verify end-to-end

```bash
contentswarm phones                          # devices online?
contentswarm installed phone_01              # discover apps on the device
contentswarm launch phone_01 Settings        # deterministic app launch
contentswarm screenshot phone_01 -o s.png    # capture proof
contentswarm run phone_01 "Open the calculator and type 2+2" --wait   # vision agent

# The core loop - learn once with the LLM, replay the exact presses:
contentswarm learn phone_01 "Open the calculator and type 2+2" --name calc-demo --wait
contentswarm replay phone_01 calc-demo --wait
```

### Verify the deterministic phone kernel

These commands do not require the vision model:

```bash
contentswarm ui phone_01
contentswarm launch phone_01 WhatsApp
contentswarm key phone_01 BACK --confirm
contentswarm swipe phone_01 500 1600 500 500 --duration-ms 300
```

Verify message preparation without sending:

```bash
umask 077
BODY_FILE=$(mktemp)
TOKEN_FILE=$(mktemp)
trap 'rm -f "$BODY_FILE" "$TOKEN_FILE"' EXIT
printf '%s' 'ContentSwarm setup test — do not send' >"$BODY_FILE"
contentswarm compose phone_01 sms +447700900123 \
  --body-file "$BODY_FILE" --token-file "$TOKEN_FILE"
contentswarm ui phone_01
contentswarm key phone_01 BACK --confirm
```

Do not include `send --confirm` in unattended deployment smoke tests. A real
send requires a person to approve the exact channel, recipient, and body.

### Messaging and social-media requirements

- Install and log into WhatsApp and each social app on the phone by hand.
- Grant only the Android permissions each app needs.
- Keep learned flows before Post, Send, Delete, Pay, Follow, Like, or Share;
  commit with one separately approved semantic tap.
- The server cannot read private app storage or bypass encrypted messaging.
- Screens protected by `FLAG_SECURE` cannot provide screenshot evidence; use
  the accessibility tree where available and require human verification when
  it is not.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `401 Unauthorized` | Token mismatch — compare with `/etc/contentswarm/env` |
| Phone shows `connected: false` | `adb connect <ip>:5555` again; phones drop TCP ADB after reboot |
| Vision task fails instantly | Model not reachable — check `PHONE_AGENT_BASE_URL`, `journalctl -u vllm` |
| Text input does nothing | ADB Keyboard APK missing on the phone |
| `adb: command not found` | Install Android Platform Tools (`android-tools` on Arch/Omarchy) |
| Phone is `unauthorized` | Unlock it and accept the USB debugging fingerprint prompt |
| `ui` returns no useful elements | App uses canvas/WebView or blocks accessibility; use screenshot + vision |
| Send returns `expected body is not present` | Draft changed since approval; inspect and obtain fresh approval |
| Send is unverified after a timeout | Inspect the conversation before any retry |
| Dashboard unreachable remotely | Server firewall — allow TCP 5000 from your network |
# Social worker deployment

See [dashboard/SOCIAL.md](../dashboard/SOCIAL.md) for the optional user timer,
account memory, draft budgets and delivery mode. `social_worker.py` calls the
REST API and the authenticated Claude CLI. `CONTENTSWARM_KEYRING=1` loads only
the agent credential from GNOME keyring on Omarchy; other hosts supply
`CONTENTSWARM_API_TOKEN` in the worker environment. Override
`CONTENTSWARM_API_URL` as needed: standalone social_worker.py defaults to
http://127.0.0.1:5000/api/v1; the Omarchy timer installer overrides it to port 5055.
`CONTENTSWARM_DELIVERY_ENABLED=1` enables approved-item delivery; its default is
off. `CONTENTSWARM_BRAIN_MODEL`, `CONTENTSWARM_BRAIN_BIN`,
`CONTENTSWARM_DRAFT_BUDGET` and `CONTENTSWARM_DELIVERY_BUDGET` configure the harness.
The worker/server share state through HTTP, not direct database access.

The pinned adb-agent-bridge dependency preserves XML parent indices so the kernel
can recognize labels inside buttons. Upgrade the pinned dependency along with
ContentSwarm (`pip install -r requirements.txt` in its environment), then restart
the service. Older bridge versions keep direct-control taps working but cannot
resolve non-clickable child labels. Do not install an unpinned bridge as a workaround.

Use bridge 0.2.1 from the pinned revision. Earlier source checkouts could contain
the correct parser while their wheel silently packaged stale tracked `build/lib`
files. The corrected release removes those generated copies. The test suite now
checks the installed parser and semantic child tap together, so a stale wheel
fails validation rather than reaching the phone test.

The optional X accessibility adapter needs the corrected pinned ADB bridge and
`CONTENTSWARM_DELIVERY_ENABLED=1`, plus an owner-selected adapter on the account.
It makes no delivery-model calls; drafting still uses the configured brain.
Validate the exact English X layout on each assigned phone. See
[the social guide](../dashboard/SOCIAL.md#x-accessibility-adapter) before enabling.

The development screenshot reader uses `CONTENTSWARM_BRAIN_BIN` and
`CONTENTSWARM_BRAIN_MODEL`, with `CONTENTSWARM_VISION_BUDGET` defaulting to 0.15
USD per invocation. It sends a PNG to the authenticated model CLI without tools
or expected post text. The experimental X delivery fallback invokes it once only when a matching
post-detail screen and fresh UI timestamp are present. Keep automatic delivery
disabled until actual publication is validated on your app version. The phone
clock endpoint accounts for its UTC offset; the laptop timezone is not used.
