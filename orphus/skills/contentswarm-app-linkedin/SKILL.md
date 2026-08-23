---
name: contentswarm-app-linkedin
description: Operate the LinkedIn app on ContentSwarm phones - browse the feed, search, and compose posts, with the semantic element map for exact targeting. Use only when a task involves LinkedIn on a fleet phone.
---

# LinkedIn on a ContentSwarm phone

Requires the `contentswarm-phones` skill basics. Substitute your phone name.
Listed as "LinkedIn" in `contentswarm apps` (package `com.linkedin.android`).

**LinkedIn detects automation more aggressively than any other major
platform** (device fingerprinting, behavioral analysis, account
restriction). Keep volumes small and human-paced, stagger across phones, and
stop a phone immediately on any verification interstitial.

## Launch and verify

```bash
contentswarm launch phone_01 LinkedIn
sleep 5
contentswarm ui phone_01 | head -40   # logged in? feed elements? login wall = stop, needs a human
```

## Semantic element map (verified on device, app v2026.08)

LinkedIn's tree is well-labeled — prefer `contentswarm ui` + element targets
over vision tasks for these:

| Surface | Element | resource-id / desc |
|---|---|---|
| Top bar | Search | id `search_bar` (desc "Search for people, jobs, posts, and more") |
| Top bar | Compose | id `home_post` (desc "Post") |
| Top bar | Messaging | id `home_messaging` |
| Top bar | Profile menu | id `me_launcher_container` |
| Bottom tabs | Home / My Network / Notifications / Video / Jobs | ids `tab_feed`, `tab_relationships`, `tab_notifications`, `tab_video`, `tab_jobs` |
| Feed post | React / Comment / Repost / Send | desc-only: "Reaction button state: …", "Comment", "Repost", "Send" |
| Composer | Text field | id `share_compose_text_input_entities` (hint "Share your thoughts…") |
| Composer | Post button | id `share_compose_post_button` (text "Post") |
| Composer | Close | id `share_compose_close_button` |
| Composer | Visibility / Schedule / Photo | ids `share_compose_visibility_toggle`, `schedule_post_button`; desc "Photo" on the editor bar |

Tab descs carry live badge counts (e.g. "Notifications 3 of 5, 20 new
notifications available") — read state without opening the tab.

## Browse

```bash
contentswarm run phone_01 "In LinkedIn, scroll the home feed through 10 posts and summarize the topics" --wait
```

## Search

```bash
contentswarm run phone_01 "In LinkedIn, tap the search bar, search for 'agentic AI', and describe the top results" --wait
```

(The search input is the focused EditText after tapping `search_bar`; the
results screen is desc-labeled, not id-labeled.)

## Post

Direct semantic sequence (fast path — verified to the final screen):

```bash
contentswarm run phone_01 "In LinkedIn, tap the Post button in the top bar, type 'POST TEXT HERE' into the share field, then tap the Post button at the top right" --wait
contentswarm screenshot phone_01 -o /tmp/li-post.png   # confirm it published
```

With an image (file must be in the gallery): after opening the composer, tap
"Photo" on the editor bar, select from the gallery, then Post.

## Engage (buttons observed on device; phrasings not yet exercised)

```bash
contentswarm run phone_01 "In LinkedIn, tap the reaction button on the current post to like it" --wait
contentswarm run phone_01 "In LinkedIn, comment 'COMMENT TEXT' on the current post" --wait
```

Verify the first use of each with a screenshot and refine this section with
what actually worked.

## Pitfalls

- **Account risk is the #1 pitfall.** New/low-history accounts get restricted
  fast; a verification or "confirm it's you" interstitial means stop that
  phone and report — never retry through it.
- Closing the composer with text entered raises a "Save as draft?" dialog —
  choose Discard for rehearsals, or drafts pile up.
- The feed is Compose-rendered: feed items are desc-labeled, not id-labeled —
  target them by desc, or fall back to the marks/vision tier.
- The composer defaults to "Post settings: Anyone"; use
  `share_compose_visibility_toggle` if a task needs a different audience.
- Exploration for this skill opened the composer and mapped all surfaces
  without publishing; the Post and Engage phrasings above follow verified
  element paths but a first live post should be screenshot-confirmed.
