"""Consume S5 documentary records; no retrieval and no condition evaluation."""
from __future__ import annotations
from copy import deepcopy
from flowfix.step5_response.formatter.guidance import validate_guidance, render_guidance


def transfer_guidance(response, reasoning, status, target):
    if response is None:
        return [], [], [], '', []
    if response.analysis_id != reasoning.analysis_id:
        return [], [], [], '', ['Documentary guidance omitted: analysis_id mismatch.']
    checks = deepcopy(getattr(response, 'diagnostic_checks', []))
    options = deepcopy(getattr(response, 'documented_solutions', []))
    documents = deepcopy(getattr(response, 'documentation', []))
    error = validate_guidance(checks, options, documents)
    if error:
        return [], [], [], '', ['Documentary guidance omitted: ' + error]
    links = {h.hypothesis_id: set(h.supporting_kb_entries) for h in reasoning.ranked_hypotheses}
    for item in checks + options:
        if any(item.entry_id not in links.get(hid, set()) for hid in item.hypothesis_ids):
            return [], [], [], '', ['Documentary guidance omitted: hypothesis provenance mismatch.']
    allowed_entries = set().union(*links.values()) if links else set()
    if any(d.entry_id not in allowed_entries for d in documents):
        return [], [], [], '', ['Documentary guidance omitted: unlinked documentation.']
    location = ('module ' + target.module_id) if target and target.module_id else None
    display_status = reasoning.reasoning_status if reasoning.reasoning_status in ('INSUFFICIENT_EVIDENCE', 'CONTRADICTED') else status
    text = render_guidance(checks, options, documents, display_status, location)
    return checks, options, documents, text, []
