---
name: contentswarm-app-twitter
description: Operate the X (Twitter) app on ContentSwarm phones - browse the timeline, check trends, engage, and post. Use only when a task involves X/Twitter on a fleet phone.
---

# X (Twitter) on a ContentSwarm phone

Requires the `contentswarm-phones` skill basics. Substitute your phone name.
The app is listed as "X" in `contentswarm apps`.

## Launch and verify

```bash
contentswarm launch phone_01 X
sleep 5
contentswarm screenshot phone_01 -o /tmp/x.png   # For You timeline? login wall?
```

## Browse and trends

```bash
contentswarm run phone_01 "In X, scroll the For You timeline through 10 posts and summarize the topics" --wait
contentswarm run phone_01 "In X, open the search tab and list the top 10 trending topics shown" --wait
```

## Search

```bash
contentswarm run phone_01 "In X, search for 'bushcraft' and describe the top posts" --wait
```

## Preparing a post or reply

Read `contentswarm-social-review` for the exact reviewed sender protocol.
Ordinary `run` tasks are for navigation and observation, not a replacement for
a social delivery lease. Keep the approved copy unchanged and do not infer send
authority from an earlier approval. If the host Phone policy forbids Post, hand
the review ID/status to the authorised sender and leave that boundary intact.

```bash
contentswarm run phone_01 "In X, open the empty composer, then stop before entering text or tapping Post" --wait
contentswarm reviews
```

Do not open a competing composer while a review is executing. Inspect a fresh
screen after navigation. A composer, successful tap, or `completed` task does
not prove publication. Uncertain sends need owner inspection, not another tap.

## Pitfalls

- Unverified accounts hit strict daily post/engagement limits - keep well
  under them and stagger across phones.
- The timeline autoplays videos; a "scroll" task may report video audio
  content it cannot hear - screen text only.
- Rate-limit interstitials ("You're doing that too much") mean stop that
  phone for an hour; report it.
