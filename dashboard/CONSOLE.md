# Mobile console

Open the server root, e.g. http://127.0.0.1:5055 on Omarchy, and sign in with its
CONTENTSWARM_API_TOKEN. This creates an eight-hour HttpOnly, SameSite session.
The token is not retained in browser storage. Server restarts invalidate sessions.
Use HTTPS remotely and keep the Omarchy service bound to localhost.
Startup requires a nonempty token; the old tokenless server mode is removed.
Cookies are Secure by default for HTTPS deployments. For local HTTP only, set
`CONTENTSWARM_HOST=127.0.0.1` and `CONTENTSWARM_COOKIE_SECURE=0`. Startup rejects
this cookie exception on a non-loopback bind address. CLI bearer requests do not
use cookies.
The service binds to loopback only. A local HTTPS proxy must overwrite
`X-Forwarded-Proto`; set `CONTENTSWARM_TRUST_PROXY=1` to trust that one proxy's
scheme header. Leave it unset for direct localhost use. Plain remote browser
requests are refused before the login form sends a token.

Tasks, phone preview, app launch, Home/Back, screen inspection and flow replay
use the existing API. Screenshots refresh on demand. Run and Learn require the
configured vision model. Review task scope or recorded steps before execution;
legacy vision tasks can mutate the device. Keep tasks within approved scope.

## Reply review

The external agent reads X, LinkedIn or Facebook, applies bundled Humanizer,
and queues drafts. Cards show the account, source author/message/link and reply.
Thumbs-up approves that revision. Thumbs-down rejects and opens an editor;
saving a rewrite returns it to pending review. Rewrite history supplies examples.

Approval does not publish. An external agent claims the approved record,
delivers the unchanged reply and reports evidence. Statuses distinguish pending,
rejected, approved, executing, verified and uncertain. No automatic collector or
delivery worker is bundled. SQLite transactions prevent stale approval and
duplicate claims. Executing/uncertain records cannot be automatically retried.

## API and CLI

- GET /api/v1/reviews lists records.
- POST /api/v1/reviews takes platform, account, phone, source_url, author,
  original, reply and humanizer_version strings.
- POST /api/v1/reviews/ID/ACTION takes revision and optional reply/evidence.
  Actions: approve, reject, edit, claim, complete, uncertain.
- `contentswarm reviews`
- `contentswarm review-add private-draft.json`
- `contentswarm review-action ID claim --revision N`
- `contentswarm review-action ID complete --revision N --evidence 'verified URL'`
- `contentswarm review-action ID uncertain --revision N --evidence 'observation'`

Private data lives in `$CONTENTSWARM_STATE_DIR/reviews.sqlite3`, defaulting to
`~/.local/state/contentswarm/reviews.sqlite3`, mode 0600. Queue mechanics use no
model. Humanizer version is the drafting agent's attestation of skill use.
Legacy dashboard routes and Socket.IO now require authentication too. Browser
mutations require CSRF tokens; agents retain bearer headers. Wildcard CORS is gone.
