# Chief of Staff Runtime Integration (Agent Builder)

> How SimpleChat connects to the **external Chief of Staff Runtime** so users can compose personal
> agents from a vetted capability catalog and run them — without SimpleChat holding any Microsoft
> Graph permissions for this feature.
>
> The Agent Builder now includes a **Test** pane backed by a **single-turn planner** (the
> `cos_planner` package) that turns a natural-language request into concrete, approval-gated
> actions, plus an optional **multi-agent reviewer handoff** that lets a second agent revise the
> proposed write actions before the approval preview.

## Overview

The runtime is a **separate network service** (an Azure Function). SimpleChat is a **client**:

1. The browser calls same-origin SimpleChat endpoints (`/api/cos/*`).
2. SimpleChat mints a **runtime-audience** access token for the signed-in user (delegated, silent
   MSAL acquisition against the runtime's exposed scope) and **forwards** the call to the runtime.
3. The runtime validates the token, derives the user identity from its claims, and performs
   **least-privilege On-Behalf-Of** Microsoft Graph calls per invocation.

This preserves the "UI is a client" boundary — there is no in-process coupling, and the runtime
token never reaches the browser.

```
Browser ──/api/cos/*──► SimpleChat ──Bearer(aud=cos-runtime)──► Chief of Staff Runtime ──OBO──► Graph
```

## Components added

| File | Purpose |
|------|---------|
| `config.py` | Adds `COS_RUNTIME_BASE_URL`, `COS_RUNTIME_SCOPE`, `COS_RUNTIME_TIMEOUT_SECONDS`, `ENABLE_COS_RUNTIME_AGENTS`. |
| `functions_cos_runtime.py` | Runtime client: mints the runtime token (`get_cos_runtime_token`) and calls the runtime REST API (catalog, agents CRUD, invoke). |
| `cos_planner/` | Portable, host-agnostic planner package (LLM planner + ports). Contains **no** SimpleChat imports so it can be extracted later. Turns a user message + gathered context into proposed actions and an approval preview. |
| `functions_cos_planner.py` | Host binding for `cos_planner`: `run_planner_turn(...)` wires the LLM and runtime ports, loads the primary agent and (optionally) a reviewer agent, and runs a planner turn. |
| `route_backend_cos_agents.py` | Same-origin proxy routes under `/api/cos/*` (forward to the runtime) **and** the planner endpoint `POST /api/cos/planner/chat`. |
| `route_frontend_cos_agents.py` | Serves the Agent Builder page at `/cos-agents`. |
| `templates/cos_agent_builder.html` | Agent Builder UI (Build + Test tabs; the Test pane has an Agent selector and an optional **Reviewer** selector). |
| `static/js/cos/cos-agent-builder.js` | Agent Builder (Build) front-end logic; talks only to `/api/cos/*`. |
| `static/js/cos/cos-planner-chat.js` | Test pane front-end: sends planner turns, renders the reviewer verdict card and the approval preview. |
| `app.py` | Registers the two new blueprints (`frontend_cos_agents`, `backend_cos_agents`). |

## Token acquisition (why it works this way)

`get_cos_runtime_token()` calls the existing `get_valid_access_token(scopes=[COS_RUNTIME_SCOPE])`,
which uses MSAL silent acquisition (session cache + refresh token).

- The runtime scope is acquired as a **separate token** from the Graph login scopes. AAD does not
  allow mixing resources in one token request, so the runtime scope is **not** added to the shared
  `SCOPE` list.
- Silent acquisition succeeds once consent for the runtime API exists (see prerequisite below).

## Prerequisites (one-time, per environment)

1. **App registration permission.** SimpleChat's app registration must have a delegated permission
   to the runtime's `access_as_user` scope:
   - Entra → App registrations → *SimpleChat app* → API permissions → Add a permission → My APIs →
     `cos-runtime-api` → Delegated → `access_as_user` → **Grant admin consent**.
   - (Equivalently, add SimpleChat's client ID to the runtime app's *Expose an API →
     Authorized client applications* for `access_as_user`.)
2. **Runtime Graph consent.** The runtime app's Graph permissions must be admin-consented in the
   tenant (already done for the POC).

Without step 1, `get_cos_runtime_token()` returns `401` with a "grant consent" message.

## Configuration

Set in `.env` (see `example.env`):

```
ENABLE_COS_RUNTIME_AGENTS="true"
COS_RUNTIME_BASE_URL="https://func-cos-runtime-dev.azurewebsites.us/api"
COS_RUNTIME_SCOPE="api://<runtime-client-id>/access_as_user"
COS_RUNTIME_TIMEOUT_SECONDS="30"
```

- `COS_RUNTIME_BASE_URL` — include the `/api` suffix for an Azure Functions host.
- `COS_RUNTIME_SCOPE` — the runtime app's exposed scope (audience of the forwarded token).

## Proxy API surface

All routes require an authenticated SimpleChat session and forward to the runtime as the user.

| SimpleChat route | Runtime route | Purpose |
|------------------|---------------|---------|
| `GET /api/cos/catalog` | `GET /v1/catalog` | Capability catalog for the Builder |
| `GET /api/cos/agents` | `GET /v1/agents` | List the user's agents |
| `POST /api/cos/agents` | `POST /v1/agents` | Create an agent |
| `GET /api/cos/agents/<id>` | `GET /v1/agents/{id}` | Fetch one agent |
| `PUT /api/cos/agents/<id>` | `PUT /v1/agents/{id}` | Update an agent |
| `DELETE /api/cos/agents/<id>` | `DELETE /v1/agents/{id}` | Delete an agent |
| `POST /api/cos/agents/<id>/invoke` | `POST /v1/agents/{id}/invoke` | Run an agent |
| `POST /api/cos/planner/chat` | *(uses `invoke` + approvals)* | Run one planner turn: gather context, propose actions, optional reviewer pass, return an approval preview. |

`owner_id` is always derived from the token by the runtime — never sent from the browser.

## Planner turn (Test pane)

`POST /api/cos/planner/chat` accepts `{ agent_id, message, history?, reviewer_agent_id? }` and runs
one turn of `run_planner_turn(...)`:

1. The runtime gathers read context for the primary agent (email/calendar/Teams) via `invoke`.
2. The LLM planner proposes concrete actions from the user's wording (draft vs. send, schedule,
   Teams message), filling parameters from the gathered context (e.g. resolving a reply recipient
   from a message's `from`/`toRecipients`).
3. **Optional reviewer handoff:** if `reviewer_agent_id` is set (and differs from the primary), a
   second agent reviews the proposed write actions and may revise them — but can only re-emit the
   **same** capability types (no new powers). Review errors fail open; the human approval gate
   still protects every write.
4. Write/send actions are returned as an **approval preview** — nothing is executed until the user
   approves, which triggers the runtime's approval endpoint.

The `cos_planner` package is deliberately free of SimpleChat imports; `functions_cos_planner.py` is
the only host binding, so the planner remains portable to another host.

## Using it

1. Complete the prerequisites and configuration, then restart SimpleChat.
2. Navigate to **`/cos-agents`**.
3. **Build** tab: compose an agent (name, instructions, capabilities from the catalog) and Save.
4. **Test** tab: pick the agent, optionally pick a **Reviewer** agent, and send a request. Review
   the reviewer verdict (if any) and the approval preview, then approve to execute write actions.

> A navigation entry is intentionally not auto-injected to avoid changing the shared nav layout.
> Link to `/cos-agents` from wherever is appropriate for your deployment (optionally gated on
> `ENABLE_COS_RUNTIME_AGENTS`).

## Security notes

- The runtime token is minted and used **server-side only**; the browser sees just SimpleChat JSON.
- Proxy routes are `@login_required` + `@user_required`; state-changing calls are same-origin
  (SimpleChat's existing CSRF/origin enforcement applies).
- SimpleChat gains **no** Graph permissions for this feature — all Graph access is the runtime's,
  scoped per invocation via OBO.
