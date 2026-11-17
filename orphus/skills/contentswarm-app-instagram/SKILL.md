---
name: contentswarm-app-instagram
description: Operate the Instagram app on ContentSwarm phones - browse Reels, search, engage, post Reels and stories. Use only when a task involves Instagram on a fleet phone.
---

# Instagram on a ContentSwarm phone

Requires the `contentswarm-phones` skill basics. Substitute your phone name.

## Launch and verify

```bash
contentswarm launch phone_01 Instagram
sleep 5
contentswarm screenshot phone_01 -o /tmp/ig.png   # read it: home feed? login wall?
```

Stop and report on a login screen - accounts are managed by a human.

## Browse Reels

```bash
contentswarm run phone_01 "In Instagram, open the Reels tab and swipe through 10 reels, pausing 3 seconds on each" --wait
```

## Search and explore

```bash
contentswarm run phone_01 "In Instagram, open the search tab, search for 'bushcraft', and describe the top 5 results" --wait
```

## Engage

```bash
contentswarm run phone_01 "In Instagram, like the current reel" --wait
contentswarm run phone_01 "In Instagram, follow the account that posted the current reel" --wait
contentswarm run phone_01 "In Instagram, comment 'Love this!' on the current reel" --wait
```

Instagram rate-limits aggressively - keep engagement under ~10 actions/hour
per phone and space actions 30s+ apart.

## Post a Reel

Video must already be in the phone's gallery.

```bash
contentswarm run phone_01 "In Instagram, tap the plus button, choose Reel, select the newest video from the gallery, tap Next twice, write the caption 'CAPTION #tag1 #tag2', then tap Share" --wait
contentswarm screenshot phone_01 -o /tmp/ig-post.png
```

## Post a story

```bash
contentswarm run phone_01 "In Instagram, tap the plus button, choose Story, select the newest image from the gallery, then tap 'Your story' to share" --wait
```

## Read comments on the account's own posts (for reply review)

Read only: never like, follow, reply or type here. The approved reply is
sent by the `instagram-accessibility-v1` worker after the owner approves it.

Path: **Home** tab, then the heart at the top (`id/notification`, no label),
which opens "Notifications". A "Finish setting up your account" sheet may
cover Home: Back closes it; never press Continue. A comment
notification reads "USERNAME commented: TEXT" (or "replied to your comment").
Tap it to open the post's comments; usernames are shown without "@", and
each comment prints as one line "USERNAME TEXT": the comment is the text after
the username.

```bash
contentswarm launch phone_01 Instagram
contentswarm ui phone_01        # Home -> Notifications; read rows; open one
```

For each comment worth answering, record for the review:

- `author`: the commenter's username exactly as the comment shows it (with or without the leading @)
- `original`: the comment's **full exact text** as it appears in the post's
  comments (open the notification; the notification line itself is often
  shortened with "…")
- `source_url`: an https instagram.com link to the post if you have one; otherwise
  `https://www.instagram.com/p/CODE/` plus a non-root path naming the post is accepted, but a real
  link is better for the owner
- `kind: "reply"`, `platform: "instagram"`, and the account `handle` from
  `contentswarm social accounts`

The worker later goes the same way: the notification must name the author and
show the comment, the comment's row must show the author and one Reply, and
the composer must reply to that author. If two comments by the same person
have the same text, it stops; reply to those yourself.

## Pitfalls

- "Suspicious activity" interstitials appear after bursts of actions - stop
  the phone for the day if one appears; report it.
- The plus-button menu order changes between app versions; the vision agent
  handles it, but verify posts with a screenshot.
- Suggested-account and notification pop-ups often cover the feed on first
  launch; a "dismiss any pop-ups" clause in the task helps.
