---
name: contentswarm-app-tiktok
description: Operate the TikTok app on ContentSwarm phones - browse the For You feed, search, engage, and post videos. Use only when a task involves TikTok on a fleet phone.
---

# TikTok on a ContentSwarm phone

Requires the `contentswarm-phones` skill basics (CLI configured, phone names
known). All flows below run on one phone; substitute the phone name.

## Launch and verify

```bash
contentswarm launch phone_01 TikTok
sleep 5
contentswarm current phone_01          # expect the TikTok package in the foreground
contentswarm screenshot phone_01 -o /tmp/tt.png   # read it: For You feed? login wall?
```

If the screenshot shows a login screen, stop and report - accounts are managed
by a human.

## Browse / discover

```bash
contentswarm run phone_01 "In TikTok, swipe up through 10 For You videos, pausing 3 seconds on each" --wait
contentswarm run phone_01 "In TikTok, open the Discover/Search tab and note the top 5 trending hashtags" --wait
```

The task result message contains what the vision agent observed - use it as
your data.

## Search

```bash
contentswarm run phone_01 "In TikTok, search for 'bushcraft shelter' and open the top result" --wait
```

## Engage

```bash
contentswarm run phone_01 "In TikTok, like the current video" --wait
contentswarm run phone_01 "In TikTok, follow the creator of the current video" --wait
contentswarm run phone_01 "In TikTok, comment 'Great tip!' on the current video" --wait
```

Space engagement actions out (30s+ between them per phone) - burst liking is
a ban signal.

## Post a video

The video file must already be on the phone (in the gallery / camera roll).

```bash
contentswarm run phone_01 "In TikTok, tap the plus button, choose Upload, select the newest video in the gallery, tap Next, write the caption 'CAPTION TEXT #tag1 #tag2', then tap Post" --wait
contentswarm screenshot phone_01 -o /tmp/tt-post.png   # verify the post confirmation
```

## Read comments on the account's own posts (for reply review)

Read only: never like, follow, reply or type here. The approved reply is
sent by the `tiktok-accessibility-v1` worker after the owner approves it.

Path: **Inbox** tab, then **Activity** (comments, mentions and likes). A
comment notification shows the commenter's name and "commented: TEXT" (or
"replied to your comment: TEXT"). Tap it to open the video with its comments
panel. The account's own comments carry a "Creator" badge.

```bash
contentswarm launch phone_01 TikTok
contentswarm ui phone_01        # Inbox tab -> Activity; read rows; open one
```

For each comment worth answering, record for the review:

- `author`: the commenter's display name exactly as the comment row shows it (TikTok comments show the name, not the @username)
- `original`: the comment's **full exact text** as it appears in the post's
  comments (open the notification; the notification line itself is often
  shortened with "…")
- `source_url`: an https tiktok.com link to the post if you have one; otherwise
  `https://www.tiktok.com/@HANDLE/video/ID` plus a non-root path naming the post is accepted, but a real
  link is better for the owner
- `kind: "reply"`, `platform: "tiktok"`, and the account `handle` from
  `contentswarm social accounts`

The worker later goes the same way: the notification must name the author and
show the comment, the comment's row must show the author and one Reply, and
the composer must reply to that author. If two comments by the same person
have the same text, it stops; reply to those yourself.

## Pitfalls

- Ads and live streams interrupt feed swiping - the vision agent usually skips
  them, but a stuck task often means a full-screen ad with an odd close button.
- Captchas pause the task for human takeover - report, do not resubmit.
- Region-restricted content makes search results differ between phones.
