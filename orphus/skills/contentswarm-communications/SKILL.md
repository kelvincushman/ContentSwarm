---
name: contentswarm-communications
description: Inspect SMS or WhatsApp, prepare a recipient and message without sending, then perform one separately approved and verified send through ContentSwarm. Use for mobile messaging tasks.
---

# SMS and WhatsApp through the phone kernel

ContentSwarm uses Android intents and the visible accessibility tree. It does
not read private app databases or bypass end-to-end encryption.

Uses `CONTENTSWARM_API_URL` and `CONTENTSWARM_API_TOKEN`. Never print the token
or place message text directly in shell history when a file or stdin will do.

## Inspect

```bash
contentswarm messages primary sms
contentswarm messages primary whatsapp
```

This opens the chosen app or composer and returns visible UI elements. Use it
to understand current state. The response is not a complete mailbox export.

## Compose without sending

Write the final text to a mode-600 temporary file, then compose:

```bash
umask 077
cat >/tmp/message.txt <<'EOF'
I will arrive at 09:00.
EOF
contentswarm compose primary sms +447700900123 --body-file /tmp/message.txt
```

For WhatsApp, use `whatsapp` and an international number. `compose` returns
`"sent": false`; it cannot press Send.

## Approval and send

Show the user the channel, exact recipient, and exact body. Obtain a clear
approval. Then call once:

```bash
contentswarm send primary sms --expect-body-file /tmp/message.txt --confirm
```

The server verifies that the approved body is still in an enabled editor,
finds exactly one enabled Send control, taps once, and checks whether the
composer cleared. Only report success when `verified` is true. If the request
times out or returns an uncertain result, inspect the conversation before any
retry.

Delete the temporary file after the result is recorded:

```bash
rm -f /tmp/message.txt
```

## Rules

- Never infer approval from an earlier unrelated request.
- Never use a vision task to bypass the confirmed send route.
- Never ask a learned flow to press Send; end it at the prepared composer.
- Never claim that SMS delivery or WhatsApp receipt is proven by a cleared
  composer. That proves submission from the UI only.
- Login and multi-factor challenges require the user at the phone.

