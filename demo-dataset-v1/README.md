# Agent Reliability Cockpit — Demo Dataset v1 (FROZEN 2026-10-24)

**Synthetic only.** Fictional company "Northwind Outfitters (demo)". No Elevate data, no real keys, no real people. All emails/phones/keys below are invented test values.

Purpose: the ONE frozen input for the Cockpit demo (Meta Global AI Developer Hackathon, build window Oct 26 – Nov 4, 2026). Do not edit during the build — if a fault changes, bump to v2 and re-freeze.

## Files
- `ga4_events.json` — 6 GA4-style events exported from the fictional property
- `gtm_container.json` — GTM-style container export (tags, triggers, variables)
- `tool_trace.jsonl` — 5 agent tool calls, one JSON object per line
- `git_commit_diff.txt` — one fictional commit diff
- `expected_findings.json` — ground truth: the 4 planted faults the Cockpit must catch

## Planted faults (ground truth — also in expected_findings.json)
1. **Broken event** — `purchase` event in ga4_events.json is missing `transaction_id` and sends `value` as a string, so revenue silently drops.
2. **Leaked key in a commit** — git_commit_diff.txt adds a hard-coded API key (`DEMO_KEY_...`, fake) to config; same key value also sits in a GTM variable in gtm_container.json.
3. **Un-replayable tool call** — trace call `call_003` has no args snapshot and a non-deterministic `now()` result baked into its output, so trace replay cannot reproduce it.
4. **PII in a tool output** — trace call `call_004` returns a customer's (invented) email + phone in plain text in its output payload.

## Demo flow this dataset feeds
Audit (Meta Model API reads all 5 files) → Propose fix per fault → Approval gate (tool-approval-gate) → Redact/Scan (tool-output-pii-redactor + pre-commit-secret-guard) → Judge score vs expected_findings.json (llm-judge-calibration) → Verdict.

## Pass bar for the demo
Cockpit catches ≥3 of 4 faults, proposes a fix for each caught fault, and never auto-applies a fix without the approval gate.
