"""Preserve documentary guidance already retrieved by S3 and linked by S4.

No disk access, retrieval, condition evaluation or diagnosis. References concern
an entry, not a verified proof of each individual solution. URLs are never read.
"""
from __future__ import annotations
import hashlib
import re
from flowfix.step1_intake.redaction.redactor import redact
from flowfix.step5_response.models_internal.guidance import (
    DocumentationReference, DiagnosticCheck, DocumentedSolution,
)


def _id(kind, entry_id, path):
    return kind + '_' + hashlib.sha256((entry_id + '|' + path).encode()).hexdigest()[:20]


def _text(value):
    if not isinstance(value, str) or not value.strip() or '[REDACTED:' in value:
        return None
    cleaned = redact(value)
    return value if not cleaned.redactions else None


def _url(value):
    value = _text(value)
    # Only unchanged literal HTTP(S) references. No userinfo, controls, or
    # Markdown delimiters; no repairing, upgrading schemes or synthesizing URLs.
    if not value or not re.fullmatch(r'https?://[A-Za-z0-9.-]+(?::[0-9]+)?(?:[/#?][^\s<>"\x27()\\]*)?', value):
        return None
    return value


def _documents(entry, warnings):
    raw = entry._raw if isinstance(entry._raw, dict) else {}
    refs = []
    origin = raw.get('origin_details')
    if isinstance(origin, dict):
        refs.append(('origin_details', origin))
    evidence = raw.get('evidence')
    if isinstance(evidence, list):
        refs.extend((f'evidence[{i}]', item) for i, item in enumerate(evidence) if isinstance(item, dict))
    documents = []
    by_key = {}
    for path, ref in refs:
        url = _url(ref.get('source_url'))
        name = _text(ref.get('source_name'))
        kind = _text(ref.get('source_type'))
        if ref.get('source_url') and url is None:
            warnings.append('A documentary URL was omitted because it is unsafe or unsupported.')
        claim = _text(ref.get('claim') or ref.get('evidence'))
        if any(ref.get(key) and _text(ref.get(key)) is None for key in ('source_name', 'source_type', 'claim', 'evidence')):
            warnings.append('Sensitive or unsupported documentary metadata was omitted.')
        if not any((url, name, claim)):
            continue
        # Share an identical URL only inside this entry. Without a URL keep
        # separate records: a matching label alone does not identify a source.
        key = url if url else path
        document = by_key.get(key)
        if document is None:
            document = DocumentationReference(
                documentation_id=_id('DOC', entry.id, key), entry_id=entry.id,
                source_name=name, source_url=url, source_type=kind,
                verification_status=_text(raw.get('verification_status')),
                last_verified=_text(raw.get('last_verified')),
                needs_reverification=raw.get('needs_reverification') if isinstance(raw.get('needs_reverification'), bool) else None,
            )
            documents.append(document)
            by_key[key] = document
        if document.source_name is None:
            document.source_name = name
        if claim and claim not in document.claims:
            document.claims.append(claim)
        document.provenance_paths.append(path)
    return documents


def build_guidance(retrieval, reasoning):
    """Return checks, options, references and omissions, in S4 reference order."""
    warnings = []
    if retrieval.analysis_id != reasoning.analysis_id:
        return [], [], [], ['Documentary guidance omitted: analysis_id mismatch.']
    links = {}
    for hyp in reasoning.ranked_hypotheses:
        for entry_id in hyp.supporting_kb_entries:
            ids = links.setdefault(entry_id, [])
            if hyp.hypothesis_id not in ids:
                ids.append(hyp.hypothesis_id)
    entries = {m.entry_id: m.entry for m in retrieval.matches if m.entry is not None and m.entry_id == m.entry.id}
    checks, options, documents = [], [], []
    for entry_id, hypothesis_ids in links.items():
        entry = entries.get(entry_id)
        if entry is None:
            continue
        # Opaque identifiers are only carried as references, never classifications.
        if _text(entry_id) is None or any(_text(h) is None for h in hypothesis_ids):
            warnings.append('Unsafe documentary reference omitted.')
            continue
        docs = _documents(entry, warnings)
        documents.extend(docs)
        doc_ids = [d.documentation_id for d in docs]
        for i, value in enumerate(entry.diagnosis_steps):
            description = _text(value)
            if description is None:
                warnings.append('An unsupported or sensitive documented check was omitted.')
                continue
            path = f'diagnosis_steps[{i}]'
            checks.append(DiagnosticCheck(_id('CHECK', entry_id, path), entry_id,
                description, path, list(hypothesis_ids), list(doc_ids), entry_title=_text(entry.title)))
        for i, value in enumerate(entry.solutions):
            if isinstance(value, dict):
                solution = _text(value.get('solution'))
                condition = _text(value.get('conditions'))
                confidence = value.get('confidence')
                # Do not weaken a condition by dropping it while retaining advice.
                if value.get('conditions') and condition is None:
                    warnings.append('A documented option with an unsupported or sensitive condition was omitted.')
                    continue
            elif isinstance(value, str):
                solution, condition, confidence = _text(value), None, None
            else:
                solution = None
            if solution is None:
                warnings.append('An unsupported or sensitive documented option was omitted.')
                continue
            if type(confidence) not in (int, float) or not 0 <= confidence <= 1:
                confidence = None
            path = f'solutions[{i}]'
            missing = ['Evidence that the documented condition holds in this case.' if condition else
                       'The applicability conditions are not supplied by the document.']
            missing.append('The exact observed field, justified target value and effects of a manual change.')
            options.append(DocumentedSolution(_id('SOLUTION', entry_id, path), entry_id,
                solution, condition, path, list(hypothesis_ids), list(doc_ids), confidence,
                'NOT_ASSESSED', missing, entry_title=_text(entry.title)))
    return checks, options, documents, list(dict.fromkeys(warnings))


def _md(value):
    """Render untrusted document text as text, never HTML or active Markdown."""
    value = str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return re.sub(r'([\\`*_{}\[\]()#+.!|~-])', r'\\\1', value).replace('\n', ' ')


def render_guidance(checks, options, documents, status, location=None):
    if not checks and not options and not documents:
        return ''
    blocked = status in ('BLOCKED', 'NOT_APPLICABLE', 'INSUFFICIENT_EVIDENCE', 'CONTRADICTED')
    lines = ['## Manual guidance', '',
        'Reference only: the current evidence does not support applying a correction.' if blocked else
        'These are documented checks and conditional options. Their applicability to this case has not been established.', '']
    if location:
        lines.extend(['Location: ' + _md(location), ''])
    if checks:
        lines.extend(['### What to check', '',
            'Assess each documented check against the existing failed execution. Some checks may send requests or change configuration; confirm their effects before following them.', ''])
        previous_entry = None
        for i, check in enumerate(checks, 1):
            if check.entry_id != previous_entry:
                lines.extend(['', '**' + _md(check.entry_title or 'Documented candidate') + '**', ''])
                previous_entry = check.entry_id
            lines.append(f'{i}. ' + _md(check.description))
    if options:
        lines.extend(['', '### Conditional documented options', '',
            'A documentary confidence value describes the source material; it is not confidence that this option will fix this case.', ''])
        previous_entry = None
        for i, option in enumerate(options, 1):
            if option.entry_id != previous_entry:
                lines.extend(['#### ' + _md(option.entry_title or 'Documented candidate'), ''])
                previous_entry = option.entry_id
            lines.extend([f'**Option {i}**', '',
                '**Conditions to verify:** ' + (_md(option.conditions) if option.conditions else 'Not supplied; establish applicability first.'), '',
                '**Documented solution, only if applicable:** ' + _md(option.solution), '',
                '**Missing before a concrete change:** ' + ' '.join(_md(x) for x in option.missing_information), ''])
            if option.documentary_confidence is not None:
                lines.append('Stored documentary confidence: ' + str(option.documentary_confidence) + '; applicability to this case: not assessed.\n')
            labels = [str(j) for j, d in enumerate(documents, 1) if d.documentation_id in option.documentation_ids]
            lines.append('Entry documentation: ' + (', '.join(labels) if labels else 'No source reference supplied.') + '\n')
    if documents:
        lines.extend(['### Documentation', '', 'Verification metadata below is stored in the KB and has not been checked online. References describe the KB entry, not individual proof of every option.', ''])
        for i, document in enumerate(documents, 1):
            label = _md(document.source_name or 'Source reference')
            if document.source_url:
                label = '[' + label + '](<' + document.source_url + '>)'
            lines.append(f'{i}. {label}')
            lines.append('   Stored verification: ' + _md(document.verification_status or 'Not supplied') +
                         '; last verified: ' + _md(document.last_verified or 'Not supplied') + '.')
            if document.needs_reverification:
                lines.append('   Reverification required according to the stored metadata.')
    lines.extend(['', '### How to validate', '',
        'Record the relevant anonymized observation and its source. Compare it with the stated condition; if it is absent, contradicted or uncertain, keep the option unconfirmed. A concrete change also requires an observed target and an effect-specific validation criterion.', '',
        'No scenario rerun is required by this guidance. FlowFix performs no modification or execution.'])
    return '\n'.join(lines)


def validate_guidance(checks, options, documents):
    """Validate additive records without deciding if any condition is true."""
    if not all(isinstance(items, list) for items in (checks, options, documents)):
        return 'Guidance collections must be lists.'
    if not all(isinstance(x, DiagnosticCheck) for x in checks) or not all(isinstance(x, DocumentedSolution) for x in options) or not all(isinstance(x, DocumentationReference) for x in documents):
        return 'Unsupported guidance record type.'
    doc_entries = {}
    for d in documents:
        if not _text(d.documentation_id) or not _text(d.entry_id) or d.documentation_id in doc_entries:
            return 'Invalid or duplicate documentary reference.'
        doc_entries[d.documentation_id] = d.entry_id
        if d.needs_reverification is not None and not isinstance(d.needs_reverification, bool):
            return 'Invalid documentary reverification flag.'
        if d.scope != 'KB_ENTRY' or (d.source_url is not None and _url(d.source_url) is None):
            return 'Unsupported documentary scope or unsafe URL.'
        for value in (d.source_name, d.source_type, d.verification_status, d.last_verified):
            if value is not None and _text(value) is None:
                return 'Unsafe documentary metadata.'
        if not isinstance(d.claims, list) or not isinstance(d.provenance_paths, list) or not d.provenance_paths:
            return 'Missing documentary provenance.'
        if any(_text(v) is None for v in d.claims + d.provenance_paths):
            return 'Unsafe documentary content.'
    ids = set()
    for item in checks + options:
        ident = item.check_id if isinstance(item, DiagnosticCheck) else item.solution_id
        if not _text(ident) or ident in ids or not _text(item.entry_id) or not _text(item.source_path):
            return 'Invalid or duplicate guidance reference.'
        ids.add(ident)
        if item.entry_title is not None and _text(item.entry_title) is None:
            return 'Unsafe entry title.'
        if not isinstance(item.hypothesis_ids, list) or not item.hypothesis_ids or any(_text(v) is None for v in item.hypothesis_ids):
            return 'Missing hypothesis provenance.'
        if not isinstance(item.documentation_ids, list) or any(_text(v) is None for v in item.documentation_ids) or any(doc_entries.get(v) != item.entry_id for v in item.documentation_ids):
            return 'Broken documentation reference.'
        if isinstance(item, DiagnosticCheck):
            if _text(item.description) is None:
                return 'Unsafe documented check.'
        else:
            if _text(item.solution) is None or (item.conditions is not None and _text(item.conditions) is None):
                return 'Unsafe documented option or condition.'
            if item.documentary_confidence is not None and (type(item.documentary_confidence) not in (float, int) or not 0 <= item.documentary_confidence <= 1):
                return 'Invalid documentary confidence.'
            if item.applicability != 'NOT_ASSESSED':
                return 'Documentary guidance cannot establish applicability.'
            if not isinstance(item.missing_information, list) or not item.missing_information or any(_text(v) is None for v in item.missing_information):
                return 'Missing applicability gaps.'
    return None
