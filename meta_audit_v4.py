#!/usr/bin/env python3
"""Agent Reliability Cockpit — strict grader for demo-dataset-v4-fresh-holdout.

Declared 2026-10-30 in day5-fix-work-order-2026-10-30.md, BEFORE any run on
v4 (first-sight stays first-sight for the Oct 31 credibility runs). This is
NOT a post-result loosening: the fingerprints below are built from the
dataset's OWN sealed ground truth — each fault's `evidence` list in
demo-dataset-v4-fresh-holdout/expected_findings.json (sealed 2026-10-28) and
the file parsed from its `location` string.

Grading rule — same shape as the v2 strict grader
(meta_audit_holdout_retry.py): a fault counts as caught only when a finding
names the right file AND matches that fault's evidence in the model's own
words (issue + fix, lowercased). Each finding maps to at most one fault;
each fault is credited at most once; the finding with the most phrase hits
wins its fault. One deliberate tightening (Claude cross-check 2026-10-30,
still BEFORE any v4 run): the sealed v4 evidence lists contain single
generic words ("currency", "token", "input"), so credit requires at least
MIN_HITS=2 DISTINCT evidence phrases, not 1 — a real catch of each fault
hits several of its words, while one incidental word no longer earns
credit. The matched phrases for every credited fault are recorded
(EvidenceGrader.last_matched_phrases -> run record) so the score is
auditable.

The strict phrase grader stays primary. grade_by_type.py stays the
secondary score, unchanged. The v1/v2 graders are untouched.

Guard: map_findings skips any expected id that is not in FINGERPRINTS
instead of raising KeyError, so an unknown dataset can never crash the
harness at grading time (Day 5 Defect 1).

Pure local, $0 — reads only expected_findings.json.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATASET_V4 = HERE / "demo-dataset-v4-fresh-holdout"

_FILE_RE = re.compile(r"[\w.\-]+\.(?:jsonl|json|txt)")


def files_from_location(location):
    """File name(s) named in an expected fault's free-text location."""
    return set(_FILE_RE.findall(location or ""))


def build_fingerprints(dataset_dir):
    """{fault_id: {"files": {...}, "phrases": [...]}} from a dataset's own
    sealed expected_findings.json — evidence list verbatim (lowercased),
    file parsed from location. Works for any dataset in this format."""
    expected = json.loads(
        (Path(dataset_dir) / "expected_findings.json").read_text(encoding="utf-8"))
    fps = {}
    for fault in expected.get("findings") or []:
        fps[fault["id"]] = {
            "files": files_from_location(fault.get("location", "")),
            "phrases": [str(e).lower() for e in fault.get("evidence") or []],
        }
    return fps


# v4 fingerprints, built at import from the sealed v4 ground truth.
try:
    FINGERPRINTS = build_fingerprints(DATASET_V4)
except Exception:
    FINGERPRINTS = {}


MIN_HITS = 2  # distinct evidence phrases required (see module docstring)


def map_findings(model_findings, expected_ids, fingerprints=None):
    """Assign each model finding to at most one expected fault id.

    Same strict rule as the v2 grader, with the MIN_HITS tightening above.
    Unknown expected ids are skipped, never raised on. Returns
    (mapping, matched) when fingerprints is passed explicitly via the
    EvidenceGrader path — module-level callers get just the mapping, the
    same signature as the v1/v2 graders.
    """
    fps = FINGERPRINTS if fingerprints is None else fingerprints
    mapping = {}
    matched = {}
    used = set()
    for i, f in enumerate(model_findings):
        file = str(f.get("file") or "")
        blob = (str(f.get("issue", "")) + " " + str(f.get("fix", ""))).lower()
        best, best_hits = None, []
        for fid in expected_ids:
            if fid in used or fid not in fps:
                continue
            fp = fps[fid]
            if fp["files"] and file not in fp["files"]:
                continue
            hits = [p for p in dict.fromkeys(fp["phrases"]) if p in blob]
            if len(hits) > len(best_hits):
                best, best_hits = fid, hits
        if best and len(best_hits) >= MIN_HITS:
            mapping[i] = best
            matched[str(i)] = {"fault": best, "phrases": best_hits}
            used.add(best)
    if fingerprints is not None:
        return mapping, matched
    globals()["last_matched_phrases"] = matched
    return mapping


class EvidenceGrader:
    """A strict grader instance built from one dataset's own sealed
    expected_findings.json. Exposes the same interface as the v1/v2 grader
    modules (FINGERPRINTS + map_findings) so agentic_loop can use any of
    them interchangeably."""

    def __init__(self, dataset_dir):
        self.dataset_dir = Path(dataset_dir)
        self.FINGERPRINTS = build_fingerprints(self.dataset_dir)
        self.last_matched_phrases = None

    def map_findings(self, model_findings, expected_ids):
        mapping, matched = map_findings(
            model_findings, expected_ids, self.FINGERPRINTS)
        self.last_matched_phrases = matched
        return mapping


def build_grader(dataset_dir):
    """Grader for an arbitrary dataset, built from its own sealed evidence."""
    return EvidenceGrader(dataset_dir)
