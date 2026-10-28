#!/usr/bin/env python3
"""VoiceID Sentinel Structured Investigation v1.1.

Local metadata-only prototype. Adds deterministic evidence-reference checks,
strict relationship-linkage safeguards, and cleaner UTF-8 Markdown output.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API_URL = "https://api.meta.ai/v1/responses"
DEFAULT_MODEL = "muse-spark-1.3"

SYSTEM_INSTRUCTIONS = r"""
You are VoiceID Sentinel, an investigative decision-support assistant. Analyze ONLY the fictional/anonymized event metadata supplied by the user.
Return one valid JSON object only, with no Markdown fences and no prose outside the JSON.
Never claim fraud, spoofing, identity, or intent unless supplied evidence directly establishes it. Verification, replay, and liveness signals are not proof of intent.
Timing, shared channel, similar outcomes, or sequence alone do not establish a shared actor, device, session, or identity.
Never override source-system verification decisions.
A relationship may be "confirmed_by_supplied_evidence" ONLY if an explicit shared identifier with non-empty values or direct linkage evidence appears in the input. Null, empty, missing, timestamp-only, or channel-only evidence is insufficient. Otherwise use "possible" when there is a concrete but inconclusive evidence basis, and "unknown" when no meaningful linkage evidence is supplied.
Evidence references must use the exact form EVENT_ID.field.path, where EVENT_ID is an event_id in the input and each field path segment exists in that event. Use only actual input fields. For general case-level facts, use a valid event field reference where possible; do not invent field paths.
Every hypothesis must have confidence "low", "moderate", or "high", and evidence_refs pointing to input fields.
Investigation queue review_priority is integer 1 (highest) to 5 (lowest). Recommendations must be human-review oriented; no automatic blocking, denial, or adverse action based only on this analysis.
Return exactly these top-level keys:
schema_version, case_id, case_summary, timeline, observed_patterns,
relationship_assessments, hypotheses, investigation_queue,
missing_evidence, recommended_next_steps, safeguards, limitations.
Schema:
schema_version string "1.1"; case_id string copied from input; case_summary non-empty string;
timeline array of {event_id, timestamp, summary};
observed_patterns array of {pattern, event_ids, evidence_refs};
relationship_assessments array of {event_ids, relationship_status, basis, evidence_refs, caveat};
hypotheses array of {hypothesis, confidence, supporting_evidence, contrary_or_missing_evidence, evidence_refs};
investigation_queue array of {review_priority, title, event_ids, rationale, evidence_to_collect, safe_action};
missing_evidence, recommended_next_steps, safeguards, limitations are arrays of strings.
"""

def extract_text(response: dict[str, Any]) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    pieces: list[str] = []
    output = response.get("output", [])
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if isinstance(block.get("text"), str):
                            pieces.append(block["text"])
                        elif isinstance(block.get("output_text"), str):
                            pieces.append(block["output_text"])
    return "\n".join(pieces).strip()

def nested_path_exists(obj: Any, path: list[str]) -> bool:
    cur = obj
    for segment in path:
        if isinstance(cur, dict) and segment in cur:
            cur = cur[segment]
        else:
            return False
    return True

def nonempty_value(obj: Any) -> bool:
    if obj is None:
        return False
    if isinstance(obj, str) and not obj.strip():
        return False
    if isinstance(obj, (list, dict)) and not obj:
        return False
    return True

def parse_evidence_ref(ref: Any, events_by_id: dict[str, dict[str, Any]]) -> tuple[bool, str]:
    if not isinstance(ref, str) or "." not in ref:
        return False, f"Evidence reference is not EVENT_ID.field.path: {ref!r}"
    event_id, *path = ref.split(".")
    if not path or event_id not in events_by_id:
        return False, f"Evidence reference uses unknown event or missing field path: {ref}"
    if not nested_path_exists(events_by_id[event_id], path):
        return False, f"Evidence reference points to a field absent from input: {ref}"
    return True, ""

def has_confirming_linkage(refs: list[Any], events_by_id: dict[str, dict[str, Any]], event_ids: list[Any]) -> bool:
    """Require a nonempty shared identifier field value across at least two named events."""
    ids = [x for x in event_ids if isinstance(x, str) and x in events_by_id]
    if len(ids) < 2:
        return False
    # Only explicit identifier fields can confirm linkage in this prototype.
    identifier_names = {"device_id", "session_id", "subject_ref", "account_id", "transaction_id", "correlation_id"}
    for ref in refs:
        if not isinstance(ref, str) or "." not in ref:
            continue
        event_id, *path = ref.split(".")
        if event_id not in ids or not path:
            continue
        leaf = path[-1]
        if leaf not in identifier_names:
            continue
        value = events_by_id[event_id]
        if not nested_path_exists(value, path):
            continue
        v = value
        for segment in path:
            v = v[segment]
        if nonempty_value(v):
            # Require same leaf identifier and equal nonempty values in another event.
            for other_id in ids:
                if other_id == event_id:
                    continue
                other = events_by_id[other_id]
                if nested_path_exists(other, path):
                    ov = other
                    for segment in path:
                        ov = ov[segment]
                    if nonempty_value(ov) and ov == v:
                        return True
                # Also support references with different event IDs but the same path.
    return False

def validate_result(data: Any, case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = [
        "schema_version", "case_id", "case_summary", "timeline", "observed_patterns",
        "relationship_assessments", "hypotheses", "investigation_queue",
        "missing_evidence", "recommended_next_steps", "safeguards", "limitations",
    ]
    if not isinstance(data, dict):
        return ["Top-level output must be a JSON object."]
    for key in required:
        if key not in data:
            errors.append(f"Missing required top-level key: {key}")
    if errors:
        return errors
    if data["schema_version"] != "1.1":
        errors.append('schema_version must be "1.1".')
    if data["case_id"] != case["case_id"]:
        errors.append("case_id does not match input case.")
    if not isinstance(data["case_summary"], str) or not data["case_summary"].strip():
        errors.append("case_summary must be a non-empty string.")

    list_keys = ["timeline", "observed_patterns", "relationship_assessments", "hypotheses",
                 "investigation_queue", "missing_evidence", "recommended_next_steps", "safeguards", "limitations"]
    for key in list_keys:
        if not isinstance(data[key], list):
            errors.append(f"{key} must be an array.")
    for key in ("missing_evidence", "recommended_next_steps", "safeguards", "limitations"):
        if isinstance(data.get(key), list) and not all(isinstance(x, str) for x in data[key]):
            errors.append(f"{key} must contain only strings.")

    input_events = case.get("events", [])
    if not isinstance(input_events, list):
        return errors + ["Input events must be an array."]
    events_by_id = {e.get("event_id"): e for e in input_events if isinstance(e, dict) and isinstance(e.get("event_id"), str)}
    valid_ids = set(events_by_id)

    def check_refs(container: Any, where: str) -> None:
        if not isinstance(container, list):
            return
        for idx, ref in enumerate(container):
            ok, message = parse_evidence_ref(ref, events_by_id)
            if not ok:
                errors.append(f"{where}[{idx}]: {message}")

    for i, item in enumerate(data.get("timeline", []) if isinstance(data.get("timeline"), list) else []):
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) for k in ("event_id", "timestamp", "summary")):
            errors.append(f"timeline[{i}] must include string event_id, timestamp, summary.")
        elif item["event_id"] not in valid_ids:
            errors.append(f"timeline[{i}] contains event_id absent from input.")
    for collection in ("observed_patterns", "relationship_assessments", "hypotheses", "investigation_queue"):
        rows = data.get(collection, [])
        if not isinstance(rows, list):
            continue
        for i, item in enumerate(rows):
            if not isinstance(item, dict):
                errors.append(f"{collection}[{i}] must be an object.")
                continue
            event_ids = item.get("event_ids", [])
            if event_ids is not None:
                if not isinstance(event_ids, list) or any(eid not in valid_ids for eid in event_ids):
                    errors.append(f"{collection}[{i}] contains event_ids absent from input.")
            check_refs(item.get("evidence_refs", []), f"{collection}[{i}].evidence_refs")
    for i, item in enumerate(data.get("relationship_assessments", []) if isinstance(data.get("relationship_assessments"), list) else []):
        if not isinstance(item, dict):
            continue
        status = item.get("relationship_status")
        if status not in {"confirmed_by_supplied_evidence", "possible", "unknown"}:
            errors.append(f"relationship_assessments[{i}] has invalid relationship_status.")
        ids = item.get("event_ids", [])
        refs = item.get("evidence_refs", [])
        if status == "confirmed_by_supplied_evidence" and not has_confirming_linkage(refs if isinstance(refs, list) else [], events_by_id, ids if isinstance(ids, list) else []):
            errors.append(f"relationship_assessments[{i}] claims confirmed linkage without matching non-empty shared identifier evidence.")
        if not isinstance(item.get("basis"), str) or not isinstance(item.get("caveat"), str):
            errors.append(f"relationship_assessments[{i}] basis and caveat must be strings.")
    for i, item in enumerate(data.get("hypotheses", []) if isinstance(data.get("hypotheses"), list) else []):
        if not isinstance(item, dict):
            continue
        if item.get("confidence") not in {"low", "moderate", "high"}:
            errors.append(f"hypotheses[{i}] has invalid confidence.")
        if not isinstance(item.get("evidence_refs"), list):
            errors.append(f"hypotheses[{i}].evidence_refs must be an array.")
        for k in ("supporting_evidence", "contrary_or_missing_evidence", "hypothesis"):
            if not isinstance(item.get(k), str):
                errors.append(f"hypotheses[{i}].{k} must be a string.")
    for i, item in enumerate(data.get("investigation_queue", []) if isinstance(data.get("investigation_queue"), list) else []):
        if not isinstance(item, dict):
            continue
        priority = item.get("review_priority")
        if not isinstance(priority, int) or isinstance(priority, bool) or priority not in range(1, 6):
            errors.append(f"investigation_queue[{i}] review_priority must be integer 1-5.")
        if not isinstance(item.get("evidence_to_collect"), list) or not all(isinstance(x, str) for x in item.get("evidence_to_collect", [])):
            errors.append(f"investigation_queue[{i}].evidence_to_collect must be an array of strings.")
    return errors

def api_request(api_key: str, model: str, case: dict[str, Any], max_output_tokens: int) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = {
        "model": model,
        "instructions": SYSTEM_INSTRUCTIONS,
        "input": "Analyze the case metadata and return the required JSON object. Use no external assumptions.\n\n" + json.dumps(case, ensure_ascii=False, indent=2),
        "max_output_tokens": max_output_tokens,
        "reasoning": {"effort": "low"},
    }
    req = urllib.request.Request(API_URL, data=json.dumps(payload).encode("utf-8"), headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"
    }, method="POST")
    with urllib.request.urlopen(req, timeout=90) as resp:
        raw = resp.read().decode("utf-8")
        status = resp.status
    response = json.loads(raw)
    return response, {"http_status": status, "api_status": response.get("status"), "model": response.get("model", model)}

def md_list(values: Any) -> list[str]:
    if not isinstance(values, list) or not values:
        return ["- None listed."]
    result = []
    for value in values:
        if isinstance(value, str):
            result.append(f"- {value}")
        else:
            result.append(f"- {json.dumps(value, ensure_ascii=False)}")
    return result

def render_markdown(data: dict[str, Any], meta: dict[str, Any]) -> str:
    lines = [
        f"# VoiceID Sentinel - Structured Investigation: {data['case_id']}", "",
        f"- **Version:** 1.1",
        f"- **Model:** {meta.get('model', 'unknown')}",
        f"- **API status:** {meta.get('api_status', 'unknown')}",
        f"- **Generated (UTC):** {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "- **Status:** Output passed local structural and evidence-reference checks; human review required.", "",
        "## Case summary", "", data["case_summary"], "", "## Timeline", ""
    ]
    for item in data["timeline"]:
        lines.append(f"- **{item['timestamp']} - {item['event_id']}:** {item['summary']}")
    lines += ["", "## Observed patterns", ""]
    for item in data["observed_patterns"]:
        lines += [f"### {item.get('pattern', 'Pattern')}", f"- **Events:** {', '.join(item.get('event_ids', []))}",
                  "- **Evidence references:**"]
        lines.extend(md_list(item.get("evidence_refs", [])))
        lines.append("")
    lines += ["## Relationship assessments", ""]
    for item in data["relationship_assessments"]:
        lines += [f"### Events: {', '.join(item.get('event_ids', []))}",
                  f"- **Status:** `{item.get('relationship_status', 'unknown')}`",
                  f"- **Basis:** {item.get('basis', '')}", "- **Evidence references:**"]
        lines.extend(md_list(item.get("evidence_refs", [])))
        lines += [f"- **Caveat:** {item.get('caveat', '')}", ""]
    lines += ["## Hypotheses", ""]
    for item in data["hypotheses"]:
        lines += [f"### {item.get('hypothesis', 'Hypothesis')}",
                  f"- **Confidence:** {item.get('confidence', 'unknown')}",
                  f"- **Supporting evidence:** {item.get('supporting_evidence', '')}",
                  f"- **Contrary or missing evidence:** {item.get('contrary_or_missing_evidence', '')}",
                  "- **Evidence references:**"]
        lines.extend(md_list(item.get("evidence_refs", [])))
        lines.append("")
    lines += ["## Prioritized investigation queue", ""]
    for item in sorted(data["investigation_queue"], key=lambda x: x["review_priority"]):
        lines += [f"### Priority {item['review_priority']}: {item.get('title', 'Review item')}",
                  f"- **Events:** {', '.join(item.get('event_ids', []))}",
                  f"- **Rationale:** {item.get('rationale', '')}",
                  "- **Evidence to collect:**"]
        lines.extend(md_list(item.get("evidence_to_collect", [])))
        lines += [f"- **Safe action:** {item.get('safe_action', '')}", ""]
    for heading, key in [("Missing evidence", "missing_evidence"), ("Recommended next steps", "recommended_next_steps"),
                         ("Safeguards", "safeguards"), ("Limitations", "limitations")]:
        lines += [f"## {heading}", ""]
        lines.extend(md_list(data[key]))
        lines.append("")
    lines += ["---", "", "**Important:** This AI-generated report is an investigative aid, not a finding of fraud or identity. Verify evidence independently. Do not take automatic adverse action based solely on this report.", ""]
    return "\n".join(lines)

def main() -> int:
    parser = argparse.ArgumentParser(description="VoiceID Sentinel v1.1 structured investigation (synthetic/anonymized metadata only).")
    parser.add_argument("input_json")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-output-tokens", type=int, default=3500)
    parser.add_argument("--save-json", default="result_SENTINEL-STRUCT-DEMO-001.json")
    parser.add_argument("--save-report", default="report_SENTINEL-STRUCT-DEMO-001.md")
    parser.add_argument("--save-raw", default="raw_response_SENTINEL-STRUCT-DEMO-001.json")
    args = parser.parse_args()
    try:
        case = json.loads(Path(args.input_json).read_text(encoding="utf-8-sig"))
    except Exception as exc:
        print(f"ERROR: Cannot read valid input JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(case, dict) or not isinstance(case.get("case_id"), str) or not isinstance(case.get("events"), list):
        print("ERROR: Input must contain string case_id and an events array.", file=sys.stderr)
        return 2
    api_key = os.environ.get("MODEL_API_KEY", "").strip()
    if not api_key:
        print("ERROR: MODEL_API_KEY is not set in this PowerShell session. Set it securely; never put it in this file or chat.", file=sys.stderr)
        return 2
    if not 500 <= args.max_output_tokens <= 12000:
        print("ERROR: --max-output-tokens must be between 500 and 12000.", file=sys.stderr)
        return 2
    print(f"VoiceID Sentinel v1.1 | {case['case_id']} | {len(case['events'])} events")
    try:
        response, meta = api_request(api_key, args.model, case, args.max_output_tokens)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"ERROR: API returned HTTP {exc.code}: {body[:1500]}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"ERROR: API request failed: {exc}", file=sys.stderr)
        return 3
    Path(args.save_raw).write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Raw API response saved: {args.save_raw}")
    print(f"Model: {meta.get('model')}")
    print(f"API status: {meta.get('api_status')}")
    if meta.get("api_status") != "completed":
        print("ERROR: API response not completed; no validated report written.", file=sys.stderr)
        return 4
    output = extract_text(response)
    try:
        structured = json.loads(output)
    except Exception as exc:
        print(f"ERROR: Model output is not valid JSON: {exc}", file=sys.stderr)
        print("No validated JSON/report written. Inspect the raw response locally.", file=sys.stderr)
        return 5
    errors = validate_result(structured, case)
    if errors:
        print("ERROR: Validation failed; no validated JSON/report written:", file=sys.stderr)
        for err in errors:
            print(f" - {err}", file=sys.stderr)
        return 6
    Path(args.save_json).write_text(json.dumps(structured, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(args.save_report).write_text(render_markdown(structured, meta), encoding="utf-8", newline="\n")
    print(f"Validated JSON saved: {args.save_json}")
    print(f"Markdown report saved: {args.save_report}")
    print("Validation: PASSED (schema + event references + relationship linkage safeguard)")
    print(f"Timeline events: {len(structured['timeline'])}")
    print(f"Relationship assessments: {len(structured['relationship_assessments'])}")
    print(f"Hypotheses: {len(structured['hypotheses'])}")
    print(f"Investigation queue items: {len(structured['investigation_queue'])}")
    print("Human review required; no automatic adverse action.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
