# Conversational multi-source evidence

## User journey

1. Create a decision and enable sharing minimized context with OpenRouter. Start clarification or send an answer. Agent NORTH asks at most two questions per reply. Messages persist in the decision, including failed requests; retry uses the same request ID.
2. Review/correct the context summary and confirm it. Changing the summary invalidates downstream approval; source discussions do not silently change confirmed context.
3. Add multiple CSVs, internet pages and PostgreSQL sources in any combination. `Discuss with agent` scopes the same conversation to that source.
4. Select columns, map numeric inputs, specify their units, definitions, observation periods and geography/population, and review deterministic aggregates. Supported filters: equality and numeric lower/upper bounds. Supported aggregation: mean, sum, min, max, last (source row order).
5. Approve each included source version. Excluded sources remain in the workspace but cannot contribute to the model. Changes invalidate model/evidence approval and preserve previous run snapshots.
6. Check combined readiness. Duplicate variable mappings are blockers, never silently averaged. If sources span different periods or populations, document alignment/lag assumptions. Distinct variables can have distinct units; the user reviews semantic comparability. This is explicit input reconciliation, not an automatic arbitrary table-join engine.
7. Optionally record estimates and their basis. They remain labeled assumptions. Approve and freeze the combined evidence snapshot, then ask the agent to propose a model. Source-backed inputs must cite exact source ID + mapped variable. Fixed source-backed values must match approved aggregates; adjusted values require explicit estimates.
8. Review the human-readable model and its advanced JSON. Model approval is separate from evidence approval. Simulations run only against the approved immutable snapshot.

## CSV

- Up to 20 sources per project, including multiple CSV files. Each CSV: UTF-8, max 2 MB, 20,000 rows and 50 unique headers.
- Raw source rows and column-name maps are encrypted using the local Fernet key in `.data/sources`. They are never included in provider prompts.
- Suspected identifier columns are blocked. Text cell values are not sent as samples. Before column selection, the agent sees only nonrestricted column schema/counts; after selection it can see the relevant numeric profiles and aggregates.
- Numeric missingness and invalid values are shown. Dates/categories may be selected for filtering but are not automatically treated as simulation outcomes. Multi-file row joins and automatic time-series calibration are not implemented.

## Tavily / internet

The POC uses **Tavily basic search**, five results maximum, without AI answer generation or raw-content retrieval from the search provider. Configure `TAVILY_API_KEY` on the API process or an encrypted key in Settings. No key means no automatic search; approved URL fetching remains available. Free-plan eligibility, remaining quota, and billing behavior belong to the Tavily account; the application does not promise unlimited free usage. Search calls require explicit consent and are not background autonomous searches.

Search results are discovery aids, never automatically approved evidence. Add a result's HTTPS URL and approve access. An unfamiliar source needs explicit uncertainty acknowledgment. The curated primary/industry-domain list is a routing hint, not certification of every statistic.

Only HTML/plain text pages up to 2 MB are supported. Redirects require adding the final URL explicitly. Non-HTTPS URLs, embedded credentials, suspicious query identifiers, private/reserved destinations and custom ports are rejected. Curated official hosts work through the environment egress proxy; other domains additionally require public DNS resolution. Network access settings may need domain-specific additions. This local control is not a substitute for a production outbound firewall.

Before any page text is sent to the agent, the user must select/review a contiguous excerpt without personal information. Unreviewed text is withheld. The agent can propose observations with exact supporting quotes; the backend checks the quote is present and the number appears in it. This lexical check does not establish the correctness of statistical interpretation, unit scaling, period or source methodology: those remain review obligations. Accepting extraction is separate from approving source quality.

## PostgreSQL

Configure a URI through Settings or `NORTH_POSTGRES_DSN`. It is never sent to the model. Use a role that is read-only at the database level; require TLS for remote connections. The app also executes every operation in a read-only transaction.

- Explicit schema-metadata consent, then per-source table scope approval.
- Agent sees approved catalog metadata, not credentials or raw identity rows.
- Identifier fields are available only inside COUNT/COUNT DISTINCT, enabling unique-customer counts without identity disclosure.
- One schema-qualified SELECT, max four tables, approved columns and a small builtin-function allowlist. No writes, locks, CTEs, subqueries, UNION, SELECT *, custom functions/types or multiple statements.
- Five-second statement timeout, one-second lock timeout, at most 1,000 output rows and 50 columns. Larger results must be aggregated/narrowed. Results pass the same privacy profiling and mapping review as CSVs.
- Connection changes require fresh source access/scope approval. Changing schema metadata externally requires adding a fresh source; it is not silently trusted.

## Privacy boundary

Outbound minimization and pattern-based redaction are defense in depth, **not comprehensive named-entity recognition or legal compliance certification**. Header heuristics and email/phone/identifier patterns can miss uncommon PII; text-based review and user consent remain required. No raw categorical samples are sent. Page text requires manual review. Do not include names, account identifiers or customer contact details in free-form chat. Sensitive roles and tiny groups require additional governance before production use.

The application remains single-user/local with SQLite application storage. It is not safe to expose publicly without authentication, tenant authorization, a robust outbound gateway and additional hardening. PostgreSQL here is a governed data-source connector; it does not migrate the application store to Postgres.

## API and implementation

- `backend/workspace.py`: messages/retry, context confirmation, source approvals, source tools, snapshots, connector settings.
- `backend/evidence.py`: legacy migration, deterministic profiles, selections, readiness and provenance.
- `backend/privacy.py`: outbound redaction and identifier-column rules.
- `backend/connectors.py`: Tavily search, bounded page retrieval, PostgreSQL metadata and SQL validation/execution.
- `web/app/Workspace.js`: conversation, context, multiple-source cards, mappings, query review and combined approval.

Core endpoints are `/api/projects/{id}/workspace`, `/messages`, `/context-confirmation`, `/sources/csv`, `/sources/internet`, `/sources/postgres`, `/sources/{sid}/selection`, `/sources/{sid}/approve`, `/evidence-review`, and `/evidence-snapshots`. Connector credentials are configured at `/api/connectors/postgres` and `/api/connectors/search`. GET connector/settings responses contain presence metadata only.

Older projects migrate lazily with stable IDs, preserving completed run artifacts. Legacy profiles without retained rows must be uploaded again for a new selection. Interrupted agent requests are recoverable; interrupted simulation jobs remain failed and must be resubmitted. Orchestration currently uses persisted explicit API stages and a bounded proposal-repair attempt; LangGraph/Deep Agents and a distributed job broker are still deferred.

## Verification

```sh
.venv/bin/python -m pytest -q
npm --prefix web run build
```

PostgreSQL integration tests require an explicitly disposable test database. Do not point these tests at a real customer database: they create/truncate `public.north_test_customers` and create a `north_readonly` fixture role.

```sh
NORTH_TEST_POSTGRES_DSN=postgresql://postgres@127.0.0.1:15432/postgres .venv/bin/python -m pytest -q
```

Unit tests remove injected provider bindings and use an isolated temporary application database; they do not consume real provider credits. Live browser validation uses clearly labeled synthetic decisions, never fabricated real-market evidence.
