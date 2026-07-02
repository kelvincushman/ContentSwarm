# Web Console

A React/Vite single-page console for configuring the phone server, onboarding
apps visually, managing accounts, and generating the agent hookup kit. It's
served **directly by the server** — no separate process.

Open **`http://<server>:8770/`** in a browser, enter the base URL + API key in
the top bar, and click **Connect**.

## Tabs

**Devices** — every connected/known phone. Set a friendly **label**, pick the
**agent model** for that phone (from live-discovered model hosts), connect phones
over WiFi (`adb connect`) or flip a USB phone to wireless (`→WiFi`). The right
panel is a **live screen you can click to tap**.

**Onboard App** — the visual training flow:
1. Pick a phone, choose the app package (autocompleted from installed apps) and a slug.
2. **Start session**, **Open app**, **Capture**.
3. Toggle the screen between **Tap** (navigate) and **Label element** (click a
   control → name it → a robust selector is derived automatically).
4. Name screens, then **build a flow** step-by-step (open_app, tap_element,
   type, swipe, wait_for, assert_screen…).
5. **Save app profile** → written to disk, immediately usable by agents.

**Accounts** — attach social accounts to each phone (Facebook business/personal,
LinkedIn, X, …), each optionally bound to an onboarded app. Agents use these to
resolve "post to the LinkedIn business account".

**Settings** — default agent model, language, live-stream FPS, the advertised
public URL, and **model hosts** (add your LAN Ollama box or any OpenAI-compatible
endpoint; reachability + model counts are shown live).

**Agent Hookup** — generate the [hookup kit](AGENT_INTEGRATION.md) (system
prompt, tool schemas, MCP config, REST cheatsheet) from live state, with copy
buttons and an "hide API key" toggle.

## Building the console

The built app is committed under `phone_server/ui/dist/`, so a fresh checkout
serves the console with no build step. To modify it:

```bash
cd phone_server/ui
npm install
npm run dev      # hot-reload dev server (proxies API to :8770)
npm run build    # rebuild dist/ that the server serves
```

Requires Node 18+. The server mounts `phone_server/ui/dist` at `/` only if it
exists; API routes always take precedence over the static mount.
