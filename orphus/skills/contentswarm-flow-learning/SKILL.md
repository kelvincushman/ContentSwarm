---
name: contentswarm-flow-learning
description: Teach ContentSwarm phones once with the vision model, then replay the exact presses deterministically without any LLM. Use to discover apps on a device, learn a repeatable app workflow, or replay a learned flow.
---

# Flow Learning: learn once with the LLM, replay with exact presses

The vision model is the *teacher*: it drives a task once and every replayable
action is recorded with its exact press points (resolution-independent
0-1000 coordinates) plus the semantic identity (text/id/desc) of the element
under each tap. Replays target the recorded element wherever it now sits -
flows can survive layout shifts. If a recorded semantic target is missing,
replay stops instead of falling back to old coordinates. No model calls,
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
current position. A missing semantic target stops replay; coordinate-only
legacy steps remain unverified.

## Verify: what it did vs what it was supposed to do

Every replay attempts to write a run report - the step-by-step ledger of what
actually happened (persistence is best-effort: a storage failure never fails
the replay, so a missing report means check the disk, not the phone):

```bash
contentswarm runs tiktok-open-upload
```

Per step: `success`, and `method` - `"element"` means the recorded semantic
target was found on screen and tapped (verified); `"coords"` means the
coordinate-only legacy step fired (unverified - the layout may have changed). The
summary's `verified` count against `executed` is the health signal: a flow
whose verified count drops after an app update needs re-learning before it
misclicks. For rendered content, a screenshot is still the ground truth:

```bash
contentswarm screenshot phone_01 -o /tmp/after-replay.png   # then read the PNG
```

## Health: trend across replays

Run reports are indexed into SQLite; `contentswarm health <flow>` rolls up
the verified-rate trend across all replays (default 30 days; use `--days N` to adjust).
If verified_rate drops after an app update, re-learn the flow.

```bash
contentswarm health tiktok-open-upload --days 7    # verified_rate trend for past week
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

Empty/failed learning is not saved as a completed flow. Empty replay fails, and
replay stops after its first failed step. Sensitive confirmation/takeover is
never auto-approved. Use `contentswarm cancel-task TASK_ID --confirm` to request
a cooperative stop. Input may already have happened; inspect before retrying.
The `verified` count measures input targeting only, not the final task outcome.

The recorder preserves sensitive-action confirmation markers; replay denies
those controls and stops, rather than treating an old approval as permanent.
Existing flows saved without such markers cannot be repaired by inference:
inspect/re-learn them before use. Semantic Double Tap/Long Press is not yet
implemented; those steps fail rather than using old coordinates. Coordinate-only
legacy gestures still require independent outcome checks.
