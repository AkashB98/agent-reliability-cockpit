# Agent Reliability Cockpit — Fresh Holdout v4 (SEALED, FROZEN 2026-10-28)

**Synthetic only.** New fictional company "Harbor & Pine Outdoors (demo)" — not used in v1/v2/v3. No real data, no real keys (the token is an obviously fake HP_TOKEN_f4k3... string), no real people (contact details use example.invalid / 555 numbers).

## Why this exists
On 2026-10-28 the agentic loop was fixed with a frozen fault_type taxonomy (Claude consult, runs/claude-consult-2026-10-28-grader-fix.md). Claude's condition: re-scoring the old v2 holdout after seeing its failure is post-hoc, disclosed — a clean proof needs a FRESH holdout evaluated after the taxonomy froze. The main agent told Akash the same day: "The clean proof is a fresh unseen dataset — that slots straight into the Oct 31 credibility runs." No such fault dataset existed (v3 is the clean/zero-finding set). This v4 fills that gap.

## Seal rules — read before Oct 31
- Do NOT run any model (single-shot audit or agentic loop) on this dataset before the Oct 31 credibility run. The first run IS the measurement.
- Do NOT tune prompts, taxonomy, or graders against this dataset. If a fault is missed, report the miss.
- expected_findings.json is never included in a model prompt.
- Do not edit these files. If something must change, bump to v5, re-freeze, and note that v4 was never run.

## Files (same layout as v1/v2/v3, so existing scripts work unchanged)
- ga4_events.json — 8 events; faults V4-1 (currency) + V4-2 (duplicate) live here
- gtm_container.json — fault V4-3 (base64/atob-obfuscated fake key, tag 23) lives here
- tool_trace.jsonl — 4 calls, all replay supported; faults V4-4 (idempotency double charge, t-202) + V4-5 (PII email+phone in input, t-203) live here; t-201/t-204 are clean decoys
- git_commit_diff.txt — clean decoy: key referenced by env-var NAME only, no credential value
- expected_findings.json — ground truth: 5 findings, types match the frozen taxonomy vocabulary used in v2

## How Oct 31 uses it
Follow the holdout pattern: copy the loop/audit script and point its DATASET constant at demo-dataset-v4-fresh-holdout — exactly how meta_audit_holdout.py points at v2. Grade against expected_findings.json with BOTH graders (strict phrase + typed), report side by side, log the run in ../runs/ with token usage + cost. Pass bar: >=4 of 5 on first sight.
