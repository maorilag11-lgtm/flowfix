# FlowFix interface languages

English (`en`) is the default for new and existing accounts after migration 0008. French (`fr`) is available in Settings → Language → Save language. The authenticated account is authoritative across sessions; the session remembers the selected locale for anonymous screens. Changing language reloads the page to avoid mixing localized JavaScript with another account locale.

The reviewed French-to-English catalog is `saas/locales/en.tsv`. Each line contains the exact source text, a tab, and its English translation. Keep leading and trailing spaces for concatenated labels. Never add technical field names, selectors, enum codes or user text as translation targets.

The template loader translates source text before rendering user variables. JavaScript assets translate complete source string literals; DOM hooks, CSS, SVGs and animation code remain unchanged. Django validation messages use the active request locale. Response error/status messages are localized, without recursively rewriting user data. The panel translates only the editorial fields of diagnostic first readings and assessments; raw error messages, Blueprints, observations, user titles and saved evidence keep their original language. No translation service receives project or user data.

Stripe Checkout receives the account locale. French and English share the same subscription identifiers, quotas and access rules. The source catalog is included by the private-release packager. Run database migrations before serving the new version.

Verification: authenticated language changes, persistence across sessions, unsupported languages, CSRF, account isolation, source-hook preservation, English/French page rendering. Browser checks include switching both ways and viewing an existing HTTP 422 diagnostic in English.

Validation completed: 126 SaaS tests pass; all five localized JavaScript assets parse; formatter checks preserve original input and evidence. The English main panel was visually checked at 1280×720 after its animations. Saved names and error excerpts intentionally remain in the language entered by the user.
