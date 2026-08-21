---
name: contentswarm-app-APPNAME
description: Operate the APPNAME app on ContentSwarm phones - FLOWS_SUMMARY. Use only when a task involves APPNAME on a fleet phone.
---

# APPNAME on a ContentSwarm phone

Requires the `contentswarm-phones` skill basics. Substitute your phone name.

## Launch and verify

```bash
contentswarm launch phone_01 "APPNAME"
sleep 5
contentswarm screenshot phone_01 -o /tmp/app.png   # DESCRIBE_EXPECTED_HOME_SCREEN
```

<!-- If the app is not in `contentswarm apps`, replace the launch line with the
     vision-task fallback and note it here. -->

Stop and report on a login screen - accounts are managed by a human.

## Browse

```bash
contentswarm run phone_01 "VERIFIED_BROWSE_TASK_PHRASING" --wait
```

## Search

```bash
contentswarm run phone_01 "VERIFIED_SEARCH_TASK_PHRASING" --wait
```

## Engage

```bash
contentswarm run phone_01 "VERIFIED_LIKE_PHRASING" --wait
contentswarm run phone_01 "VERIFIED_FOLLOW_PHRASING" --wait
contentswarm run phone_01 "VERIFIED_COMMENT_PHRASING" --wait
```

<!-- Note any rate-limit behavior observed. -->

## Post

<!-- Only include if the posting flow was rehearsed to the confirmation screen. -->

```bash
contentswarm run phone_01 "VERIFIED_POST_PHRASING" --wait
contentswarm screenshot phone_01 -o /tmp/app-post.png
```

## Pitfalls

- <!-- Every phrasing that failed, pop-up that interfered, or screen that
       needed human takeover, with what to do about it. -->
