# NORTH — local decision intelligence

First vertical milestone: English decision intake → contextual agent clarification → CSV evidence profile → model review and explicit approval → asynchronous paired Monte Carlo → quantitative results → optional evidence-linked agent brief → recorded human decision and history.

## Run locally

Requirements: Python 3.12, Node 24 and npm. From the repository root:

```sh
python -m venv .venv
.venv/bin/pip install -r backend/requirements.lock
npm --prefix web ci --cache /tmp/north-npm
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In another terminal, from the repository root:

```sh
npm --prefix web run dev
```

Open port 3000 in your local browser. Settings accepts your OpenRouter key and defaults to `openai/gpt-6-luna` (owner-supplied ID; authenticated inference verified). A missing key, unavailable model or denied provider access is reported explicitly. No fake agent response or synthetic business result is substituted. Inputs and generated content are English. The API does not need provider credentials to validate and run a manually supplied model.

Docker alternative: `docker compose up --build`. Ports are bound to loopback. Data is in the `north-data` volume. Compose configuration validates. Image builds were attempted here, but container DNS/proxy resolution prevented package downloads; image startup is therefore not yet verified. Native startup is verified.

## Use

1. Enter a management decision. Describe role, industry, outcome, units, target, horizon, constraints and alternatives in context.
2. Optionally upload UTF-8 CSV (max 2 MB / 20,000 rows / 50 columns). Upload authorizes local parsing. Numeric statistics, missingness, nonnumeric counts and file hash are shown. Raw rows are not sent to OpenRouter or retained. CSV profiles, business context and explicit estimates are sent only when requesting an agent proposal.
3. Ask the agent to clarify. Answer in context and request a new proposal. Cases outside the independent-input expression engine must be simplified or deferred. No universal domain model is hardcoded.
4. Review/edit model JSON and provenance. Approve the model and evidence limitations. Context or evidence edits revoke prior approval. Prior run snapshots remain unchanged.
5. Run 1K/10K/100K samples. Baseline and strategy share draws (seed 42). The job progresses queued → running → completed/failed, polled by the UI. Quantitative outputs are calculated in NumPy, never by the LLM.
6. Optionally request a qualitative agent brief. Input references are validated; business meaning and recommendations still require human review. Record the chosen decision and rationale. History and audit survive process restart.

## Storage and security boundary

This is a trusted, **single-user local application**, not a production multi-tenant SaaS. Keep both services on loopback; do not expose them publicly. There is no login, RBAC or organization isolation. SQLite persists projects, approvals, audit and immutable completed run snapshots. A bounded one-thread background executor runs simulations outside HTTP requests; it is not a durable distributed broker. Interrupted jobs are marked failed on startup. Only one API worker should be used. Moving to Postgres, Redis and authenticated tenant authorization is a subsequent milestone.

The API key is encrypted with Fernet in `.data/north.db`; the encryption key lives in `.data/encryption.key` (mode 0600). Back up both securely; encryption does not protect against an attacker controlling this machine. Keys are never returned to the browser or stored in browser storage. Delete a key in Settings. No environment secret is embedded in source. Configure `NORTH_DATA_DIR` to relocate local storage and `API_URL` for the Next.js backend target. The outbound provider endpoint is fixed to OpenRouter. Browser cross-origin writes are blocked.

## Numerical boundary

Supported distributions: fixed, normal, triangular, Beta-PERT, Bernoulli. Operators: add/subtract/multiply/divide/min/max in an ordered acyclic graph. No `eval`, arbitrary code or SQL execution. The compiler checks references, bounds, finite parameters and operator restrictions; semantic unit compatibility and calibration require human review in this milestone. Inputs are sampled independently; correlation, Markov, Pareto, calibration, optimization and live data connectors are not yet implemented. Normal inputs are unbounded: use bounded distributions when required. Invalid sampled division fails the run rather than manufacturing a number. The worker reports target probability with Monte Carlo standard error, mean, P10/P50/P90, histogram and paired mean change. This does not estimate model misspecification uncertainty or prove causal effects.

The uploaded HTMA code is retained as `docs/htma_simulation_reference.py` for provenance, not silently adopted as a universal engine. Its legacy workbook compatibility functions explicitly identify questionable formulas. The implemented engine uses NumPy's validated distributions and independent PCG64 sampling. Reproducibility metadata includes seed, model hash, engine source hash, Python dependency lock hash, dtype and NumPy version; exact replay requires the same execution environment.

## Validation

```sh
.venv/bin/python -m pytest -q
npm --prefix web run build
curl -f http://127.0.0.1:8000/api/health
```

Tests cover seeded statistical behavior, common random numbers, unsafe expression rejection, CSV profiling, approval guards, asynchronous completion, idempotency, immutable results after edits, key redaction and cross-origin protection. Live OpenRouter calls require a Settings key or OPENROUTER_API_KEY and network access; an offline test does not establish provider compatibility.

## Current validation evidence

- Production Next.js build: passed (Next.js 16.4.2 / React 19.3.1).
- Backend: 6 tests passed, including a mocked OpenRouter contract check (not a live provider test).
- Headless Chromium: create → approve → simulate → record decision → reload history passed; desktop and 390 px mobile checked, no browser errors or horizontal overflow.
- npm production dependency audit: zero reported vulnerabilities at implementation time.
- Native API and frontend proxy health requests: passed.
- OpenRouter live access: verified after configuration publication on 2026-10-18. The runtime key was detected without exposing its value, model discovery returned HTTP 200, and authenticated inference with openai/gpt-6-luna returned valid clarification JSON. The application proposal flow also reached CLARIFYING with a real provider response. This does not certify forecasting accuracy. Unit tests isolate injected credentials to avoid real provider requests.
- Docker Compose: syntax passed; image build blocked by container DNS/proxy resolution. No container readiness claim.

Agent orchestration currently uses explicit persisted API stages and structured OpenRouter calls; LangGraph/Deep Agents checkpoint orchestration and Postgres/Redis deployment are deferred. This local milestone does not claim full P0 or production readiness.

## OpenRouter environment key

The backend reads `OPENROUTER_API_KEY` as a fallback when no key is saved in Settings. Restart the backend after adding or changing its process environment. Settings reports the active source without exposing the value. A key explicitly saved in Settings takes precedence; removing it restores the environment fallback. Environment keys are not copied into SQLite. Docker Compose forwards this variable to the API container; recreate that container after changing it. Never put credentials in Git-tracked files or send them in chat.
