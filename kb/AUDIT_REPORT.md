# KB V1.4.1 — recherche des symptômes et révisions ciblées

**Total entries:** 67

Trois fiches historiques révisées et deux fiches natives enrichies de motifs de recherche. Voir ../RAPPORT_RECHERCHE_MAKE.md. Les sections suivantes sont historiques et décrivent V1.4 puis V1.3.1.

---

**Total entries:** 67

# KB V1.4 — 2026-09-08

67 entrées : les 61 fiches V1.3.1 conservées et 6 diagnostics Make ajoutés dans make_core/native_diagnostics.json. Documentation vérifiée ; aucun nouveau cas réel résolu. Le contenu historique ci-dessous décrit V1.3.1, pas le total actuel. Voir ../RAPPORT_ENRICHISSEMENT_KB.md.

---

# AUDIT REPORT — Make Workflow Doctor Knowledge Base
## Version 1.3 — Synchronized with actual KB state

**Generated:** 2026-09-02  
**Total entries:** 61  
**Validation:** `python3 validate.py` → EXIT 0, 0 errors, 0 warnings

---

## Statistics

| Metric | Value |
|--------|-------|
| Total entries | 61 |
| `verified` | 0 |
| `partially_verified` | 60 |
| `community_reported` | 1 |
| `needs_review` | 0 |
| Average quality score | 0.822 |
| Entries quality ≥ 0.85 | 17 |
| Entries quality 0.80–0.84 | 32 |
| Entries quality < 0.80 | 12 |
| needs_reverification = true | 0 |

**Note on verification status:** 0 entries are `verified`. This is intentional — `verified` requires pinpoint official documentation confirming every significant claim verbatim. Most entries are grounded in official documentation for core behavior with some details inferred from Make's execution model or community reports. The RAG system should present `partially_verified` entries with appropriate epistemic caution.

---

## Coverage by Domain

| Domain | Current | Target | % | Coverage | Priority |
|--------|---------|--------|---|----------|----------|
| HTTP | 9 | 15 | 60% | substantial | critical |
| Authentication | 4 | 10 | 40% | partial | critical |
| Mapping | 10 | 12 | 83% | substantial | critical |
| Webhooks | 6 | 10 | 60% | substantial | critical |
| Error Handling | 5 | 10 | 50% | partial | high |
| Iterators | 2 | 6 | 33% | partial | high |
| Aggregators | 2 | 5 | 40% | partial | high |
| Filters | 5 | 6 | 83% | substantial | high |
| Routers | 2 | 5 | 40% | partial | high |
| JSON | 2 | 6 | 33% | partial | high |
| Scenarios | 4 | 8 | 50% | partial | high |
| Scheduling | 2 | 5 | 40% | partial | medium |
| Gmail | 4 | 10 | 40% | partial | high |
| Google Sheets | 4 | 10 | 40% | partial | high |
| Google Drive | 0 | 6 | 0% | not_started | medium |
| HubSpot | 0 | 8 | 0% | not_started | high |
| Slack | 0 | 6 | 0% | not_started | medium |
| Notion | 0 | 6 | 0% | not_started | medium |
| Airtable | 0 | 6 | 0% | not_started | medium |
| OpenAI | 0 | 6 | 0% | not_started | medium |
| Shopify | 0 | 6 | 0% | not_started | medium |
| Real World Cases | 0 | 20 | 0% | not_started | high |

**Target note:** `target_entries` is an internal coverage goal, not a canonical count of all possible errors in the domain.

---

## Entry count by file

| File | Entries |
|------|---------|
| applications/gmail.json | 4 |
| applications/google_sheets.json | 4 |
| make_core/aggregators.json | 2 |
| make_core/error_handling.json | 5 |
| make_core/filters.json | 5 |
| make_core/iterators.json | 2 |
| make_core/json.json | 2 |
| make_core/mapping.json | 10 |
| make_core/routers.json | 2 |
| make_core/scenarios.json | 4 |
| make_core/scheduling.json | 2 |
| make_core/webhooks.json | 6 |
| protocols/http.json | 9 |
| protocols/oauth.json | 4 |

---

## Lowest quality entries (monitoring list)

Entries with `quality_score < 0.80` require priority review before expanding their claims:

| Entry | Quality | Issue |
|-------|---------|-------|
| `make-core-scenario-cycle-detected` | 0.70 | The infinite loop pattern is widely reported in Make community and is a logical  |
| `json-create-invalid-structure` | 0.74 | JSON module existence confirmed in Make documentation |
| `http-413-payload-too-large` | 0.76 | HTTP 413 semantics are standard (RFC 7231) |
| `gmail-attachment-size-limit` | 0.78 | Gmail 25 MB limit is documented in Gmail API documentation |
| `gsheets-required-field-empty` | 0.78 | Google Sheets module documented in Make |
| `gsheets-search-rows-returns-0` | 0.78 | Search Rows module documented in Make |
| `make-core-operation-timeout` | 0.78 | Make does enforce per-operation timeouts (documented), and ETIMEDOUT is commonly |
| `webhook-inactive-410` | 0.78 | 410 for inactive webhooks is documented in Make Help Center |
| `http-400-bad-request` | 0.78 | HTTP 400 is a standard HTTP status code well-defined in RFC 7231 |
| `http-500-internal-server-error` | 0.78 | HTTP 500 semantics are standard (RFC 7231) |
| `auth-insufficient-scope` | 0.78 | OAuth2 scope management by Make connections is documented |
| `error-handler-not-triggering` | 0.79 | Error handler directives confirmed in Make documentation |

---

## error_messages policy

`error_messages` contains **only verbatim-confirmed messages** — text that appears exactly as documented in Make Help Center or an official specification (e.g., OAuth2 RFC error codes).

**Currently confirmed messages (7 total across 5 entries):**
- `DataError`, `ConnectionError` — Make error type names (Make Help Center)
- `ECONNREFUSED`, `ENOTFOUND`, `ETIMEDOUT` — Node.js network error codes
- `invalid_grant` — OAuth2 RFC 6749
- `insufficient_scope` — OAuth2 RFC 6750

Unconfirmed formulations are stored in `diagnostic_signals` with the `[observed message variant]` prefix. This prevents the RAG system from presenting plausible-but-unconfirmed text as canonical Make error messages.

---

## Schema fields (all 61 entries)

| Field | Present on all entries | Notes |
|-------|----------------------|-------|
| `evidence[]` | ✅ | Array of claim-level proofs with individual confidence scores |
| `workflow_pattern` | ✅ | Module sequence, conditions, failure point |
| `diagnostic_signals` | ✅ | Observable signals for RAG matching |
| `next_review` | ✅ | Date-based reverification trigger |
| `needs_reverification` | ✅ | Calculated from `next_review` vs today by validator |
| `last_verified` | ✅ | All set to 2026-09-02 |

---

## Reverification policy

| Domain type | Policy | Files |
|-------------|--------|-------|
| Make core (mapping, error handling, etc.) | 180 days | `make_core/*` |
| HTTP, OAuth | 90 days | `protocols/*` |
| Webhooks | 90 days | `make_core/webhooks.json` |
| Applications (Gmail, Sheets, etc.) | 90 days | `applications/*` |

Next scheduled reviews:
- `protocols/`, `applications/`, `make_core/webhooks.json` → 2026-12-01
- `make_core/*` (excluding webhooks) → 2027-03-01

---

## Package integrity

The knowledge base is validated by `validate.py` (exit 1 on any failure).

**Checks performed:**
1. All files referenced in `knowledge_index.json` and `coverage_matrix.json` exist on disk
2. No orphan JSON files (every file is referenced)
3. All JSON files parse without error
4. All entries pass schema validation (required fields, enum values, numeric ranges)
5. All entries appear in `knowledge_index.json`
6. `coverage_matrix.json` counts match actual file lengths
7. `needs_reverification` correctly reflects `next_review` vs today (added in v1.3)
8. `AUDIT_REPORT.md` entry count matches actual total (added in v1.3)

Run: `python3 validate.py`

---

## Changelog

| Version | Date | Entries | Changes |
|---------|------|---------|---------|
| v0.1 | 2025-08-01 | 23 | Initial — Make Core, HTTP, Auth |
| v0.2 | 2025-08-01 | 38 | New schema: layer/origin/surface, webhooks, error handling, routers, scheduling, JSON |
| v1.2 | 2026-09-02 | 42 | evidence[], workflow_pattern, diagnostic_signals, next_review, webhook rewrite |
| v1.3 | 2026-09-02 | 61 | error_messages cleaned (87 removed), mapping 3→10, filters 1→5, Gmail 0→4, Google Sheets 0→4, AUDIT_REPORT synchronized |

---

## What the RAG system can trust

**High confidence — use directly:**
- Make function names: `ifempty()`, `get()`, `formatDate()`, `parseDate()`, `parseNumber()`, `lower()`, `parseJSON()`, `trim()`
- Error handler directives: Break, Resume, Rollback, Ignore, Commit
- Aggregator "Stop processing after empty aggregation" option
- Iterator: 1-based array indexing, "Run once to discover structure"
- Router: top-to-bottom evaluation, first match wins, fallback route
- Webhook HTTP status codes returned by Make: 400 (queue full), 429 (rate limit), 410 (inactive)
- OAuth2 error codes: `invalid_grant`, `insufficient_scope`
- Make data types: Array vs Collection distinction
- Connection management: Reauthorize flow

**Medium confidence — use with nuance:**
- Most `likely_causes` confidence scores 0.80–0.88
- Specific error message text — stored as `[observed message variant]` in `diagnostic_signals`, not in `error_messages`
- Application-specific behaviors (Gmail, Google Sheets) — confirm against current API docs

**Lower confidence — flag for user verification:**
- `make-core-scenario-cycle-detected` (0.70) — community-only, no specific URL
- Any numeric limits (file sizes, quota values, rate limits) — deliberately omitted to avoid stale data

---

## Next priorities

1. **Real World Cases** (0/20) — most impactful gap; requires Make Community research with specific URLs
2. **Gmail** (4→8) — high user volume; continue with documented errors only
3. **Google Sheets** (4→8) — continue with documented errors only
4. **Error Handling** (5/10) — add: RollbackError, CommitError, retry patterns
5. **Iterators** (2/6) — add: limit, position, slice patterns

*Report generated: 2026-09-02*  
*Next audit: after 20+ new entries or 2027-01-01*
