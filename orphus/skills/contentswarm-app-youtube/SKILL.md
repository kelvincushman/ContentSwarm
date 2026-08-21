---
name: contentswarm-app-youtube
description: Operate the YouTube app on ContentSwarm phones - browse Shorts, search, engage, and upload Shorts. Use only when a task involves YouTube on a fleet phone.
---

# YouTube on a ContentSwarm phone

Requires the `contentswarm-phones` skill basics. Substitute your phone name.

## Launch and verify

```bash
contentswarm launch phone_01 YouTube
sleep 5
contentswarm screenshot phone_01 -o /tmp/yt.png   # home feed? account picker?
```

## Browse Shorts

```bash
contentswarm run phone_01 "In YouTube, open the Shorts tab and swipe through 10 shorts, pausing 3 seconds on each" --wait
```

## Search

```bash
contentswarm run phone_01 "In YouTube, search for 'bow drill fire' and list the titles of the top 5 results" --wait
contentswarm run phone_01 "In YouTube, open the first search result and watch for 10 seconds" --wait
```

## Engage

```bash
contentswarm run phone_01 "In YouTube, like the current video" --wait
contentswarm run phone_01 "In YouTube, subscribe to the current channel" --wait
contentswarm run phone_01 "In YouTube, comment 'Really useful, thanks' on the current video" --wait
```

## Upload a Short

Video must already be in the phone's gallery.

```bash
contentswarm run phone_01 "In YouTube, tap the plus button, choose 'Create a Short', tap the gallery icon, select the newest video, tap Next, add the title 'TITLE #Shorts', set visibility to Public, then tap Upload" --wait
contentswarm screenshot phone_01 -o /tmp/yt-post.png
```

Uploads process in the background - the confirmation screenshot may show
"Uploading"; check again after a minute for the published state.

## Pitfalls

- Ads before videos delay "watch" tasks; allow generous wait clauses.
- The plus button sometimes offers "Upload a video" vs "Create a Short" - the
  gallery route above works for both, but Shorts must be vertical and <60s.
- Multi-account phones show an account picker on launch; the task should say
  which account to use, or report what the picker shows.
