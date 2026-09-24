# KB V1.4.1 — recherche des symptômes et révisions ciblées

**Total entries:** 67

Trois fiches historiques révisées et deux fiches natives enrichies de motifs de recherche. Voir ../RAPPORT_RECHERCHE_MAKE.md. Les sections suivantes sont historiques et décrivent V1.4 puis V1.3.1.

---

# KB V1.4 — 2026-09-08

67 entrées : les 61 fiches V1.3.1 conservées et 6 diagnostics Make ajoutés dans make_core/native_diagnostics.json. Documentation vérifiée ; aucun nouveau cas réel résolu. Le contenu historique ci-dessous décrit V1.3.1, pas le total actuel. Voir ../RAPPORT_ENRICHISSEMENT_KB.md.

---

# Make Workflow Doctor — Knowledge Base

## Purpose

This knowledge base powers the AI diagnostic system of **Make Workflow Doctor**.

It enables the RAG (Retrieval-Augmented Generation) system to:
1. Identify the probable cause of a Make.com error
2. Determine which module or layer is responsible
3. Explain what the error means and why it occurs
4. Provide step-by-step diagnostic procedures
5. Offer concrete, verified solutions
6. Suggest preventive measures

---

## Core Principle

> **Quality > Coverage > Quantity**

A base of 250 well-verified entries is more useful than 2,000 invented ones.
Every entry must be grounded in a verifiable source. Hypotheses are clearly labeled with confidence scores below 0.80 and `partially_verified` or `needs_review` status.

---

## File Structure

```
knowledge/
│
├── make_core/              # Make.com core engine errors
│   ├── mapping.json        # Mapping, data types, JSON parsing
│   ├── iterators.json      # Iterator module errors
│   ├── aggregators.json    # Aggregator module errors
│   ├── filters.json        # Filter errors
│   ├── routers.json        # Router errors
│   ├── webhooks.json       # Webhook trigger errors
│   ├── error_handling.json # Error handlers, directives, error types
│   ├── scenarios.json      # Scenario-level errors (quota, cycles, timeouts)
│   ├── scheduling.json     # Scheduling errors
│   └── json.json           # JSON module specific errors
│
├── protocols/              # Cross-service protocol errors
│   ├── http.json           # HTTP status codes (400–503)
│   └── oauth.json          # OAuth2, API key, connection errors
│
├── applications/           # Application-specific errors (to build)
│   ├── gmail.json
│   ├── google_sheets.json
│   └── ...
│
├── real_world_cases/       # Real user-reported cases
│   └── cases.json
│
├── knowledge_index.json    # Fast lookup index (id, category, keywords, severity)
├── coverage_matrix.json    # Coverage tracking per domain
├── AUDIT_REPORT.md         # Quality audit report
└── README.md               # This file
```

---

## Entry Schema

Each entry follows this structure:

```json
{
  "id": "unique-slug",
  "title": "Human-readable title",
  "problem": "Clear description of what the problem is",
  "error_messages": ["Exact error message when documented"],
  "error_codes": ["422"],
  "category": "validation",
  "layer": "external_api",
  "origin": "external_service",
  "surface": "module",
  "severity": "high",
  "symptoms": ["Observable symptom 1"],
  "likely_causes": [{"cause": "...", "confidence": 0.90}],
  "diagnosis_steps": ["Step 1", "Step 2"],
  "solutions": [{"solution": "...", "conditions": "...", "confidence": 0.90}],
  "prevention": ["Preventive measure"],
  "make_context": {"apps": [], "modules": [], "features": []},
  "related_errors": ["related-id"],
  "search_keywords": ["keyword"],
  "origin_details": {
    "source_type": "official_documentation",
    "source_name": "Make Help Center",
    "source_url": "https://...",
    "evidence": "What this source specifically confirms for this entry"
  },
  "evidence": [
    {
      "claim": "Specific verifiable claim",
      "source_type": "official_documentation",
      "source_url": "https://...",
      "confidence": 0.90
    },
    {
      "claim": "Another claim, possibly inferred",
      "source_type": "inference",
      "source_url": null,
      "confidence": 0.70
    }
  ],
  "workflow_pattern": {
    "modules": ["Source module", "Action module"],
    "sequence": ["step 1", "step 2", "failure point"],
    "conditions": ["condition that triggers the problem"]
  },
  "diagnostic_signals": [
    "Observable signal 1 in Make UI or execution log",
    "[observed message variant] \"Plausible error text not confirmed verbatim\""
  ],
  "next_review": "YYYY-MM-DD",
  "confidence": 0.90,
  "verification_status": "partially_verified",
  "quality_score": 0.85,
  "last_verified": "2025-08-01",
  "needs_reverification": false,
  "audit_notes": "Notes on verification status and limitations"
}
```

---

## Taxonomy

### Layer
Where the problem actually occurs:
- `make_core` — Make's execution engine
- `make_module` — A specific Make module
- `external_api` — External API response
- `user_configuration` — User mapping/config error
- `data` — Problem in the data itself
- `network` — Network-level failure
- `unknown`

### Origin
Root cause:
- `make` — Make platform issue
- `external_service` — External service rejection
- `user` — User configuration mistake
- `network` — Network failure
- `data` — Data quality issue
- `unknown`

### Surface
Where the error appears:
`connection` | `module` | `scenario` | `mapping` | `webhook` | `execution` | `filter` | `iterator` | `aggregator` | `router` | `scheduler` | `api` | `unknown`

### Verification Status
- `verified` — Confirmed by official documentation with specific evidence
- `partially_verified` — Core behavior documented, some details inferred or community-reported
- `community_reported` — Reported by users but not confirmed by official documentation
- `needs_review` — Insufficient confidence, requires manual verification

### error_messages policy

`error_messages` contains **only verbatim-confirmed messages** — text that appears exactly as documented in Make Help Center or an official API specification (e.g., OAuth2 RFC error codes like `invalid_grant`).

Messages that are plausible but not confirmed verbatim are stored in `diagnostic_signals` with the prefix `[observed message variant]`. This prevents the RAG system from presenting unconfirmed text as canonical Make error messages.

If `error_messages` is empty `[]`, use `error_codes` and `diagnostic_signals` for matching instead.

## Quality Score
- `0.90+` — Excellent, well-grounded in official docs
- `0.80–0.89` — Good, mostly verified
- `0.70–0.79` — Acceptable, some uncertainty
- `< 0.70` — Requires review before production use

---

## Sources Priority

1. **Make Help Center** — highest priority
2. **Make official documentation**
3. **Official application/API documentation**
4. **Make Community** — for real-world cases, clearly labeled `community_reported`
5. **Technical inference from known Make behavior** — lowest, clearly labeled

---

## Current Coverage (v0.2)

| Domain | Progress | Priority |
|--------|----------|----------|
| HTTP | 60% (9/15) | Critical |
| Authentication | 40% (4/10) | Critical |
| Mapping | 25% (3/12) | Critical |
| Webhooks | 40% (4/10) | Critical |
| Error Handling | 50% (5/10) | High |
| Iterators | 17% (1/6) | High |
| Aggregators | 20% (1/5) | High |
| Filters | 17% (1/6) | High |
| Routers | 40% (2/5) | High |
| JSON | 33% (2/6) | High |
| Scenarios | 50% (4/8) | High |
| Scheduling | 40% (2/5) | Medium |
| Applications | 0% | High |
| Real World Cases | 0% | High |

**Total: 38 entries** — Target V1: 150–200 entries

---

## Next Priorities

1. **Mapping** — expand to cover all mapping error types (currently 3/12)
2. **Iterators** — expand (currently 1/6)
3. **Filters** — expand (currently 1/6)
4. **Gmail** — start application layer (0/10)
5. **Google Sheets** — start (0/10)
6. **Real World Cases** — begin collecting (0/20)

---

## Version History

| Version | Date | Entries | Notes |
|---------|------|---------|-------|
| v0.1 | 2025-08-01 | 23 | Initial dataset — Make Core, HTTP, Auth |
| v0.2 | 2025-08-01 | 38 | Phase 2/3 — new schema, webhooks, error handling, routers, scheduling, JSON |
| v1.2 | 2026-09-02 | 42 | Phase 4 — evidence[], workflow_pattern, diagnostic_signals, next_review, webhook rewrite |
| v1.3 | 2026-09-02 | 60+ | Phase 5 — error_messages cleaned, mapping+filters expanded, Gmail+Google Sheets started |
