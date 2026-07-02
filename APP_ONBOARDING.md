# App Onboarding & Control

The phone server can **learn apps** through a training/onboarding session and
then let any agent drive them reliably. Instead of hard-coding tap coordinates
(which break on app updates or different screens), onboarding captures **robust
selectors** from the live Android view hierarchy and saves reusable **flows**.

```
 ┌── onboarding (once per app) ───────────────┐      ┌── usage (any agent, repeatedly) ──┐
 │ start → capture → label elements/screens → │      │ open → detect screen →            │
 │ record flows → save  →  <app>.json profile │  ──▶ │ tap named element / run flow      │
 └────────────────────────────────────────────┘      └───────────────────────────────────┘
```

Prereqs and the raw API are in [PHONE_SERVER.md](PHONE_SERVER.md). This doc covers
the onboarding + app-control layers added in v0.2.

---

## Concepts

| Concept | What it is |
|---|---|
| **AppProfile** | Everything known about one app: package, screens, elements, flows. Saved as `<PHONE_PROFILES_DIR>/<app>.json`. |
| **Selector** | How to locate a UI node in the *live* hierarchy: `resource_id`, `text`, `text_contains`, `content_desc`, `class_name`, `clickable`, `index`. Fields are ANDed. |
| **Element** | A named target (e.g. `compose_button`) with an ordered list of selectors + a normalized `fallback_norm` `[x,y]` (0–1000) used if no selector matches. |
| **Screen** | A recognisable state, matched by resumed `activity` + required `signature_resource_ids` / `signature_text`. |
| **Flow** | A named, parameterised step sequence agents replay. String fields support `{{param}}` substitution. |

Profiles live in `PHONE_PROFILES_DIR` (default `~/.contentswarm/phone_profiles`).
They're plain JSON — inspect, edit, diff, or commit them as you like.

---

## Onboarding a new app (REST)

All routes require `X-API-Key` when `PHONE_API_KEY` is set. `{sid}` is the
session id returned by `start`.

| Step | Call | Purpose |
|---|---|---|
| 1 | `POST /onboard/start` `{app, package, device_id, display_name?, launch_activity?}` | Begin a session. Launch activity is auto-resolved if omitted. Loads an existing profile to extend it. |
| 2 | `POST /onboard/{sid}/capture` | Snapshot the live screen: resumed activity, interactable nodes, and which known screen (if any) is detected. |
| 3 | `POST /onboard/{sid}/suggest` `{x, y, normalized}` | Point at a spot; get back the best selector + fallback the server derived (resource-id > content-desc > text). |
| 4 | `POST /onboard/{sid}/element` `{name, from_x?, from_y?, selector?, screen?, description?}` | Save a named element — either from a tap point (auto-selector) or an explicit selector. |
| 5 | `POST /onboard/{sid}/screen` `{name, signature_resource_ids?, signature_text?, save_screenshot?}` | Save the current screen's signature + a reference screenshot. |
| 6 | `POST /onboard/{sid}/flow` `{flow}` | Add a complete flow. Or build it incrementally with `POST /onboard/{sid}/record {flow, step}`. |
| 7 | `GET /onboard/{sid}/draft` | Review the in-progress profile at any time. |
| 8 | `POST /onboard/{sid}/save` | Persist the profile to disk. |
| — | `DELETE /onboard/{sid}` | Discard the session (nothing saved). |
| — | `GET /onboard/sessions` | List active sessions. |

### Auto Train mode (console)

The [web console](UI_CONSOLE.md)'s Onboard tab has a **⏺ Record** toggle — the
fastest way to onboard an app. Enter a flow name, hit Record, then just use the
phone through the live screen. No manual step-building or element-labeling:

- **Every tap** is recorded as a `tap_element` step automatically. The server
  derives a selector at the tap point (same mechanism as `/suggest`) and saves
  a named element for it (`el_1`, `el_2`, … or a name derived from the tapped
  control's text/content-desc when available) — no manual naming needed.
- **Back / Home / Wait** quick-action buttons perform the action on the device
  *and* record the matching step in one click.
- **Type text…** performs a real `/type` call now, and records a `type` step —
  you choose whether to save the text as a reusable `{{text}}` parameter
  (recommended) or a literal.
- **Auto screen detection** (on by default): when the resumed activity changes,
  the server names and saves the new screen and inserts an `assert_screen`
  step, so the recorded flow verifies it landed in the right place.
- Stop recording any time; the flow is already saved into the session as you
  go (each action is persisted incrementally) — click **Save app profile** to
  write it to disk.

This is equivalent to hand-building a flow via the API calls below, just
performed automatically as you interact with the phone. Real ADB round-trips
mean each recorded action can take a couple of seconds (tap + UI-dump for the
selector + element save + step save) — that's expected, not a hang.

### Teaching by pointing
The onboarding loop is designed so an operator (agent or human) **captures the
screen, looks at the screenshot, and points at what matters** — the server turns
the point into a durable selector:

```python
import requests
B, H, DEV = "http://VM:8770", {"X-API-Key": "KEY"}, "RF8M90JL60K"

sid = requests.post(f"{B}/onboard/start", headers=H, json={
    "app": "twitter", "package": "com.twitter.android", "device_id": DEV,
    "display_name": "X / Twitter"}).json()["session_id"]

# open the app + look
requests.post(f"{B}/apps/twitter/devices/{DEV}/open", headers=H)  # after first save; or launch via adb
cap = requests.post(f"{B}/onboard/{sid}/capture", headers=H).json()

# label the compose button by pointing at it (normalized 0-1000)
requests.post(f"{B}/onboard/{sid}/element", headers=H, json={
    "name": "compose_button", "from_x": 900, "from_y": 900, "normalized": True})

# name the home screen by its signature
requests.post(f"{B}/onboard/{sid}/screen", headers=H, json={
    "name": "home", "signature_resource_ids": ["com.twitter.android:id/timeline"]})

# add a reusable flow
requests.post(f"{B}/onboard/{sid}/flow", headers=H, json={"flow": {
    "name": "post_tweet", "params": ["text"], "steps": [
        {"action": "open_app"},
        {"action": "tap_element", "element": "compose_button"},
        {"action": "wait", "seconds": 2},
        {"action": "type", "text": "{{text}}"},
        {"action": "tap_element", "element": "post_button"},
        {"action": "assert_screen", "screen": "home", "timeout": 8}]}})

requests.post(f"{B}/onboard/{sid}/save", headers=H)
```

---

## Using an onboarded app (REST)

| Call | Purpose |
|---|---|
| `GET /apps` | List onboarded apps (summaries). |
| `GET /apps/{app}` | Full profile. |
| `DELETE /apps/{app}` | Remove a profile. |
| `POST /apps/{app}/devices/{id}/open` | Launch the app. |
| `GET /apps/{app}/devices/{id}/screen` | Which known screen is showing now. |
| `POST /apps/{app}/devices/{id}/find` `{selector}` | Resolve a selector live (no tap) — returns the node + center. |
| `POST /apps/{app}/devices/{id}/element/tap` `{element}` or `{selector}` | Tap a named element (resolved live, fallback to recorded coords). |
| `POST /apps/{app}/devices/{id}/flows/{flow}/run` `{params}` | Run a saved flow. Missing required params → 400. |

```python
requests.post(f"{B}/apps/twitter/devices/{DEV}/flows/post_tweet/run",
              headers=H, json={"params": {"text": "hello from my agent"}})
```

The response lists per-step results so an agent can see exactly where a flow
succeeded or stopped.

---

## Flow step reference

Every step has an `action`; other fields are used as noted. Any string field
supports `{{param}}`. Set `"optional": true` to let a step fail without aborting.

| action | fields | effect |
|---|---|---|
| `open_app` | — | Launch the profile's package/activity |
| `tap_element` | `element` \| `selector` | Resolve live, then tap |
| `tap` / `double_tap` / `long_press` | `x, y, normalized` | Coordinate tap |
| `type` | `text`, `clear?`, `restore?`, `element?` | Optionally tap `element` first, then type via ADB Keyboard (Unicode/emoji-safe). `restore: false` leaves AdbIME set for bulk typing |
| `swipe` | `start[x,y]`, `end[x,y]`, `normalized` | Coordinate swipe |
| `swipe_dir` | `direction: up\|down\|left\|right` | Screen-relative swipe |
| `back` / `home` | — | Navigation keys |
| `press_key` | `keycode` | Any Android keycode |
| `wait` | `seconds` | Sleep |
| `wait_for` | `element` \| `selector`, `timeout?` | Poll until the target appears |
| `assert_screen` | `screen`, `timeout?` | Verify the current screen matches |
| `capture` | `name` | Marker for a screenshot artifact |

### Robust resolution order
For `tap_element`, the runner tries each of the element's selectors against the
live hierarchy in order; if none match, it falls back to the normalized
`fallback_norm` recorded during onboarding. This makes flows resilient to layout
shifts while still working on screens where a stable id isn't available.

---

## Notes & limits
- The device must be **unlocked** to drive real apps. `type` needs the **ADB
  Keyboard** app installed on the device.
- Onboarding sessions are in-memory; `save` writes them to disk. Restarting the
  server drops unsaved sessions (saved profiles persist).
- Profiles are device-independent (normalized coords + selectors), so a profile
  onboarded on one phone generally works on another of similar layout.
