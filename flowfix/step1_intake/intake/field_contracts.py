"""Caller-supplied field observations, not a Make export schema.

The caller supplies the exact path and format requirement; neither is inferred.
Source labels record declarations, not independently authenticated evidence.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import hashlib
import json


@dataclass
class JsonFieldObservation:
    module_id: str = ''
    field_path: list[str] = field(default_factory=list)
    execution_value: str = ''
    expected_format: str = ''
    value_origin: str = ''
    format_source: str = ''
    error_kind: str = ''
    error_source: str = ''


def parse_observation(value):
    if not isinstance(value, dict):
        return None
    keys = {'module_id', 'field_path', 'execution_value', 'expected_format', 'value_origin', 'format_source', 'error_kind', 'error_source'}
    if set(value) != keys:
        return None
    path = value['field_path']
    if not isinstance(path, list) or not 2 <= len(path) <= 6 or path[0] not in ('mapper', 'parameters'):
        return None
    strings = [value[k] for k in keys - {'field_path'}] + path
    if any(not isinstance(s, str) or not s or len(s) > 10000 or '[REDACTED:' in s for s in strings):
        return None
    return JsonFieldObservation(**{**value, 'field_path':list(path)})


def observed_value(problem, observation):
    """Resolve an exact metadata path, never search for a similar field."""
    modules = [m for m in problem.blueprint.modules if m.id == observation.module_id]
    if len(modules) != 1:
        return None
    value = modules[0].metadata
    for segment in observation.field_path:
        if not isinstance(value, dict) or segment not in value:
            return None
        value = value[segment]
    return value


def observation_digest(problem, observation):
    from dataclasses import asdict
    data = {'problem':problem.to_dict(), 'observation':asdict(observation)}
    try:
        encoded = json.dumps(data,sort_keys=True,ensure_ascii=True,allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError):
        return None
    return hashlib.sha256(encoded).hexdigest()


def pointer(path):
    return '/' + '/'.join(s.replace('~','~0').replace('/','~1') for s in path)
