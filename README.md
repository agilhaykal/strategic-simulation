# SimplifySimulation — local decision intelligence

English decision chat → confirmed context → multiple CSV / internet / PostgreSQL sources → PII-minimized source discussions and mappings → source and combined-evidence approval → model review → paired Monte Carlo → decision and immutable history. See [the multi-source guide](docs/MULTISOURCE.md).

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

Open port 3000 in your local browser. Settings accepts your OpenRouter key and defaults to `openai/gpt-6-luna` (owner-supplied ID; authenticated inference verified). A missing key, unavailable model or denied provider access is reported explicitly. No fake agent response or synthetic business result is substituted. API key presence can also come from the backend environment. Inputs and generated content are English. The API does not need provider credentials to validate and run a manually supplied model.

Docker alternative: `docker compose up --build`. Ports are bound to loopback. Data is in the `north-data` volume. Compose configuration validates. Image builds were attempted here, but container DNS/proxy resolution prevented package downloads; image startup is therefore not yet verified. Native startup is verified.

## Use

Start a decision, allow minimized context sharing, and use **Start clarification** or send a message to Agent SimplifySimulation. Confirm the context summary. Add multiple CSV files, approved internet URLs or read-only PostgreSQL sources; discuss each source in the same thread. Select and map only the relevant columns with units, definitions, observation periods and population. Review privacy/quality limitations, approve included source versions, and freeze the combined evidence. Then request and approve a model before running simulations. Source edits revoke affected approvals while old completed run snapshots are retained.

Tavily basic search requires `TAVILY_API_KEY` or an encrypted Settings key. Use a free-plan key for the POC and monitor account quota; unlimited free usage is not promised. Configure PostgreSQL through Settings or `NORTH_POSTGRES_DSN`. Raw CSV/query rows remain encrypted locally and are never put in the agent prompt. Page excerpts require manual privacy review before AI access. Credentials are backend-only. See [MULTISOURCE.md](docs/MULTISOURCE.md) for controls, API, and limitations.

## Storage and security boundary

This is a trusted, **single-user local application**, not a production multi-tenant SaaS. Keep both services on loopback; do not expose them publicly. There is no login, RBAC or organization isolation. SQLite persists projects, approvals, audit and immutable completed run snapshots. A bounded one-thread background executor runs simulations outside HTTP requests; it is not a durable distributed broker. Interrupted jobs are marked failed on startup. Only one API worker should be used. Moving to Postgres, Redis and authenticated tenant authorization is a subsequent milestone.

The API key is encrypted with Fernet in `.data/north.db`; the encryption key lives in `.data/encryption.key` (mode 0600). Back up both securely; encryption does not protect against an attacker controlling this machine. Keys are never returned to the browser or stored in browser storage. Delete a key in Settings. No environment secret is embedded in source. Configure `NORTH_DATA_DIR` to relocate local storage and `API_URL` for the Next.js backend target. The outbound provider endpoint is fixed to OpenRouter. Browser cross-origin writes are blocked.

## Numerical boundary

Supported distributions: fixed, normal, triangular, Beta-PERT, Bernoulli. Operators: add/subtract/multiply/divide/min/max in an ordered acyclic graph. No `eval`, arbitrary code or SQL execution. The compiler checks references, bounds, finite parameters and operator restrictions; semantic unit compatibility and calibration require human review in this milestone. Inputs are sampled independently; correlation, Markov, Pareto, automatic calibration and optimization are not yet implemented. Normal inputs are unbounded: use bounded distributions when required. Invalid sampled division fails the run rather than manufacturing a number. The worker reports target probability with Monte Carlo standard error, mean, P10/P50/P90, histogram and paired mean change. This does not estimate model misspecification uncertainty or prove causal effects.

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
- Backend verification now includes persistent chat/retry, privacy exclusions, source versions, conflicts, snapshot guards, and actual disposable PostgreSQL metadata/query tests. See the latest test run for counts; PostgreSQL tests skip explicitly if their disposable DSN is absent.
- Headless Chromium: create → approve → simulate → record decision → reload history passed; desktop and 390 px mobile checked, no browser errors or horizontal overflow.
- npm production dependency audit: zero reported vulnerabilities at implementation time.
- Native API and frontend proxy health requests: passed.
- OpenRouter live access: verified after configuration publication on 2026-10-18. The runtime key was detected without exposing its value, model discovery returned HTTP 200, and authenticated inference with openai/gpt-6-luna returned valid clarification JSON. The application proposal flow also reached CLARIFYING with a real provider response. This does not certify forecasting accuracy. Unit tests isolate injected credentials to avoid real provider requests.
- Docker Compose: syntax passed; image build blocked by container DNS/proxy resolution. No container readiness claim.

Agent orchestration uses persisted conversation/API stages and structured OpenRouter calls with one bounded proposal repair. LangGraph/Deep Agents, a distributed broker, and Postgres application storage are deferred. PostgreSQL as a read-only evidence connector is implemented. This local milestone does not claim full P0 or production readiness.

## OpenRouter environment key

The backend reads `OPENROUTER_API_KEY` as a fallback when no key is saved in Settings. Restart the backend after adding or changing its process environment. Settings reports the active source without exposing the value. A key explicitly saved in Settings takes precedence; removing it restores the environment fallback. Environment keys are not copied into SQLite. Docker Compose forwards this variable to the API container; recreate that container after changing it. Never put credentials in Git-tracked files or send them in chat.

Self-hosted performance monitoring setup and privacy scope: [docs/MONITORING.md](docs/MONITORING.md).
