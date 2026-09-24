"""
FlowFix — Step 3 Retrieval — KB Loader

Loads the Knowledge Base from disk as a read-only collection of entries.

Rules:
- NEVER write, update, delete, or append to KB files.
- Cache entries in memory after first load (immutable reference).
- Expose the path to the KB directory so tests can verify isolation.
- needs_reverification is surfaced but NEVER modified.
"""

from __future__ import annotations
import json
import copy
import os
from dataclasses import dataclass, field
from typing import Optional
from functools import lru_cache

# Absolute path to the KB directory (two levels up from this file's package)
_KB_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "kb")
)

# Files that are metadata, not entry collections
_META_FILES = {"knowledge_index.json", "coverage_matrix.json"}


@dataclass(frozen=True)
class KBEntry:
    """
    Frozen top-level representation of a single KB entry.
    Fields match the KB schema v1.3.1.
    Nested public dicts are preserved; load_kb returns defensive deep copies.
    """
    id: str
    title: str
    problem: str = ""
    error_messages: tuple = field(default_factory=tuple)
    error_codes: tuple = field(default_factory=tuple)
    category: str = ""
    layer: str = ""
    origin: str = ""
    surface: str = ""
    severity: str = ""
    symptoms: tuple = field(default_factory=tuple)
    likely_causes: tuple = field(default_factory=tuple)
    diagnosis_steps: tuple = field(default_factory=tuple)
    solutions: tuple = field(default_factory=tuple)
    prevention: tuple = field(default_factory=tuple)
    make_context: dict = field(default_factory=dict)
    related_errors: tuple = field(default_factory=tuple)
    search_keywords: tuple = field(default_factory=tuple)
    confidence: float = 0.0
    quality_score: float = 0.0
    verification_status: str = ""
    needs_reverification: bool = False
    diagnostic_signals: tuple = field(default_factory=tuple)
    # Raw dict preserved for fields not individually mapped
    _raw: dict = field(default_factory=dict, compare=False, hash=False)


def _entry_from_dict(d: dict) -> Optional[KBEntry]:
    """Convert a raw KB dict to a KBEntry. Returns None on error."""
    if not isinstance(d, dict):
        return None
    array_fields = ("error_messages", "error_codes", "symptoms", "likely_causes", "diagnosis_steps", "solutions", "prevention", "related_errors", "search_keywords", "diagnostic_signals")
    if any(k in d and d[k] is not None and not isinstance(d[k], list) for k in array_fields):
        return None
    if "make_context" in d and not isinstance(d["make_context"], dict):
        return None
    entry_id = d.get("id")
    if not entry_id:
        return None
    try:
        return KBEntry(
            id=str(entry_id),
            title=str(d.get("title", "")),
            problem=str(d.get("problem", "")),
            error_messages=tuple(d.get("error_messages") or []),
            error_codes=tuple(str(c) for c in (d.get("error_codes") or [])),
            category=str(d.get("category", "")),
            layer=str(d.get("layer", "")),
            origin=str(d.get("origin", "")),
            surface=str(d.get("surface", "")),
            severity=str(d.get("severity", "")),
            symptoms=tuple(d.get("symptoms") or []),
            likely_causes=tuple(d.get("likely_causes") or []),
            diagnosis_steps=tuple(d.get("diagnosis_steps") or []),
            solutions=tuple(d.get("solutions") or []),
            prevention=tuple(d.get("prevention") or []),
            make_context=dict(d.get("make_context") or {}),
            related_errors=tuple(d.get("related_errors") or []),
            search_keywords=tuple(d.get("search_keywords") or []),
            confidence=float(d.get("confidence") or 0.0),
            quality_score=float(d.get("quality_score") or 0.0),
            verification_status=str(d.get("verification_status", "")),
            needs_reverification=bool(d.get("needs_reverification", False)),
            diagnostic_signals=tuple(d.get("diagnostic_signals") or []),
            _raw=d,
        )
    except Exception:
        return None


@lru_cache(maxsize=1)
def _load_cached() -> tuple[KBEntry, ...]:
    """
    Load all KB entries from disk. Cached after first call (read-only).
    Returns a tuple of KBEntry objects sorted by id for determinism.
    """
    entries: list[KBEntry] = []
    if not os.path.isdir(_KB_DIR):
        raise KBIntegrityError("KB directory unavailable")

    for root, _dirs, files in os.walk(_KB_DIR):
        for filename in sorted(files):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(root, filename)
            try:
                with open(filepath, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError, RecursionError) as exc:
                raise KBIntegrityError("Unreadable or invalid KB collection: " + filename) from exc

            if filename in _META_FILES:
                if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
                    raise KBIntegrityError("Invalid KB metadata: " + filename)
                continue
            if not isinstance(data, list):
                raise KBIntegrityError("Invalid KB collection: " + filename)
            if isinstance(data, list):
                for item in data:
                    entry = _entry_from_dict(item)
                    if entry is None:
                        raise KBIntegrityError("Invalid KB entry: " + filename)
                    entries.append(entry)

    if not entries or len({e.id for e in entries}) != len(entries):
        raise KBIntegrityError("KB empty or duplicate entry IDs")
    # Sort by id for deterministic ordering
    entries.sort(key=lambda e: e.id)
    return tuple(entries)


def kb_dir() -> str:
    """Return the absolute path to the KB directory (for isolation tests)."""
    return _KB_DIR


class KBIntegrityError(RuntimeError):
    """KB unavailable/corrupt, distinct from successful retrieval with no matches."""


def load_kb() -> tuple[KBEntry, ...]:
    """Return defensive deep copies; callers cannot change the shared cache."""
    return copy.deepcopy(_load_cached())

load_kb.cache_clear = _load_cached.cache_clear
load_kb.cache_info = _load_cached.cache_info
