---
name: contentswarm-app-facebook
description: Operate the Facebook app on ContentSwarm phones - browse the feed and Watch/Reels, engage, and post. Use only when a task involves Facebook on a fleet phone.
---

# Facebook on a ContentSwarm phone

Requires the `contentswarm-phones` skill basics. Substitute your phone name.

## Launch and verify

```bash
contentswarm launch phone_01 Facebook
sleep 5
contentswarm screenshot phone_01 -o /tmp/fb.png   # news feed? login wall?
```

## Browse

```bash
contentswarm run phone_01 "In Facebook, scroll the news feed through 10 posts and summarize the topics" --wait
contentswarm run phone_01 "In Facebook, open the Watch or Reels tab and swipe through 5 videos" --wait
```

## Search

```bash
contentswarm run phone_01 "In Facebook, search for 'bushcraft groups' and list the top results" --wait
```

## Engage

```bash
contentswarm run phone_01 "In Facebook, like the current post" --wait
contentswarm run phone_01 "In Facebook, comment 'Great post' on the current post" --wait
contentswarm run phone_01 "In Facebook, share the current post to my timeline" --wait
```

## Post

```bash
contentswarm run phone_01 "In Facebook, tap 'What's on your mind', type 'POST TEXT HERE', then tap Post" --wait
contentswarm screenshot phone_01 -o /tmp/fb-post.png
```

With video (file must be in the gallery):

```bash
contentswarm run phone_01 "In Facebook, tap 'What's on your mind', tap Photo/Video, select the newest video from the gallery, add the caption 'CAPTION', then tap Post" --wait
```

## Pitfalls

- Facebook's UI is dense and changes often; expect vision tasks to take more
  steps here than on other apps - raise `--wait-timeout` for posting flows.
- Notification and friend-suggestion pop-ups frequently cover the feed; add
  "dismiss any pop-ups first" to tasks.
- Checkpoint/"confirm your identity" screens require human takeover - report
  and stop that phone.
