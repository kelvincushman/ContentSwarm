---
name: contentswarm-skill-maker
description: Generate a new contentswarm-app-<name> skill for an app that has no skill yet, by exploring the app on a real fleet phone and documenting its flows. Use when asked to operate an unfamiliar app, add support for a new app, or "make a skill" for an app.
---

# ContentSwarm App-Skill Generator

Creates a new on-demand skill (`contentswarm-app-<name>`) for any Android app
by exploring it on a real phone and writing down what actually works. Run
this once per new app; afterwards the generated skill is what loads when that
app comes up.

## Prerequisites

- `contentswarm-phones` basics: CLI configured, at least one connected phone.
- A phone you may freely explore on (check `contentswarm phones`; prefer one
  tagged `testing`).

## Procedure

### 1. Confirm the app exists and launches

```bash
contentswarm apps | grep -i "<app>"        # find the exact launchable name
contentswarm launch phone_01 "<AppName>"
sleep 5
contentswarm screenshot phone_01 -o /tmp/explore-01-home.png
```

Read the screenshot. If the app is not in `contentswarm apps`, it is not in
ContentSwarm's app registry — you can still open it with a vision task
("Open the app drawer, find and open <AppName>"), but note this in the
generated skill's Launch section.

If the first screen is a login wall, stop: report that the app needs a human
to sign in on that phone before a skill can be explored.

### 2. Map the primary surfaces

Explore each main area with short vision tasks, screenshotting after each.
Number the screenshots so you can cite what you saw.

```bash
contentswarm run phone_01 "In <AppName>, describe every tab or button in the bottom and top navigation" --wait
contentswarm run phone_01 "In <AppName>, open the main content feed and describe what one item looks like" --wait
contentswarm screenshot phone_01 -o /tmp/explore-02-feed.png
contentswarm run phone_01 "In <AppName>, find the search feature, search for 'test', and describe the results screen" --wait
contentswarm screenshot phone_01 -o /tmp/explore-03-search.png
```

### 3. Probe the flows the fleet cares about

For each flow relevant to this app (skip ones it does not have), run it once
end-to-end and record the exact task phrasing that worked:

- **Browse/scroll** the main feed
- **Search** and open a result
- **Engage**: like/favorite, comment/reply, follow/subscribe, share
- **Post/upload** content (only rehearse to the final confirmation screen,
  then back out — do not actually publish during exploration)
- **Profile/settings** areas worth knowing

A phrasing "works" when the task completes and the follow-up screenshot shows
the expected state. Keep failed phrasings too — they become Pitfalls.

### 4. Write the skill

Copy `references/APP_SKILL_TEMPLATE.md` and fill it with only the flows you
verified, using the exact task phrasings that worked. Name and location:

```bash
SKILL_DIR=~/.orphus/agent/skills/contentswarm-app-<name>   # loads user-wide
mkdir -p "$SKILL_DIR"
# write the filled template as $SKILL_DIR/SKILL.md
```

If you are working inside the ContentSwarm repo, also save a copy to
`orphus/skills/contentswarm-app-<name>/SKILL.md` so it ships with the repo
and reaches other machines via `orphus/install.sh`.

Frontmatter rules:
- `name: contentswarm-app-<name>` — lowercase, hyphenated
- `description` must say what app it operates and end with
  "Use only when a task involves <AppName> on a fleet phone." — this is what
  keeps the skill loading only when needed.

### 5. Validate

```bash
head -5 "$SKILL_DIR/SKILL.md"     # frontmatter has name + description?
```

Then dry-run one flow from the new skill verbatim on the phone. If it works,
report the skill created, its path, and which flows were verified vs. skipped.

## Rules

- Never publish real content or change account settings while exploring.
- Never explore on a phone another task is using (`contentswarm tasks` first).
- Document only what you verified on screen — no guessed flows.
- One skill per app; if `contentswarm-app-<name>` already exists, improve it
  in place instead of duplicating.
