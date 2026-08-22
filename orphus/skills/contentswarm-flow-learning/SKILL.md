---
name: contentswarm-flow-learning
description: Teach ContentSwarm phones once with the vision model, then replay the exact presses deterministically without any LLM. Use to discover apps on a device, learn a repeatable app workflow, or replay a learned flow.
---

# Flow Learning: learn once with the LLM, replay with exact presses

The vision model is the *teacher*: it drives a task once and every replayable
action is recorded with its exact press points (resolution-independent
0-1000 coordinates) plus the semantic identity (text/id/desc) of the element
under each tap. Replays target the recorded element wherever it now sits -
flows survive layout shifts and different screens - and fall back to the
recorded coordinates when the element is not found. No model calls,
near-zero cost.

Uses the same environment as `contentswarm-phones`
(`CONTENTSWARM_API_URL`, `CONTENTSWARM_API_TOKEN`).

## Discover apps on a device

```bash
contentswarm installed phone_01     # third-party apps actually on the phone
contentswarm apps                   # apps launchable by name in the registry
```

## Learn a flow (LLM drives, recorder captures)

```bash
contentswarm learn phone_01 "Open TikTok, tap the plus button, choose Upload, select the newest gallery video, tap Next, then stop at the caption screen" --name tiktok-open-upload --wait
```

The result reports `recorded_steps` (replayable presses) and `manual_steps`
(login walls/captchas the model hit - flows with manual steps will not replay
cleanly; re-learn after a human clears the blocker).

Learning tips:
- One flow = one job. Learn "open the upload screen" and "post with caption"
  as separate flows rather than one giant flow.
- Word the task so the model takes a stable path (name the exact tabs and
  buttons); avoid tasks that depend on feed content, which changes every day.
- Anything typed during learning is recorded literally - use placeholder text
  only if the replayed text should be identical every time.

## Inspect what was recorded

```bash
contentswarm flows                  # all learned flows with step counts
contentswarm flow tiktok-open-upload   # exact recorded actions and timings
```

## Replay (deterministic driver - the exact points, no LLM)

```bash
contentswarm replay phone_01 tiktok-open-upload --wait
contentswarm replay phone_02 tiktok-open-upload --wait --speed 1.5
```

Flows record relative coordinates, so a flow learned on one phone replays on
any phone. Taps first look for the recorded element (text/id/desc) at its
current position and only fall back to the recorded point.

## Verify: what it did vs what it was supposed to do

Every replay writes a run report - the step-by-step ledger of what actually
happened:

```bash
contentswarm runs tiktok-open-upload
```

Per step: `success`, and `method` - `"element"` means the recorded semantic
target was found on screen and tapped (verified); `"coords"` means the
coordinate fallback fired (unverified - the layout may have changed). The
summary's `verified` count against `executed` is the health signal: a flow
whose verified count drops after an app update needs re-learning before it
misclicks. For rendered content, a screenshot is still the ground truth:

```bash
contentswarm screenshot phone_01 -o /tmp/after-replay.png   # then read the PNG
```

## When to use which driver

| Situation | Use |
|---|---|
| First time driving an app or workflow | `learn` (vision model, records the flow) |
| Same workflow again, any phone | `replay` (exact presses, free, fast) |
| App updated its UI and replay misses | re-`learn` the flow, replay resumes working |
| One-off task that will never repeat | plain `run` (no recording overhead) |

## curl fallback

```bash
CS() { curl -s -H "Authorization: Bearer $CONTENTSWARM_API_TOKEN" "$@"; }
CS -X POST -H "Content-Type: application/json" -d '{"task":"...","flow_name":"my-flow"}' "$CONTENTSWARM_API_URL/phones/phone_01/learn"
CS -X POST -H "Content-Type: application/json" -d '{"flow_name":"my-flow"}' "$CONTENTSWARM_API_URL/phones/phone_01/replay"
CS "$CONTENTSWARM_API_URL/flows"
```
