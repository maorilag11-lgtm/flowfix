#!/usr/bin/env python3
"""
validate.py — Make Workflow Doctor Knowledge Base integrity check
Exit code 0 = OK
Exit code 1 = one or more critical errors (missing file, broken JSON, schema violation)

Usage:
  python3 validate.py [--kb-root PATH]
"""

import sys
import os
import json
import glob
import argparse
from collections import defaultdict

# ── Configuration ────────────────────────────────────────────────────────────

REQUIRED_SCHEMA_FIELDS = [
    "id", "title", "problem", "category", "layer", "origin", "surface",
    "severity", "symptoms", "likely_causes", "diagnosis_steps", "solutions",
    "make_context", "search_keywords", "origin_details", "confidence",
    "verification_status", "quality_score", "last_verified",
    "evidence", "workflow_pattern", "diagnostic_signals",
    "next_review", "needs_reverification",
]

VALID_LAYERS = {
    "make_core", "make_module", "external_api",
    "user_configuration", "data", "network", "unknown",
}

VALID_ORIGINS = {
    "make", "external_service", "user", "network", "data", "unknown",
}

VALID_SURFACES = {
    "connection", "module", "scenario", "mapping", "webhook", "execution",
    "filter", "iterator", "aggregator", "router", "scheduler", "api", "unknown",
}

VALID_SEVERITIES = {"low", "medium", "high", "critical"}

VALID_STATUSES = {"verified", "partially_verified", "community_reported", "needs_review"}

META_FILES = {"knowledge_index.json", "coverage_matrix.json", "AUDIT_REPORT.md", "README.md", "validate.py"}

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def rel(path, root):
    return path.replace(root + "/", "")

# ── Checks ────────────────────────────────────────────────────────────────────

def check_referenced_files_exist(kb, errors, warnings):
    """Every file listed in knowledge_index.json and coverage_matrix.json must exist."""
    idx_path    = os.path.join(kb, "knowledge_index.json")
    matrix_path = os.path.join(kb, "coverage_matrix.json")

    if not os.path.exists(idx_path):
        errors.append("MISSING knowledge_index.json — cannot run referential check")
        return set(), set()
    if not os.path.exists(matrix_path):
        errors.append("MISSING coverage_matrix.json — cannot run referential check")
        return set(), set()

    idx    = load_json(idx_path)
    matrix = load_json(matrix_path)

    files_in_index  = set(e.get("file", "") for e in idx if e.get("file"))
    files_in_matrix = set(f for row in matrix for f in row.get("files", []))
    all_referenced  = files_in_index | files_in_matrix

    missing = set()
    for ref in sorted(all_referenced):
        full = os.path.join(kb, ref)
        if not os.path.exists(full):
            errors.append(f"MISSING FILE referenced in index/matrix: {ref}")
            missing.add(ref)

    return all_referenced, missing


def check_no_orphan_files(kb, all_referenced, warnings):
    """Every non-meta JSON file should be referenced somewhere."""
    for fpath in sorted(glob.glob(os.path.join(kb, "**", "*"), recursive=True)):
        if not os.path.isfile(fpath):
            continue
        fname = os.path.basename(fpath)
        relpath = rel(fpath, kb)
        if fname in META_FILES:
            continue
        if not fpath.endswith(".json"):
            continue
        if relpath not in all_referenced:
            warnings.append(f"ORPHAN FILE (not referenced in index or matrix): {relpath}")


def check_json_files_parse(kb, all_referenced, errors):
    """Every referenced JSON file must parse without error."""
    for relpath in sorted(all_referenced):
        full = os.path.join(kb, relpath)
        if not os.path.exists(full):
            continue  # already reported above
        try:
            data = load_json(full)
            if not isinstance(data, list):
                errors.append(f"INVALID FORMAT in {relpath}: expected JSON array, got {type(data).__name__}")
        except json.JSONDecodeError as e:
            errors.append(f"JSON PARSE ERROR in {relpath}: {e}")


def check_entry_schema(kb, all_referenced, errors, warnings):
    """Every entry in every referenced data file must satisfy the schema."""
    seen_ids = {}  # id -> first file seen

    for relpath in sorted(all_referenced):
        full = os.path.join(kb, relpath)
        if not os.path.exists(full):
            continue
        try:
            entries = load_json(full)
        except Exception:
            continue
        if not isinstance(entries, list):
            continue

        for i, entry in enumerate(entries):
            loc = f"{relpath}[{i}]"
            eid = entry.get("id", f"<no-id at index {i}>")

            # Required fields
            for field in REQUIRED_SCHEMA_FIELDS:
                if field not in entry:
                    errors.append(f"MISSING FIELD '{field}' in {loc} (id={eid})")

            # Duplicate IDs
            if eid in seen_ids:
                errors.append(f"DUPLICATE ID '{eid}' in {loc} — first seen in {seen_ids[eid]}")
            else:
                seen_ids[eid] = relpath

            # Enum validation
            layer = entry.get("layer", "")
            if layer and layer not in VALID_LAYERS:
                errors.append(f"INVALID layer='{layer}' in {loc} (id={eid})")

            origin = entry.get("origin", "")
            if origin and origin not in VALID_ORIGINS:
                errors.append(f"INVALID origin='{origin}' in {loc} (id={eid})")

            surface = entry.get("surface", "")
            if surface and surface not in VALID_SURFACES:
                errors.append(f"INVALID surface='{surface}' in {loc} (id={eid})")

            severity = entry.get("severity", "")
            if severity and severity not in VALID_SEVERITIES:
                errors.append(f"INVALID severity='{severity}' in {loc} (id={eid})")

            status = entry.get("verification_status", "")
            if status and status not in VALID_STATUSES:
                errors.append(f"INVALID verification_status='{status}' in {loc} (id={eid})")

            # Numeric ranges
            conf = entry.get("confidence")
            if conf is not None and not (0.0 <= float(conf) <= 1.0):
                errors.append(f"CONFIDENCE out of range [{conf}] in {loc} (id={eid})")

            qs = entry.get("quality_score")
            if qs is not None and not (0.0 <= float(qs) <= 1.0):
                errors.append(f"QUALITY_SCORE out of range [{qs}] in {loc} (id={eid})")

            # evidence must be a list (can be empty for stubs)
            ev = entry.get("evidence")
            if ev is not None and not isinstance(ev, list):
                errors.append(f"evidence must be an array in {loc} (id={eid})")

            # workflow_pattern must be an object
            wp = entry.get("workflow_pattern")
            if wp is not None and not isinstance(wp, dict):
                errors.append(f"workflow_pattern must be an object in {loc} (id={eid})")

            # Non-empty critical lists
            if isinstance(entry.get("symptoms"), list) and len(entry["symptoms"]) == 0:
                warnings.append(f"EMPTY symptoms list in {loc} (id={eid})")
            if isinstance(entry.get("diagnosis_steps"), list) and len(entry["diagnosis_steps"]) == 0:
                warnings.append(f"EMPTY diagnosis_steps in {loc} (id={eid})")
            if isinstance(entry.get("solutions"), list) and len(entry["solutions"]) == 0:
                warnings.append(f"EMPTY solutions list in {loc} (id={eid})")

            # origin_details structure
            od = entry.get("origin_details", {})
            if isinstance(od, dict):
                for subfield in ("source_type", "source_name", "source_url"):
                    if subfield not in od:
                        warnings.append(f"MISSING origin_details.{subfield} in {loc} (id={eid})")
            else:
                errors.append(f"origin_details must be an object in {loc} (id={eid})")

            # next_review date format
            nr = entry.get("next_review", "")
            if nr:
                try:
                    import datetime
                    datetime.date.fromisoformat(nr)
                except ValueError:
                    warnings.append(f"Invalid next_review date format '{nr}' in {loc} (id={eid})")

            # Related errors: check they don't reference non-existent IDs
            # (can only validate against seen_ids collected so far — partial check)


def check_knowledge_index_consistency(kb, all_referenced, errors, warnings):
    """Every entry in every data file must appear in knowledge_index.json."""
    idx_path = os.path.join(kb, "knowledge_index.json")
    if not os.path.exists(idx_path):
        return
    idx = load_json(idx_path)
    index_ids = {e["id"] for e in idx if "id" in e}

    for relpath in sorted(all_referenced):
        full = os.path.join(kb, relpath)
        if not os.path.exists(full):
            continue
        try:
            entries = load_json(full)
        except Exception:
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            eid = entry.get("id")
            if eid and eid not in index_ids:
                errors.append(f"ENTRY NOT IN INDEX: id='{eid}' from {relpath}")

    # Reverse: every index entry's file should be present
    for idx_entry in idx:
        eid   = idx_entry.get("id", "")
        efile = idx_entry.get("file", "")
        if efile and not os.path.exists(os.path.join(kb, efile)):
            errors.append(f"INDEX REFERENCES MISSING FILE: id='{eid}' file='{efile}'")


def check_coverage_matrix(kb, errors, warnings):
    """coverage_matrix.json counts must match actual file lengths."""
    matrix_path = os.path.join(kb, "coverage_matrix.json")
    if not os.path.exists(matrix_path):
        return
    matrix = load_json(matrix_path)
    for row in matrix:
        cat     = row.get("category", "?")
        claimed = row.get("current_entries", -1)
        actual  = 0
        for relpath in row.get("files", []):
            full = os.path.join(kb, relpath)
            if os.path.exists(full):
                try:
                    data = load_json(full)
                    if isinstance(data, list):
                        actual += len(data)
                except Exception:
                    pass
        if claimed != actual:
            errors.append(
                f"COVERAGE COUNT MISMATCH for '{cat}': "
                f"coverage_matrix says {claimed} but files contain {actual}"
            )



def check_needs_reverification(kb, errors, warnings):
    """needs_reverification must be True if next_review <= today, False otherwise."""
    import datetime
    today = datetime.date.today()
    meta = {"knowledge_index.json","coverage_matrix.json","AUDIT_REPORT.md","README.md","validate.py"}
    for fpath in sorted(glob.glob(os.path.join(kb,"**","*.json"), recursive=True)):
        fname = os.path.basename(fpath)
        if fname in meta: continue
        try:
            data = load_json(fpath)
        except: continue
        if not isinstance(data, list): continue
        for e in data:
            eid  = e.get("id","<no-id>")
            nr   = e.get("next_review","")
            flag = e.get("needs_reverification")
            if not nr: continue
            try:
                nr_date = datetime.date.fromisoformat(nr)
            except ValueError:
                continue
            expected = nr_date <= today
            if flag != expected:
                errors.append(
                    f"needs_reverification MISMATCH for '{eid}': "
                    f"next_review={nr} (today={today}) → expected {expected}, got {flag}"
                )


def check_audit_report_count(kb, errors, warnings):
    """AUDIT_REPORT.md must state the correct total entry count."""
    import re, glob, os
    report_path = os.path.join(kb, "AUDIT_REPORT.md")
    if not os.path.exists(report_path):
        warnings.append("AUDIT_REPORT.md not found — skipping count check")
        return

    meta = {"knowledge_index.json","coverage_matrix.json","AUDIT_REPORT.md","README.md","validate.py"}
    actual = 0
    for fpath in glob.glob(os.path.join(kb,"**","*.json"), recursive=True):
        fname = os.path.basename(fpath)
        rel   = fpath.replace(kb+os.sep,"")
        if rel in meta: continue
        try:
            data = load_json(fpath)
            if isinstance(data, list):
                actual += len(data)
        except: pass

    text = open(report_path, encoding="utf-8").read()
    # Look for "**Total entries:** N" or "| Total entries | N |"
    patterns = [
        r"\*\*Total entries:\*\*\s*(\d+)",
        r"\| Total entries \|\s*(\d+)\s*\|",
        r"Total entries[^\d]+(\d+)",
    ]
    found = None
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            found = int(m.group(1))
            break

    if found is None:
        warnings.append("AUDIT_REPORT.md: could not find total entry count — add '**Total entries:** N'")
    elif found != actual:
        errors.append(
            f"AUDIT_REPORT.md says {found} entries but actual count is {actual}. "
            f"Regenerate AUDIT_REPORT.md."
        )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Validate the Make Workflow Doctor knowledge base.")
    parser.add_argument("--kb-root", default=os.path.dirname(os.path.abspath(__file__)),
                        help="Root directory of the knowledge base (default: directory of this script)")
    args = parser.parse_args()

    kb = os.path.realpath(args.kb_root)
    if not os.path.isdir(kb):
        print(f"[FATAL] kb-root does not exist: {kb}", file=sys.stderr)
        sys.exit(1)

    errors   = []
    warnings = []

    print(f"Validating knowledge base at: {kb}\n")

    # Step 1 — referential integrity
    print("Step 1/5  Referential integrity (no missing files) …")
    all_referenced, missing = check_referenced_files_exist(kb, errors, warnings)

    # Step 2 — no orphan files
    print("Step 2/5  Orphan file check …")
    check_no_orphan_files(kb, all_referenced, warnings)

    # Step 3 — JSON parse
    print("Step 3/5  JSON parse check …")
    check_json_files_parse(kb, all_referenced, errors)

    # Step 4 — schema
    print("Step 4/5  Entry schema validation …")
    check_entry_schema(kb, all_referenced, errors, warnings)

    # Step 5 — index consistency + coverage counts
    print("Step 5/7  Index consistency + coverage matrix counts …")
    check_knowledge_index_consistency(kb, all_referenced, errors, warnings)
    check_coverage_matrix(kb, errors, warnings)

    # Step 6 — needs_reverification derived from next_review
    print("Step 6/7  needs_reverification date check …")
    check_needs_reverification(kb, errors, warnings)

    # Step 7 — AUDIT_REPORT.md count matches actual
    print("Step 7/7  AUDIT_REPORT.md count sync …")
    check_audit_report_count(kb, errors, warnings)

    # ── Report ──────────────────────────────────────────────────────────────
    print()
    if warnings:
        print(f"⚠️  WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"   {w}")
        print()

    if errors:
        print(f"❌ ERRORS ({len(errors)}) — validation FAILED:")
        for e in errors:
            print(f"   {e}")
        print()
        print("EXIT 1 — knowledge base is NOT ready for production.")
        sys.exit(1)
    else:
        print(f"✅ All checks passed — 0 errors, {len(warnings)} warning(s).")
        print("EXIT 0 — knowledge base is consistent and ready.")
        sys.exit(0)


if __name__ == "__main__":
    main()
