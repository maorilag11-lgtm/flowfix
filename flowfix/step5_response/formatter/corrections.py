"""Presentation only: retain the narrow scope and source declarations of S4."""
from __future__ import annotations
from flowfix.step1_intake.intake.field_contracts import pointer
from .guidance import _md


def render_corrections(proposals):
    lines = []
    for p in proposals:
        lines.extend(['## Proposed manual JSON syntax correction', '',
            'Module ' + _md(p.module_id) + '; observed field: ' + _md(pointer(p.field_path)), '',
            'This path comes from the supplied blueprint and field contract. It is not a verified Make UI label.', '',
            '### Observed value', '', '\n'.join('    ' + line for line in p.observed_value.split('\n')), '',
            '### Proposed value', '', '\n'.join('    ' + line for line in p.proposed_value.split('\n')), '',
            'The blocks show the actual field text. Only the identified comma is removed; no field, value or mapping is added.', '',
            '### Why this proposal applies to the supplied contract', ''])
        lines.extend('- ' + _md(s) for s in p.preconditions)
        lines.extend(['', '### Manual change', '',
            'After confirming the field contract and unchanged observed value, remove the comma at zero-based character offset ' + str(p.removed_character_index) + ' in this field. FlowFix does not write to Make or the blueprint.', '',
            '### Validation and limits', '', _md(p.validation_instruction), '', _md(p.limitation), ''])
    return '\n'.join(lines)
