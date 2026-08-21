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

## Engage

```bash
contentswarm run phone_01 "In X, like the current post" --wait
contentswarm run phone_01 "In X, repost the current post" --wait
contentswarm run phone_01 "In X, reply 'Interesting take' to the current post" --wait
contentswarm run phone_01 "In X, follow the author of the current post" --wait
```

## Post

```bash
contentswarm run phone_01 "In X, tap the compose button and post: 'POST TEXT HERE'" --wait
contentswarm screenshot phone_01 -o /tmp/x-post.png
```

With media (file must be in the gallery):

```bash
contentswarm run phone_01 "In X, tap the compose button, tap the image icon, select the newest video from the gallery, add the text 'POST TEXT', then tap Post" --wait
```

## Pitfalls

- Unverified accounts hit strict daily post/engagement limits - keep well
  under them and stagger across phones.
- The timeline autoplays videos; a "scroll" task may report video audio
  content it cannot hear - screen text only.
- Rate-limit interstitials ("You're doing that too much") mean stop that
  phone for an hour; report it.
