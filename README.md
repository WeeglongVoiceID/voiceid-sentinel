# VoiceID Sentinel™ v1.6

**Evidence-grounded AI investigation workbench · Weeglong AI™**\
**Hackathon theme:** Build for Your World · Meta Global AI Developer Hackathon 2026

VoiceID Sentinel is a **local, synthetic-data-only investigation demonstrator** that helps human analysts examine sequences of voice-authentication events. Its deterministic engine preserves the source system's verification decisions and review priorities. Meta Muse Spark can optionally produce structured, evidence-referenced **advisory** analysis; it cannot change those source decisions or authorize adverse actions.

> **Scope:** This is a hackathon prototype with selected production-oriented controls, **not** a bank-deployed product, an independently certified forensic system, or a fraud/identity determination service. The public demo does not connect to production VoiceID.

## What was built during the hackathon

This distinction is essential to the event rules.

| Pre-existing Weeglong technology | New VoiceID Sentinel hackathon work |
|---|---|
| VoiceID™ voice biometric authentication and forensic platform (separate, existing product) | Local event-metadata investigation engine and multi-event case handling |
| Existing biometric verification and liveness/replay detection concepts | Evidence-referenced Meta Muse Spark investigative advisory and validation boundary |
| Existing VoiceID product branding and domain expertise | Deterministic investigation queue, synthetic scenario gallery, safeguard challenges, dossier/audit exports and investigation workbench |

**No pre-existing production VoiceID code, voice recordings, biometric templates, bank data, or customer records are needed to run this repository.** The demo uses deliberately fictional events. VoiceID makes biometric decisions in the separate underlying product; Sentinel does **not** perform biometric matching.

## Why it matters

Authentication logs can contain failed and passed checks, liveness signals, replay flags, and opaque device/session references. Investigators need a traceable way to review this evidence without confusing timing, a shared channel, or an identical token with proof of a common human actor. Sentinel makes evidence and uncertainty visible, while leaving consequential decisions to authorized people.

## Quick start (Windows)

**Prerequisite:** Python 3.11 or 3.13 and an up-to-date Chrome or Edge browser. The documented offline demo uses Python's standard library.

From a terminal in the **cloned repository root** (the directory containing `workbench_v1_6.py`):

```powershell
py -X utf8 .\workbench_v1_6.py
```

Alternatively, double-click `START_WORKBENCH.bat` from the project folder. Keep the terminal open. The local server normally uses port `8765` and should open your browser. If automatic opening fails, use the **complete local address printed by your own terminal**. **Never share a URL containing the session token.** Stop the server with `Ctrl+C`.

The application starts **offline**. Loading the dashboard, switching scenarios, running local checks, and exporting reports do **not** call Meta's API.

### Five-minute product walkthrough

1. **Scenario gallery:** Open each of the three fictional cases and compare their source events, review queues, and executive conclusions.
2. **Shared-token scenario:** Show that a repeated opaque token is a correlation signal, **not proof of shared person, identity, device ownership, session continuity, or fraud**.
3. **Meta analysis:** Click **Preview illustrative AI panel** to see a clearly marked **illustration only**. It is not a live model result.
4. **Guardrails:** Run **14 fixed local safeguard challenges**. These are targeted regression checks, not a comprehensive adversarial evaluation.
5. **Audit consistency:** Export the dossier and audit JSON, then verify the pair using **12 consistency checks**. Hash equality is **not** a cryptographic signature or proof of authorship.

## Optional live Meta Muse Spark demonstration

**Only use fictional, authorized synthetic input.** The local demo rejects selected prohibited fields, but a label such as `synthetic_demo_data` cannot independently prove that records are synthetic.

Configure `MODEL_API_KEY` locally in your own session; **never commit it, paste it into a message, or put it in a screenshot**. Then run:

```powershell
py -X utf8 .\workbench_v1_6.py --enable-meta
```

The dashboard indicates that Meta mode is available. A live model request occurs only after you explicitly click **Run LIVE Meta AI** and confirm. A request may consume credits.

**Demonstrated during development:** Two user-run live Meta responses were reported as structurally validated: the baseline three-event synthetic case and the four-event shared-token case. In the shared-token case, the model recognized the common opaque value while explicitly declining to infer a common human identity. These are individual demonstration results, **not a measured accuracy rate**. The full 270-test offline suite makes no live Meta calls.

**Model boundary:** Structural and evidence-reference validation does **not** fully fact-check all natural-language claims. Human review remains mandatory. The model does not change verification results or the deterministic investigation queue.

## Run the offline tests

On Windows, from the repository root:

```powershell
.\RUN_OFFLINE_TESTS.bat
```

Or run the suites individually with UTF-8 enabled (the Windows launcher also enables it):

```powershell
py -X utf8 .\test_v1_6.py
py -X utf8 .\test_v1_5.py
py -X utf8 .\test_workbench_v1_4.py
py -X utf8 .\test_navigation_v1_4_1.py
py -X utf8 .\test_typography_v1_4_2.py
py -X utf8 .\engine_v1_2\test_v1_2.py
py -X utf8 .\legacy_v1_3\test_dashboard_v1_3.py
```

**Observed on the prepared Windows release copy:** 270 passing checks across seven suites. The GitHub Actions workflow (`.github/workflows/offline-tests.yml`) is configured to repeat the tests on supported Python versions; its hosted execution must still be confirmed after publication. For a reproducible, offline-only evaluation of three known cases:

```powershell
py -X utf8 .\evaluation_v1_6.py
```

This generates `EVALUATION_RESULTS.json` and refreshes `EVALUATION_REPORT.md`. Evaluation of the fixed synthetic scenarios reported **14/14 safeguard checks** and **0 Meta calls**. This is not an evaluation of real-world biometric or fraud-detection accuracy.

## Architecture at a glance

```text
Fictional event metadata
        |
        v
Strict input validation + source-derived event facts
        |
        +--> Deterministic review priorities and shared-token signals
        |
        +--> Optional Meta Muse Spark advisory (validated, non-authoritative)
        |
        v
Human-review investigation workbench
        |
        +--> Evidence links and executive conclusion
        +--> Dossier / audit JSON and SHA-256 consistency checks
```

| Component | Purpose |
|---|---|
| `workbench_v1_6.py` | Local HTTP entry point and scenario / assurance / export-verification routes |
| `workbench_v1_4.py`, `workbench_v1_5.py` | Maintained investigation request handling and model integration |
| `engine_v1_2/` | Authoritative event facts, validation, deterministic queue, and audit hashing |
| `showcase_v1_6.py` | Three authored synthetic investigation scenarios |
| `assurance_v1_6.py` | Local safeguard cases and exported dossier/audit pair consistency checks |
| `report_v1_5.py` | Source-derived executive summary and privacy-first human review plan |
| `assets/`, `index.html` | Browser interface, evidence navigation, and exports |
| `evaluation_v1_6.py` | Reproducible fixed-fixture evaluation; no live API calls |
| `legacy_v1_3/` | Retained earlier offline dashboard and regression suite |

See `ARCHITECTURE_AND_THREAT_MODEL.md`, `SECURITY.md`, `PRODUCTION_READINESS_GATE.md`, `EVALUATION_REPORT.md`, and `HACKATHON_DEMO_GUIDE.md` for additional details.

## Important limitations and privacy rules

- **Synthetic data only.** Do not paste production logs, customer details, voice recordings, biometric templates, or real bank records into this local demonstration or send them to Meta.
- **No inferred common person.** Matching device or session tokens can indicate equal recorded values, not actual identity or intent.
- **No automatic adverse action.** There is no automatic account blocking, accusation, or determination of fraud.
- **Model output is advisory.** References are structurally checked but the model's interpretation is not exhaustively independently fact-checked.
- **No signed evidence custody.** SHA-256 of a dossier and audit pair checks self-consistency only; a malicious party able to rewrite both can recreate matching hashes.
- **Not public-server-ready.** The local single-user server is intended for loopback-only use, not internet-facing or multi-user enterprise operation.
- **Not production certified.** Enterprise use would require threat modeling, authentication and authorization, privacy assessment, independent security testing, operational controls, and rigorous model evaluation.

## Hackathon submission notes

The three-minute video and public repository must show what was **newly built during the event**, not claim pre-existing VoiceID capabilities were created in this hackathon. The demonstration should show the actual workbench, source evidence, Meta's advisory boundary, and safeguard behavior. Do not expose a local session URL, API keys, or customer data in the recording.

**Owner/brand:** Weeglong AI™ / Weeglong International Agency.\
**Project:** VoiceID Sentinel™ — a synthetic, human-reviewed AI investigation workbench.
