# Agent Reliability Cockpit — FINAL demo script v2 (rev. 2, Claude fixes applied)
Written: Sun Nov 1, 2026 (pulled forward from Nov 2 at Akash's order)
Rev. 2: Claude cross-check (QUESTION — all numbers correct; 8 presentation
defects) → fixes applied same day. Consult saved verbatim at
`runs/claude-consult-2026-11-01-demo-script-v2.md`.
Runtime: 3:00 target. Spoken ≈ 400 words at a brisk demo pace (~2.5 w/s).
Results cards are on-screen text — full text also lives in the repo README,
so a judge who wants every word can pause or read it there.
Sources (results lines are VERBATIM from these — do not paraphrase):
- `nov2-script-decision-pack-2026-10-31.md` lines 1–4 + 3b
- `nov2-approval-climax-lines-2026-11-01.md` (climax lines + corrected spend line; supersedes pack line 5)
- `built-during-event-manifest-v2-2026-11-01.md` (built-during-event framing)
- `runs/run-2026-11-01-approval-moment.md`, `runs/run-2026-10-31-credibility-runs.md`

BEFORE RECORDING, have open: terminal in the project folder · the v1 dataset
folder · `report/findings-report-agentic-v1-approval-moment.html` ·
`report/findings-report-agentic-v4-fresh-holdout-v4-first-sight.html`.
Fallback if the live call stalls: switch to the saved reports (see
`recording-checklist-2026-11-01.md`) — the script works word-for-word either way.

---

## SEG 1 — HOOK · 0:00–0:18 · spoken ~42 words

**On screen:** the v1 findings report's impact header — recorded revenue
**$0.00** for the demo store's purchase, next to the $49.99 price of the
item that was bought.

**Say:**
> "This report says the store made zero dollars from a purchase that cost
> forty-nine ninety-nine. The sale happened. The revenue vanished —
> silently, no error anywhere. That's the kind of failure I built this
> to catch."

## SEG 2 — WHO I AM / BUILD FOR YOUR WORLD · 0:18–0:45 · spoken ~68 words

**On screen:** me, then the project folder / Cockpit report page.

**Say:**
> "I'm Akash Bhargava, a marketing data analyst. Build for Your World —
> this is literally my job: GA4 and Google Tag Manager setups that break
> quietly and take revenue data with them. So I built the Agent
> Reliability Cockpit: an AI auditor, powered by Meta's Muse Spark,
> composing guardrail libraries I'd already open-sourced — secret
> scanning, trace replay, PII redaction, an approval gate — behind one
> workflow that isn't allowed to change anything on its own."

*(Disclosure fix, per Claude: the guardrail modules are pre-existing
open-source work and are named as such ON CAMERA here — never present
them as built during the event.)*

## SEG 3 — THE LIVE AUDIT · 0:45–1:12 · spoken ~40 words + screen time

**On screen:** terminal. Run the agentic loop on demo-dataset-v1. The run
header shows the model name — keep it visible: **muse-spark-1.1** via the
Meta Model API. Tool calls stream: validate events, secret scan, replay
check, PII scrub, impact math. A full audit takes 11.8–21.6s.
**Recording note (Claude fix):** the "four faults" line below is only safe
against the known run. Either (a) let the live run finish on camera and
confirm the findings before the take you keep, or (b) cut to the saved
Oct 31 timing-run report (`report/findings-report-agentic-v1-timing.html`,
4/4) and narrate over it.

**Say:**
> "Watch it work. Muse Spark drives the tools itself — checks the GA4
> events, scans the code and the tag container, tests replay, scrubs
> private data, and computes the dollar impact of what it finds.
> Four faults. Every one priced."

## SEG 4 — THE FAULTS + THE GATE · 1:12–1:35 · climax line 1 verbatim

**On screen:** the 4 fault cards in the report — (1) purchase event
missing `transaction_id`, value sent as a string → revenue dropped;
(2) a leaked API key in the commit diff and a GTM variable — the planted
key is obviously fake, it reads `DEMO_KEY_9f8e7d6c5b4a_fake_do_not_use`;
(3) a tool call that can't be replayed; (4) customer email + phone in
plain text in a tool output. Then the gate column: every fix BLOCKED.

**Say (climax line 1, verbatim):**
> "The audit proposed fixes in 6 tool calls. Grouped by fault, that's
> 4 fixes — the revenue fault and the leaked-key fault each had two
> calls. Every one was blocked by default: no fix applies itself."

## SEG 5 — CLIMAX: THE APPROVAL MOMENT · 1:35–2:22 · climax lines 2–4 verbatim

**On screen:** the approval-moment report
(`report/findings-report-agentic-v1-approval-moment.html`): the one
approval, applied to a COPY; revenue line $0.00 → $49.99; the other three
fixes still BLOCKED. (Scope, from the supplement: the applier implements
the revenue fault only, by design — the approval performed on screen is
FAULT-1.)

**Say (climax line 2, verbatim):**
> "I approve exactly one: the revenue fix — the model's own proposed
> change, add the missing transaction ID and make the value a number.
> The harness, never the model, applies it — to a copy. The originals
> don't move."

**Say (climax line 3, verbatim):**
> "On that demo copy, recorded revenue for the one synthetic purchase
> goes from $0.00 to $49.99. In production the same fix lands in the
> checkout code; here we patch the copy so you can see the effect."

**Say (climax line 4, verbatim):**
> "The other 3 fixes stay blocked and unapplied. And in harness probes,
> a credential-rotation change and an irreversible change were denied
> even with approval marked — the credential deny is a keyword match
> on the change text, and I scoped the claim to exactly that."

## SEG 6 — PROOF + THE HONEST FAILURE · 2:22–2:50

**On screen:** v4 first-sight report, then the results cards in order,
each clearly labelled. Full card text is verbatim; holds are short on
purpose — the same text is in the repo README for judges to read in full.

**Say (decision-pack line 1, verbatim):**
> "First sight on a sealed dataset it had never seen: 5 of 5 faults
> detected — strict grader 5/5, typed grader 5/5. Precision was 6 of 7
> findings; the extra finding double-labelled the double-charge call."

**On-screen card — label: HOLDOUT v2 — CONSISTENCY (decision-pack line 2,
verbatim; hold ~5s):**
> "Same holdout, 10 runs: 5 of 5 detected in all 10. In 3 of the 10
> runs it added one extra label — unsafe_replay — on the same
> double-charge call. Known, explainable, disclosed."

**On-screen caption (decision-pack line 4, verbatim, shown separately —
it is NOT part of line 2):**
> "Runs took 11.8–21.6 seconds each"

**Say (decision-pack line 3, first sentence, verbatim):**
> "Clean set: FAIL under the pre-registered zero-submission rule."

**On-screen card — label: CLEAN SET — PRE-REGISTERED TEST (decision-pack
line 3, full, verbatim; hold ~5s):**
> "Clean set: FAIL under the pre-registered zero-submission rule.
> Root cause: the harness requires at least one finding, so the model
> submitted a 'no faults found' placeholder. Zero real faults flagged.
> The rule could never be met by this harness — that flaw was ours,
> in the pre-registration, and we are reporting it as a fail."

**On-screen card — label: CLEAN SET — POST-FIX RE-RUN, A NEW TEST
(decision-pack line 3b, verbatim; hold ~5s, it is the last card):**
> "Later the same day, I fixed the harness so an empty findings
> list — the way a clean audit should be reported — is accepted,
> and ran the clean set once more as a new, post-fix test. This
> time the Cockpit submitted zero findings: strict record 0/0 with
> zero submissions, typed grader clean-pass, no placeholder. The
> pre-registered result in line 3 stays a FAIL; this re-run is a
> separate, later test and does not change it."

## SEG 7 — CLOSE · 2:50–3:00

**On screen:** spend line + the gate tally (1 approved on a copy, 3 blocked).

**Say (corrected spend line, verbatim):**
> "13 credibility runs cost $0.75; the clean-set post-fix re-run
> added $0.0389; the Nov 1 approval moment cost $0. Cumulative spend:
> $1.1534 of the $150 credit."

**Say (close, only if time remains — cut this first if the take runs long):**
> "An auditor that proposes, a human who disposes. That's the Cockpit."

**Presenter note on the spend math (not spoken):** the three items in the
spend line total $0.7889; the remaining ~$0.36 of the $1.1534 cumulative
is the Oct 26–28 development runs, itemized in `spend-ledger.json`.
If a judge asks, that's the answer — the line itself stays verbatim.

---

## TIGHT CUT — if a take runs over 3:00, cut in this order
1. SEG 7 close line (marked above).
2. SEG 3, second half of sentence 2 ("tests replay, scrubs private data")
   — the modules were already named in SEG 2.
3. Card holds in SEG 6 to 3s each (text lives in the README).

## Production notes (not spoken)

- Everything presented as new was BUILT DURING THE EVENT (Oct 26 – Nov 1):
  the agentic loop, the Meta Model API wiring, the typed grader, the
  sealed v2/v3/v4 datasets, the Oct 31 credibility runs, and the Nov 1
  approval moment. The guardrail modules it composes are my own
  pre-existing open-source libraries — disclosed on camera in SEG 2.
- The demo data (demo store) is 100% synthetic. Planted secrets are
  obviously fake by design.
- Number sources: `spend-ledger.json`,
  `runs/run-2026-10-31-credibility-runs.md` (v4, holdout, clean),
  `runs/run-2026-10-31-agentic-loop-v3-clean-clean-postfix.md` (re-run),
  `runs/run-2026-11-01-approval-moment.md` (approval moment).
- Cross-checks of the two claims Claude could not verify from the facts
  sheet: "the revenue fault and the leaked-key fault each had two calls"
  is stated verbatim in the run record basis (6 tool-level calls grouped
  to 4 faults) and in the Claude-corrected climax supplement; "later the
  same day" is exact — the pre-registered clean run and the post-fix
  re-run both ran on Oct 31 (14:02 and 21:14 local).
