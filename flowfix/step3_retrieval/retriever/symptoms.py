"""Bounded editorial symptom patterns: retrieval hints, never diagnosis evidence.

Each alternative requires every concept group in a single supplied text field.
No regex from the KB is executed. Invalid/oversized patterns fail closed.
"""
import re
import unicodedata


def normalize(text):
    text = unicodedata.normalize('NFKD', text.casefold())
    return ' '.join(re.findall(r'[^\W_]+', ''.join(c for c in text if not unicodedata.combining(c)), re.UNICODE))


def _phrases(values):
    return (isinstance(values, list) and 0 < len(values) <= 16
            and all(isinstance(v, str) and 0 < len(v) <= 160 and normalize(v) for v in values))


def match_pattern(raw, texts):
    patterns = raw.get('retrieval_patterns', [])
    if not isinstance(patterns, list) or len(patterns) > 8:
        return None
    for i, pattern in enumerate(patterns):
        if not isinstance(pattern, dict) or set(pattern) != {'all_groups', 'exclude'}:
            continue
        groups, exclude = pattern['all_groups'], pattern['exclude']
        if not (isinstance(groups, list) and 2 <= len(groups) <= 6
                and all(_phrases(g) for g in groups)
                and isinstance(exclude, list) and len(exclude) <= 16
                and (not exclude or _phrases(exclude))):
            continue
        for source, text in texts:
            if not isinstance(text, str) or len(text) > 20000 or '[REDACTED:' in text:
                continue
            normalized = ' ' + normalize(text) + ' '
            contains = lambda phrase: ' ' + normalize(phrase) + ' ' in normalized
            if any(contains(x) for x in exclude):
                continue
            if all(any(contains(phrase) for phrase in group) for group in groups):
                return f'retrieval_patterns[{i}] in {source} (editorial symptom candidate)'
    return None
