# Integration & Extraction Plan

> How SimpleChat (and any future UI) talks to the Chief of Staff Runtime, and how this folder is kept
> **extraction-ready** so it can be lifted onto a separate platform with no code changes.

## Core rule

The runtime is a **network service**. UIs are **clients**. There is **no in-process coupling** in
either direction.

- ❌ SimpleChat must **not** `import` runtime modules, and the runtime must **not** import SimpleChat
  modules (e.g., `application/single_app/*`).
- ✅ All interaction goes through a documented HTTP contract (REST + SSE for streaming) — or, later, a
  message queue.

## The integration boundary (contract)

The runtime exposes a small, stable API. Draft surface (to be finalized when code lands):

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/agents` | Create / update an agent definition (from the Builder UI) |
| `GET` | `/v1/agents` | List agent definitions for the caller's tenant |
| `GET` | `/v1/agents/{id}` | Fetch a single definition |
| `POST` | `/v1/agents/{id}/invoke` | Run an agent against a user request (returns result / SSE stream) |
| `GET` | `/v1/catalog` | Return the vetted capability catalog (for the Builder UI) |

- **Auth:** the UI forwards the user's identity; the runtime performs delegated (OBO) Graph calls
  per invocation. The runtime holds its **own** app identity/config, not SimpleChat's.
- **Contract versioning:** path-prefixed (`/v1/`) so the UI and runtime can evolve independently.

## What lives where

| Concern | SimpleChat (UI) | Chief of Staff Runtime |
|--------|-----------------|------------------------|
| Chat / Teams tab rendering | ✅ | — |
| Agent Builder UI (compose agents) | ✅ (calls runtime API) | — |
| Agent Registry / Schema | — | ✅ |
| Orchestrator | — | ✅ |
| Shared Memory | — | ✅ |
| Tool Registry / Graph calls | — | ✅ |
| Capability Catalog definition | — | ✅ |

## Keeping this folder extraction-ready

Follow these so the folder can be moved to its own repo/platform cleanly:

1. **Self-contained tree** — everything (code, docs, config templates, IaC, CI) lives under
   `chief-of-staff-runtime/`.
2. **Own dependency manifest** — when code lands, declare `requirements.txt` / `pyproject.toml`
   here; do not rely on SimpleChat's.
3. **Config via environment only** — no shared `config.py`; ship a `.env.example` here.
4. **No relative imports crossing the folder boundary.**
5. **Own tests** under `chief-of-staff-runtime/tests/`.
6. **Own docs** under `chief-of-staff-runtime/docs/` (this folder).

## Extraction procedure (when the POC graduates)

1. Confirm no cross-boundary imports (grep for `application.single_app` / `single_app` references).
2. Create the new repo.
3. Move history:
   `git filter-repo --path chief-of-staff-runtime/ --path-rename chief-of-staff-runtime/:`
   (or `git subtree split -P chief-of-staff-runtime -b cos-runtime` then push to the new repo).
4. Stand up the runtime's own CI/CD and hosting (Container App / Function / AKS in GCC High).
5. Point SimpleChat at the deployed runtime base URL via configuration.

Because the boundary is a network contract, SimpleChat needs only a URL change — no code rewrite.
