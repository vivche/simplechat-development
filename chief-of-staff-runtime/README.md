# Chief of Staff Runtime

> **Status:** POC scaffold. Runnable skeleton in [`src/`](src/README.md); design docs in `docs/`.
> **Portability principle:** This folder is a **self-contained, decoupled component**. It must be removable from the SimpleChat repository and hostable on a separate platform without code changes. See [`docs/INTEGRATION.md`](docs/INTEGRATION.md).

## What this is

The **Chief of Staff Runtime** is the *product*: a governed orchestration service that runs
predefined and **dynamically created** AI agents against Microsoft 365 data (email, calendar,
Teams) on a user's behalf, with per-invocation least-privilege enforcement.

SimpleChat is treated as **one possible UI** (Teams tab + web) that talks to this runtime over a
network API. The runtime does **not** depend on SimpleChat, and SimpleChat integrates with it only
through a documented HTTP contract.

```
┌───────────────────────┐        HTTP / API contract        ┌─────────────────────────────┐
│  SimpleChat (UI)      │  ───────────────────────────────► │  Chief of Staff Runtime      │
│  Teams tab + web      │                                    │  (this folder — the product) │
│  Agent Builder UI     │  ◄─────────────────────────────── │  orchestration + governance  │
└───────────────────────┘        JSON responses / SSE        └─────────────────────────────┘
```

## Why decoupled

- The runtime is the differentiator and the reusable asset; the UI is replaceable.
- Governed **dynamic agent creation** (constrained to a vetted capability catalog) is the core value,
  and it should be hostable independently (Azure Container App / Function / AKS) regardless of which
  front end calls it.
- Keeping it self-contained now means extraction to a standalone repo later is a `git mv` +
  history filter, not a rewrite.

## Portability rules (enforced for this folder)

1. **No imports from `application/single_app/`** or any SimpleChat module. Ever.
2. **Own dependency manifest** (this folder declares its own `requirements.txt` / `pyproject.toml`
   when code lands — not SimpleChat's).
3. **Own configuration** via environment variables only (no shared `config.py`).
4. **Integration is over the network** (HTTP/REST or message queue), never in-process function calls
   into SimpleChat.
5. **All documentation lives here**, under `docs/`.

## Contents

| Path | Purpose |
|------|---------|
| [`docs/DESIGN_DISCUSSION.md`](docs/DESIGN_DISCUSSION.md) | Running record of the strategy discussion and decisions |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | The six components and how they fit together |
| [`docs/CAPABILITY_CATALOG.md`](docs/CAPABILITY_CATALOG.md) | Governed, capability-scoped agent-creation model + M365 catalog |
| [`docs/INTEGRATION.md`](docs/INTEGRATION.md) | The SimpleChat ↔ runtime boundary and extraction plan |
| [`docs/AUTH_FLOW.md`](docs/AUTH_FLOW.md) | Delegated OBO auth flow, per-invocation least privilege, consent model |
| [`docs/APP_REGISTRATION.md`](docs/APP_REGISTRATION.md) | `cos-runtime-api` identity record (IDs, scopes, consent status) — no secrets |
| [`docs/BACKLOG.md`](docs/BACKLOG.md) | Parked items (consent, Key Vault, integration, hardening) |
| [`src/`](src/README.md) | Azure Functions (Python) runtime skeleton + `/v1/*` API |
| [`infra/`](infra/) | Subscription-scope Bicep (GCC High) — Function App, ACR, Key Vault, storage, MI |
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | How to provision infra and deploy the runtime container via GitHub Actions |
| [`tests/`](tests/) | Skeleton smoke test (no network/consent required) |

## Not yet included

Cosmos DB is intentionally deferred to Phase 1 (`COS_USE_IN_MEMORY_STORES=true` for the Phase 0
governance proof). IaC and CI now live in [`infra/`](infra/) and the repo-root
`.github/workflows/cos-*.yml`; see [`DEPLOYMENT.md`](DEPLOYMENT.md). Remaining items are tracked in
[`docs/BACKLOG.md`](docs/BACKLOG.md). The runtime code under `src/` stays within the portability
rules above.
