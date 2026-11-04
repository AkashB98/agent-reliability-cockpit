#!/usr/bin/env python3
"""Agent Reliability Cockpit — Meta Model API audit (Meta Global Hackathon).

I run the demo-dataset-v1 audit through Meta's Muse Spark 1.1 and grade what
it finds against the ground truth in expected_findings.json, alongside my
deterministic local pipeline in cockpit_day1.py.

Why this version exists: my first run (2026-10-26) scored 0/4 because the
model spent all 2,500 completion tokens on reasoning and returned empty
content. On this API, reasoning and the answer share ONE output cap — there
is no separate thinking budget. The fix recipe:
  - max_completion_tokens set HIGH (12000). I only pay for tokens used.
  - reasoning_effort: "low" at the top level, so reasoning stays short.
  - A developer-role message carries the format rules (highest precedence).
  - response_format json_schema with an object root {"findings": [...]}.
    If the API rejects "strict": true with HTTP 400, drop it and retry once.
  - Streamed response, so a long generation cannot die on a client timeout.
  - Fallback: finish_reason=length with empty content -> one retry at
    double the cap (24000). Hard stop after that.

Design rules I hold this to:
  - ONE batched API call per run: all 4 input files in a single prompt.
  - muse-spark-1.1 only (1.3 has the same reasoning problem, worse; the
    contributor tier trains on prompts — no).
  - Every run is logged with its token usage (reasoning tokens included)
    and estimated cost, so the $150 hackathon credit is accounted for.
  - Task budget guard: stop before any call once this run's tracked spend
    reaches $0.10.

Run:  python3 meta_audit.py
"""
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import add_surrogate_to_request, read_json_response

HERE = Path(__file__).resolve().parent
DATASET = HERE / "demo-dataset-v1"
RUNS = HERE / "runs"
OUT_JSON = RUNS / "model-audit-2026-10-26b.json"
OUT_MD = RUNS / "run-2026-10-26-meta-audit-2.md"
BASE = "https://api.meta.ai/v1"
PROVIDER = "custom.meta-model-api"
HOSTS = ["api.meta.ai"]
MODEL = "muse-spark-1.1"
INPUTS = ["ga4_events.json", "gtm_container.json", "tool_trace.jsonl", "git_commit_diff.txt"]
RATE_IN_PER_M = 1.25   # USD per 1M input tokens
RATE_OUT_PER_M = 4.25  # USD per 1M output tokens
BUDGET_CAP_USD = 0.10  # hard stop for this run task
FIRST_CAP = 12000
RETRY_CAP = 24000

DEVELOPER_RULES = """Output rules — follow exactly:
- Respond with ONLY a JSON object matching the provided schema: {"findings": [...]}. No prose, no markdown fences, nothing outside the JSON.
- At most 10 findings.
- Each finding has exactly: file (the exact file name), line (integer line number where the fault appears), severity ("low", "medium", or "high"), issue (under 25 words), fix (under 25 words).
- Do not restate or quote the input code in your answer."""

AUDIT_ASK = """You are auditing a small analytics + AI-agent setup for reliability faults.
Below are 4 files (each shown with line numbers). Report every fault you find.
Hunt for: broken analytics events (missing required fields, values sent with the
wrong type), leaked secrets or API keys in code or config, AI tool calls that
cannot be replayed deterministically (missing inputs, wall-clock values baked
into outputs), and personal data (PII) exposed in tool outputs.
If a file is clean, report nothing for it."""

FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "issue": {"type": "string"},
                    "fix": {"type": "string"},
                },
                "required": ["file", "line", "severity", "issue", "fix"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def numbered(text):
    return "\n".join(f"{i + 1:>4}| {line}" for i, line in enumerate(text.splitlines()))


def build_user_prompt(data):
    parts = [AUDIT_ASK, ""]
    for name in INPUTS:
        parts.append(f"=== FILE: {name} ===")
        parts.append(numbered(data[name]))
        parts.append("")
    return "\n".join(parts)


def call_model(user_prompt, cap, strict):
    """One streamed chat call. Returns (http_status, content, usage,
    finish_reason, error_text). Never raises for HTTP errors."""
    json_schema = {"name": "audit_findings", "schema": FINDINGS_SCHEMA}
    if strict:
        json_schema["strict"] = True
    body = {
        "model": MODEL,
        "messages": [
            {"role": "developer", "content": DEVELOPER_RULES},
            {"role": "user", "content": user_prompt},
        ],
        "max_completion_tokens": cap,
        "reasoning_effort": "low",
        "response_format": {"type": "json_schema", "json_schema": json_schema},
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    req = urllib.request.Request(BASE + "/chat/completions",
                                 data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "text/event-stream")
    add_surrogate_to_request(req, PROVIDER, allowed_hosts=HOSTS)
    opener = urllib.request.build_opener(NoRedirect())
    try:
        resp_cm = opener.open(req, timeout=240)
    except urllib.error.HTTPError as e:
        try:
            err = read_json_response(e)
        except Exception:
            err = {"error": "unreadable error body"}
        return e.code, None, None, None, json.dumps(err)[:800]
    content_parts, usage, finish_reason = [], None, None
    with resp_cm as resp:
        status = resp.status
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if chunk.get("usage"):
                usage = chunk["usage"]
            for ch in chunk.get("choices") or []:
                delta = ch.get("delta") or {}
                if delta.get("content"):
                    content_parts.append(delta["content"])
                if ch.get("finish_reason"):
                    finish_reason = ch["finish_reason"]
    return status, "".join(content_parts) or None, usage, finish_reason, None


def usage_cost(usage):
    if not usage:
        return 0, 0, 0.0
    pt = usage.get("prompt_tokens", 0)
    ct = usage.get("completion_tokens", 0)
    return pt, ct, pt / 1e6 * RATE_IN_PER_M + ct / 1e6 * RATE_OUT_PER_M


def reasoning_tokens(usage):
    if not usage:
        return None
    details = usage.get("completion_tokens_details") or {}
    return details.get("reasoning_tokens")


def parse_findings(content):
    if not content:
        return None
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    parsed = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            try:
                parsed = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                parsed = None
    if isinstance(parsed, dict) and isinstance(parsed.get("findings"), list):
        return [f for f in parsed["findings"] if isinstance(f, dict)]
    if isinstance(parsed, list):
        return [f for f in parsed if isinstance(f, dict)]
    return None


# Keyword fingerprints per ground-truth fault, matched against the model's
# own words (issue + fix + file).
FINGERPRINTS = {
    "FAULT-1": {"files": {"ga4_events.json"},
                "words": ["transaction_id", "transaction", "purchase", "value",
                          "string", "number", "missing"]},
    "FAULT-2": {"files": {"git_commit_diff.txt", "gtm_container.json"},
                "words": ["secret", "api key", "api_key", "api-key", "hard-coded",
                          "hardcoded", "leaked", "credential", "gtm", "variable",
                          "plain-text", "plaintext", "plain text"]},
    "FAULT-3": {"files": {"tool_trace.jsonl"},
                "words": ["replay", "args", "snapshot", "now()", "wall-clock",
                          "wall clock", "deterministic", "call_003", "timestamp"]},
    "FAULT-4": {"files": {"tool_trace.jsonl"},
                "words": ["pii", "personal", "email", "phone", "call_004",
                          "customer data", "privacy", "redact"]},
}


def map_findings(model_findings, expected_ids):
    """Assign each model finding to at most one expected fault id."""
    mapping = {}
    used = set()
    for i, f in enumerate(model_findings):
        file = str(f.get("file") or "")
        blob = (str(f.get("issue", "")) + " " + str(f.get("fix", ""))).lower()
        best, best_score = None, 0
        for fid in expected_ids:
            if fid in used:
                continue
            fp = FINGERPRINTS[fid]
            score = sum(1 for w in fp["words"] if w in blob)
            if file in fp["files"]:
                score += 1
            if score > best_score:
                best, best_score = fid, score
        if best and best_score >= 2:
            mapping[i] = best
            used.add(best)
    return mapping


def main():
    print("== Cockpit — Meta Model API audit run 2 (reasoning-effort recipe) ==")
    data = {name: (DATASET / name).read_text(encoding="utf-8") for name in INPUTS}
    total_chars = sum(len(t) for t in data.values())
    print(f"loaded 4 input files ({total_chars} chars total)")
    prompt = build_user_prompt(data)
    print(f"batched prompt: {len(prompt)} chars -> {MODEL}, "
          f"max_completion_tokens={FIRST_CAP}, reasoning_effort=low")

    attempts = []
    findings = None
    content = usage = finish_reason = None
    spent = 0.0
    plan = [(FIRST_CAP, True)]  # (cap, strict); retries appended per policy
    idx = 0
    while idx < len(plan):
        cap, strict = plan[idx]
        idx += 1
        if spent >= BUDGET_CAP_USD:
            attempts.append({"cap": cap, "strict": strict,
                             "error": f"budget guard: tracked spend ${spent:.4f} "
                                      f"already at the ${BUDGET_CAP_USD} task cap — call not made"})
            print("budget guard hit — no further calls")
            break
        print(f"attempt {idx}: cap={cap} strict={strict} ...")
        try:
            status, content, usage, finish_reason, err = call_model(prompt, cap, strict)
        except Exception as e:  # transport-level failure, no response at all
            attempts.append({"cap": cap, "strict": strict,
                             "error": f"transport: {type(e).__name__}: {str(e)[:300]}"})
            print(f"  transport error: {e}")
            break
        pt, ct, cost = usage_cost(usage)
        spent += cost
        attempts.append({"cap": cap, "strict": strict, "http_status": status,
                         "usage": usage, "reasoning_tokens": reasoning_tokens(usage),
                         "finish_reason": finish_reason,
                         "content_returned": bool(content),
                         "estimated_cost_usd": round(cost, 6),
                         "error": err})
        if status != 200:
            print(f"  HTTP {status}: {err[:200]}")
            if status == 400 and strict:
                plan.append((cap, False))
                print("  -> dropping \"strict\" and retrying once (recipe policy)")
                continue
            break
        findings = parse_findings(content)
        print(f"  HTTP 200, finish_reason={finish_reason}, "
              f"reasoning_tokens={reasoning_tokens(usage)}, "
              f"completion={ct}, findings parsed: "
              f"{len(findings) if findings is not None else 'no'}")
        if findings is not None:
            break
        if finish_reason == "length" and not content and cap == FIRST_CAP:
            plan.append((RETRY_CAP, strict))
            print("  -> length cap hit with empty content: one retry at double cap")
            continue
        break

    stamp = datetime.now().astimezone()
    RUNS.mkdir(exist_ok=True)

    if findings is None:
        last = attempts[-1] if attempts else {}
        raw = {"run": "meta-audit-2", "timestamp": stamp.isoformat(timespec="seconds"),
               "model": MODEL, "status": "no_findings_returned",
               "recipe": {"max_completion_tokens_first": FIRST_CAP,
                          "reasoning_effort": "low",
                          "response_format": "json_schema object root {findings:[...]}"},
               "attempts": attempts,
               "estimated_cost_usd": round(spent, 6), "model_findings": [],
               "score": {"model_audit": "0/4", "local_pipeline": "4/4"}}
        OUT_JSON.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        err_lines = [f"- Attempt {i + 1} (cap {a.get('cap')}, strict {a.get('strict')}): "
                     f"HTTP {a.get('http_status')} — {a.get('error') or 'no parseable findings'}"
                     for i, a in enumerate(attempts)]
        lines = [
            "# Cockpit run log — Meta Model API audit, run 2",
            "",
            f"- When: {stamp.strftime('%a %b %d, %Y %H:%M %Z')}",
            f"- Model: {MODEL} — one batched call per attempt, all 4 demo files, streamed",
            "- Recipe: max_completion_tokens 12000, reasoning_effort \"low\", developer-role format rules, json_schema object root",
            f"- Estimated cost (all attempts): ${spent:.4f} — from the $150 hackathon credit",
            "",
            "## What happened",
            "",
            *err_lines,
            "",
            "## Score",
            "",
            "- Meta model audit: **0/4** this run (no findings returned)",
            "- Local deterministic pipeline (cockpit_day1.py): **4/4**",
            "",
            f"Raw run record: `{OUT_JSON.name}` (same folder).",
        ]
        OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("ERROR: no parseable findings. Records saved to "
              f"{OUT_JSON.name} and {OUT_MD.name}")
        return 2

    # Totals across attempts (the successful call is the last one, but any
    # earlier billed attempt counts toward the run's spend).
    total_pt = sum((a.get("usage") or {}).get("prompt_tokens", 0) for a in attempts)
    total_ct = sum((a.get("usage") or {}).get("completion_tokens", 0) for a in attempts)
    total_rt = sum(a.get("reasoning_tokens") or 0 for a in attempts)
    pt, ct, _ = usage_cost(usage)
    rt = reasoning_tokens(usage)

    expected = json.loads((DATASET / "expected_findings.json").read_text(encoding="utf-8"))
    expected_ids = [f["id"] for f in expected["findings"]]
    mapping = map_findings(findings, expected_ids)
    caught = sorted(set(mapping.values()))
    missed = [fid for fid in expected_ids if fid not in caught]
    score = len(caught)

    print(f"\nmodel findings: {len(findings)}")
    for i, f in enumerate(findings):
        tag = mapping.get(i, "unmatched")
        print(f"  [{tag}] {f.get('file')}:{f.get('line')}: {f.get('issue')} "
              f"(severity={f.get('severity')}) — fix: {f.get('fix')}")
    print(f"\nMeta model audit score: {score}/{len(expected_ids)}"
          + (f" — missed: {', '.join(missed)}" if missed else ""))
    print("Local deterministic pipeline score: 4/4 (cockpit_day1.py)")
    print(f"tokens (successful call): prompt={pt} completion={ct} reasoning={rt}")
    print(f"tokens (all attempts): prompt={total_pt} completion={total_ct} "
          f"reasoning={total_rt} | est. cost ${spent:.4f}")

    effort_verdict = (
        f"reasoning_effort=low: reasoning_tokens on the successful call = {rt} "
        f"(baselines without the control: 232 on a trivial prompt, 2,498 on the "
        f"first audit attempt). "
        + ("The control WORKED — reasoning stayed a small share and the answer "
           "was emitted." if rt is not None and ct and rt < ct
           else "Verdict unclear from this run — see the run record."))

    raw = {
        "run": "meta-audit-2",
        "timestamp": stamp.isoformat(timespec="seconds"),
        "model": MODEL,
        "recipe": {"max_completion_tokens_first": FIRST_CAP,
                   "reasoning_effort": "low",
                   "developer_role_format_rules": True,
                   "response_format": "json_schema object root {findings:[...]}"},
        "attempts": attempts,
        "usage_successful_call": usage,
        "totals_all_attempts": {"prompt_tokens": total_pt,
                                "completion_tokens": total_ct,
                                "reasoning_tokens": total_rt},
        "estimated_cost_usd": round(spent, 6),
        "reasoning_effort_verdict": effort_verdict,
        "model_findings": findings,
        "mapping": {str(i): fid for i, fid in mapping.items()},
        "score": {"caught": caught, "missed": missed,
                  "model_audit": f"{score}/{len(expected_ids)}",
                  "local_pipeline": "4/4"},
    }
    OUT_JSON.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    lines = [
        "# Cockpit run log — Meta Model API audit, run 2",
        "",
        f"- When: {stamp.strftime('%a %b %d, %Y %H:%M %Z')}",
        f"- Model: {MODEL} (one batched call, all 4 demo files in a single prompt, streamed)",
        "- Recipe: max_completion_tokens 12000 (reasoning and answer share one cap), "
        "reasoning_effort \"low\", developer-role format rules, json_schema object root {\"findings\": [...]}",
        f"- Attempts: {len(attempts)} (" +
        ", ".join(f"cap {a['cap']}" + ("" if a.get("strict") else ", strict dropped")
                  for a in attempts) + ")",
        f"- Tokens, successful call: prompt {pt} · completion {ct} · reasoning {rt}",
        f"- Tokens, all attempts: prompt {total_pt} · completion {total_ct} · reasoning {total_rt}",
        f"- Estimated cost: ${spent:.4f} (input $1.25/M, output $4.25/M) — from the $150 hackathon credit",
        "",
        "## Did the reasoning-effort control work?",
        "",
        f"- {effort_verdict}",
        "- Run 1 context: with no control, Spark burned 2,498 of 2,500 tokens on reasoning and returned nothing (score 0/4).",
        "",
        "## What the model found",
        "",
    ]
    for i, f in enumerate(findings):
        lines.append(f"- **{mapping.get(i, 'unmatched')}** — {f.get('file')} line {f.get('line')}: "
                     f"{f.get('issue')} (severity: {f.get('severity')}). Fix: {f.get('fix')}")
    lines += [
        "",
        "## Score",
        "",
        f"- Meta model audit: **{score}/{len(expected_ids)}**"
        + (f" (missed: {', '.join(missed)})" if missed else ""),
        "- Local deterministic pipeline (cockpit_day1.py): **4/4**",
        "- Pass bar: ≥3 of 4 — " + ("**PASS**" if score >= 3 else "**below bar**"),
        "",
        f"Raw model findings + full run record: `{OUT_JSON.name}` (same folder).",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nsaved: runs/{OUT_JSON.name}")
    print(f"saved: runs/{OUT_MD.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
