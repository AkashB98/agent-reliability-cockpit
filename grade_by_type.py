#!/usr/bin/env python3
"""grade_by_type.py — secondary, type-based grader for the Agent Reliability Cockpit.

PRE-REGISTERED 2026-10-29, before any Oct 31 credibility run.
Declared in day4-spec-2026-10-29.md / day4-work-order-2026-10-29.md.

What this is
------------
A SECOND score, reported side by side with the strict phrase grader
(meta_audit_holdout_retry.py), never instead of it. The strict grader is
untouched and stays primary. This grader ignores issue/fix prose entirely
and scores only (file + fault_type) against a dataset's
expected_findings.json.

Why an alias map is required (found 2026-10-29, verified in the data)
---------------------------------------------------------------------
The loop's findings carry a fault_type from the cockpit's FIXED generic
taxonomy (FAULT_TYPES in agentic_loop.py, frozen 2026-10-28 with Claude).
The datasets' expected_findings.json predate that taxonomy and use their
own vocabulary, so exact type matching would score the known-good
2026-10-28 graderfix runs v1 0/4 and v2 3/5 — contradicting the strict
grader's 4/4 and 5/5 for reasons that are pure vocabulary, not detection.

ALIAS_MAP below translates each EXPECTED (dataset) type into the set of
canonical taxonomy types that mean the same thing, judged from the
taxonomy definitions — written 2026-10-29, before the Oct 31 runs, and
not fitted to any Oct 31 result. Any expected type not listed maps to
itself (identity), which covers v2/v4's currency_mismatch,
duplicate_event and obfuscated_secret.

Credit rules
------------
- A fault is CAUGHT when at least one submitted finding has a fault_type
  in the fault's alias set AND its file is one of the files named in the
  expected fault's location. Duplicates never double-count.
- v1 FAULT-1 (broken_event) is a composite: the taxonomy splits it into
  missing_required_field and wrong_value_type. Either one, in
  ga4_events.json, credits the fault; both together still credit it once.
- v1 FAULT-2 (leaked_secret) names two files; a mapped finding in either
  file credits it.
- A submitted finding that matches no expected fault (file + alias) is a
  FALSE ALARM and is listed. Extra findings that match an already-caught
  fault are "supporting", not false alarms.
- fault_type "other" never credits a fault here (it has no canonical
  meaning to match against); such findings are listed as unclassified.
- Clean datasets (expected findings list empty, e.g. demo-dataset-v3-clean):
  PASS iff zero findings were submitted; every submitted finding is a
  false alarm.

Usage
-----
    python3 grade_by_type.py <run.json> <dataset_dir> [--out <file.json>]

Exit code 0 = graded (whatever the score); 2 = usage/input error.
Pure local, $0 — reads only the run JSON and expected_findings.json.
"""

import json
import re
import sys
from pathlib import Path

# Expected (dataset vocabulary) -> canonical taxonomy types (agentic_loop.FAULT_TYPES)
ALIAS_MAP = {
    "broken_event": {"missing_required_field", "wrong_value_type"},
    "leaked_secret": {"exposed_secret"},
    "unreplayable_tool_call": {"unsafe_replay"},
    "pii_in_tool_output": {"pii_exposure"},
    "pii_in_tool_input": {"pii_exposure"},
    "missing_idempotency_double_charge": {"missing_idempotency"},
}

FILE_RE = re.compile(r"[\w.\-]+\.(?:jsonl|json|txt)")


def expected_files(location: str):
    """File names named in an expected fault's free-text location."""
    return set(FILE_RE.findall(location or ""))


def grade(run_path: Path, dataset_dir: Path) -> dict:
    run = json.loads(run_path.read_text())
    expected = json.loads((dataset_dir / "expected_findings.json").read_text())
    findings = run.get("model_findings") or []
    faults = expected.get("findings") or []

    per_fault = []
    matched_idx = set()
    for fault in faults:
        want_types = ALIAS_MAP.get(fault["type"], {fault["type"]})
        want_files = expected_files(fault.get("location", ""))
        hits = [
            i
            for i, f in enumerate(findings)
            if f.get("fault_type") in want_types
            and (not want_files or f.get("file") in want_files)
        ]
        if hits:
            matched_idx.update(hits)
        per_fault.append(
            {
                "id": fault["id"],
                "expected_type": fault["type"],
                "alias_types": sorted(want_types),
                "expected_files": sorted(want_files),
                "caught": bool(hits),
                "finding_indices": hits,
            }
        )

    false_alarms = []
    unclassified = []
    for i, f in enumerate(findings):
        if f.get("fault_type") == "other":
            unclassified.append(i)
        elif i not in matched_idx:
            false_alarms.append(i)

    caught = [p["id"] for p in per_fault if p["caught"]]
    missed = [p["id"] for p in per_fault if not p["caught"]]
    if faults:
        score = f"{len(caught)}/{len(faults)}"
        clean_pass = None
    else:
        score = "clean-pass" if not findings else "clean-fail"
        clean_pass = not findings

    return {
        "grader": "grade_by_type (secondary; strict phrase grader stays primary)",
        "pre_registered": "2026-10-29",
        "run_file": run_path.name,
        "dataset": expected.get("dataset", dataset_dir.name),
        "typed_score": score,
        "caught": caught,
        "missed": missed,
        "per_fault": per_fault,
        "false_alarm_indices": false_alarms,
        "false_alarms": [
            {
                "file": findings[i].get("file"),
                "fault_type": findings[i].get("fault_type"),
                "issue": findings[i].get("issue"),
            }
            for i in false_alarms
        ],
        "unclassified_other_indices": unclassified,
        "clean_pass": clean_pass,
        "findings_submitted": len(findings),
    }


def main(argv):
    out = None
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    skip = {argv.index("--out"), argv.index("--out") + 1} if out else set()
    args = [a for j, a in enumerate(argv[1:], start=1)
            if j not in skip and not a.startswith("--")]
    if len(args) != 2:
        print(__doc__.split("Usage")[1].strip().splitlines()[0])
        print("usage: grade_by_type.py <run.json> <dataset_dir> [--out <file.json>]")
        return 2
    result = grade(Path(args[0]), Path(args[1]))
    print(f"typed score: {result['typed_score']}  ({result['dataset']})")
    for p in result["per_fault"]:
        mark = "CAUGHT" if p["caught"] else "MISSED"
        print(f"  {mark}  {p['id']}  expected={p['expected_type']} "
              f"alias={','.join(p['alias_types'])} findings={p['finding_indices']}")
    if result["false_alarms"]:
        print(f"  FALSE ALARMS: {len(result['false_alarms'])}")
        for fa in result["false_alarms"]:
            print(f"    - {fa['file']} [{fa['fault_type']}] {fa['issue']}")
    if result["unclassified_other_indices"]:
        print(f"  UNCLASSIFIED ('other'): {result['unclassified_other_indices']}")
    if out:
        Path(out).write_text(json.dumps(result, indent=1))
        print(f"  wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
