# Chief of Staff Runtime — Architecture

> Design draft. Describes the six components and their boundaries. The runtime is decoupled from any
> UI and communicates only over a network contract (see [`INTEGRATION.md`](INTEGRATION.md)).

## Component overview

```
                          ┌──────────────────────────────────────────────┐
   UI (SimpleChat)        │            Chief of Staff Runtime             │
   ─────────────►  API ──►│                                                │
                          │   ┌────────────────────────────────────────┐  │
                          │   │  Chief-of-Staff Orchestrator (3)        │  │
                          │   └───┬───────────────┬──────────────┬─────┘  │
                          │       │               │              │        │
                          │  ┌────▼────┐   ┌──────▼──────┐  ┌────▼─────┐  │
                          │  │ Agent   │   │ Shared      │  │ Tool     │  │
                          │  │ Registry│   │ Memory (4)  │  │ Registry │  │
                          │  │  (1)    │   └─────────────┘  │  (5)     │  │
                          │  └────┬────┘                    └────┬─────┘  │
                          │       │ uses                         │        │
                          │  ┌────▼───────────────┐         Microsoft    │
                          │  │ Agent Definition   │          Graph        │
                          │  │ Schema (2)         │       (delegated OBO) │
                          │  └────────────────────┘                       │
                          └──────────────────────────────────────────────┘
   Agent Builder UI (6) lives in the UI layer and writes definitions to the runtime via the API.
```

## 1. Agent Registry

- Stores agent **definitions** (predefined shipped as config + dynamically created).
- CRUD over the API; every definition validated against the Agent Definition Schema (2).
- Enforces that catalog-constrained fields reference only entries that exist in the Tool Registry (5).
- Isolation: definitions are scoped to a tenant/owner.

## 2. Agent Definition Schema

The contract for an agent. Split into two zones:

**Free-form (no security review):**
- `name`, `description`
- `instructions` (system prompt)
- `examples`
- `output_format`
- `memory_scope` (which slice of shared memory the agent may read/write)

**Catalog-constrained (validated against the vetted catalog):**
- `capabilities[]` — references to Tool Registry entries (each carries a max Graph scope)
- `data_scope` — POC fixed to `self-only`
- `model` — selected from an approved model list

A dynamically created agent is valid **iff** every catalog-constrained field is a subset of the
vetted catalog. See [`CAPABILITY_CATALOG.md`](CAPABILITY_CATALOG.md).

## 3. Chief-of-Staff Orchestrator

- Entry point for a user request from the UI.
- Selects the appropriate agent(s), loads the definition from the Registry (1).
- Requests only the delegated scopes required by the agent's capabilities (least privilege per invocation).
- Executes tools via the Tool Registry (5), reads/writes Shared Memory (4), aggregates, returns result.
- Enforces gating: write capabilities (e.g., send email) require a **propose → human approves** step.

## 4. Shared Memory Service

- Per-user / per-tenant memory with **strict isolation** (no cross-user leakage).
- Agent access limited to its declared `memory_scope`.
- Candidate store: Cosmos DB (aligns with SimpleChat's existing datastore choice), but owned by the
  runtime — not shared in-process.

## 5. Tool Registry

- The **security-reviewed catalog**: each tool maps to a **maximum Graph scope** and an implementation.
- Defined and versioned by the platform owner (tier 1).
- Agents may only reference tools from here; the runtime never grants a scope beyond a tool's max.
- The union of all tool scopes = the finite superset that is admin-consented **once** in GCC High.

## 6. Agent Builder UI

- Lives in the UI layer (SimpleChat), not in the runtime.
- Lets a tenant admin / power user compose an agent by editing free-form fields and selecting a
  **subset** of catalog capabilities.
- Submits the definition to the runtime's Agent Registry API; the runtime validates and stores it.

## Security posture (summary)

- **Least privilege per invocation** — orchestrator requests only scopes the agent's capabilities need.
- **Delegated OBO** — actions run as the end user, scoped to `self-only` data in the POC.
- **Tool sandboxing** — tools can only reach their declared Graph scope; no arbitrary code/tools.
- **Governance & audit** — bounded scope superset, per-invocation logging, write actions gated.
