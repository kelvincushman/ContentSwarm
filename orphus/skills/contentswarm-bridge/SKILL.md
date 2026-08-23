---
name: contentswarm-bridge
description: Semantic-first phone control - read a phone's UI element tree and address elements by text/id/desc instead of guessing pixels from screenshots. Use before falling back to vision tasks; it is faster, cheaper, and removes pixel-guess mis-taps.
---

# Semantic UI Bridge: address elements, not pixels

ContentSwarm phones expose their accessibility tree over plain ADB via
[adb-agent-bridge](https://github.com/kelvincushman/adb-agent-bridge). Every
element's text, resource-id, content-desc, bounds, and center are available
as JSON - so most decisions need no vision model and no screenshot.

Uses the same environment as `contentswarm-phones`
(`CONTENTSWARM_API_URL`, `CONTENTSWARM_API_TOKEN`).

## Read the screen semantically

```bash
contentswarm ui phone_01
```

Returns `{"elements": [{"text", "id", "desc", "class", "bounds", "center",
"clickable", "scrollable"}, ...]}`. Grep it instead of reading a screenshot:

```bash
contentswarm ui phone_01 | jq '.elements[] | select(.clickable)'
contentswarm ui phone_01 | jq '.elements[] | select((.text // "") | test("Post"))'
```

## Decision order (cheapest first)

1. **`ui`** - is the element/state you need in the tree? Usually yes.
2. **`screenshot`** - only when the tree is thin (games, canvas, some
   WebViews) or you need to see rendered content.
3. **`run` (vision task)** - only for genuinely open-ended navigation.

## How the bridge changes existing commands

- **Replays** tap the recorded element's current position (text/id/desc
  match), falling back to recorded coordinates - flows survive layout shifts.
- **Typing** commits in ~100ms with no keyboard on screen (media pickers are
  never hidden). The device keeps ADBKeyboard active during automation.
- **Run reports** (`contentswarm runs <flow>`) show, per replayed step,
  whether it hit the intended element (`"method": "element"` = verified) or
  fell back to coordinates (`"method": "coords"` = unverified - eyeball it).
- **Actions** (replay taps, typing) silently fall back to the original
  vision/ADB path on any phone where the bridge is unavailable - nothing
  breaks. **`ui` is the exception**: inspection has no vision fallback, so it
  returns an error when the bridge library or the device's UI tree is
  unavailable - treat that error as "switch to screenshot + vision".

## Guidance

- A `ui` dump takes 2-3s per call - fine for decisions, do not poll it in a
  tight loop.
- Empty tree or missing elements? The app is likely canvas-drawn - switch to
  `screenshot` + vision.
- `bridge.installed` in `contentswarm status` tells you whether the server
  has the bridge library at all.
