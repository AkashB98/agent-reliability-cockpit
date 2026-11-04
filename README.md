# Agent Reliability Cockpit

**An AI auditor for analytics setups that proposes fixes — and is not allowed to apply any of them by itself.**

I'm Akash Bhargava, a marketing data analyst. My day job is GA4 and Google
Tag Manager implementations, and the recurring pain is setups failing
*silently*: a purchase event that drops revenue without an error, an API
key leaked into a commit, a tool call nobody can replay, customer PII
sitting in plain text inside a tool output. This is my Meta Global AI
Developer Hackathon project (Indie Developer track, theme: **Build for
Your World**) — I built the auditor I want standing between an AI agent
and a production analytics setup.

## What it does

Powered by Meta's **Muse Spark** (`muse-spark-1.1`, via the Meta Model
API), the Cockpit's agent drives its own audit tools over a synthetic
analytics setup (GA4 events, a GTM container, an AI tool-call trace, a
git diff):

- checks event schemas (the broken `purchase` event: missing
  `transaction_id`, `value` sent as a string → revenue silently dropped)
- scans code and container for leaked secrets
- tests whether tool calls can be replayed deterministically
- scrubs PII out of tool outputs before anything is stored or shown
- computes the dollar impact of every fault, in code

Every fix the agent proposes goes through an **approval gate**: blocked
by default. A human approves; the harness — never the model — applies
an approved fix, and in the demo it applies it to a *copy*, so you can
see the effect (recorded revenue for one synthetic purchase:
**$0.00 → $49.99**) while the originals stay byte-identical
(sha256-verified).

## Results — including the failure

All datasets are 100% synthetic. Graders are deterministic and were
never loosened after seeing results.

- **Fresh holdout (v4), first run ever on a sealed dataset:** 5/5 faults
  detected — strict grader 5/5, typed grader 5/5. Precision 6/7: the one
  extra finding double-labelled the double-charge call. Disclosed.
- **Holdout (v2), 10 consistency runs:** 5/5 detected in all 10. In 3 of
  10 runs the agent added one extra `unsafe_replay` label on the same
  double-charge call. Known, explainable, disclosed.
- **Clean set (v3), pre-registered test: FAIL.** The rule was zero
  findings submitted on a clean set. The harness required at least one
  finding, so the model submitted a "no faults found" placeholder.
  Zero real faults were flagged — detection was right, the submission
  format made the pre-registered rule unmeetable. That flaw was in my
  harness, and I'm reporting it as a fail.
- **Clean set, post-fix re-run (a separate, later test):** I fixed the
  harness to accept an empty findings list and re-ran once. Zero
  findings submitted, strict record 0/0, typed grader clean-pass.
  This does **not** change the pre-registered FAIL above.
- **Timing:** full audits took 11.8–21.6 seconds each.
- **Spend:** total Meta Model API spend for the whole build was
  **$1.1534 of the $150 credit** (itemized in `spend-ledger.json`).
- **Approval moment:** of 4 proposed fixes, exactly 1 was approved and
  applied — to a copy. The other 3 stayed blocked. In harness probes, a
  credential-rotation change and an irreversible change were denied
  even with approval marked (the credential deny is a keyword match on
  the change text — I claim exactly that, no more).

## Built during the event

Everything in `BUILT-DURING-EVENT.md` was built Oct 26 – Nov 1, 2026:
the agentic audit loop, the Meta Model API wiring, the typed grader,
the sealed v2/v3/v4 evaluation datasets, the Oct 31 credibility runs,
the human-approval moment, and the visual report renderer.

The Cockpit composes guardrail libraries I had **already open-sourced
before the event** — a tool-approval gate, a secret guard, a trace
replay system, a PII redactor, an LLM-judge calibration harness, a
prompt-injection firewall, and an MCP tool server. Those are prior
work, used as libraries; they are not presented as new.

## Layout

- `agentic_loop.py` — the agent loop (Muse Spark drives the tools;
  every proposed fix passes the gate)
- `render_report.py` — visual HTML findings reports (`report/`)
- `grade_by_type.py`, `meta_audit_v4.py` — the graders
- `impacts.py` — per-fault dollar-impact math
- `demo-dataset-v1/` … `demo-dataset-v4-fresh-holdout/` — synthetic
  datasets (planted secrets are obviously fake, e.g.
  `DEMO_KEY_9f8e7d6c5b4a_fake_do_not_use`)
- `runs/` — machine records for every run cited above
- `DEMO-SCRIPT.md` — the 3-minute demo script
- `spend-ledger.json` — every cent of API spend, itemized

## Links

- GitHub: https://github.com/AkashB98
- Portfolio: https://akashbhargava999.netlify.app
