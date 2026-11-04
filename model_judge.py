#!/usr/bin/env python3
"""Agent Reliability Cockpit — model-as-judge calibration check.

I use a second Muse Spark 1.1 call in a different role: grader. It receives
the audit's findings and the sealed ground truth, and returns a caught /
missed verdict per planted fault with a one-line reason. This is a
calibration check on my deterministic grader, not a replacement for it —
both scores are printed side by side, and any disagreement between them is
information (that is the whole point of my llm-judge-calibration work).

Ground truth goes to the JUDGE prompt only. It was never in the audit prompt.

Same discipline as the audit: muse-spark-1.1 only, reasoning_effort "low",
max_completion_tokens 12000, streamed, json_schema object root, one batched
call, established retry policy only, every token and cent logged.

Run:
  python3 model_judge.py --run runs/model-audit-holdout-v2-retry.json \
      --dataset-dir demo-dataset-v2-holdout --label holdout-v2
"""
import argparse
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
RUNS = HERE / "runs"
BASE = "https://api.meta.ai/v1"
PROVIDER = "custom.meta-model-api"
HOSTS = ["api.meta.ai"]
MODEL = "muse-spark-1.1"
RATE_IN_PER_M = 1.25
RATE_OUT_PER_M = 4.25
BUDGET_CAP_USD = 0.10
FIRST_CAP = 12000
RETRY_CAP = 24000

DEVELOPER_RULES = """Output rules — follow exactly:
- Respond with ONLY a JSON object matching the provided schema: {"verdicts": [...], "extras": [...]}. No prose, no markdown fences, nothing outside the JSON.
- One verdict per ground-truth fault, using its exact fault_id.
- verdict is "caught" or "missed". A fault is caught only if some audit finding identifies the same problem in the same file (wording may differ).
- reason: one line, under 25 words, naming the evidence you matched or what was absent.
- extras: for each audit finding that matches no ground-truth fault, one entry with its finding_index and a one-line assessment of whether it is a correct observation anyway."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fault_id": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["caught", "missed"]},
                    "reason": {"type": "string"},
                },
                "required": ["fault_id", "verdict", "reason"],
                "additionalProperties": False,
            },
        },
        "extras": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "finding_index": {"type": "integer"},
                    "assessment": {"type": "string"},
                },
                "required": ["finding_index", "assessment"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdicts", "extras"],
    "additionalProperties": False,
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def call_model(user_prompt, cap, strict):
    json_schema = {"name": "judge_verdicts", "schema": JUDGE_SCHEMA}
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
    return (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")


def parse_verdicts(content):
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
    if isinstance(parsed, dict) and isinstance(parsed.get("verdicts"), list):
        return parsed
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--dataset-dir", required=True)
    ap.add_argument("--label", required=True)
    args = ap.parse_args()

    run = json.loads((HERE / args.run).read_text(encoding="utf-8"))
    expected = json.loads((HERE / args.dataset_dir / "expected_findings.json")
                          .read_text(encoding="utf-8"))
    gt_ids = [f["id"] for f in expected["findings"]]
    det_score = run["score"]["model_audit"]

    gt_text = "\n".join(
        f"- {f['id']} [{f['type']}, {f['severity']}] at {f['location']}: {f['description']}"
        for f in expected["findings"])
    findings_text = "\n".join(
        f"{i}. {f.get('file')} line {f.get('line')} (severity {f.get('severity')}): "
        f"{f.get('issue')} Fix proposed: {f.get('fix')}"
        for i, f in enumerate(run["model_findings"]))
    prompt = (
        "You are grading an automated reliability audit. Below is the ground truth "
        "(the faults that were actually planted, with ids) and the audit's findings. "
        "For each ground-truth fault, decide whether the audit caught it.\n\n"
        f"GROUND TRUTH — dataset {expected['dataset']}:\n{gt_text}\n\n"
        f"AUDIT FINDINGS (from run {run['run']}, model {run['model']}):\n{findings_text}\n")
    print(f"== Cockpit — model-as-judge calibration check ({args.label}) ==")
    print(f"judge prompt: {len(prompt)} chars -> {MODEL}")

    attempts, parsed, spent = [], None, 0.0
    usage = finish_reason = None
    plan = [(FIRST_CAP, True)]
    idx = 0
    while idx < len(plan):
        cap, strict = plan[idx]
        idx += 1
        if spent >= BUDGET_CAP_USD:
            attempts.append({"cap": cap, "strict": strict,
                             "error": "budget guard hit — call not made"})
            print("budget guard hit — no further calls")
            break
        print(f"attempt {idx}: cap={cap} strict={strict} ...")
        try:
            status, content, usage, finish_reason, err = call_model(prompt, cap, strict)
        except Exception as e:
            attempts.append({"cap": cap, "strict": strict,
                             "error": f"transport: {type(e).__name__}: {str(e)[:300]}"})
            print(f"  transport error: {e}")
            # established policy: one transport retry, then stop
            if idx == 1:
                plan.append((cap, strict))
                print("  -> one transport retry (established policy)")
                continue
            break
        pt, ct, cost = usage_cost(usage)
        spent += cost
        attempts.append({"cap": cap, "strict": strict, "http_status": status,
                         "usage": usage, "reasoning_tokens": reasoning_tokens(usage),
                         "finish_reason": finish_reason,
                         "content_returned": bool(content),
                         "estimated_cost_usd": round(cost, 6), "error": err})
        if status != 200:
            print(f"  HTTP {status}: {(err or '')[:200]}")
            if status == 400 and strict:
                plan.append((cap, False))
                print("  -> dropping \"strict\" and retrying once (recipe policy)")
                continue
            break
        parsed = parse_verdicts(content)
        print(f"  HTTP 200, finish_reason={finish_reason}, "
              f"reasoning_tokens={reasoning_tokens(usage)}, completion={ct}, "
              f"verdicts parsed: {len(parsed['verdicts']) if parsed else 'no'}")
        if parsed is not None:
            break
        if finish_reason == "length" and not content and cap == FIRST_CAP:
            plan.append((RETRY_CAP, strict))
            print("  -> length cap hit with empty content: one retry at double cap")
            continue
        break

    stamp = datetime.now().astimezone()
    out_json = RUNS / f"model-judge-{args.label}.json"
    out_md = RUNS / f"run-2026-10-27-model-judge-{args.label}.md"
    total_pt = sum((a.get("usage") or {}).get("prompt_tokens", 0) for a in attempts)
    total_ct = sum((a.get("usage") or {}).get("completion_tokens", 0) for a in attempts)
    total_rt = sum(a.get("reasoning_tokens") or 0 for a in attempts)

    if parsed is None:
        raw = {"run": f"model-judge-{args.label}", "timestamp": stamp.isoformat(timespec="seconds"),
               "model": MODEL, "role": "judge (calibration check)",
               "graded_run": run["run"], "status": "no_verdicts_returned",
               "attempts": attempts, "estimated_cost_usd": round(spent, 6),
               "deterministic_score": det_score, "judge_score": None}
        out_json.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        lines = [
            f"# Cockpit run log — model-as-judge calibration check ({args.label})",
            "",
            f"- When: {stamp.strftime('%a %b %d, %Y %H:%M %Z')}",
            f"- Model in the judge role: {MODEL} (same verified recipe as the audit)",
            f"- Estimated cost (all attempts): ${spent:.4f} — from my $150 hackathon credit",
            "",
            "## What happened",
            "",
            "- The judge call returned no parseable verdicts within the established retry policy, so this calibration check is ungraded. My deterministic grade stands on its own.",
            f"- Deterministic grader score for this run: **{det_score}**",
            "",
            f"Raw run record: `{out_json.name}` (same folder).",
        ]
        out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"no verdicts. saved {out_json.name}, {out_md.name}")
        return 2

    verdicts = {v["fault_id"]: v for v in parsed["verdicts"]}
    judge_caught = [fid for fid in gt_ids
                    if verdicts.get(fid, {}).get("verdict") == "caught"]
    judge_score = f"{len(judge_caught)}/{len(gt_ids)}"
    agree = (judge_score == det_score)

    raw = {"run": f"model-judge-{args.label}",
           "timestamp": stamp.isoformat(timespec="seconds"),
           "model": MODEL, "role": "judge (calibration check)",
           "graded_run": run["run"], "dataset": expected["dataset"],
           "recipe": {"max_completion_tokens_first": FIRST_CAP,
                      "reasoning_effort": "low",
                      "developer_role_format_rules": True,
                      "response_format": "json_schema object root {verdicts:[...], extras:[...]}"},
           "attempts": attempts,
           "totals_all_attempts": {"prompt_tokens": total_pt,
                                   "completion_tokens": total_ct,
                                   "reasoning_tokens": total_rt},
           "estimated_cost_usd": round(spent, 6),
           "verdicts": parsed["verdicts"], "extras": parsed.get("extras", []),
           "judge_score": judge_score, "deterministic_score": det_score,
           "agreement": agree}
    out_json.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    lines = [
        f"# Cockpit run log — model-as-judge calibration check ({args.label})",
        "",
        f"- When: {stamp.strftime('%a %b %d, %Y %H:%M %Z')}",
        f"- Model in the judge role: {MODEL} (one batched call, streamed, same verified recipe as the audit)",
        f"- Graded run: {run['run']} on {expected['dataset']}",
        f"- Attempts: {len(attempts)}",
        f"- Tokens, all attempts: prompt {total_pt} · completion {total_ct} · reasoning {total_rt}",
        f"- Estimated cost: ${spent:.4f} (input $1.25/M, output $4.25/M) — from my $150 hackathon credit",
        "",
        "## Calibration footnote",
        "",
        "This is a lab check on my own grader, not a headline result: the judge graded "
        "the audit against my sealed answer key, which only exists because I planted the faults.",
        "",
        f"- Deterministic grader: **{det_score}** · Model judge: **{judge_score}** — "
        + ("**the two agree.**" if agree else "**the two disagree — see the verdicts.**"),
        "",
        "## Judge verdicts",
        "",
    ]
    for fid in gt_ids:
        v = verdicts.get(fid)
        if v:
            lines.append(f"- **{fid}** — {v['verdict']}: {v['reason']}")
        else:
            lines.append(f"- **{fid}** — no verdict returned")
    if parsed.get("extras"):
        lines += ["", "## Extra findings the audit raised", ""]
        for e in parsed["extras"]:
            lines.append(f"- Finding {e['finding_index']}: {e['assessment']}")
    lines += ["", f"Raw verdicts + full run record: `{out_json.name}` (same folder)."]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\njudge score: {judge_score} | deterministic: {det_score} | agree: {agree}")
    for fid in gt_ids:
        v = verdicts.get(fid, {})
        print(f"  {fid}: {v.get('verdict')} — {v.get('reason')}")
    print(f"cost: ${spent:.4f} | saved {out_json.name}, {out_md.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
