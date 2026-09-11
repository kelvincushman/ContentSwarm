# Social accounts, memory and schedules

Open **Accounts & schedules** in the owner console. Create one profile for each
X, LinkedIn or Facebook identity. Set its voice, audience and boundaries in
the soul field, then assign one or more enrolled phones. A device assignment
is not proof of login: delivery must verify the active account on the screen.
Changing a handle or platform requires a separate profile, preserving the
meaning of existing approvals.

Add source-backed knowledge with a URL, Obsidian note reference or other source.
Owner additions are trusted knowledge; API captures are untrusted observations.
Account context includes only that profile's memory and linked review records.
Thread matches and query words rank memory, with bounded context sizes. Recent
verified posts and owner edits supply conversational history and voice examples.
Pending, rejected and uncertain text is never described as published.

This is SQLite-backed literal retrieval, not the HMLR dialogue engine. It does
not silently ingest the personal Obsidian vault or share knowledge across
accounts. Add an intended fact separately to each account that should use it.
The brain cannot guarantee complete understanding or retrieve missing context.

## Drafting and recurrence

The brief can run now, once at a date/time, every N minutes (60 = hourly), or
daily, weekly or monthly. Calendar repeats carry an IANA timezone. One-date
inputs use the browser's timezone. Spring DST gaps are skipped, autumn folds
run once at the earlier instant, and monthly dates absent in a month are skipped.
Edit/resume resets the next occurrence and cancels unstarted work from that
schedule. Pause prevents new occurrences and cancels queued work; a model call
already running may still finish. Missed occurrences are coalesced to one job,
and a schedule with queued/running work cannot accumulate more jobs.

The worker reads the account context and full vendored Humanizer 3.0.0 skill.
It invokes the installed Claude CLI with no tools or connectors and puts the
result in the review queue. The version field records that workflow; it is not
an independent guarantee of writing quality. Every fresh draft needs owner
approval. A stopped worker leaves a running job visible for inspection; it does
not automatically repeat a potentially completed model request.

## Publication and multiple phones

Set a publish time on the draft **before** approving it. Without one, approval
makes it eligible immediately. Changing time preserves approval; changing text
clears the time and requires approval again. Cancel is available until claimed.

Automatic **original-post** delivery is optional and off by default. X can use
the dedicated accessibility adapter described below. For the generic driver,
the owner calibrates a composer account indicator in the console:
the full resource ID and exact account label of a trusted app control, never
post text or a mention. Test that control on each assigned phone. If an app
does not expose a reliable indicator, use agent-assisted delivery instead.
The worker checks this indicator on each observation and immediately before
sending; earlier sightings do not grant authority. Automatic replies remain
unsupported until platform-specific source adapters are verified; they stay
in the existing review-and-deliver workflow. When enabled, the worker
claims eligible approved text once, checks the phone's signed-in account and
source, enters the exact approved text, sends once, and inspects the result.

If the navigation button opening the composer is itself labelled Post, calibrate
its separate resource ID as `compose_id`. This permits that navigation before
typing; never configure the final commit button as the composer entry.
Also calibrate `posted_id`, the full resource ID of actual published content,
not a toolbar label or editor. Automatic posting is disabled without it.
Account, composer-entry and published-content IDs must be distinct after trimming.
Before sending, the editable composer's entire text must equal the approved
body. Completion requires that exact body in one calibrated non-editor content
element on a later screen. A short body matching a button label is insufficient.
The model interprets accessibility trees; kernel primitives perform each action. This
is a harness-guided path, not a fully learned deterministic posting flow.
No general-purpose API can independently prove account identity or platform
delivery: evidence is reported by the worker and should be audited on-device.

The delivery model has no tools, shell, API token or lease token. It proposes
one semantic action from the UI tree; the kernel constrains the phone, inserts
only approved text, permits one final send and checks for visible posted text
outside an editor before accepting a finish proposal. This conservative loop
stops when the accessibility tree cannot prove identity or source; it does not
fall back to arbitrary pixel taps. Verify support on each target app first.

The claimed review reserves its phone across API calls. Other direct and
background actions are rejected while it is executing. Its calls carry
`X-ContentSwarm-Review: <id>` plus `X-ContentSwarm-Lease: <secret>`; the CLI reads
`CONTENTSWARM_REVIEW_ID` and `CONTENTSWARM_LEASE_TOKEN`. Claim returns the lease
once; only its hash is stored. Listing reviews never reveals leases.
That session cannot operate another phone. Two separate phones may deliver in
parallel, capped at two workers to limit laptop memory use. The draft currently
pins the first connected assigned phone; it does not switch devices after approval.
Offline phones wait. Uncertain deliveries never retry automatically. A process
crash leaves an executing reservation until the lease holder reports an outcome
or the owner inspects the phone and uses **Stop delivery and mark uncertain**.
Recovery revokes the lease, prevents further calls and does not retry the post.

## Omarchy timer

Use the installed server environment and run:

```bash
CONTENTSWARM_PYTHON=/path/to/ContentSwarm/.venv/bin/python bash deploy/install_social_timer.sh
```

This installs a persistent **systemd user timer**, the same native scheduling
mechanism Omarchy reminders use. It wakes once per minute; no model is invoked
when no work is due. `Persistent=true` catches up after login without a burst.
The worker defaults to Omarchy's local API on port 5055 and gets the **agent**
token from GNOME keyring (`service=contentswarm account=api-token`). It never
reads the owner console credential. Claude must already be authenticated.

Optional overrides live in `~/.config/contentswarm/social.env` (systemd
EnvironmentFile syntax). Keep credentials in the keyring:

```ini
CONTENTSWARM_API_URL=http://127.0.0.1:5055/api/v1
CONTENTSWARM_BRAIN_MODEL=your-installed-model
CONTENTSWARM_DRAFT_BUDGET=0.15
CONTENTSWARM_DELIVERY_ENABLED=0
CONTENTSWARM_DELIVERY_BUDGET=0.30
```

The draft cap applies per draft; the delivery cap is shared across up to twelve
screen interpretation calls for one delivery. There is no daily budget. Interval schedules create recurring
model usage. Enable delivery with `CONTENTSWARM_DELIVERY_ENABLED=1` only after
validating account identity and an approved test through the target app.
Check `systemctl --user status contentswarm-social.timer` and
`journalctl --user -u contentswarm-social.service`. Stop scheduling with
`systemctl --user disable --now contentswarm-social.timer`; an active service
continues until completion unless separately stopped.

## API and CLI

All routes below are under `/api/v1`, using existing authentication and CSRF.
Account/schedule edits, draft requests and approval decisions require an owner
console session. The agent token cannot create its own publishing authority.

| Route | Meaning |
|---|---|
| GET/POST `/social/accounts` | List / owner create or edit (id + revision) |
| GET/POST `/social/accounts/<id>/memory` | Scoped context / append sourced knowledge or observation |
| GET/POST `/api/v1/social/schedules` | List / owner create or edit with `account_id`, `prompt`, `spec` |
| POST `/social/schedules/<id>/pause` | Owner pause with revision |
| GET/POST `/social/jobs` | List / owner enqueue draft with account_id and prompt |
| POST `/social/tick` | Enqueue due occurrences, no model calls |
| POST `/social/claim` | Atomically claim one draft job |
| POST `/social/jobs/<id>/finish` | Report result or error for running draft job |
| POST `/reviews/<id>/schedule` | Owner set future `at` with UTC offset and revision |
| POST `/reviews/<id>/cancel` | Owner cancel unstarted draft with revision |

`spec` examples: `{"kind":"interval","minutes":60}`,
`{"kind":"weekly","weekday":0,"time":"09:00","timezone":"Europe/London"}`,
`{"kind":"once","at":"2027-01-12T09:00:00+00:00"}`. Monthly uses `day:1..31`.

```bash
contentswarm social accounts
contentswarm social context --account ACCOUNT_ID --query "pricing"
contentswarm social remember --account ACCOUNT_ID --file observation.json
contentswarm social schedules
contentswarm social jobs
contentswarm social tick
```

Memory input: `{"text":"Source words","source":"https://…","thread":"…"}`.
Post reviews use `kind:"post"` and `account_id`, plus the existing review
fields; `author` and `original` have post defaults. Replies should include
`account_id` so their source and outcome appear in that account's context.

The social store and review queue live under `CONTENTSWARM_STATE_DIR`, default
`~/.local/state/contentswarm`, with private SQLite files. Back them up together.

### Contextual reply drafts

In **Accounts & schedules**, select the account, choose **Reply to a
conversation**, and enter its link, author and original message. Add your brief
and choose Draft now or a schedule. Each job retains that source, retrieves
account-scoped knowledge with the conversation link as its thread key, and applies
the full Humanizer skill. Its result enters Post & reply review with the original
message alongside the proposed response. Approve or rewrite there; drafting never
sends a message. Repeated reply schedules prepare a fresh draft of the same target
for review on each occurrence; they do not collect new replies automatically.

The owner-only `POST /api/v1/social/jobs` and `/api/v1/social/schedules` accept
`kind: "reply"` with required `source_url`, `author`, and `original` fields.
Omitting `kind` retains original-post behavior. The source must be a non-root HTTPS
link on the selected account's platform. Schedule edits copy the new source only
into future jobs, cancelling queued work as before; running jobs retain their
original target. Automatic phone reply delivery still needs a source-verifying
platform adapter. A pending or approved draft is not proof that it was sent.

### Labels inside buttons

Some X and Facebook controls expose their name on a non-clickable child. The
phone kernel now accepts a unique semantic match when its XML ancestry proves
an enabled clickable control containing that label. It taps the label's center,
not a guessed screen position or another point inside the parent. Duplicate
matches, disabled ancestors and invalid/out-of-parent bounds are rejected.
This improves navigation but does not by itself verify an account, conversation,
approval or successful publication.

### X accessibility adapter

For an X profile with an exact `@handle`, choose **X accessibility controls** as
its delivery method and save the account check. This adapter handles original
text posts using deterministic API calls, without a model interpreting each
screen. It uses the existing review lease and global delivery opt-in.

The adapter requires the app's main navigation and opens its global composer,
checks the exact account switcher label, inserts only approved text, and checks
account and editor again before its single final Post tap. Existing composers
are left untouched. It will not switch accounts or navigate arbitrary pages.
A lost response or unexpected screen leaves the review uncertain through the
worker's existing recovery path.

Completion requires the exact body in one fresh post subtree with its author
handle before the body and reply/repost/like controls. Old timestamps, editors,
multiple matching posts and quoted or mixed-account subtrees cannot supply
that proof. Layout or language changes may prevent verification; inspect an
uncertain result instead of retrying. This adapter does not yet handle replies,
attachments, long posts, other languages or app screens lacking those controls.
Resource-ID calibration remains available for other original-post workflows.

Owner account configuration accepts `delivery_adapter: "x-accessibility-v1"`;
only X profiles with valid handles may use it. Omitting the field while editing
preserves the selection; sending an empty string disables the adapter.

Verification stays inside the nearest post subtree with reply/repost/like controls;
identity or timestamps in neighbouring screen regions cannot prove publication.
The adapter does not press Home: X may expose that label without a clickable
control when the navigation bar is clipped.

Live validation on the connected Samsung (11 September 2026) reached the X
composer, verified the exact signed-in handle and Unicode text, then intercepted
the final send and cleared the draft. Publication was not exercised. The observed
feed exposed display names without handles, so that feed alone cannot satisfy
the publication proof. A reliable detail-view verification path still needs
on-device validation before enabling automatic delivery on this app version.
LinkedIn exposes its personal identity in the navigation drawer but not in the
composer; a platform-specific identity path remains to be implemented there.
