# Self-hosted performance monitoring

Set these variables in the backend environment (or the environment used by Docker Compose):

```dotenv
LANGFUSE_BASE_URL=https://langfuse.staging.ximplify.id
LANGFUSE_PUBLIC_KEY=<project public key>
LANGFUSE_SECRET_KEY=<project secret key>
LANGFUSE_ENVIRONMENT=local
```

Never commit keys. Restart the backend after changing its environment. The base URL is explicit: the application does not default to Langfuse Cloud. HTTPS is required except on loopback. Set `LANGFUSE_ENABLED=false` to disable monitoring.

Settings → Performance monitoring → Test monitoring connection checks project authentication and submits a synthetic trace. Confirm ingestion in your self-hosted dashboard; a successful submission alone is not proof that the dashboard stored it. Self-hosted Langfuse must support the pinned SDK's OTLP ingestion endpoint. Ensure its reverse proxy permits `/api/public/otel/v1/traces` and `/api/public/projects`.

Traces correlate application requests with assistant generations, search, source retrieval, company-data access and simulation execution. Generations include model ID, token counts and provider-reported total cost when supplied; absent cost is not estimated. Spans include elapsed time, status, attempts, validation failures and counts. Background simulations retain parent request context. HTTP names use route templates rather than project IDs.

Prompts, replies, CSV contents, database records, queries, credentials and source URLs are excluded. Project references are hashed. Exception messages and stacks are excluded; only exception types are recorded. No automatic framework or HTTP instrumentation is enabled. Operational metrics and model identifiers remain visible to monitoring administrators.

Monitoring is optional and fails independently from the decision workflow. Missing keys or an unavailable endpoint do not prevent simulation. Local submission counters describe SDK submissions, not confirmed remote delivery. Monitor collector/export errors in server operations and verify traces in the dashboard.

The decision workflow uses business language. Credential and infrastructure controls remain in collapsed administrator configuration sections in Settings.
