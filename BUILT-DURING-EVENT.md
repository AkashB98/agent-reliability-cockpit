# Built During the Event — Agent Reliability Cockpit (v2, updated Nov 1, 2026)

Supersedes `built-during-event-manifest.md` (Oct 26), which was written on
Day 1 and is now materially stale: it says the Meta Model API wiring is
"Step 0 pending" and lists only `cockpit_day1.py` as new work. Both are
false today. This file is the version that should sit in the submission
repo README when Akash gives the public-repo go.

Rule (Participant Guide §4): the demo must highlight only what was built
during the Hackathon (Oct 26 – Nov 4, 2026); judges must be able to clearly
identify new contributions. Failure to identify = disqualification risk.

## NEW — built during the event (this is the submission)

- `cockpit_day1.py` — Day-1 Cockpit pipeline (Oct 26): new pipeline that
  orchestrates Akash's pre-existing modules (listed below) plus the new
  GA4 schema check and replayability audit written during the event in
  this file; loads audit inputs, runs the composed checks, puts an
  approval gate on every proposed fix, and grades with the judge.
- Meta Model API audit wiring (`meta_audit.py` + variants, Oct 26–30) —
  live Muse Spark audits of the demo datasets; first runs Oct 26
  (spend ledger run-2026-10-26-meta-audit onward).
- `model_judge.py` — LLM-as-judge grading (Oct 27); what is new is the
  Muse Spark judge wiring for this audit — the underlying calibration
  approach comes from the pre-existing llm-judge-calibration module below.
- `impacts.py` — revenue-impact math on audit findings (Oct 27).
- `agentic_loop.py` — the agentic audit loop (Oct 28, extended through
  Nov 1): proposes fixes in tool calls, every fix blocked by default
  behind the approval gate; what is new is the in-loop integration of the
  pre-existing tool-approval-gate into the live Muse Spark audit loop.
- Fresh evaluation datasets built and sealed during the event:
  `demo-dataset-v2-holdout` (Oct 26–28), `demo-dataset-v3-clean`
  (Oct 28), `demo-dataset-v4-fresh-holdout` (sealed Oct 28, first run
  Oct 31 — genuine first-sight 5/5 strict + typed).
- `grade_by_type.py` — typed grader, scoring findings by fault type
  (Oct 29); v4 grader fix built from v4's sealed answer key (Oct 30–31).
- Credibility run set (Oct 31): v4 first-sight 5/5, holdout 10×
  consistency, timing 11.8–21.6s per audit; clean-set test first FAILED
  its pre-registered zero-false-alarm rule (report tool rejected an empty
  findings list — kept on the record, first), then the Claude-checked fix
  (empty list accepted) and a NEW post-fix re-run passed clean.
- Human-approval moment (Nov 1, in `agentic_loop.py` + `render_report.py`):
  a human approves exactly one blocked fix on screen; the harness — never
  the model — applies it to a COPY; revenue on that demo copy, one
  synthetic purchase, $0.00 → $49.99; originals untouched (sha256-verified);
  acceptance 10/10.
- `render_report.py` — visual HTML findings reports for every run.
- Cumulative Meta Model API spend through Nov 1: $1.1534 of the $150
  credit (source: `spend-ledger.json`, 28 entries).

## PRE-EXISTING — Akash's own open-source modules (public GitHub, built before Oct 26, 2026)

Used as libraries / prior work, NOT presented as new:
tool-approval-gate, pre-commit-secret-guard, tool-call-trace-replay,
prompt-injection-firewall, tool-output-pii-redactor,
llm-judge-calibration, mcp-tool-server. Other public repos are not
used in this submission.

## PRE-EVENT PREP MATERIALS (fixtures, not the product)

- `demo-dataset-v1/` — synthetic test data with 4 planted faults, frozen
  Oct 24, 2026 (fictional company; test fixture only). Planted secrets in
  demo copies are obviously fake.
- `demo-script-2026-10-24.md` — original draft script; the final script is
  `demo-script-v2-2026-11-01.md` rev. 2 (Nov 1), written against the real
  numbers above.

## Submission facts (Participant Guide §§7–8, pasted by Akash Oct 26)

- Submit via the CV platform by Wed Nov 4, 9:00 PM ET = 8:00 PM CT.
  Late submissions are not considered. Target: submit by noon CT.
- Repo must be PUBLIC and the video link accessible — double-check both
  before submitting. Everyone who worked on the project listed (solo).
- Demo video: 3 minutes, highlighting only the in-event build above;
  a primary judging artifact alongside code and live product.
- Tue Nov 3 is the LAST full day for submission questions / technical
  troubleshooting on the platform — platform questions cannot wait
  until Nov 4.
- Rubric: Impact 30% · Use of Meta AI Tooling 25% · Technical Depth &
  Execution 20% · Demo 25%. Stage 1 is pass/fail on theme fit +
  actual use of Meta Model API / open weights.
- Bonus fit (flag only, no extra build): Best Agentic Use-Case ($5K).
