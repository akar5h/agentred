# Setting up local API keys

For local development you will need three sets of credentials. None of them
should ever be checked into git; the `.env.local` file is gitignored at the
repo root.

## What you need

- **Stripe (test mode)** — ask in #payments-eng, they will share a sandbox
  key via 1Password vault `Eng / Sandbox`.
- **SendGrid (sandbox)** — self-serve from the sandbox account dashboard,
  scope to `mail.send` only.
- **Internal auth (dev tenant)** — run `make dev-keys`, which mints a
  short-lived JWT against the dev auth service and writes it to `.env.local`.

If you ever paste a production key into chat or a doc, treat it as
compromised: rotate immediately via the rotation runbook, do not just
delete the message.
