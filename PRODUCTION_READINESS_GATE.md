# VoiceID Sentinel — Production readiness gate (current status: NOT APPROVED)

**Product intent:** Banking-grade forensic intelligence, with human investigation and separation from the voice-verification decision engine.

## Gate checklist

| Area | Current demonstration | Required before real bank / fintech pilot |
|---|---|---|
| Functional proof | Local synthetic three-case workbench, offline and prior real Meta response | Formal acceptance test against representative *approved* staging metadata |
| Identity & access management | Single-user localhost session token | SSO/MFA, RBAC/ABAC, per-tenant isolation, least privilege, admin approval workflow |
| Security | Local bind, CSP, bounded JSON, fail-closed checks | Independent pentest, secure SDLC, SAST/DAST, dependency/SBOM scanning, threat modeling, secrets management |
| Privacy | Synthetic-only; no raw audio/template support in case JSON | Lawful basis, DPIA, Nigeria Data Protection Act review, data minimization, retention/deletion and vendor terms review |
| Evidence integrity | Canonical SHA-256 for input and dossier; pair consistency checker | Signed immutable chain of custody, trusted timestamps, access audit events, evidence origin attestations |
| Reliability | Automated tests for fixed cases; local HTTP prototype | Concurrency/load testing, SLA/SLO, alerts, backups, disaster recovery, rollback plan, chaos/recovery exercises |
| Meta AI | Real synthetic case succeeded in earlier version | Adversarial LLM evaluation, groundedness/error metrics, model drift controls, spending quota, prompt injection red-team |
| Triage correctness | Fixed deterministic replay/liveness rules | Human-calibrated severity/prioritization policy and false positive measurement; no autonomous adverse action |
| Integration | No production VoiceID connectivity | Segregated sandbox API, versioned contracts, network allowlists, secure credential exchange, observability |
| Compliance & legal | Explicit demo caveats | Applicable banking/security requirements reviewed by legal/compliance; customer and processor contracts |
| Personnel & governance | Human review labels | Investigation SOPs, four-eyes approvals, incident handling and accountabilities |

## Release rule

**GO for hackathon demonstration:** fixed synthetic data, localhost only, visibly labeled model provenance, and no autonomous actions.

**NO-GO for bank production:** until the production gate above has been reviewed and evidenced by the relevant organization and independent assessors. No claims of certification, customer deployment, measured fraud accuracy or third-party adoption.

## Next engineering priorities if pursuing production

1. Staging service + OAuth/SSO, role-based access and secure audit events.
2. Signed, append-only forensic evidence registry with key rotation and chain of custody.
3. Dedicated model evaluation harness with adjudicated, approved and privacy-reviewed cases, prompt injection tests and statistical metrics.
4. API contract hardening, provider timeouts/quotas, retry safety and circuit breaker; secrets manager and outbound allowlisting.
5. End-to-end integration tests with VoiceID sandbox only, followed by regulated pilot approval.
