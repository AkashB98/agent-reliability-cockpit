#!/usr/bin/env python3
"""Agent Reliability Cockpit — visual findings report renderer.

I turn one audit run's JSON record into a single self-contained HTML page a
judge can read in seconds: what broke, where, how bad, the fix I propose —
and the approval gate state on every fix, because nothing in the Cockpit
applies without my approval.

No server, no external assets, no API calls. Pure local rendering.

Run:
  python3 render_report.py runs/model-audit-holdout-v2-retry.json \
      --dataset-dir demo-dataset-v2-holdout --cumulative 0.0287 \
      --out report/findings-report-holdout-v2.html
"""
import argparse
import html
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import impacts as impacts_mod

SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
SEV_COLORS = {
    "critical": ("#b00020", "#fdecea"),
    "high": ("#c62828", "#fdecea"),
    "medium": ("#e65100", "#fff3e0"),
    "low": ("#33691e", "#f1f8e9"),
}
TYPE_PLAIN = {
    "broken_event": "Broken analytics event",
    "leaked_secret": "Leaked secret",
    "obfuscated_secret": "Secret hidden in code",
    "unreplayable_tool_call": "Tool call that cannot be replayed",
    "pii_in_tool_output": "Private data in tool output",
    "pii_in_tool_input": "Private data in tool input",
    "currency_mismatch": "Wrong currency on revenue",
    "duplicate_event": "Same purchase counted twice",
    "missing_idempotency_double_charge": "Customer charged twice",
}


def esc(x):
    return html.escape(str(x if x is not None else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_json")
    ap.add_argument("--dataset-dir", required=True)
    ap.add_argument("--cumulative", type=float, default=None,
                    help="cumulative hackathon spend in USD at the time of the run; "
                         "when omitted, read from spend-ledger.json (the single "
                         "source of truth since 2026-10-29)")
    ap.add_argument("--judge-json", default=None,
                    help="optional model-judge run record, rendered as a calibration footnote")
    ap.add_argument("--approval-json", default=None,
                    help="optional harness approval-moment record (runs/approval-moment-*.json), "
                         "rendered as an approval-moment section: blocked fix, human approval, "
                         "corrected number")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.cumulative is None:
        ledger = json.loads((HERE / "spend-ledger.json").read_text(encoding="utf-8"))
        args.cumulative = round(sum(float(e["cost_usd"]) for e in ledger["entries"]), 6)

    impact_map, locator_map, totals = impacts_mod.compute(HERE / args.dataset_dir)
    judge = None
    if args.judge_json:
        judge = json.loads((HERE / args.judge_json).read_text(encoding="utf-8"))

    run = json.loads(Path(args.run_json).read_text(encoding="utf-8"))
    expected = json.loads((HERE / args.dataset_dir / "expected_findings.json")
                          .read_text(encoding="utf-8"))
    gt = {f["id"]: f for f in expected["findings"]}
    findings = run["model_findings"]
    mapping = {int(k): v for k, v in (run.get("mapping") or {}).items()}

    # Attach unmapped findings: same file+line as a mapped finding wins,
    # otherwise a fault whose ground-truth location names the file.
    attached = {}
    for i, f in enumerate(findings):
        if i in mapping:
            attached[i] = mapping[i]
            continue
        target = None
        for j, fid in mapping.items():
            mf = findings[j]
            if mf.get("file") == f.get("file") and mf.get("line") == f.get("line"):
                target = fid
                break
        if target is None:
            for fid, g in gt.items():
                if f.get("file") and f["file"] in g.get("location", ""):
                    target = fid
                    break
        attached[i] = target  # may stay None -> extra observation

    usage = run.get("usage_successful_call") or run.get("totals_all_attempts") or {}
    pt = usage.get("prompt_tokens", run.get("totals_all_attempts", {}).get("prompt_tokens"))
    ct = usage.get("completion_tokens", run.get("totals_all_attempts", {}).get("completion_tokens"))
    rt = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    score = run["score"]["model_audit"]
    caught = run["score"].get("caught", [])
    total_faults = len(gt)

    def card(i, f):
        fid = attached.get(i)
        sev = (f.get("severity") or "medium").lower()
        color, bg = SEV_COLORS.get(sev, SEV_COLORS["medium"])
        if fid and fid in gt:
            g = gt[fid]
            sev = (g.get("severity") or sev).lower()
            color, bg = SEV_COLORS.get(sev, SEV_COLORS["medium"])
            title = TYPE_PLAIN.get(g.get("type"), g.get("type", "Fault"))
            detail = esc(g["description"])
            tag = esc(fid)
            if i not in mapping:
                tag += " · same problem, second half"
        else:
            title = "Extra observation"
            detail = ""
            tag = "Not a planted fault — flagged anyway"
        loc = locator_map.get((fid, f.get("file"))) if fid else None
        if not loc:
            # text files keep a true line number; structured files use the path we computed
            loc = f"{f.get('file')} · line {f.get('line')}" if str(f.get("file", "")).endswith(".txt") \
                else str(f.get("file"))
        impact = impact_map.get(fid) if fid else None
        if i not in mapping and fid:
            impact = None  # second-half findings share the primary finding's impact line
        return f"""
    <article class="card" style="border-left:8px solid {color};background:{bg}">
      <div class="card-top">
        <span class="sev" style="background:{color}">{esc(sev.upper())}</span>
        <span class="tag">{tag}</span>
        <span class="loc">{esc(loc)}</span>
      </div>
      <h3>{esc(title)} — {esc(f.get('issue'))}</h3>
      {f'<p class="detail">{detail}</p>' if detail else ''}
      {f'<p class="impact"><strong>💥 Impact:</strong> {esc(impact)}</p>' if impact else ''}
      <p class="fix"><strong>Proposed fix:</strong> {esc(f.get('fix'))}</p>
      <div class="gate">
        <span class="gate-state">⛔ Approval gate: REQUIRES APPROVAL — nothing applied yet</span>
        <span class="gate-btns"><span class="btn approve">APPROVE</span><span class="btn reject">REJECT</span></span>
      </div>
    </article>"""

    ordered = sorted(range(len(findings)),
                     key=lambda i: (SEV_RANK.get((findings[i].get("severity") or "medium").lower(), 2), i))
    cards = "\n".join(card(i, findings[i]) for i in ordered)

    # Zero-findings (clean) state — added 2026-10-31 with the harness
    # clean-set fix: a submitted empty findings list renders as an
    # explicit clean report, not as an empty findings section.
    clean_block = ""
    findings_heading = ("Findings — every fix stops at my approval gate. "
                        "Nothing below has been applied.")
    if not findings:
        # Report what was SUBMITTED, not a verdict on cleanliness —
        # grading is the grader's job, recorded in the run log (Claude
        # cross-check 2026-10-31).
        findings_heading = "Findings — none submitted."
        clean_block = """
  <article class="card" style="border-left:8px solid #2e7d32;background:#f1f8e9">
    <h3 style="margin:0 0 6px">No findings submitted — the auditor reported no faults</h3>
    <p class="detail">The auditor inspected this dataset and submitted an empty findings list.
    Nothing was flagged, so nothing is waiting at the approval gate.</p>
  </article>"""
    if not findings:
        impact_sentence = ("none — the auditor reported no faults, so there "
                           "is no quantified impact from this audit.")
    else:
        impact_sentence = (
            esc(' · '.join(totals))
            + " — every figure computed from the data itself, not estimated by the model."
        ) if totals else "none — no faults found, so there is no quantified impact."

    # Approval-moment section (Nov 1 build) — present only when an
    # approval record is passed. It shows the one moment the gate opens:
    # a fix that was BLOCKED, a human approval recorded as a distinct
    # gate event, and the corrected number the harness produced by
    # applying that one fix to a COPY of the dataset.
    approval_block = ""
    if args.approval_json:
        ap_rec = json.loads(Path(args.approval_json).read_text(encoding="utf-8"))
        rev = ap_rec.get("revenue") or {}
        tally = ap_rec.get("final_gate_tally") or {}
        appr = next((g for g in ap_rec.get("gate_log") or []
                     if g.get("event") == "human_approval"), {})
        blocked = next((g for g in ap_rec.get("gate_log") or []
                        if g.get("event") == "initial_proposal"
                        and g.get("fault_id") == ap_rec.get("selection")), {})
        probes = "".join(
            f"<p class='detail'>⛔ Still denied, approval or not: {esc(p.get('probe'))} "
            f"— <b>{esc(p.get('gate_rule'))}</b>: {esc(p.get('reason'))}</p>"
            for p in ap_rec.get("deny_probes") or [])
        applied_list = "".join(f"<li>{esc(a)}</li>"
                               for a in ap_rec.get("applied_changes_on_copy") or [])
        approval_block = f"""
  <h2>✅ The approval moment — the one fix a human let through</h2>
  <article class="card" style="border-left:8px solid #2e7d32;background:#f1f8e9">
    <div class="card-top">
      <span class="sev" style="background:#2e7d32">APPROVED · APPLIED TO A COPY</span>
      <span class="tag">{esc(ap_rec.get('selection'))}</span>
      <span class="loc">{esc(blocked.get('target_file'))}</span>
    </div>
    <h3>Blocked fix: {esc(blocked.get('change'))}</h3>
    <p class="detail">⛔ At the gate it was <b>BLOCKED</b> ({esc(blocked.get('gate_action'))} — {esc(blocked.get('reason'))}).
    The model-facing tool still cannot approve anything itself.</p>
    <p class="detail">🧑 <b>Human approval:</b> the harness re-evaluated this one fix with
    human_approved=True → <b>{esc(appr.get('verdict'))}</b> ({esc(appr.get('gate_action'))} via {esc(appr.get('gate_rule'))}: {esc(appr.get('reason'))}),
    logged as a distinct gate event. The harness — never the model — then applied it, to a
    <b>copy</b> of the dataset only ({esc(ap_rec.get('copy_dir'))}); the originals are untouched (hash-verified).</p>
    <ul class="detail">{applied_list}</ul>
    <p class="impact"><strong>💰 Revenue corrected:</strong> recorded purchase revenue on the demo copy
    <b>${float(rev.get('recorded_before_usd') or 0):,.2f}</b> (wrong — the purchase was silently dropped)
    → <b>${float(rev.get('recorded_after_usd') or 0):,.2f}</b> after the approved fix (one synthetic purchase).
    {esc(rev.get('impact_line_before') or '')}</p>
    <p class="detail">Fine print, on purpose: the fix text above is the model's own proposed change from the
    Oct 31 run. The harness applied it as a data patch to the copy (an invented DEMO-TXN-1001 + the value
    conversion) — in production the same fix lands in checkout code. The demo's applier implements this
    FAULT-1 fix only, and the credential-rotation deny is a keyword match on the fix text, tested with a
    harness-worded probe below.</p>
    <p class="detail">Gate tally for this demo: <b>{esc(tally.get('approved'))} APPROVED + applied (copy only) ·
    {esc(tally.get('blocked'))} BLOCKED / unapplied</b> — every other proposed fix stayed at the gate.</p>
    {probes}
  </article>"""

    footer_gate = ("every proposed fix above returned <b>require_approval</b> from my gate — "
                   "the Cockpit proposes, I decide, only then does anything change.")
    if args.approval_json:
        footer_gate = ("every proposed fix above was held at the gate; the single exception is the "
                       "approval moment below — one fix a human approved, applied by the harness "
                       "to a copy of the dataset only.")

    judge_block = ""
    if judge and judge.get("judge_score"):
        agree_txt = "the two agree" if judge.get("agreement") else "the two DISAGREE — see the run log"
        judge_block = f"""
  <div class="calib"><strong>Calibration footnote (lab check, not a headline result):</strong>
  a second Muse Spark 1.1 call, grading in the judge role against the sealed answer key,
  scored this audit <b>{esc(judge['judge_score'])}</b>; my deterministic grader scored it
  <b>{esc(judge['deterministic_score'])}</b> — {esc(agree_txt)}. Judge call cost
  ${judge['estimated_cost_usd']:.4f}. Grading against my own answer key only exists because the
  faults were planted — it checks my grader, it does not prove the audit.</div>"""

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Reliability Cockpit — Audit Report ({esc(expected['dataset'])})</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         margin: 0; background: #f6f7f9; color: #1a1a2e; }}
  .wrap {{ max-width: 880px; margin: 0 auto; padding: 28px 18px 40px; }}
  header {{ background: #16213e; color: #fff; border-radius: 12px; padding: 22px 24px; }}
  header h1 {{ margin: 0 0 4px; font-size: 24px; }}
  header .sub {{ color: #b8c4de; font-size: 14px; }}
  .score {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 14px; }}
  .score div {{ background: #0f3460; border-radius: 8px; padding: 8px 14px; font-size: 14px; }}
  .score b {{ font-size: 18px; }}
  h2 {{ margin: 26px 0 10px; font-size: 17px; }}
  .card {{ border-radius: 10px; padding: 16px 18px; margin: 12px 0; background: #fff; }}
  .card-top {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; font-size: 12.5px; }}
  .sev {{ color: #fff; font-weight: 700; padding: 2px 9px; border-radius: 20px; }}
  .tag {{ font-weight: 700; }}
  .loc {{ color: #555; font-family: ui-monospace, Menlo, Consolas, monospace; }}
  .card h3 {{ margin: 10px 0 6px; font-size: 16.5px; }}
  .detail {{ margin: 4px 0; color: #333; font-size: 14.5px; }}
  .fix {{ margin: 8px 0 0; font-size: 14.5px; }}
  .impact {{ margin: 8px 0 0; font-size: 14.5px; background: #fff8e1; border-radius: 6px; padding: 8px 10px; }}
  .impact-total {{ margin-top: 14px; background: #7b1f1f; border-radius: 8px; padding: 10px 14px; font-size: 14.5px; }}
  .calib {{ margin-top: 22px; font-size: 13px; color: #555; border: 1px dashed #bbb; border-radius: 8px; padding: 10px 14px; background: #fff; }}
  .gate {{ display: flex; justify-content: space-between; align-items: center; gap: 10px;
          flex-wrap: wrap; margin-top: 12px; padding-top: 10px; border-top: 1px dashed #bbb; }}
  .gate-state {{ font-weight: 700; font-size: 13.5px; color: #7a3b00; }}
  .btn {{ display: inline-block; padding: 5px 14px; border-radius: 6px; font-size: 13px;
         font-weight: 700; margin-left: 6px; opacity: .55; }}
  .approve {{ background: #2e7d32; color: #fff; }}
  .reject {{ background: #eceff1; color: #37474f; border: 1px solid #90a4ae; }}
  footer {{ margin-top: 28px; font-size: 13px; color: #555; border-top: 1px solid #ddd; padding-top: 12px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Agent Reliability Cockpit — Audit Report</h1>
    <div class="sub">Dataset: {esc(expected['dataset'])} (synthetic) · Audited by {esc(run['model'])} via the Meta Model API · Run {esc(run['timestamp'])}</div>
    <div class="score">
      <div>Score <b>{esc(score)}</b></div>
      <div>Pass bar <b>{esc(expected['pass_bar'].split('—')[0].strip() if '—' in expected['pass_bar'] else expected['pass_bar'])}</b></div>
      <div>Faults caught <b>{len(caught)}/{total_faults}</b></div>
      <div>Tokens <b>{esc(pt)} in · {esc(ct)} out · {esc(rt)} reasoning</b></div>
      <div>Run cost <b>${run['estimated_cost_usd']:.4f}</b></div>
    </div>
    <div class="impact-total"><strong>Total quantified impact:</strong> {impact_sentence}</div>
  </header>

  <h2>{esc(findings_heading)}</h2>
  {clean_block}
  {cards}

  {approval_block}

  {judge_block}

  <footer>
    Approval gate: {footer_gate}
    Cumulative hackathon spend: <b>${args.cumulative:.4f} of the $150 credit</b>.
    Report generated locally from the run record — rendering cost $0.
  </footer>
</div>
</body>
</html>
"""
    out = HERE / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out} ({len(page)} chars, {len(findings)} finding cards, score {score})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
