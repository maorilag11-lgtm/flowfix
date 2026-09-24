"""Additive documentary contracts. These records never authorize a correction."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DocumentationReference:
    documentation_id: str = ''
    entry_id: str = ''
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    source_type: Optional[str] = None
    claims: list[str] = field(default_factory=list)
    provenance_paths: list[str] = field(default_factory=list)
    verification_status: Optional[str] = None
    last_verified: Optional[str] = None
    needs_reverification: Optional[bool] = None
    scope: str = 'KB_ENTRY'


@dataclass
class DiagnosticCheck:
    check_id: str = ''
    entry_id: str = ''
    description: str = ''
    source_path: str = ''
    hypothesis_ids: list[str] = field(default_factory=list)
    documentation_ids: list[str] = field(default_factory=list)
    entry_title: Optional[str] = None


@dataclass
class DocumentedSolution:
    solution_id: str = ''
    entry_id: str = ''
    solution: str = ''
    conditions: Optional[str] = None
    source_path: str = ''
    hypothesis_ids: list[str] = field(default_factory=list)
    documentation_ids: list[str] = field(default_factory=list)
    documentary_confidence: Optional[float] = None
    applicability: str = 'NOT_ASSESSED'
    missing_information: list[str] = field(default_factory=list)
    entry_title: Optional[str] = None
