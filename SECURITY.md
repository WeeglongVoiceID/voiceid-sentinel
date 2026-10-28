# Security posture — synthetic prototype only

## Supported usage

Run on a trusted computer, bound to `127.0.0.1` with an opaque per-session URL/token, using fictional metadata. Never expose the local server through a reverse proxy or internet-facing IP. Keep the Meta API key in the `MODEL_API_KEY` environment variable, only when intentionally enabling live requests. No real VoiceID or bank data is permitted.

## What is **not** provided

No enterprise authentication, tenant isolation, encryption/signature scheme for evidentiary custody, compliance attestation, production audit storage, model truth guarantee or automatic fraud determination. The SHA-256 pair checker is a *self-consistency check*; it does not prove provenance.

## Public repository checklist

- Search the working directory for `MODEL_API_KEY`, access tokens, keys, session URLs and sensitive data before publishing.
- Keep `.env`, `*.key`, `*.pem`, exported live case reports and raw provider responses out of Git. If a key has ever appeared in a commit, rotate it and rewrite history as appropriate.
- No screenshots of URL tokens, browser profile, real customer IDs or local Windows account path.
- Do not upload production VoiceID code or API credentials into this hackathon repository.
- If reporting a vulnerability, do not disclose actual customer details or credentials; use fabricated repro inputs.

## If considering production

Carry out separate architecture, legal/privacy and security reviews before any staging integration. See `PRODUCTION_READINESS_GATE.md`.
