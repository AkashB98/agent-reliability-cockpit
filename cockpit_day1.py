#!/usr/bin/env python3
"""Agent Reliability Cockpit — Day 1 (Meta Global Hackathon, Oct 26).

Loads the FROZEN demo-dataset-v1, runs the local shipped modules that do NOT
need the Meta Model API, audits the dataset with deterministic local
detectors, gates every proposed fix through the approval gate, and grades
the findings against expected_findings.json.

Local paths (no Meta API needed):
  - prompt-injection-firewall: scan() + decide() on every ingested file
  - FAULT-1: GA4 purchase-event schema check (missing transaction_id,
             value sent as a string) — structured-output-validator style
  - FAULT-2: pre-commit-secret-guard scan_diff() on git_commit_diff.txt
  - FAULT-3: trace replayability audit on tool_trace.jsonl (a call with no
             args snapshot and a now() wall-clock output can never replay)
  - FAULT-4: tool-output-pii-redactor scrub() on tool_trace.jsonl
  - Approval gate: approval_gate evaluate() on every proposed fix —
             nothing is applied; every fix comes back require_approval
  - Judge grading: findings matched by fault id vs expected_findings.json
             (pass bar >=3 of 4, per the dataset's own pass_bar)

The Meta Model API audit lives in meta_audit.py (one batched call, all 4
files in a single prompt). First run 2026-10-26: the call executed but
Muse Spark spent its whole completion budget on reasoning and returned no
findings — see runs/run-2026-10-26-meta-audit.md. Its findings will feed the
same gate + grading steps below once the reasoning budget is controlled.

Run:  python3 cockpit_day1.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATASET = HERE / "demo-dataset-v1"
BUILDS = Path.home() / "workspace" / "builds"
INPUTS = ["ga4_events.json", "gtm_container.json", "tool_trace.jsonl", "git_commit_diff.txt"]

def load_inputs():
    data = {}
    for name in INPUTS:
        p = DATASET / name
        data[name] = p.read_text(encoding="utf-8")
        print(f"loaded  {name:22s} {len(data[name]):6d} chars")
    return data

def main():
    print("== Cockpit Day 1 — local audit run (Meta API audit: meta_audit.py) ==\n")
    data = load_inputs()
    findings = []  # list of fault ids caught by the local audit

    # Make the shipped local modules importable (they live in ~/workspace/builds)
    sys.path.insert(0, str(BUILDS / "pre-commit-secret-guard"))
    sys.path.insert(0, str(BUILDS / "prompt-injection-firewall"))
    sys.path.insert(0, str(BUILDS / "tool-output-pii-redactor"))
    sys.path.insert(0, str(BUILDS / "tool-approval-gate"))

    # 1) Injection defense on every ingested file, before any model sees it
    print("\n-- injection firewall (scan + decide per file) --")
    from firewall.detectors import scan as fw_scan
    from firewall.policy import decide as fw_decide
    for name, text in data.items():
        d = fw_decide(fw_scan(text))
        print(f"{name:22s} decision={getattr(d, 'action', d)}")

    # 2) FAULT-1 path: GA4 purchase-event schema check
    print("\n-- FAULT-1 check: purchase event schema (ga4_events.json) --")
    ga4 = json.loads(data["ga4_events.json"])
    for ev in ga4.get("events", []):
        if ev.get("event_name") != "purchase":
            continue
        params = ev.get("event_params", {})
        problems = []
        if "transaction_id" not in params:
            problems.append("missing required transaction_id")
        if isinstance(params.get("value"), str):
            problems.append("value is a string, not a number")
        if problems:
            print(f"purchase event: {'; '.join(problems)}")
            findings.append("FAULT-1")
        else:
            print("purchase event: schema OK")

    # 3) FAULT-2 path: secret scan on the commit diff
    print("\n-- FAULT-2 check: secret guard scan_diff(git_commit_diff.txt) --")
    from secretguard.scanner import scan_diff
    res = scan_diff(data["git_commit_diff.txt"])
    for f in res.findings:
        print(f"finding: {f.detector} kind={f.kind} severity={f.severity} line={f.line}")
    print(f"total active findings: {len(res.findings)} (exit_code={res.exit_code})")
    if res.findings:
        findings.append("FAULT-2")

    # 4) FAULT-3 path: trace replayability audit
    print("\n-- FAULT-3 check: replayability audit (tool_trace.jsonl) --")
    trace_calls = [json.loads(line) for line in data["tool_trace.jsonl"].splitlines() if line.strip()]
    for call in trace_calls:
        reasons = []
        if call.get("args_snapshot") is None:
            reasons.append("no args snapshot")
        if "now()" in json.dumps(call.get("output", {})):
            reasons.append("output embeds now() wall-clock value")
        if call.get("replayable") is False:
            reasons.append("marked replayable=false")
        if reasons:
            print(f"{call.get('call_id')}: UNREPLAYABLE — {'; '.join(reasons)}")
            if "FAULT-3" not in findings:
                findings.append("FAULT-3")
        else:
            print(f"{call.get('call_id')}: replayable")

    # 5) FAULT-4 path: PII scrub on the tool trace before display/storage
    print("\n-- FAULT-4 check: pii redactor scrub(tool_trace.jsonl) --")
    from pii_redactor.scrubber import scrub
    out = scrub(data["tool_trace.jsonl"])
    scrubbed = out.text if hasattr(out, "text") else str(out)
    changed = scrubbed != data["tool_trace.jsonl"]
    print(f"scrub changed the trace: {changed}")
    if hasattr(out, "findings"):
        print(f"pii findings: {len(out.findings)}")
    if changed:
        findings.append("FAULT-4")

    # 6) Approval gate: every proposed fix must pass evaluate() first
    print("\n-- approval gate: evaluate() on every proposed fix --")
    from approval_gate.policy import Policy, ToolCall, evaluate
    gate_policy = Policy(name="cockpit-day1", default_action="require_approval")
    gated = 0
    for fid in findings:
        result = evaluate(gate_policy, ToolCall(tool="cockpit.apply_fix", args={"fault": fid}))
        print(f"{fid}: fix action={result.action} (nothing applied without approval)")
        if result.action == "require_approval":
            gated += 1
    print(f"gated fixes: {gated}/{len(findings)}")

    # 7) Judge grading: local findings vs expected_findings.json
    print("\n-- judge grading vs expected_findings.json --")
    expected = json.loads((DATASET / "expected_findings.json").read_text(encoding="utf-8"))
    expected_ids = [f["id"] for f in expected["findings"]]
    caught = [fid for fid in expected_ids if fid in findings]
    print(f"caught: {len(caught)}/{len(expected_ids)} — {', '.join(caught) if caught else 'none'}")
    missed = [fid for fid in expected_ids if fid not in findings]
    if missed:
        print(f"missed: {', '.join(missed)}")
    passed = len(caught) >= 3 and gated == len(findings)
    print(f"pass bar >=3 of 4 with every fix gated: {'PASS' if passed else 'FAIL'}")

    # 8) Meta Model API audit — separate script (meta_audit.py)
    print("\n-- Meta Model API audit: see meta_audit.py --")
    print("First Meta run (2026-10-26) executed end-to-end but returned no findings:")
    print("Muse Spark spent its full completion budget on reasoning and emitted no")
    print("answer content. Record: runs/run-2026-10-26-meta-audit.md. Controlling the")
    print("reasoning budget is the Day-2 fix before the next audit call.")
    print(f"\nDay 1 local run complete: {len(caught)}/{len(expected_ids)} faults caught, "
          f"all fixes gated; Meta audit wired, first run returned no findings.")
    return 0 if passed else 1

if __name__ == "__main__":
    raise SystemExit(main())
