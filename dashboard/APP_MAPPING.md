# Social app mapping and verification

Mapping records observations, not a guarantee that a workflow can publish.
The connected Samsung was inspected on 11 September 2026 using the phone API.
Re-sense before each action and require one exact match. Never reuse a final
send/post action as a recorded navigation step.

| App | Observed controls | Still required for complete delivery |
| --- | --- | --- |
| X | Composer account switcher, exact body editor, Post, detail, native share preview | Approved fresh-post E2E; canonical source capture; reply adapter |
| LinkedIn | Profile launcher, profile name, composer entry/editor/close | Stable composer account identity; source collection; single-send and independent publication proof |
| Facebook | Menu and personal/page switcher | Composer identity, original/comment workflows, source and publication proof |
| Instagram | Profile, exact profile username, Create menu | Media binding/selection, caption and comment editors, source and publication proof |

## Instagram observations

Package: `com.instagram.android`. Resource IDs below share that prefix.

- `id/profile_tab`: Profile navigation.
- `id/action_bar_title`: username on the profile screen. Require the profile
  screen as well; the resource name alone is not identity proof in a composer.
- `id/profile_header_full_name_above_vanity`: display name, not unique identity.
- `id/profile_header_create_button`: opens Create, without uploading anything.
- Create menu descriptions: `Create new post`, `Create new reel`,
  `Create new story`. The generic `id/label` is repeated; never select it alone.

Live inspection reached Profile and Create, then backed out and returned Home.
No media was selected and nothing was posted. Existing accounts, schedules and
review data need no migration when adding an Instagram profile. Caption drafts
and comment reply drafts can be scheduled and reviewed; automatic Instagram
delivery is explicitly unavailable until media/comment adapters are verified.

Instagram publication must bind the owner's reviewed media and caption to the
same revision. An approved caption cannot authorize arbitrary camera-roll media.
