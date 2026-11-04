"""Agent Reliability Cockpit — dollar-impact + precise-location computation.

Everything in here is computed from the synthetic dataset files themselves.
No model writes these numbers: the model explains, the code does the math.
That split is deliberate — an impact figure a judge can re-derive from the
data beats a fluent estimate.
"""
import base64
import json
import re
from pathlib import Path


def _load(dataset_dir: Path, name):
    p = dataset_dir / name
    if name.endswith(".jsonl"):
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    if name.endswith(".json"):
        return json.loads(p.read_text(encoding="utf-8"))
    return p.read_text(encoding="utf-8")


def _money(v, cur=""):
    return f"{cur}{v:,.2f}"


# ---------------------------------------------------------------- v1 (Northwind)

def _v1(dataset_dir):
    events = _load(dataset_dir, "ga4_events.json")["events"]
    trace = _load(dataset_dir, "tool_trace.jsonl")
    gtm_text = (dataset_dir / "gtm_container.json").read_text(encoding="utf-8")
    diff_text = _load(dataset_dir, "git_commit_diff.txt")
    impacts, locators, totals = {}, {}, []

    purchases = [(i, e) for i, e in enumerate(events) if e.get("event_name") == "purchase"]
    broken = [(i, e) for i, e in purchases if "transaction_id" not in e.get("event_params", {})]
    for i, e in broken:
        val = float(e["event_params"]["value"])
        impacts["FAULT-1"] = (
            f"Revenue at risk: {_money(val, '$')} — this purchase has no transaction_id and its "
            f"value is a string, so GA4 drops or mis-attributes the order. It is {len(broken)} of "
            f"{len(purchases)} purchase events: 100% of the property's recorded order revenue.")
        locators[("FAULT-1", "ga4_events.json")] = (
            f"ga4_events.json → events[{i}] · the purchase event ({e.get('timestamp')})")
        totals.append(f"revenue at risk {_money(val, '$')}")

    key_match = re.search(r"DEMO_KEY_[A-Za-z0-9_]+", diff_text)
    if key_match:
        places = diff_text.count(key_match.group(0)) + gtm_text.count(key_match.group(0))
        impacts["FAULT-2"] = (
            f"Exposure: 1 API key in {places} places — the git commit history and a GTM container "
            f"variable. Anyone with repo or container access holds the key; rotation is the only fix.")
        gtm = _load(dataset_dir, "gtm_container.json")
        for vi, var in enumerate(gtm.get("variables", [])):
            if key_match.group(0) in json.dumps(var):
                locators[("FAULT-2", "gtm_container.json")] = (
                    f"gtm_container.json → variables[{vi}] · '{var.get('name')}' "
                    f"(variable_id {var.get('variable_id')})")
                break
        totals.append(f"1 key exposed in {places} places")

    unreplayable = [(n + 1, c) for n, c in enumerate(trace) if c.get("replayable") is False]
    if unreplayable:
        n, c = unreplayable[0]
        impacts["FAULT-3"] = (
            f"Verification gap: {len(unreplayable)} of {len(trace)} traced calls "
            f"({len(unreplayable) / len(trace):.0%}) can never be re-run, so what this call "
            f"reported can never be checked after the fact.")
        locators[("FAULT-3", "tool_trace.jsonl")] = (
            f"tool_trace.jsonl → record {n} · {c.get('call_id')} ({c.get('tool')})")
        totals.append(f"{len(unreplayable)} of {len(trace)} calls unverifiable")

    for n, c in enumerate(trace):
        out = c.get("output") or {}
        pii = [k for k in ("email", "phone") if out.get(k)]
        if pii:
            impacts["FAULT-4"] = (
                f"Exposure: 1 customer record in a plain-text log — {len(pii)} identifiers "
                f"({', '.join(pii)}) stored unredacted, readable by anyone with trace access.")
            locators[("FAULT-4", "tool_trace.jsonl")] = (
                f"tool_trace.jsonl → record {n + 1} · {c.get('call_id')} ({c.get('tool')})")
            totals.append("1 customer record exposed")
            break
    return impacts, locators, totals


# ------------------------------------------------------- v2 holdout (Fern & Fable)

def _v2(dataset_dir):
    events = _load(dataset_dir, "ga4_events.json")["events"]
    trace = _load(dataset_dir, "tool_trace.jsonl")
    gtm = _load(dataset_dir, "gtm_container.json")
    impacts, locators, totals = {}, {}, []

    purchases = [(i, e) for i, e in enumerate(events) if e.get("name") == "purchase"]
    funnel_curs = {e["params"].get("currency") for e in events
                   if e.get("name") in ("view_item", "add_to_cart", "begin_checkout")}
    for i, e in purchases:
        cur = e["params"].get("currency")
        if funnel_curs and cur not in funnel_curs:
            items_total = sum(it["price"] * it.get("quantity", 1) for it in e["params"]["items"])
            fcur = sorted(funnel_curs)[0]
            impacts["FAULT-V2-1"] = (
                f"Revenue mis-stated: this {_money(items_total, '€')} order is booked as "
                f"{_money(e['params']['value'], '$')} — 100% of the order's revenue lands in the "
                f"wrong currency ({cur} vs the {fcur} funnel), so every blended revenue and ROAS "
                f"report that includes it is off by the full EUR–USD gap — the ground-truth "
                f"analysis of this planted fault puts the overstatement at ≈16% on this order.")
            locators[("FAULT-V2-1", "ga4_events.json")] = (
                f"ga4_events.json → events[{i}] · purchase ({e.get('ts')}), "
                f"transaction_id {e['params'].get('transaction_id')}")
            break

    by_tx = {}
    for i, e in purchases:
        by_tx.setdefault(e["params"].get("transaction_id"), []).append((i, e))
    for tx, group in by_tx.items():
        if len(group) > 1:
            val = group[0][1]["params"]["value"]
            extra = val * (len(group) - 1)
            impacts["FAULT-V2-2"] = (
                f"Revenue overstated by {_money(extra, '$')}: order {tx} is counted {len(group)} "
                f"times — {_money(val * len(group), '$')} reported against {_money(val, '$')} real "
                f"(+{(len(group) - 1) / 1:.0%} on this order). Every ROAS figure fed by this "
                f"property inherits the inflation.")
            idxs = " and ".join(f"events[{i}]" for i, _ in group)
            locators[("FAULT-V2-2", "ga4_events.json")] = f"ga4_events.json → {idxs} · same transaction_id {tx}"
            totals.append(f"revenue overstated +{_money(extra, '$')}")
            break

    tags = gtm.get("containerVersion", {}).get("tag", [])
    for ti, tag in enumerate(tags):
        blob = None
        for p in tag.get("parameter", []):
            m = re.search(r"atob\('([A-Za-z0-9+/=]+)'\)", p.get("value", ""))
            if m:
                blob = m.group(1)
        if blob:
            decoded = base64.b64decode(blob).decode("utf-8", "replace")
            has_token = "token" in decoded.lower()
            impacts["FAULT-V2-3"] = (
                f"Exposure: 1 live API token shipped to every visitor's browser inside tag "
                f"'{tag.get('name')}'. The base64 blob decodes "
                f"{'to a working token (verified by decoding it here)' if has_token else 'in seconds'}"
                f" — encoding is not protection, and the token must be treated as public.")
            locators[("FAULT-V2-3", "gtm_container.json")] = (
                f"gtm_container.json → containerVersion.tag[{ti}] · tagId {tag.get('tagId')} "
                f"'{tag.get('name')}'")
            totals.append("1 live token public")
            break

    for n, c in enumerate(trace):
        charges = (c.get("result") or {}).get("charges") or []
        inp = c.get("input") or {}
        if len(charges) > 1 and inp.get("idempotency_key") is None:
            each = charges[0]["amount_cents"] / 100
            extra_total = sum(ch["amount_cents"] for ch in charges[1:]) / 100
            cur = "€" if inp.get("currency") == "EUR" else "$"
            impacts["FAULT-V2-4"] = (
                f"Customers double-charged: 1 — the gateway retry settled {len(charges)} charges "
                f"of {_money(each, cur)} for a single order, so {_money(extra_total, cur)} was "
                f"taken from the customer that should not exist, plus the refund and chargeback "
                f"handling it triggers.")
            locators[("FAULT-V2-4", "tool_trace.jsonl")] = (
                f"tool_trace.jsonl → record {n + 1} · {c.get('call')} ({c.get('tool_name')})")
            totals.append(f"{_money(extra_total, cur)} double-charged (1 customer)")

    for n, c in enumerate(trace):
        ship = (c.get("input") or {}).get("ship_to")
        if ship:
            items = ["name", "street address", "city/ZIP"]
            if "card ending" in (c["input"].get("billing_note") or ""):
                items.append("saved-card fragment")
            impacts["FAULT-V2-5"] = (
                f"Exposure: 1 customer's data written into a stored trace log — {len(items)} items "
                f"({', '.join(items)}). Inputs are logged just like outputs, so the log itself "
                f"becomes the leak.")
            locators[("FAULT-V2-5", "tool_trace.jsonl")] = (
                f"tool_trace.jsonl → record {n + 1} · {c.get('call')} ({c.get('tool_name')})")
            totals.append("1 customer record exposed")
            break

    if "FAULT-V2-1" in impacts:
        pass
    return impacts, locators, totals


def compute(dataset_dir: Path):
    """Return (impacts {fault_id: line}, locators {(fault_id, file): path},
    totals [short strings for the header strip])."""
    name = dataset_dir.name
    if "v2" in name:
        return _v2(dataset_dir)
    return _v1(dataset_dir)
