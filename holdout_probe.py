#!/usr/bin/env python3
"""One streamed audit call on the holdout dataset, byte-level timing log.

Same body as the successful v1 run-2 call, same endpoint. Exists to find
out why the first holdout attempt died: this logs when the connection
opens, when the first byte arrives, and every chunk after that."""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import add_surrogate_to_request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import meta_audit_holdout as mh

data = {name: (mh.DATASET / name).read_text(encoding="utf-8") for name in mh.INPUTS}
prompt = mh.build_user_prompt(data)
print(f"prompt: {len(prompt)} chars; model={mh.MODEL}", flush=True)

body = {
    "model": mh.MODEL,
    "messages": [
        {"role": "developer", "content": mh.DEVELOPER_RULES},
        {"role": "user", "content": prompt},
    ],
    "max_completion_tokens": mh.FIRST_CAP,
    "reasoning_effort": "low",
    "response_format": {"type": "json_schema", "json_schema": {
        "name": "audit_findings", "schema": mh.FINDINGS_SCHEMA, "strict": True}},
    "stream": True,
    "stream_options": {"include_usage": True},
}
req = urllib.request.Request(mh.BASE + "/chat/completions",
                             data=json.dumps(body).encode(), method="POST")
req.add_header("Content-Type", "application/json")
req.add_header("Accept", "text/event-stream")
t0 = time.monotonic()
add_surrogate_to_request(req, mh.PROVIDER, allowed_hosts=mh.HOSTS)
print(f"[{time.monotonic() - t0:6.1f}s] surrogate attached, opening...", flush=True)
opener = urllib.request.build_opener(mh.NoRedirect())
try:
    resp = opener.open(req, timeout=180)
except Exception as e:
    print(f"[{time.monotonic() - t0:6.1f}s] OPEN FAILED: {type(e).__name__}: {e}", flush=True)
    raise SystemExit(2)
print(f"[{time.monotonic() - t0:6.1f}s] connection open, HTTP {resp.status}", flush=True)

content_parts, usage, finish = [], None, None
nchunks = 0
with resp:
    for raw in resp:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            print(f"[{time.monotonic() - t0:6.1f}s] [DONE]", flush=True)
            break
        nchunks += 1
        if nchunks == 1 or nchunks % 25 == 0:
            print(f"[{time.monotonic() - t0:6.1f}s] chunk {nchunks}", flush=True)
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if chunk.get("usage"):
            usage = chunk["usage"]
        for ch in chunk.get("choices") or []:
            d = ch.get("delta") or {}
            if d.get("content"):
                content_parts.append(d["content"])
            if ch.get("finish_reason"):
                finish = ch["finish_reason"]
content = "".join(content_parts) or None
print(f"finish={finish} usage={usage}", flush=True)
print(f"content_chars={len(content) if content else 0}", flush=True)
out = HERE / "runs" / "holdout-probe-raw.json"
out.write_text(json.dumps({
    "probe": "direct-stream",
    "usage": usage,
    "finish_reason": finish,
    "content": content,
}, indent=2), encoding="utf-8")
print(f"saved {out}", flush=True)
