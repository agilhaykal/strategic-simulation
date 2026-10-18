---
title: NORTH — Technical Implementation Blueprint
subtitle: From interactive HTML prototype to a secure, auditable strategy simulation SaaS
version: 1.0 (architecture baseline)
date: 2026-10-15
status: Proposed design — not yet implemented
---

# NORTH — Technical Implementation Blueprint

**Product:** NORTH / AI-powered Strategic Decision Intelligence  
**Audience:** CTO, Tech Lead, AI Engineer, Backend, Frontend, Data, DevOps, QA, Security  
**Baseline:** `strategy-simulation-prototype.html` (latest sidebar + blue glassmorphism design) and `HTMA_3rd_Ch6-2.xlsx` reference work  
**Status:** Engineering design proposal. All source code, infrastructure, permissions, and integrations described below must still be implemented and tested.

> **Core principle:** Deep Agents proposes and explains; validated deterministic services calculate. A language model must never invent simulation outcomes, silently self-approve data access, or execute an unvalidated mathematical expression.

## Executive architecture decisions

| Decision | Recommended choice | Why |
|---|---|---|
| Runtime boundary | Next.js UI → FastAPI application API → LangGraph/Deep Agents orchestration → simulation worker | Isolates UX, reasoning, and numeric execution |
| Product architecture | Modular monolith plus separate asynchronous worker, not day-one microservices | Lower operational overhead, explicit domains |
| Source of truth | PostgreSQL for domain data; object storage for files/results; Redis for queue/cache | Durable, auditable, cost-efficient |
| AI orchestration | LangGraph controlled state graph with Deep Agents specialist calls | Human approval and recoverable execution |
| Model representation | Versioned declarative `SimulationModel` JSON, strict schemas and expression DSL | Prevents arbitrary agent-generated code execution |
| Simulation execution | NumPy/SciPy deterministic worker with pinned versions, PRNG state, seed, input hash | Reproducibility and mathematical testing |
| Results | Percentiles, chance of target, tail risk, uncertainty of estimator, diagnostics | More useful than one forecast number |
| Enterprise security | Tenant-scoped authorization at every layer; read-only data gateways; BYOK encrypted | Protects sensitive strategic/company data |
| UX | Sidebar + centered hero + glass decision workspace | Retains approved prototype direction; technical details progressive disclosure |

## 1. Scope, assumptions, and non-goals

### 1.1 Outcome to build

A signed-in executive writes a strategic question, such as: “Can we increase EBITDA by 20% next year through pricing and operational efficiency?” NORTH transforms it into a reviewable decision model, obtains approved evidence, runs scenarios in a validated engine, and returns a concise, defensible decision brief. Executives can alter strategic levers, compare baseline versus proposed strategy, review KPI ranges and risk mitigation, approve decisions, and retrieve prior versions.

### 1.2 Prototype-to-production gap

Inspection of the supplied latest HTML confirms a functional presentation prototype with local JavaScript calculations and browser-based history. It is **not** an integrated SaaS: no real authentication, no backend API calls (`fetch` absent), no Deep Agents runtime, no configured database reads, no real web research, no secure BYOK, and no governed simulation job orchestration. Demo risk/KPI/tactic strings are illustrative, not evidence-backed conclusions. Treat all prototype-generated metrics as **synthetic demos** until replaced with validated service outputs. Frontend visual components can be reused after conversion into React/Next.js; calculation and permission logic must be replaced.

### 1.3 Delivery assumptions (confirm at kickoff)

- Web-based B2B multi-tenant product with **organization-scoped** data and RBAC.
- UI language may be English initially, but domain objects and prompts must support English/Indonesian text.
- Each model has one primary decision outcome and optional secondary KPIs; planning horizon and units are explicit.
- Default simulation volume configured in Settings: 1,000 / 10,000 / 100,000 runs; backend enforces tenant resource limits.
- Onboarding can begin with CSV and structured expert estimates; warehouse connections and internet retrieval follow permission review.
- Beta-phase decisions are **decision support**, not autonomous operational execution or a guarantee of business performance.

### 1.4 MVP inclusions / exclusions

**MVP (P0):** account + workspace, company profile, project/versions/history/delete, decision intake, structured agent proposal, explicit model and data approval, CSV ingestion, expert estimates, Monte Carlo with normal/triangular/Beta-PERT/Bernoulli/discrete + correlated sampling, async 1K/10K/100K runs, KPI definitions, result visualization, AI insights with citations to inputs, basic strategy comparison, testable API, audit logs.

**P1:** governed SQL integration, internet research connector, Markov simulation, Power Law/Pareto tail-specific diagnostics, advanced sensitivity, KPI monitoring and department tactics review, BYOK multiple providers, export/share and organization governance.

**P2:** recurrent monitoring, measured intervention outcomes, optimizer, automatic recalibration, granular role workflows, enterprise SSO/SCIM, policies for regulated industries.

**Non-goals of MVP:** arbitrary Python execution generated by LLM; agent-controlled write access to ERP; universal coverage of every business model or statistical method; automatic causal discovery from observational data; real-time trading or automated purchase decisions; production forecasts without approved evidence.

## 2. Target architecture

```text
┌──────────────────────────────────────────────────────────────────────┐
│ NEXT.JS WEB CLIENT                                                  │
│ Sidebar • Centered Hero • Model/Data Review • Decide • History     │
│ Settings • SSE events • Auth session • Responsive Glass UI          │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ HTTPS / SSE
┌───────────────────────────────▼──────────────────────────────────────┐
│ FASTAPI APPLICATION/BFF                                             │
│ Auth context • Tenant/RBAC • Project/Model/KPI APIs                 │
│ Approvals • Upload URLs • Source policies • API contracts           │
├───────────────────────────────┬──────────────────────────────────────┤
│ LANGGRAPH WORKFLOW            │ DATA ACCESS GATEWAY                 │
│ Deterministic stage control   │ CSV parse • curated SQL reads       │
│ Deep Agents orchestration     │ approved web retrieval             │
│ Interrupts/checkpoints        │ provenance • schema catalog        │
├───────────────────────────────┴──────────────────────────────────────┤
│ SIMULATION JOB SERVICE                                             │
│ Model validator/compiler → queue → NumPy/SciPy worker              │
│ Common-random-number comparisons • metrics • model diagnostics     │
└───────┬──────────────────────┬───────────────────────┬──────────────┘
        │                      │                       │
 PostgreSQL tenant data     S3 object storage     Redis broker/cache
 model + approval state     source files/results   queue, rate limits
 audit + KPI metadata      immutable snapshots    job coordination
```

**Operational boundary:** start with independently deployable `web`, `api`, `worker` containers and managed Postgres, Redis, object storage. Run Deep Agents inside API/worker orchestration module at MVP; extract agent service later only if scalability, security zone, or deployment frequency justifies it. Long-running simulations are never executed synchronously inside HTTP requests.

### 2.1 Responsibilities by service

| Component | Owns | Must never own |
|---|---|---|
| Frontend | interaction, accessible UI, charts, progress indicators | source-of-truth metrics, permissions, secret keys |
| API | authz, domain logic, approval records, rate limits, idempotency | heavy simulation loops or long agent executions |
| Workflow controller | stage transition, retries, resumable checkpoints | authorization bypass, direct data queries |
| Deep Agents | hypotheses, model candidates, data requirements, explanations, tactics drafts | executing unreviewed SQL/code or fabricating statistical results |
| Data gateway | extraction, typing, provenance, query guardrails | unrestricted arbitrary connections or exfiltration |
| Model compiler | JSON validation, static dependency graph, unit checks, whitelisted operators | `eval`, arbitrary import, shell, dynamic code execution |
| Simulation worker | sampling, expression evaluation, statistics, persisted run artifacts | spontaneous model changes or unapproved input retrieval |
| Report service | verified outputs + model lineage + interpretive narrative | inventing quantitative values not present in validated artifacts |

## 3. User journeys and workflow state machine

### 3.1 Stages displayed in product

1. **Define:** user poses strategic question; agent discovers target, time horizon, constraints, decision alternatives, and business context.
2. **Model:** agent creates nontrivial formula graph with dependencies, risks, controllable levers, competing candidates, and validation plan. The method name may remain in expandable “Methodology” detail; no method selector is imposed on CEO.
3. **Evidence:** user selects CSV, Database, Internet exploration, and/or estimates; explicit source approvals precede reads. Parser builds typed variables; data quality and conflicts are reported.
4. **Approve:** the application shows model summary, important uncertainties, data limitations, and permission scope; explicit human sign-off freezes the executable version.
5. **Run:** job runs asynchronously with progress and completion event. A run references immutable model version + input snapshot.
6. **Decide:** UI shows probability, outcome quantiles, downside, warnings, sensitivity, AI risk mitigation, strategy fit and tactics by division.
7. **Monitor/History:** user saves, reopens, compares, or deletes project; future integration ties actual KPI movement to decisions.

### 3.2 Machine-enforced states

```text
DRAFT
  → CLARIFYING
  → MODEL_PROPOSED
  → MODEL_APPROVED
  → SOURCE_ACCESS_PENDING
  → EVIDENCE_COLLECTED
  → DATA_REVIEW_PENDING
  → READY_TO_RUN
  → QUEUED → RUNNING → COMPLETED
                       ↘ FAILED / CANCELLED
  → DECISION_REVIEW → DECISION_RECORDED
```

**Guards:** `MODEL_APPROVED` requires `model_version_id`, no unresolved fatal validation errors, approver identity and timestamp. `SOURCE_ACCESS_PENDING` includes channel-specific policy, target resource scope and purpose; an absent approval cannot be interpreted as default permission. `READY_TO_RUN` requires acknowledged data quality warnings, input snapshot hash, approved target KPI and validated expression graph. `RUNNING` may only read the locked model and evidence snapshot. Edits to any assumption produce a new version; previously completed runs stay immutable.

### 3.3 Approval and retry semantics

- Model approval and source approval are separate actions, each written as `approval_records` with actor, organization, project, scope, version hash and audit trail.
- Resume a LangGraph checkpoint only after backend authorization and freshness checks; UI confirmation alone is not sufficient.
- External actions use idempotency keys so workflow resume/retry cannot duplicate ingestion, billing, exports, or job creation.
- If an approval is revoked, future reads are blocked; already created artifacts are handled under the agreed retention/deletion policy.
- Each step emits typed UI events (`stage.changed`, `approval.required`, `evidence.ready`, `run.progress`, `run.completed`, `run.failed`).

## 4. Domain model and schema

### 4.1 Core entities and ownership

```text
Organization 1─N Membership N─1 User
Organization 1─N Project 1─N ModelVersion 1─N SimulationRun
Project 1─N AgentThread / DecisionRecord / Strategy
ModelVersion 1─N VariableDefinition / FormulaNode / ModelDependency
ModelVersion N─1 EvidenceSnapshot 1─N EvidenceItem
Organization 1─N Connection / KPIMetric / CompanyContext
Strategy 1─N Intervention / TacticalAction / RiskMitigation
SimulationRun 1─N Statistic / Artifact / SensitivityResult
ApprovalRecord N─1 Project [and resource/version scope]
AuditEvent [tenant-scoped, append-only]
```

### 4.2 Database tables (minimum useful fields)

| Table | Key fields (in addition to UUID PK, `org_id`, timestamps) |
|---|---|
| `organizations` | name, plan, region, retention_policy |
| `users` | auth_subject, email_normalized, display_name, status |
| `memberships` | user_id, role, status, UNIQUE(org_id,user_id) |
| `company_context` | industry, business_model, currency, fiscal_year, risk_appetite, summary_version |
| `projects` | title, objective, horizon, owner_user_id, status, archived_at, deleted_at |
| `model_versions` | project_id, version_no, schema_version, spec_json, spec_sha256, validation_state, approved_at, created_by |
| `evidence_items` | source_type, source_uri_ref, file_hash, dataset_id, extraction_metadata_json, grain, window, freshness, permission_id |
| `evidence_snapshots` | project_id, content_hash, source_refs_json, validation_summary_json, created_by |
| `variable_definitions` | model_version_id, key, unit, distribution_json, provenance_ref, derived_flag |
| `simulation_runs` | model_version_id, evidence_snapshot_id, engine_version, rng_name, seed, iterations, status, progress, output_hash, idempotency_key, started_at, completed_at |
| `run_statistics` | run_id, metric_key, p05, p10, p50, p90, p95, mean, probability_target, cvar, standard_error, warnings_json |
| `run_artifacts` | run_id, kind, object_key, sha256, byte_count, expires_at |
| `kpi_definitions` | key, formula_ref, unit, direction, target, warning, critical, cadence, owner_division, effective_from, active_version |
| `strategies` | project_id, description, author_id, status, version |
| `interventions` | strategy_id, lever_key, change_json, timing_json, evidence_quality |
| `tactical_actions` | strategy_id, division, owner_id, action, leading_kpi_key, due_date, status |
| `approval_records` | resource_type, resource_id, action, scope_json, fingerprint, reviewer_id, decision, decided_at |
| `data_connections` | connector_kind, secret_ref, allowed_schema_json, status, last_test_at, catalog_version |
| `agent_threads` | project_id, thread_id, checkpoint_ref, latest_stage, last_event_at |
| `audit_events` | actor_type, actor_id, action, entity_type, entity_id, metadata_redacted, request_id |

**Data isolation:** `org_id` is mandatory for tenant-owned resources; enforce in service query predicates and PostgreSQL Row Level Security where feasible, with explicit service roles and separate tenant tests. Foreign keys must prevent cross-tenant references. Never trust an `org_id` supplied by a client without reconciling authenticated membership and resource ownership.

### 4.3 Reproducibility envelope

Every completed run must record `org_id`, `project_id`, `model_version_id`, `spec_sha256`, `evidence_snapshot_id`, `snapshot_sha256`, `engine_git_sha`, `engine_semver`, `python_package_lock_hash`, `rng_name`, `seed`, `iterations`, `dtype`, `distribution_implementation`, `created_at`, `result_sha256`, and software warnings. Identical seeds do not ensure bit-for-bit equality across libraries, algorithms, hardware or numerical environments; exact reproducibility is guaranteed only under pinned execution conditions.

## 5. Simulation model contract

### 5.1 JSON schema approach

The LLM proposes a `SimulationModel` Pydantic object, **never an executable string**. The expression DSL permits only whitelisted operators (`add`, `subtract`, `multiply`, `divide`, `min`, `max`, `clip`, `pow`, `if_else`, comparisons, aggregation). References must resolve to declared variables/derived nodes. The compiler checks: DAG acyclicity, unit compatibility, bounded parameter domains, calibration evidence, sample independence assumptions, correlation PSD, finite values, prohibitions against zero-divisions and invalid state transitions. Parser output is validated again server-side, including authorization and evidence lineage.

```json
{
  "schema_version": "1.0",
  "question": "Which strategy maximizes 12-month EBITDA target attainment?",
  "horizon": {"value": 12, "unit": "month"},
  "target": {"metric": "ebitda_delta_pct", "operator": ">=", "value": 20},
  "variables": [
    {"id": "base_volume", "unit": "units/year", "distribution": {"type": "triangular", "min": 80000, "mode": 100000, "max": 120000}, "evidence_ref": "ev_volume"},
    {"id": "base_price", "unit": "IDR/unit", "distribution": {"type": "fixed", "value": 150000}, "evidence_ref": "ev_price"},
    {"id": "price_elasticity", "unit": "dimensionless", "distribution": {"type": "beta_pert", "min": 0.3, "mode": 0.8, "max": 1.8}, "evidence_ref": "ev_elasticity"},
    {"id": "variable_cost", "unit": "IDR/unit", "distribution": {"type": "triangular", "min": 80000, "mode": 90000, "max": 105000}, "evidence_ref": "ev_cost"},
    {"id": "fixed_opex", "unit": "IDR/year", "distribution": {"type": "fixed", "value": 3000000000}, "evidence_ref": "ev_opex"},
    {"id": "price_change", "unit": "dimensionless", "role": "strategy_lever", "distribution": {"type": "fixed", "value": 0.03}}
  ],
  "formula_graph": [
    {"output": "demand_multiplier", "op": "max", "args": [0.0, {"op": "subtract", "args": [1.0, {"op": "multiply", "args": [{"ref": "price_elasticity"}, {"ref": "price_change"}]}]}]},
    {"output": "volume", "op": "multiply", "args": [{"ref": "base_volume"}, {"ref": "demand_multiplier"}]},
    {"output": "net_price", "op": "multiply", "args": [{"ref": "base_price"}, {"op": "add", "args": [1.0, {"ref": "price_change"}]}]},
    {"output": "revenue", "op": "multiply", "args": [{"ref": "volume"}, {"ref": "net_price"}]},
    {"output": "ebitda", "op": "subtract", "args": [{"op": "subtract", "args": [{"ref": "revenue"}, {"op": "multiply", "args": [{"ref": "volume"}, {"ref": "variable_cost"}]}]}, {"ref": "fixed_opex"}]}
  ],
  "comparison": {"baseline_levers": {"price_change": 0.0}, "strategy_levers": {"price_change": 0.03}, "common_random_numbers": true},
  "simulation": {"iterations": 10000, "seed": 42, "rng": "pcg64"}
}
```

**Example only:** IDs and nominal figures are synthetic. The `ebitda_delta_pct` target must be defined as an additional derived metric against an approved baseline (both baseline and strategy computed on matched draws). The numeric choices are not business recommendations. In production, generate and validate the corresponding complete typed schema; this JSON is an illustrative excerpt rather than a ready-to-run payload.

### 5.2 Model complexity policy

Use sufficient structural detail, not complexity for its own sake. Candidate model must explicitly include: target decomposition, controllable vs uncontrollable variables, uncertainty distributions, meaningful correlation/dependencies, time horizon, key downside event(s), strategy causal assumptions, and validation plan. For EBITDA/pricing, include demand elasticity, channel mix, volume, COGS, fixed vs variable cost, execution lag, and risk events where relevant. Reject a simplistic “fixed percentage times target” model unless the executive explicitly requests a rough back-of-envelope scenario.

### 5.3 Distribution/method registry

| Method family | Implementation rule | Required tests |
|---|---|---|
| Normal (bounded-percentile interpretation) | `sigma=(P95-P5)/(2*1.6448536269)` for compatible assumptions; not hard bounds | moment/quantile tests, extreme tails |
| Triangular | inverse-CDF or trusted RNG; `min <= mode <= max` | support, mean `(min+mode+max)/3` |
| Modified Beta-PERT | `alpha=1+4*(mode-min)/(max-min)`; `beta=1+4*(max-mode)/(max-min)` | support, mode shape, mean, endpoint cases |
| Bernoulli + conditional impact | event flag and event-dependent loss | frequencies and no-loss branch |
| Correlated sampling | PSD covariance / Gaussian copula or domain-specific structural driver | matrix validation, achieved correlation |
| Pareto/power law | `X=x_min*U^(-1/alpha)` with explicit tail policy | quantiles, divergent-moment warnings |
| Markov chain (P1) | row-stochastic transition matrix; explicit horizon/absorbing states | row sums, deterministic matrix benchmark |
| Stress test | fixed scenario overrides; no implied likelihood without an explicit distribution | overrides, units, reproducibility |

**Workbook validation note:** original HTMA analysis flagged mislabeled triangular summary mean, a Beta-PERT parameter reversal / mislabeled inverse-CDF, and incomplete Power Law histogram tail coverage. Retain validated math as default. If legacy Excel matching is needed, expose it only as a separately labeled compatibility mode, not the default model method.

### 5.4 Numerical outputs and uncertainty

Output per run: histogram, P05/P10/P50/P90/P95, mean when mathematically defined, target probability, probability standard error/interval (with method), loss percentiles, expected shortfall/CVaR when finite and meaningful, sensitivity with method+limitations, model warnings and calibration diagnostics. The Monte Carlo error of a binomial target estimate is approximately `sqrt(p*(1-p)/N)`; the 95% half-width at p≈0.5 is about **3.10pp / 0.98pp / 0.31pp** for 1K/10K/100K. Those intervals quantify simulation sampling only, not uncertainty of the business model or data.

KPI “best” and “worst” must use direction-specific percentiles and make tail probability explicit (e.g., upside P95 vs downside P05, **not guaranteed extrema**). KPI warning/critical thresholds come from validated policy, risk appetite or approved user estimates, never arbitrary LLM inventions. For Pareto distributions with undefined expectation, suppress misleading “expected outcome” summaries.

### 5.5 Comparing alternative strategies

Compute baseline and candidate strategies with matched uncertainty draws (common random numbers) when valid. Define `delta_kpi = kpi_strategy - kpi_baseline` sample-by-sample; report the delta distribution, P(delta>0), downside effects and guardrail breaches. Distinguish **observed correlations** from **assumed intervention mechanisms**. Model triangulation can compare bottom-up finance model, forecast model and market-based model, but agreement is not independent validation if inputs overlap; perform backtests, calibration and holdout validation when data exists.

## 6. Deep Agents / LangGraph specification

### 6.1 Graph-controlled execution

Use a deterministic LangGraph outer graph with nodes `clarify`, `propose_model`, `validate_spec`, `request_model_approval`, `resolve_data_access`, `ingest`, `assess_quality`, `request_data_approval`, `freeze_snapshot`, `submit_run`, `await_result`, `generate_decision_brief`, `review_strategy`, `record_decision`. Agents execute bounded sub-tasks within graph nodes; do not let an autonomous agent decide whether mandatory approvals are skipped.

**Specialist agents:** `model_designer`, `evidence_analyst`, `model_validator`, `strategy_advisor`, optionally `tactics_planner`. Keep specialist context isolated and expose only minimal approved tools. Use Deep Agents `create_deep_agent(...)` with declared `subagents` and `interrupt_on` for sensitive tools, using persistent checkpointer; preserve stable `thread_id`, tenant context and authorization through resumes. Deep Agents and LangGraph are implementation technologies, not sources of permission.

### 6.2 Agent tool contracts (strongly typed)

| Tool | Inputs | Outputs | Authorization rule |
|---|---|---|---|
| `lookup_company_context` | tenant-scoped project ID | approved profile + KPI catalog | user in organization |
| `suggest_model` | objective + approved metadata | candidate `SimulationModel` JSON | no data access beyond current context |
| `validate_model` | model version | pass/errors/warnings + DAG | deterministic, no LLM changes |
| `list_available_sources` | project ID | allowed source descriptors | metadata only |
| `request_evidence` | source ID, purpose, scope | evidence job ID | recorded approval + policy enforced server side |
| `assess_evidence` | snapshot ID | data-quality report | tenant-scoped data |
| `create_simulation_run` | approved model version, snapshot, N, seed | async run ID | backend checks stage and quota |
| `get_simulation_result` | run ID | typed immutable statistics | same tenant + project access |
| `compare_strategies` | approved baseline + candidate versions | delta statistics and guardrails | both locked and authorized |
| `write_decision_brief` | result IDs + validated sources | narrative with source refs and uncertainty statements | cannot alter numeric payload |

Tools must be side-effect free unless explicitly designed for an authorized domain mutation. All tool calls include correlation ID, user identity, tenant ID, timeout, token/cost budget and structured errors. Untrusted source content is data, never instructions. Approved database reads are brokered through the data gateway rather than direct agent DB connections.

### 6.3 State and checkpoint strategy

Store `graph_thread_id` and request identity in `agent_threads`; use a persistent production checkpointer (e.g., Postgres-backed) rather than in-memory; a LangGraph checkpoint is resumable workflow state **not** a substitute for `projects`/`simulation_runs` records. Persist stage transitions transactionally in the application DB, and emit an outbox event after commit. Checkpoint resumes must revalidate authorization and current approval scope. Side effects on resumes require idempotency controls, especially where a node may rerun.

### 6.4 Failure policy

- `invalid_spec`: agent receives typed compiler errors and may revise up to configured retry cap; escalate to user after cap.
- `missing_data`: mark affected variable estimate provisional; ask permission or require explicit approval of the estimate.
- `sql_timeout` / `internet_unavailable`: return partial evidence status; no fabricated replacement.
- `agent_timeout`: retry boundedly with budget; preserve checkpoint and stage.
- `simulation_failed`: retain sanitized diagnostics and partial logs, permit rerun with idempotent new ID.
- `approval_rejected`: record rejection; return to proposal/data step without executing.

### 6.5 Version-compatibility note

LangChain/Deep Agents interfaces evolve; pin a tested dependency lockfile and include an adapter package (`agents/adapters/langchain_runtime.py`). The public docs as of the design date describe `create_deep_agent`, `subagents`, LangGraph persistent checkpoints and `interrupt_on` approvals. Run a compatibility smoke test against the pinned version in CI before rollout. [S1–S4]

## 7. Data ingress and evidence quality

### 7.1 CSV / spreadsheet path (P0)

1. API issues short-lived presigned upload URL, scoped to tenant/project and file type.
2. Client uploads file directly to object storage; storage hook/worker scans file, verifies MIME, size, checksum, safe parser limits.
3. Parse CSV (and XLSX at P0 if scope confirmed) to typed tabular data with schema inference and preview.
4. Compute row count, missingness, duplicates, parse errors, quantile/range checks, effective time horizon, seasonality clues and outlier report.
5. Show user variable mapping, units, fit candidate distributions, supporting row counts and confidence caveats.
6. Obtain approval; snapshot the exact canonical transformed dataset (content-addressed) before simulation.

Reject unsafe formulas/macros, decompression bombs, invalid encodings and giant files beyond quota. Spreadsheet formulas are **not executed** as trusted code. Avoid uploading raw sensitive rows to an LLM unless organization policy specifically permits it.

### 7.2 SQL connector path (P1)

Onboard connector with **network + TLS + auth + read-only policy + allowed schemas + table catalog + approved joins/KPI definitions**. Connection test returns only sanitized status; secrets remain in vault and are never logged. Agent asks gateway for a semantic query such as “monthly net revenue for last 36 complete months”; gateway validates scope, compiles parameterized allowlisted SQL, adds tenant row predicates, enforces EXPLAIN/cost/timeout/row ceiling, redacts sensitive columns, audits query ID and returns minimum aggregate dataset. Prefer curated views/warehouse replicas to production OLTP tables. A prompt is not an authorization boundary.

### 7.3 Internet research path (P1)

Web retrieval allowed only after consent and network policy. Store URL, publisher, captured timestamp, access timestamp, units, currency, geography, definition, source reliability, and restrictions. Separate public external evidence from private company context; sanitize outbound query payload and strip confidential details. Use browser/network allowlists and egress controls; guard against prompt injection, SSRF and dubious benchmark comparisons. Results remain hypotheses unless data applicability is established.

### 7.4 Expert estimates (P0)

Support `fixed`, bounded min/mode/max, and percentile elicitation (P05/P50/P95), with estimator role, date, justification and confidence. Do not silently convert subjective extreme bounds into 90% intervals. Preview how distribution choice affects downstream outputs. Mark estimates distinctly as `expert_estimate`, and allow sensitivity/stress testing of them.

### 7.5 Data readiness gates

The deterministic evidence validator checks schema, coverage, time granularity, unit/currency, staleness, missing values, outliers, extreme values, baseline/forecast overlap, duplicated measures, and material correlation assumptions. Report status `validated`, `provisional`, or `insufficient` per variable with blockers. System may proceed with provisional inputs only if user approves an explicit risk/limitations statement. Data reliability is not determined by an opaque LLM score alone.

## 8. Public API contract (v1 REST + SSE)

Base prefix: `/v1`; OIDC-based session authentication (secure HTTP-only session or short-lived bearer tokens); each call derives org + user from auth context. Paginated lists, `request_id`, `Idempotency-Key` on writes, error envelope, validation errors, and stable API versioning.

| HTTP | Path | Purpose | Key response |
|---|---|---|---|
| `POST` | `/projects` | create decision | `project_id`, `stage` |
| `GET` | `/projects` | list recent/history | paginated items |
| `GET` | `/projects/{id}` | retrieve scoped project | project with versions/runs |
| `DELETE` | `/projects/{id}` | soft-delete | 204 + audit event |
| `POST` | `/projects/{id}/messages` | add executive prompt | `thread_id`, staged response/event ref |
| `GET` | `/projects/{id}/events` | SSE activity and approvals | typed event stream |
| `POST` | `/projects/{id}/models:propose` | get structured proposed model | `model_version_id`, review summary |
| `POST` | `/projects/{id}/approvals` | approve/reject scope | approval ID, next stage |
| `POST` | `/uploads/presign` | create file upload URL | URL, object key, expires |
| `POST` | `/evidence/imports` | import approved source | job ID |
| `GET` | `/evidence/imports/{id}` | data quality summary | status + variable profiles |
| `POST` | `/connections/test` | connector test, admin only | sanitized connectivity result |
| `POST` | `/projects/{id}/runs` | queue simulation | `run_id`, status, event endpoint |
| `GET` | `/runs/{id}` | progress/status | stage, progress, timings |
| `GET` | `/runs/{id}/results` | immutable result | metrics + artifact refs |
| `POST` | `/projects/{id}/strategies` | create candidate intervention | strategy ID |
| `POST` | `/strategies/{id}/review` | compare against baseline | comparison run ID |
| `GET/PUT` | `/settings/simulation` | choose 1K/10K/100K | selected default |
| `GET/PUT` | `/kpis` | list and manage KPIs | catalog versions |

### 8.1 Example create-run request

```http
POST /v1/projects/{project_id}/runs
Authorization: Bearer <redacted>
Idempotency-Key: 9a15cc2c-9d1d-47a0-a0de-45c904800791
Content-Type: application/json

{
  "model_version_id": "modv_01JABC",
  "evidence_snapshot_id": "evs_01JDEF",
  "iterations": 10000,
  "seed": 42,
  "comparison_baseline_model_version_id": "modv_01JAAA"
}
```

```http
HTTP/1.1 202 Accepted
{
  "run_id": "run_01JGHI",
  "status": "queued",
  "events_url": "/v1/projects/{project_id}/events"
}
```

The server returns `409` if approvals or frozen specs are missing, `403` for scope violations, `422` for invalid numerical inputs, `429` when budget/quota exceeded, `503` for unavailable queue/gateway. Clients retry only idempotent writes with same idempotency key.

### 8.2 SSE event contracts

```json
{"type":"stage.changed","project_id":"proj_1","stage":"RUNNING","event_id":"evt_1001"}
{"type":"run.progress","run_id":"run_1","completed":6400,"total":10000,"event_id":"evt_1002"}
{"type":"approval.required","project_id":"proj_1","scope":"data_access","approval_id":"apr_1","event_id":"evt_1003"}
{"type":"run.completed","run_id":"run_1","result_url":"/v1/runs/run_1/results","event_id":"evt_1004"}
```

Use stored outbox/event IDs to support reconnect with `Last-Event-ID`, and server-side membership verification on both initial connection and reauthorization/expiry. Do not stream sensitive DB rows or provider credentials.

## 9. Frontend migration from HTML prototype

### 9.1 Keep and replace

| Current element | Keep | Replace for production |
|---|---|---|
| Sidebar, glass panels, orbital canvas | visual grammar, responsive layout | React components, accessible focus/keyboard, reduced-motion behavior |
| Centered headline + textarea | executive-first entry | authenticated `POST /projects` and streamed agent messages |
| “Bring context” cards | CSV/DB/Internet choices | actual upload/import/consent flows with provenance and source-specific states |
| Decide KPI cards and chart | concise decision framing | server-validated units, time periods, uncertainty labeling, real artifacts |
| Risk mitigation, strategy/tactics panels | content architecture | structured agent insights bound to result IDs and evidence |
| History | list/open/delete affordances | backend persistent, versioned projects; org-level access policy |
| Settings | simulation scale and company/permissions/BYOK IA | encrypted secrets, real connectivity tests and role checks |
| JS `simulate()` and hardcoded tactic text | demo only | **remove** and consume numeric/agent service APIs |
| `localStorage` project state | draft UX if appropriate | backend source of truth; no secrets/client-trusted approvals |

### 9.2 Suggested React tree

```text
app/
  (auth)/sign-in, sign-up
  (workspace)/layout.tsx
  (workspace)/page.tsx                    # Hero + orbital dots + recent decisions
  (workspace)/projects/[id]/page.tsx      # Project steps & agent conversation
  (workspace)/projects/[id]/data/page.tsx
  (workspace)/projects/[id]/decide/page.tsx
  (workspace)/history/page.tsx
  (workspace)/kpis/page.tsx
  (workspace)/settings/page.tsx
components/
  navigation/Sidebar.tsx
  home/OrbitalDotsCanvas.tsx
  agent/StageTimeline.tsx, ApprovalCard.tsx, EvidenceBadge.tsx
  modeling/AssumptionReview.tsx, ModelVersionBadge.tsx
  decide/OutcomeDistribution.tsx, RiskInsights.tsx,
         KpiRangeTable.tsx, StrategyReview.tsx, TacticsByDivision.tsx
  settings/ConnectionTestCard.tsx, ProviderConfig.tsx
lib/api/client.ts, lib/api/events.ts, lib/types/contracts.ts
```

### 9.3 UI behavior criteria

- Hero contains **one** decision question, no attach button; latest decisions remain directly underneath.
- No mathematical method picker is shown in executive default view; “How this model works” is optional evidence disclosure.
- Background orbital points track pointer smoothly but are nonblocking; provide reduced-motion mode and lower rendering duty cycle on battery/mobile.
- Executives should see no more than one primary CTA and 3–4 top-line decision metrics at once.
- All percentages display numerator/denominator explanation or tooltip, time horizon and units; result panels show “provisional” and “illustrative” flags where applicable.
- Selection controls 1K/10K/100K live **only in Settings**, not Decide; Decide may display count as read-only metadata.
- All async actions use optimistic UI sparingly, with explicit submitted/queued/running/complete/failure statuses and retry affordances.
- Support keyboard navigation, text contrast, screen reader announcements for run completion; moving dots do not capture clicks on input.

## 10. AI insights: requirements and evidence discipline

The `DecisionReport` serializer produces a structured response whose **quantitative fields are copied from simulation artifacts**; the LLM only drafts bounded explanations referencing result IDs. Every recommendation is categorized as `measured`, `simulated`, `assumed`, or `hypothesis`.

| Section | Backend data dependency | Required fields |
|---|---|---|
| Executive summary | run statistics | `decision_question`, `recommended_action`, `p_target`, `risk`, `confidence_caveat` |
| Risk mitigation | event/tail risk + sensitivities | risk ID, failure mode, risk level, trigger KPI, proposed action, owner, residual-risk assumption |
| KPI best / worst / warning | run quantiles + KPI policy | unit, direction, best quantile, worst quantile, warning value/source, time horizon |
| Strategy review | baseline/candidate paired results | delta distribution, P(improvement), affected KPIs, tradeoffs, model assumptions |
| Tactics by division | industry/org context + strategies | division, action, owner placeholder, leading KPI, milestone, validation experiment |
| Assumptions & sources | model + evidence provenance | data quality flags, citations, version lineage, missing evidence |

**Guardrails:** do not claim causation from correlation; avoid unconditional “will increase” wording; where warning thresholds have no approved source, display “Not defined—confirm with owner.” An agent’s tactic is a recommended experiment until endorsed by the accountable division. Industry context affects suggested action design, not the validity of a probability computation.

## 11. Security, privacy, compliance foundations

### 11.1 Identity and tenancy

OIDC login/signup; organizations, membership invitations, roles `org_admin`, `executive`, `analyst`, `viewer`, and future `integration_admin`. Enforce least privilege per resource and capability, not only frontend hiding. Validate session, tenant membership, project ownership, connector scope and environment policy at every access. Separate organization administration and billing permissions. Log actor and effective role for high-impact changes.

### 11.2 Prompt injection and tool isolation

Treat web pages, CSV cells, database text, user-uploaded documents and connector metadata as untrusted. Strip instruction-like content from retrieved material only as a supplementary measure; true mitigation is no privileged tool access from raw content. Strict tool allowlists, schema validation, outbound URL allowlists, SQL proxy, egress firewall, row caps, redaction, secrets isolation, sandboxed parser, source provenance, and human approvals. Follow OWASP LLM application risk guidance; test attempts to redirect agents to reveal secrets or approve a source themselves. [S5]

### 11.3 BYOK model credentials

Store keys in cloud secrets manager/KMS-encrypted vault, never plaintext in Postgres or browser localStorage. Record secret reference, provider, permitted models, organization, version and last successful test. Display **masked** status, not raw key. Check each provider’s retention/data-use rules and approved region against organization policy before sending confidential context. Make provider selection and model version part of the decision audit. Rotate/revoke keys, rate-limit provider spend, and prohibit credentials in agent traces.

### 11.4 Retention / deletion / incident response

Soft-delete projects for configurable grace period; schedule hard deletion across database, object storage, vector/agent stores, and backups according to published retention policy. Some tamper-evident audit metadata may be retained subject to contract/regulation; document what is and is not removed. Encrypt in transit and at rest, isolate production from test, restore backups in staging quarterly, maintain incident playbooks and breach escalation path. Compliance standards and jurisdictional requirements require legal/security review before commercial launch.

## 12. Operations, infrastructure and DevOps

### 12.1 Recommended repository

```text
north/
  apps/web/                     # Next.js app
  services/api/                 # FastAPI routes/auth/domain
  services/worker/              # queue consumers, simulation
  packages/contracts/           # OpenAPI JSON schemas, types
  packages/simulation/          # numeric registry/DSL/tests
  packages/agents/              # Deep Agents + LangGraph adapter
  packages/evidence/            # ingest, profiling, semantic queries
  packages/decision/            # metric aggregation, report schema
  infra/terraform/              # network, DB, queue, storage, IAM
  ops/                          # runbooks, dashboards, alerts
  docs/adr/                     # design decisions & rationale
  tests/e2e/ tests/security/ tests/numerical/
```

### 12.2 Deployment topology

Managed container platform (e.g., ECS/Fargate, Cloud Run + appropriate job workers, or Kubernetes after scale justifies it); private subnets for DB and connector gateway; public ingress only for authenticated web/API; managed Postgres with backups, object storage, Redis, central log/traces, secret manager and KMS. CI builds signed images, produces SBOM, runs dependency scanners and migrations, promotes to staging and then production via approval. No database credentials or BYOK values in image/environment visible to browser.

### 12.3 Non-functional target SLOs (proposed, verify with load testing)

| Metric | Initial target | Verification |
|---|---|---|
| Availability | 99.5% monthly for beta API | uptime synthetic probes |
| Non-LLM API latency | p95 < 400 ms | load test excluding streaming/long jobs |
| Decision stage events | first event within 2 s at healthy provider conditions | SSE instrumentation |
| 10K draws | p95 worker compute < 20 s for bounded reference models | perf benchmark on target hardware |
| Job submission | p95 < 700 ms (excluding auth redirects) | API load test |
| Job reliability | > 99% finish or produce a classified failure within budget | durable queue dashboard |
| Restore target | RPO ≤ 24 h; RTO ≤ 4 h in beta | scheduled backup restore drill |
| Audit completeness | 100% for approvals, data access, and run creation/deletion | event reconciliation checks |

The numerical 10K compute target assumes a bounded, vectorizable model; not valid for expensive path-dependent Markov or iterative optimization. Define per-model complexity caps and separate job classes/queues. Agent response latency depends on provider and evidence workload, so report time-to-first-update and eventual completion separately.

### 12.4 Cost and quotas

Per-tenant monthly counters: LLM input/output tokens, research requests, connector query compute, simulation CPU-seconds, storage bytes, monthly active projects. Use budgets, token caps, concurrency limits and cancellation support. Large 100K jobs use background workers and must not block UI. Attach usage to project/run and provider version so finance can explain cost per decision.

## 13. Verification and testing matrix

| Area | Test | Release gate |
|---|---|---|
| Authentication & RBAC | no cross-tenant project/file/connector access | zero bypasses |
| Agent workflows | forced interrupts; reject, resume, timeout; tool retry | no action without matching approval |
| DSL compiler | unknown refs, cycles, unsupported operator, dimensional errors | reject all invalid specs |
| Distribution tests | seeded draws and expected moments/quantiles/support | tolerances defined statistically |
| Reference workbook | compare validated implementations vs HTMA reference tests | expected method-specific checks pass |
| Correlation | PSD rejection, empirical covariance under seeded runs | test precision bounds |
| Markov | analytic absorption probabilities vs simulation | within estimator CI |
| Strategy comparison | matched RNG, baseline identical, pairwise delta correctness | reproducible within pinned stack |
| Data quality | missing, duplicates, stale, inconsistent units, untrusted CSV | correct blockers and warnings |
| Security | prompt injection, SQL injection, SSRF, oversized files, key leakage | no high/critical vulnerability |
| Job orchestration | cancel, retry, duplicate submit, worker crash | no duplicate side effects; recoverable |
| UI E2E | login → question → approval → evidence → run → decide → history | passes desktop/mobile; WCAG-focused checks |
| Observability | tracing IDs from UI through agent and worker | one coherent run trace |
| Export/history | versions, immutability, delete/retention | consistent with policy |

### 13.1 Numerical regression cases from workbook

`FirstMCExample`: verify exact structural formula `Savings=(Maintenance+Labor+Material)*Production` and `success=(Savings>400000)`; saved workbook empirical success **~86.1173%** over 15,170 stored scenarios is historical reference only, not exact requirement for new RNG. `MCExampleWcontractloss`: 10% event probability and conditional production adjustment must be modeled explicitly. Triangular corrected mean; Beta-PERT corrected alpha/beta; Pareto tail counts; correlation theoretical/empirical; Markov row transition and absorption. Maintain two test suites: deterministic golden fixtures and statistical distribution tests. New seeded draws need not reproduce Excel `RAND()` sequence.

### 13.2 AI quality evaluation

Build 30–50 curated decision prompts across manufacturing, SaaS, retail, logistics and finance ops. Each has expert-annotated objective, required variables, model family, source permissions, KPI direction and escalation path. Evaluate model completeness, unjustified assumptions, hallucinated figures, citation validity, strategy-to-KPI linkage, tactic specificity, and refusal to bypass approval. Store evaluation traces and scores in CI/staging. Include adversarial input cases and ambiguous questions; manual expert review remains mandatory for finance-critical production scenarios.

## 14. Engineering roadmap / delivery plan

The following is a **planning estimate, not a delivery commitment**; assumes a cross-functional 4–6-person team with frontend, backend, AI/data, QA/DevOps coverage, reusable managed auth/infra, and no major legacy integration constraints.

| Sprint | Main deliverables | Definition of done |
|---|---|---|
| 0 — Foundation (1–2 weeks) | repo, CI, auth/RBAC, Postgres/Redis/storage, contracts, architecture ADR | staging boots; tenant access enforced |
| 1 — Workspace (2 weeks) | Next.js sidebar/hero, project creation/history, company context, SSE shell | E2E signed-in project roundtrip |
| 2 — Model & approval (2 weeks) | declarative DSL, typed model proposal, versioning, controlled LangGraph stages | approved model immutable and traceable |
| 3 — Evidence (2 weeks) | CSV upload/profile, expert estimates, provenance, data readiness and approval | source → typed snapshot → consent evidence |
| 4 — Simulation (2 weeks) | Monte Carlo worker, calibrated distributions, async queue, artifact and metrics | 1K/10K/100K; reproducibility and tests |
| 5 — Decision Studio (2 weeks) | charts, risks, KPI thresholds, paired strategy comparison, tactics draft | no fabricated metrics; drilldown lineage |
| 6 — Hardening (2–3 weeks) | adversarial/security/load testing, audit, observability, deployment runbooks | beta go/no-go gates pass |
| P1 (after beta) | governed database/internet connectors, multi-model validation, monitoring, exports | security and domain validation specific to each integration |

**Critical path:** authenticated tenancy → model JSON/compiler → evidence snapshot+approval → deterministic worker → immutable result contract → agent narrative. Avoid building many agents or dozens of distributions before this end-to-end slice works. The illustrative 13–15-week beta scope can extend materially with enterprise procurement, production-grade connectors, staffing limitations or sector compliance.

### 14.1 First vertical slice (mandatory proof)

One executive enters a pricing + EBITDA question. The app creates a project, agent proposes a model with price elasticity/cost-volume links, user approves model, uploads sales CSV or enters an explicit estimate, approves evidence, worker runs 10K paired baseline/strategy samples, API returns P(target), quantiles, warning flags and simulation metadata, Decision Studio shows risk mitigation and tactics bound to verified outputs, history reloads the same immutable result, and another organization cannot retrieve any linked object. This is the first **real service** milestone.

### 14.2 Engineering tickets (initial order)

- `NORTH-001` OIDC auth + organization membership middleware + basic audit event.
- `NORTH-002` Project CRUD + soft delete + tenant-scoped history.
- `NORTH-003` Pydantic `SimulationModel` spec + JSON Schema + unit/cycle/PSD checks.
- `NORTH-004` LangGraph stage machine with persistent checkpoint and explicit approval interrupts.
- `NORTH-005` CSV ingest/presigned upload/data quality/evidence snapshot.
- `NORTH-006` Model registry and NumPy/SciPy seeded reference engine with numerical tests.
- `NORTH-007` Worker queue, job idempotency, progress SSE, cancellation and quotas.
- `NORTH-008` Typed results schema and Decision Studio components.
- `NORTH-009` Agent narrative guardrails and source-linked mitigation/strategy/tactics.
- `NORTH-010` Security hardening, secrets management, load + adversarial tests.

## 15. Acceptance criteria for the product owner

A production beta is ready only if all of the following are demonstrably true:

1. A new CEO can create a meaningful simulation without choosing statistical algorithms.
2. The agent produces a reviewable nontrivial structural model with variable provenance and limitations.
3. Every external/internal source access has a recorded and enforceable policy/approval.
4. A CSV or estimate produces a typed immutable evidence snapshot; malformed/low-quality data is flagged.
5. Model expressions pass deterministic validation; no arbitrary LLM-generated code is executed.
6. A 10K reference run is asynchronous, reproducible under pinned conditions, and accurately exposes progress/failures.
7. P(target), quantiles, tail risk and KPI warning values come from engine/policy, not creative text generation.
8. A strategy comparison uses matched assumptions and exposes tradeoffs and uncertainty.
9. Risk mitigation and division tactics cite relevant KPI drivers and distinguish hypotheses from measured facts.
10. Project history, report version, delete and authorization survive logout/restart and enforce tenant boundaries.
11. BYOK values and source credentials never appear in browser storage, traces, logs or returned JSON.
12. Desktop/mobile UX retains centered hero, blue orbital dots and translucent glass panels with usable contrast and accessibility.

## 16. Open decisions requiring owner sign-off

| Question | Default recommendation | Owner |
|---|---|---|
| Primary market / first industry | Manufacturing + 2 validated financial decisions | CEO/Product |
| Hosting jurisdiction and data residency | Start in customer-approved region; configurable later | CEO/Security |
| Tenant architecture | Shared Postgres with RLS/strict scoping; dedicated tenancy for enterprise later | CTO/Security |
| BYOK in MVP | Launch with one managed provider first; add BYOK after vault/billing checks | CTO/Product |
| CSV only vs XLSX also in P0 | CSV core; XLSX guarded parser if customer demand justifies | Product/Engineering |
| Autonomy in approval workflows | Always explicit for source reads, run freeze and external effects | Security/Product |
| KPI threshold ownership | Business user/accountable function defines values; agent may propose | CEO/Finance |
| Document export | JSON/CSV result first; PDF/DOCX share view P1 | Product |
| Simulation pricing/quota | Usage tier + per-tenant policy for 100K/high-complexity models | Finance/Platform |
| Custom Python formulas | Never in default SaaS; isolated reviewed plugin extension later | CTO/Security |

## 17. Reference material and verification notes

**Project inputs reviewed:**

- `strategy-simulation-prototype.html`: latest NORTH prototype (sidebar layout, `page-home`, `page-data`, `page-decide`, `page-history`, `page-settings`, orbital canvas, browser demo simulation, local history).
- `HTMA_Chapter6_Reverse_Engineering.md` and `htma_simulation_reference.py`: previously prepared reverse engineering of seven Excel methods; used only as numerical reference, not as automatically production-certified source.
- `HTMA_3rd_Ch6-2.xlsx`: uploaded workbook for method provenance.

**External primary references (checked 2026-10-15):**

- [S1] LangChain — Deep Agents overview: https://docs.langchain.com/oss/python/deepagents/overview
- [S2] LangChain — Deep Agents human-in-the-loop: https://docs.langchain.com/oss/python/deepagents/human-in-the-loop
- [S3] LangChain — Deep Agents subagents: https://docs.langchain.com/oss/python/deepagents/subagents
- [S4] LangChain — LangGraph persistence and interrupts: https://docs.langchain.com/oss/python/langgraph/persistence and https://docs.langchain.com/oss/python/langgraph/interrupts
- [S5] OWASP — Top 10 for LLM Applications: https://owasp.org/projects/top-10-for-large-language-model-applications
- [S6] NIST — AI Risk Management Framework: https://www.nist.gov/itl/ai-risk-management-framework

**Important boundaries:** Proposed architecture and timelines are engineering recommendations. No production service has been deployed, no live connector was exercised, no provider credential was tested, and no regulatory certification was established. The HTML demo's figures must not be interpreted as forecasts. Verify the locked Deep Agents/LangGraph APIs and cloud/vendor contracts again when implementation begins.
