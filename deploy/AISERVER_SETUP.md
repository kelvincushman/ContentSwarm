# AI Server Setup

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

On the machine running Orphus (the server itself, or any machine that can
reach it — a Netbird peer address works the same as a LAN IP):

```bash
./orphus/install.sh                      # installs skills/agent/fleet into ~/.orphus/agent/
pip install -e /path/to/ContentSwarm     # provides the contentswarm CLI

export CONTENTSWARM_API_URL="http://<server-ip>:5000/api/v1"
export CONTENTSWARM_API_TOKEN="<token from /etc/contentswarm/env>"
contentswarm status                      # smoke test
```

Put the two exports in the shell profile of whatever user runs Orphus.
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
contentswarm key phone_01 BACK
contentswarm swipe phone_01 500 1600 500 500 --duration-ms 300
```

Verify message preparation without sending:

```bash
umask 077
printf '%s' 'ContentSwarm setup test — do not send' >/tmp/cs-message.txt
contentswarm compose phone_01 sms +447700900123 --body-file /tmp/cs-message.txt
contentswarm ui phone_01
contentswarm key phone_01 BACK
rm -f /tmp/cs-message.txt
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
