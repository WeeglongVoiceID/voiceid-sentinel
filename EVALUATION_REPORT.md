# VoiceID Sentinel v1.6 — Reproducible Synthetic Evaluation

**Scope:** fixed synthetic demo scenarios only; no live Meta model calls, production data or external evaluation.

| Synthetic scenario | Events | Passed | Failed | Replay flags | Shared token signals | Review items | Export consistency |
|---|---:|---:|---:|---:|---:|---:|---|
| Two failures, then a pass | 3 | 1 | 2 | 1 | 0 | 3 | 12/12 |
| Explicit correlation, uncertain identity | 4 | 2 | 2 | 1 | 1 | 5 | 12/12 |
| Avoid false accusations | 3 | 3 | 0 | 0 | 0 | 3 | 12/12 |

**Fixed safeguard challenges:** 14/14 passed.

**Model API credits consumed:** 0.

**Not demonstrated:** statistical fraud-detection performance, adjudicated real incidents, correct model interpretations across varied populations, privacy compliance, multi-user authentication, enterprise uptime, production security posture, independent validation.

**Caveat:** Hash-pair verification checks self-consistency only. Model advisory references are structurally validated but not fully semantically fact-checked.

**Rule:** No automatic fraud/identity outcome or adverse action based on these synthetic observations.
