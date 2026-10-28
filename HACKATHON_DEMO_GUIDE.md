# VoiceID Sentinel v1.6 — Proposed 3-minute judge video

**Production-truthful pitch:** “Weeglong AI VoiceID Sentinel converts fragmented *synthetic* voice-authentication metadata into traceable human investigation with separate Meta AI reasoning and explicit safety controls.”

**User persona:** Bank security operations analyst who needs to review contradictory verification, liveness and replay signals without treating them as automatic fraud or identity decisions.

| Video time | Show | Presenter line |
|---|---|---|
| 00:00–00:22 | Title, Weeglong AI and three cards | “Authentication systems make decisions. Investigators need to understand patterns without inventing blame.” |
| 00:22–00:48 | Scenario 1, replay flag, failed/then passed event, human queue | “Two failures and a pass are observable facts. There is no evidence these were the same actor.” |
| 00:48–01:12 | Scenario 2, one shared token. Click evidence refs | “Now an actual shared *opaque token* is supplied. The engine recognizes equality without claiming who held the device.” |
| 01:12–01:28 | Scenario 3, zero flags, all passed | “On low-signal events, Sentinel does not fabricate a threat.” |
| 01:28–02:04 | **Live Meta** case if credits and validation permit; otherwise explicitly labeled illustrative preview | “Meta adds structured hypotheses, uncertainties, and evidence-linked commentary. It never overrides the source or human.” |
| 02:04–02:30 | Run 14 checks; show denied claims and mismatch verifier | “Safety isn’t a slogan: these fixed tests demonstrate rejected invented evidence and altered reports.” |
| 02:30–02:50 | Export dossier/audit/report and integrity explanation | “Review copies and canonical SHA-256 digests make modifications detectable against the original audit; no digital signature is claimed.” |
| 02:50–03:00 | Conclusion and human oversight | “VoiceID Sentinel makes expert investigation more traceable. Next: regulated staging, external security and privacy validation.” |

## Live Meta strategy (use credits deliberately)

- An authentic live Meta test on the original three-event case **already worked in v1.4.2**. Do not waste credits repeating it solely for a new screenshot.
- A high-value *additional* test is **Scenario 2: Shared token**, because it checks whether the model distinguishes correlation of an opaque identifier from personal identity. If and only if your v1.6 offline checks succeed, start with `--enable-meta`, select Scenario 2 and authorize one call.
- Save the returned dossier and audit JSON if validation succeeds. If model output fails validation, the refusal itself demonstrates fail-closed behavior; report the failure accurately and refine the prompts offline before another paid test.
- **Never display** the API key, local token URL, browser profile identifiers or real data in the submitted recording. Crop out the Chrome address bar and Windows username.
- If filming an illustrative panel, keep its **NOT META** label clearly visible. Do not claim illustrative content was returned by Meta.

## Suggested submission description (adapt to actual organizer fields)

**Title:** VoiceID Sentinel — Evidence-Grounded AI Investigation for Voice Authentication

**Theme:** Build for Your World

**Problem:** Security analysts need to reconcile discrete authentication outcomes and detector signals. A replay flag alone does not prove fraud; time proximity alone does not establish a shared individual.

**Innovation:** A deterministic event-facts authority, explicit correlation limits, Meta Muse Spark's structured investigative hypotheses, clickable field-level evidence, human-only triage, offline adversarial checks, and auditable outputs. The workbench visibly differentiates observed facts from AI interpretation.

**Demo status:** Working local synthetic-data prototype with a previously successful real Meta API round-trip; no production customer integration or independently validated fraud-detection metrics are claimed.

**Repository note:** Publish source, sample fictional metadata, documentation and reproducible tests. Remove all local keys, session URLs and personal paths. Test the repository from a clean machine before submission.

## Submission deadline

Official event page lists **November 4, 2026, 9:00 PM Eastern Time**. With Eastern Standard Time in effect after November 1, that corresponds to **Thursday, November 5, 2026, 03:00 WAT**. Confirm the submission portal's exact time and any official rule updates before relying on this conversion.

The official hackathon page describes the startup track as evaluated for technical execution and whether it holds up in production. This local demo is therefore explicit about what has *not* been validated.
