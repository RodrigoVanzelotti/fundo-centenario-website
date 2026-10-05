# AGENTS.md

## Project

Fundo Centenário website and donation platform.

Main routes:

- `/` — institutional homepage
- `/como-apoiar/` — donation flow

Architecture:

- Static frontend
- FastAPI backend
- PSP adapters under `backend/app/providers/`
- Local persistence for confirmed donations in the current MVP

Read these files when relevant:

- `README.md` — architecture and local setup
- `INTEGRATION.md` — PSP integration
- `SECURITY.md` — payment, PII and deployment security

## Critical Git Rule

NEVER create a Git commit.

Do not run:

```bash
git commit
git commit --amend
git merge --commit
git tag
git push
```

Leave all changes uncommitted for human review.

You may inspect:

```bash
git status
git diff
git log
```

## Payment Rules

Never trust the frontend as proof of payment.

A donation is confirmed only through:

- a validated PSP webhook; or
- an authenticated server-to-server PSP status check.

Never mark a payment as successful because of:

- a browser redirect;
- query parameters;
- frontend state;
- the user clicking a confirmation button.

Credit-card data must never pass through this application.

Card payments must use a PSP-hosted checkout.

Never collect or store:

- card number;
- CVV;
- expiration date.

## Donor Data

The donation form collects:

- Name
- Email
- CPF
- Preferred program

Programs:

- `edital-projetos`
- `bolsas-permanencia`
- `mentoria`
- `masterclasses-alumni`
- `geral`

Do not persist Name, Email or CPF in the confirmed-donation storage before payment confirmation.

Do not log CPF or full donor payloads.

Do not place CPF or other PII in URLs, query parameters or analytics events.

## PSP Integrations

Keep provider-specific code inside:

```text
backend/app/providers/
```

Do not spread PSP-specific fields throughout routes, services or frontend code.

Never expose these values to the frontend:

- API keys
- OAuth secrets
- webhook secrets
- private keys
- certificates
- access tokens

Do not guess PSP API contracts. Use the provider's official documentation.

## Frontend

Keep HTML, CSS and JavaScript separated.

Use:

- DM Sans for primary typography
- IBM Plex Mono for labels, metadata and technical UI elements

Follow the Fundo Centenário visual identity.

Keep the interface clean and institutional. Avoid excessive gradients, decorative grids and visual noise.

For students, prioritize:

```text
Opportunities → Eligibility → Application → About the Fund
```

For donors and partners:

```text
Impact → How it works → Trust → Support
```

Keep `/como-apoiar/` as the canonical donation route.

## Backend

Use FastAPI.

Prefer:

- typed models;
- small route handlers;
- service boundaries;
- provider adapters;
- async HTTP integrations.

Payment webhooks must be:

- authenticated;
- idempotent;
- safe against duplicate delivery.

## Testing

For payment-related changes, verify at minimum:

- form validation;
- Pix creation;
- pending status;
- valid webhook;
- invalid webhook;
- duplicate webhook;
- payment confirmation;
- donor data persisted only after confirmation;
- Pix Automático flow;
- hosted card redirect.

Critical invariant:

```text
Before payment confirmation:
confirmed donor PII must not be persisted.

After payment confirmation:
the donation must be persisted exactly once.
```

## Before Finishing

1. Run relevant tests.
2. Inspect `git diff`.
3. Check for exposed secrets.
4. Check for accidentally persisted donor data.
5. Update documentation if behavior changed.
6. Leave all changes uncommitted.