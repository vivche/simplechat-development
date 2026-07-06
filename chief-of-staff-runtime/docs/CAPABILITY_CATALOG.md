# Capability Catalog & Governed Agent Creation

> The heart of the governance model: users create agents, but only by composing from a
> **vetted capability catalog**. This document defines the model and the initial M365 catalog.

## Why not open-ended agent creation

Letting an admin/user pick "any tool, any permission" is unacceptable in a regulated (GCC High)
environment:

- Each new permission combination could require **separate admin consent**.
- The audit surface becomes **unbounded** — you can't reason about what any agent can do.
- Least-privilege review can't scale to arbitrary agents.

## The two-tier, capability-scoped model

### Tier 1 — Platform owner (security-reviewed)

Defines the **Capability Catalog**: a fixed set of capabilities, each mapping a tool to its
**maximum Graph scope**. This is the only place scopes are introduced.

The **union of all catalog scopes** is a finite superset that is **admin-consented once**.

### Tier 2 — Tenant admin / power user (composition)

Builds an agent by:

- Filling **free-form** fields (name, instructions, examples, output format, memory scope) — no
  security review needed.
- Selecting a **subset** of catalog capabilities — validated automatically.

Because every agent's scopes are a **subset** of the already-consented superset, **no per-agent
consent** is required, and audit stays bounded.

### End user — execution

Runs the agent. The runtime enforces the delegated scope **per invocation** (least privilege),
acting as the user (OBO) over `self-only` data in the POC.

## Agent definition zones

| Zone | Fields | Review needed? |
|------|--------|----------------|
| Free-form | name, instructions, examples, output_format, memory_scope | No |
| Catalog-constrained | capabilities[], permission/scope bundle, data_scope (self-only), model | Validated against catalog |

## Initial M365 Capability Catalog (POC)

Narrowed to **email, calendar, Teams**. The POC ships **read/summarize only**; write capabilities are
**present but disabled** to demonstrate governance without shipping risk.

| Capability | Description | Max Graph scope | POC status | Gating |
|-----------|-------------|-----------------|-----------|--------|
| **Email — Read / Triage** | Read & summarize inbox, prioritize | `Mail.Read` | ✅ granted | none |
| **Email — Draft** | Compose draft replies (not sent) | `Mail.ReadWrite` | deferred | — |
| **Email — Send** | Send email | `Mail.Send` | deferred | propose → human approves |
| **Calendar — Read / Prep** | Read events, prep briefings | `Calendars.Read` | ✅ granted | none |
| **Calendar — Schedule** | Create / modify events | `Calendars.ReadWrite` | deferred | propose → human approves |
| **Teams — Chat Read** | Read recent chats, summarize | `Chat.Read` | ✅ granted | none |

> ✅ granted = delegated scope already consented on the Flask app registration.
> deferred = catalog entry defined but not enabled/consented in the POC.

## Enforcement rules

1. An agent definition is **valid only if** every capability references a catalog entry.
2. The runtime never requests a scope beyond a capability's declared **max Graph scope**.
3. `data_scope` is fixed to `self-only` for the POC.
4. Write capabilities require a **propose → human approves** step before execution.
5. Every invocation logs: agent id, user, capabilities used, scopes requested, and outcome.

## Extending the catalog

New capabilities are added **only by the platform owner** (Tier 1) after security review, which may
expand the consented scope superset. Tenant/power users can never introduce a new scope.
