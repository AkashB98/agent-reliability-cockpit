# Agent Reliability Cockpit — Clean Dataset v3 (FROZEN 2026-10-28)

**Synthetic only.** Same fictional company "Northwind Outfitters (demo)" as v1/v2. No real data, no real keys, no real people.

Purpose: the **false-alarm test** for the Oct 31 credibility runs in the win plan (Day 3 spec, `../day3-build-spec-2026-10-28.md`). Every fault class from v1/v2 is present here in its *correct* form, so a good auditor reports **zero findings** — anything it flags is a measurable false alarm, which is exactly the credibility number the judges need to see alongside the 4/4 and 5/5 catch rates.

Prepared early (Oct 28, proactive run) so Oct 31 is plug-and-play. Do not edit — if something must change, bump to v4 and re-freeze.

## Files (same layout as v1/v2, so the existing scripts work unchanged)
- `ga4_events.json` — 6 events; the `purchase` event is CORRECT: `transaction_id` present, `value` a number
- `gtm_container.json` — variable 302 holds an env reference (`env:DEMO_SERVICE_KEY`), never a key value
- `tool_trace.jsonl` — 5 calls, all with args snapshots, all replayable; call_003's summary uses a fixed recorded `as_of`; call_004's CRM lookup returns no PII
- `git_commit_diff.txt` — a commit that documents env-based key handling; it names the variable, contains no credential
- `expected_findings.json` — ground truth: `findings: []`, pass bar = zero findings

## How Oct 31 uses it
Follow the holdout pattern: copy the audit script (or the agentic loop, once built) and point its `DATASET` constant at `demo-dataset-v3-clean` — exactly how `meta_audit_holdout.py` points at v2. Grade against `expected_findings.json`: score = number of findings reported (target 0). Log the run in `../runs/` with token usage + cost, same as prior days.

## Deliberate near-misses (all CORRECT — flagging any of these = false alarm)
1. Purchase event that looks like v1's FAULT-1 but has `transaction_id` + numeric `value`
2. The word "key" in a commit that only references `process.env.DEMO_SERVICE_KEY`
3. GTM variable named "Demo Service Key Source" whose value is an env reference
4. A daily-summary output mentioning a date — but the date is a recorded input, so replay reproduces it
5. A CRM tool call that touches a customer record but returns only tier + a boolean
