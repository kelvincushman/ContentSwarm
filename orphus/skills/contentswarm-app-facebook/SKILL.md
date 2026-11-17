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

## Read comments on the account's own posts (for reply review)

Read only: never like, follow, reply or type here. The approved reply is
sent by the `facebook-accessibility-v1` worker after the owner approves it.

Path: the **Notifications** tab (described "Notifications, tab 5 of 6",
plus ", N new"; scroll up if the tab bar is hidden). A "Get notified on time"
push-permission dialog may appear first: stop and leave it for the owner. A comment notification reads "NAME
commented on your post: "TEXT"" (or "replied to your comment"). Tap it to
open the post with that comment.

```bash
contentswarm launch phone_01 Facebook
contentswarm ui phone_01        # Notifications tab; read rows; open one
```

For each comment worth answering, record for the review:

- `author`: the commenter's name exactly as the comment shows it
- `original`: the comment's **full exact text** as it appears in the post's
  comments (open the notification; the notification line itself is often
  shortened with "…")
- `source_url`: an https facebook.com link to the post if you have one; otherwise
  `https://www.facebook.com/PROFILE/posts/ID` plus a non-root path naming the post is accepted, but a real
  link is better for the owner
- `kind: "reply"`, `platform: "facebook"`, and the account `handle` from
  `contentswarm social accounts`

The worker later goes the same way: the notification must name the author and
show the comment, the comment's row must show the author and one Reply, and
the composer must reply to that author. If another notification or comment
by the same person with the same text is on the same page or the next one
down, it stops; reply to those yourself. It does not open `source_url`.

## Pitfalls

- Facebook's UI is dense and changes often; expect vision tasks to take more
  steps here than on other apps - raise `--wait-timeout` for posting flows.
- Notification and friend-suggestion pop-ups frequently cover the feed; add
  "dismiss any pop-ups first" to tasks.
- Checkpoint/"confirm your identity" screens require human takeover - report
  and stop that phone.
