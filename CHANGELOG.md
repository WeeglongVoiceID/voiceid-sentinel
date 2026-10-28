# Changelog — VoiceID Sentinel v1.6 (2026-10-28)

- Added 3 independent synthetic scenario cards: unlinked sequence, explicit shared opaque device token, and low-signal benign-looking events. All analyzed through the unchanged deterministic engine.
- Added 14 fixed, locally demonstrable safeguard challenges with a transparent limitation statement.
- Added audit pair verifier with 12 structural/hash consistency checks and explicit **not a signature** warning.
- Added case-aware illustrative preview restriction (only the original scenario has an illustrative panel).
- Added v1.6 localhost routes under token/origin/host restrictions: `/api/showcase`, `/api/showcase/{slug}`, `/api/assurance`, and POST `/api/verify`.
- Added 51 v1.6 offline regression tests. Inherited v1.5 test suite and v1.4.2 typography test had release-tag assertions updated from v1.5 to v1.6; all other inherited behavior remains.
- Kept v1.5 Meta client; no real paid Meta requests were made for this release. Prior live Meta success is user-reported for the earlier build.
- Added reproducible synthetic evaluation report, architecture/threat model, production-readiness gate, three-minute demo script and Windows launch shortcuts.
- The deployment boundary remains **local and synthetic only**; no VoiceID production endpoints or banking customer data.
