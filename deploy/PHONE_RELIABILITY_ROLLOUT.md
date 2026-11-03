# Phone reliability: review, rollout and rollback

This is a **candidate release**, not authority to change production. OB-16,
OB-19 and OB-29 fixes are combined on `fix/ob-19-phone-task-outcomes`. Host reports map the configured MCP target to the loopback 5055 service; its
working tree still matches the base, not this candidate. Never report a full live fix
from the offline suite, dispatch, a composer, or a successful input.

## First gate: identify what actually runs

Run the inspected collector as the normal service owner on aiserver. Do not use
sudo, print credentials, open ports, or restart services. The shared `/shared`
name in the bot is a bind mount; the host backing path was obtained from
`/proc/self/mountinfo`, not guessed:

First compare the host copy with this candidate's pinned collector SHA-256.
Do not run a mismatching copy: it may be the old source-exporting collector.
Stop and escalate a mismatch to the service owner. Do not run or deploy the
host copy until an approved collector is supplied. Matching a hash does not
itself authorise execution or deployment; the normal service owner still
approves execution.

```sh
COLLECTOR=/mnt/ai_storage/home_cache/local/share/containers/storage/volumes/orphusbot-team/_data/diagnostics/collect-phone-runtime.py
EXPECTED_COLLECTOR_SHA256=93b15e628792dbd78b535617c897e74da6ead75c0c1eed91d9be590477d3961e
if printf '%s  %s\n' "$EXPECTED_COLLECTOR_SHA256" "$COLLECTOR" | sha256sum --check -; then
    python3 "$COLLECTOR"
else
    printf '%s\n' 'STOP: collector hash differs. Do not run or deploy it; ask the service owner for an approved collector.'
fi
```

The same file is versioned at `scripts/collect_phone_runtime.py`. It exports
only relevant systemd properties, process executable/cwd and source hashes,
non-secret fields of explicitly referenced MCP registration JSON, and
allowlisted journal failure markers/task IDs. The extended collector projects
only exact named connection URL/host/port/state/enable fields from matched
service environments; token/password fields are not decoded or exported.
Credential/config files are not copied. Source review data is metadata-only:
file paths, hashes, reference line numbers and known connection-key names.
Origins are projected from allowlisted runtime connection settings and
explicitly referenced MCP registration URL fields, not from arbitrary strings
in application source.
It never exports application source text; regex redaction cannot cover arbitrary
credential syntax. Phone session summaries contain markers only, not messages.
Historical source-bearing diagnostic reports are not rewritten by this change;
keep them private and inspect before sharing. It makes no
network calls and never controls the phone or services. Output goes into the
shared team's `diagnostics/phone-runtime/` directory with private permissions.
A missing unit, denied journal or absent registration is a reported gap, not
inferred deployment identity. ContentSwarm and the MCP adapter may be separate
services. Do not treat static source references as runtime routing proof.

Coder must compare the host report to the release manifest and verify the
active Phone policy/sender handoff before selecting a deployment target. The
installer strips `.git`, so compare source hashes where a revision is absent.
If the report cannot locate the MCP registration, inspect the exact entry
files/units it identifies; do not search credentials or guess more endpoints.

## Local review and staging (no production changes)

1. Run `python -m pytest -q`, compile the touched modules, check import lint,
   validate JSON/YAML and skill frontmatter, and review the source manifest.
2. Obtain permission to push a review branch/PR. Follow `CLAUDE.md`: CodeRabbit
   findings must be addressed and GPT Sol must pass. A local helper review does
   not replace those gates. Do not push or merge without approval.
3. Stage the **reviewed commit**, not a dirty tree. In an isolated checkout:

   ```sh
   BASE=ed82e539b2930543254b9145e2d92477b485a815
   RELEASE=<reviewed-commit-from-the-ticket-report>
   git diff --name-only "$BASE" "$RELEASE" -- \
     phone_agent social_delivery.py social_worker.py contentswarm_cli.py \
     > source-files.txt
   git archive "$RELEASE" > reviewed-source.tar
   ```

   Extract to a fresh private stage directory, create its own venv and install
   `requirements.txt`, `dashboard/requirements.txt`, and test tools there.
   Test offline with mocks. The bridge must match the pinned requirement; do
   not silently update a shared live venv. Record staged package versions.
   This release does not change requirements or database schema.

## Explicitly approved rollout only

The following values must come from the host report; no default unit, install
path, service scope or interpreter is assumed:

- active ContentSwarm API service and system/user scope;
- active reviewed-social worker/timer, if any;
- actual application working directory, interpreter/venv and Phone definition
  location (if it uses the repo-shipped definition);
- current source fingerprints and applicable pending/executing review/task IDs.

**Stop here until Kelvin approves the specific services and files to change.**
The installation scripts are not an upgrade shortcut: `install_aiserver.sh`
uses `rsync --delete`, copies phone configuration and starts services. Do not
run it over a live installation for this patch.

After specific approval:

1. Suspend the identified social delivery scheduler/worker so a restart cannot
   trigger queued approved sends during checks. Preserve its prior enabled/
   running state for later owner-controlled restoration. Do not revoke leases
   or change review rows to force the deployment through.
2. Inspect pending/executing tasks and reviews. Stop new submissions and drain
   safe work; have the owner inspect uncertain commitments. Do not terminate
   an executing send and then retry it. Process-local task history disappears
   on API restart, so save its status/evidence first.
3. Record the actual service definition and source manifest; create a private
   backup of **every existing file in `source-files.txt`**, plus an inventory
   of manifest files that did not previously exist. Copy the actual agent
   definition separately only if its installation/update is approved. Keep
   secrets, SQLite state, phone registry, learned flows and media outside the
   release overlay. Do not export credential files to `/shared`.
4. Stop only the identified API unit, using its observed scope. For example,
   `systemctl --user stop "$UNIT"` is valid **only for a confirmed user unit**;
   use the system-service equivalent only if the report identifies that scope
   and the operator has the required authority. Do not guess a service name.
5. Overlay **only manifest source files** from the clean stage into the
   observed working directory. Preserve relative paths and permissions. Never
   copy `phones_config.json`, environment files, databases or flows, and never
   use directory-wide `rsync --delete`. If a new venv is required, retain the
   old venv and use a separately approved service override; record it for
   rollback. This patch itself does not require a dependency-version change.
6. Start that same API unit. Compare deployed hashes against the reviewed
   commit manifest and check its journal for startup errors. Keep automatic
   social delivery suspended during all verification.
7. Through the already-supported authenticated route, read task/status data
   and observe the phone with `look`/screenshot. Verify a benign task only if
   its initial screen is recorded and exact restoration is supported (for
   example a Settings screen, not any Send/Post/purchase control). Otherwise
   remain read-only and record that limitation. No sends are authorised here.
   An execution status is not proof: require fresh screen evidence of the
   requested outcome and restoration. A timeout is uncertainty, not permission
   to repeat input.
8. Have Kelvin decide whether and when to restore the social scheduler. This
   is a separate approval because existing approved jobs may then go live.

## Rollback after specific approval

Use the same observed units/scope and keep delivery suspended:

1. Stop the changed API unit only after accounting for in-flight work.
2. Restore backed-up manifest files and the prior interpreter/service override
   if one was changed. Remove **only the newly introduced source files listed
   in the saved pre-upgrade inventory**, never state, phone config, flows or
   media. Do not rewrite reviews or replay uncertain actions. In particular,
   this release adds `phone_agent/task_control.py`; it must not be mistaken
   for a database or generic directory to delete.
3. Start the prior API unit; compare source hashes with the saved pre-upgrade
   manifest and inspect startup logs. Perform only read-only checks.
4. Preserve new failure evidence and obtain the owner's decision before
   restoring any social-delivery timer. No schema rollback is required because
   this patch does not migrate persistent review/social tables.

## Known limits

Stops remain cooperative, not a hard kill of ADB calls/streams. Task state is
process-local. Generic tasks retain `outcome_verified: false`; input target
matching does not prove the final goal. Old learned flows stripped of approval
markers need inspection/re-learning. Missing typing bridge now stops without
falling back to unchecked legacy IME. Discovery events match pollable status;
event transport failures are logged but cannot reverse a successful operation
or leave it stuck running. API errors redact common/configured credentials;
they remain private diagnostic data, not material to publish unreviewed.

## Observed host mapping (read-only reports, not deployment approval)

Reports in `diagnostics/phone-runtime/20261102T234032007327Z.json` and
`20261102T235433644919Z.json` established:

| Component | Observed state |
| --- | --- |
| Orphusbot server | User unit `orphusbot-server.service`; `ORPHUSBOT_CONTENTSWARM_URL` origin `http://127.0.0.1:5055` |
| Intended API target | User unit `orphusbot-contentswarm.service`, listening on 5055, working directory `/home/aiserver/orphusbot-contentswarm` |
| API source working tree | `ed82e539b2930543254b9145e2d92477b485a815`; all changed source hashes match the base or are absent, not the candidate |
| Durable queue location | Configured `CONTENTSWARM_STATE_DIR=/home/aiserver/.local/state/orphusbot-contentswarm` — never overlay or delete it |
| Delivery scheduler | User timer `orphusbot-contentswarm-social.timer` active/waiting; oneshot `orphusbot-contentswarm-social.service` inactive/dead between runs, not itself evidence of failure |
| Other installation | User unit `contentswarm-api.service`, `/home/aiserver/contentswarm`, revision `36a21fd8ce291eb1adf303bbca7464422cc1c949`, listening on 8771 — do not deploy/restart this copy for the 5055 integration |

The extended source inspection exports `crates/server/src/phone.rs` and
`social.rs` from the native Orphusbot checkout. The Phone classifier identifies
Post/Send as Commit actions requiring the separate owner gate. Social's proxy
allows owner approval but deliberately excludes claim/complete; delivery belongs
to ContentSwarm's worker. Do not remove the Phone gate to make Social delivery
complete. The exact historical precondition/error is still lost behind the old
worker's generic evidence unless a suitable task record can be recovered.

These are configuration and on-disk source checks, not proof that every binary
was built from the accompanying checkout, nor a successful send. No production
service or scheduler has been stopped, restarted or updated by this work.

## OB-35 review corrections

Pre-tap dependency/UI errors remain ordinary errors. Missing/invalid selectors
and typed `AmbiguousSelector` failures occur before dispatch; no uncertainty is
invented from an error-message string. Only an exception during the one bridge
tap call becomes `TapOutcomeUncertain`, regardless of its exception class. It
never permits a coordinate fallback or a second tap.

The diagnostic collector no longer exports raw source under any redaction
pattern. The existing `adapter_source_review` report field contains metadata
only. Do not rerun an older source-exporting collector while preparing rollout;
stop and escalate a hash mismatch to the service owner; do not run or deploy
that host copy until an approved collector is supplied. This candidate must
complete CodeRabbit and the requested actual independent reviewer before the
specific deployment approval gate; merging earlier PRs does not waive it.
