# Chief of Staff Runtime — Design Discussion

> Living document. Captures the reasoning behind the decoupled runtime and the governed
> dynamic-agent-creation model. Add dated entries as the discussion evolves.

## 1. The reframe

The insight that reshaped the project:

| Layer | Role | Notes |
|-------|------|-------|
| **SimpleChat** | UI | Teams tab + web front end. Replaceable. Not the product. |
| **Chief of Staff Runtime** | Product | Orchestration, memory, tool execution, governance. The reusable asset. |
| **Predefined agents** | Configuration | Example agents shipped as config, not hard-coded features. |
| **Dynamic agent creation** | Differentiator | Users compose new agents from a vetted capability catalog — *governed*, not open-ended. |

Context: this arose from Michael Miller's (architect) challenge about whether SimpleChat is the right
base versus copilot cli / Claude Code / OpenAI Codex, and the observation that "Scout started as a
skin on top of copilot cli." The conclusion: the value isn't the chat skin — it's a **governed
orchestration runtime that can safely create agents** in a regulated (GCC High) environment.

## 2. Why the runtime must be decoupled

- The UI is a commodity; the governed runtime is the durable IP.
- It should be hostable on its own platform (Container App / Function / AKS) independent of any UI.
- SimpleChat integrates *as a client*, over a network contract — see [`INTEGRATION.md`](INTEGRATION.md).
- Decoupling now keeps future extraction to a standalone repo cheap.

## 3. The six components

Detailed in [`ARCHITECTURE.md`](ARCHITECTURE.md):

1. **Agent Registry** — stores agent definitions (predefined + dynamically created).
2. **Agent Definition Schema** — the contract describing an agent (free-form + catalog-constrained parts).
3. **Chief-of-Staff Orchestrator** — routes a user request to the right agent(s), executes, aggregates.
4. **Shared Memory Service** — per-user/tenant memory with strict isolation.
5. **Tool Registry** — the vetted catalog of tools each mapped to a maximum Graph scope.
6. **Agent Builder UI** — (lives in SimpleChat) lets users compose agents by selecting a subset of the catalog.

## 4. The governance problem and the answer

**Problem:** We cannot offer agent creation where an admin/user "can do anything." In GCC High,
open-ended tool/permission selection is a non-starter (per-agent admin consent, unbounded audit).

**Answer — capability-scoped, two-tier model** (detailed in [`CAPABILITY_CATALOG.md`](CAPABILITY_CATALOG.md)):

- Split an agent definition into:
  - **Free-form** (safe, no security review): name, instructions, examples, output format, memory scope.
  - **Catalog-constrained** (from a vetted catalog): tools, permission/scope bundles, data scope
    (self-only), model choice.
- **Two tiers of ownership:**
  - *Platform owner* defines the security-reviewed **Capability Catalog** (tool → max Graph scope).
  - *Tenant admin / power user* composes agents by selecting a **subset** of the catalog.
  - *End user* runs the agent; the runtime enforces the delegated scope **per invocation**.
- **GCC High benefit:** admin-consent the **finite superset** of catalog scopes **once**. Every agent
  is a subset → no per-agent consent, bounded and auditable.

## 5. M365 capability catalog (POC scope)

Narrowed to email, calendar, and Teams. Full table in [`CAPABILITY_CATALOG.md`](CAPABILITY_CATALOG.md).
POC ships **read/summarize only**; write actions are **present but disabled** to demonstrate governance
(propose → human approves).

| Capability | Graph scope | POC status |
|-----------|-------------|-----------|
| Email — Read / Triage | `Mail.Read` | ✅ granted |
| Email — Draft | `Mail.ReadWrite` | deferred |
| Email — Send | `Mail.Send` | deferred, gated (propose → approve) |
| Calendar — Read / Prep | `Calendars.Read` | ✅ granted |
| Calendar — Schedule | `Calendars.ReadWrite` | deferred |
| Teams — Chat Read | `Chat.Read` | ✅ granted |

## 6. Recommended POC slice

**One custom agent, end-to-end, through all six layers.** Prove the full loop:
Builder UI → schema → registry → orchestrator → tool registry (read-only Graph) → shared memory →
result back to UI — with governance enforced. Write capabilities are shown as disabled to prove the
guardrails without shipping risk.

## 7. Decisions (resolved)

| # | Question | Decision |
|---|----------|----------|
| 1 | Hosting target | **Azure Functions** (GCC High). HTTP-triggered functions expose the `/v1/*` API. |
| 2 | Runtime language | **Python** (continuity with SimpleChat skills/patterns). |
| 3 | Memory store | **Cosmos DB** (aligns with SimpleChat), owned by the runtime, per-user isolation. |
| 4 | Capability Catalog storage | **Versioned config file in the repo** for the POC — a `capability_catalog.v1.json` under `chief-of-staff-runtime/config/`, loaded at startup, git-versioned (bump filename/`version` field to evolve). Move to a datastore only if runtime editing is needed later. |
| 5 | Auth flow | **Delegated On-Behalf-Of (OBO)** with the runtime as its own confidential client; per-invocation scope subsetting = the least-privilege enforcement point. App registration `cos-runtime-api` created. See [`AUTH_FLOW.md`](AUTH_FLOW.md). |

## 8. POC slice (agreed)

**One custom agent, end-to-end, through all six layers.** Builder UI → schema → registry →
orchestrator → tool registry (read-only Graph) → shared memory → result back to UI, with governance
enforced. Write capabilities shown as **disabled** to prove the guardrails without shipping risk.

## 10. Canonical end-to-end scenario (Michael's prompt)

The scenario we design against — a single natural-language request that exercises the whole platform:

> "Review my email and Teams chats for the last 60 days. Create an action list of things I may have
> missed or important follow-up. For all completed actions please send an email to the primary person
> in the discussion and ask them if I have satisfied all of my pending actions or concerns. Each email
> should summarize our interaction. Prior to sending this, have my chief of staff Gary the all-knowing
> agent review and then confirm any email summaries that I might find against my conversational style.
> Have my confidential assistant Georgia review all responses from these emails and route a summary to
> me in Teams for my comments and follow-up actions."

Decomposition (actor → capability → gate):

| # | Step | Actor | Capability / scope | R/W | Gate |
|---|------|-------|--------------------|-----|------|
| 1 | Read email + Teams chats, last 60 days | Chief of Staff | `email.read` (Mail.Read), `teams.chat.read` (Chat.Read) + chat message bodies (ChatMessage.Read) | R | — |
| 2 | Build action list of missed items / follow-ups | Chief of Staff | LLM synthesis | — | — |
| 3 | Draft summary emails to the primary person | Chief of Staff | `email.draft` (Mail.ReadWrite) | W | disabled in POC |
| 4 | **Gary** reviews drafts against my conversational style | reviewer sub-agent | reads drafts + style memory | R | — |
| 5 | Confirm summaries with me before sending | orchestrator | approval gate | — | **approval** |
| 6 | Send the emails | Chief of Staff | `email.send` (Mail.Send) | W | disabled + approval |
| 7 | **Georgia** reviews replies to those emails | monitor sub-agent | `email.read`, ongoing/async | R | — |
| 8 | Route a summary to me in Teams | Georgia | Teams message send (ChatMessage.Send) | W | — |

Why it matters: every **write** is a capability that is (a) catalog-gated and (b) currently disabled,
and can only ever run after a **human approval** exists. This is the "ambitious intent, bounded
authority" demo — the user can ask for anything; the runtime can read and reason freely but physically
cannot send until the tenant enables the capability *and* a human approves the specific action.

## 11. Cross-review reconciliation (second Copilot)

An independent review converged on the same shape (SimpleChat = UI; the real product = an agent
**platform**: registry + memory + tool registry + workflow engine; Chief of Staff = the first agent
package). Points of agreement, one gap, and two refinements:

- **Agreement:** dynamic agent creation is the differentiator; named agents (Gary/Georgia) are separate
  collaborating agent definitions; "no code, no deployment" self-service agent creation is the goal.
- **Gap in the other review:** it under-specified **governance**. Its "power user creates an agent, no
  admin involvement" is only safe *because* the capability catalog pre-bounds what any agent can ever
  do. Self-service creation = choosing a **subset of an already-consented catalog**; a user can never
  select a capability that wasn't vetted. In GCC High this mechanism is the whole point and must be
  stated explicitly, not glossed.
- **Refinement 1 — split "human-in-the-loop" into two things:**
  - A **reviewer agent** (Gary checking style) *is* a sub-agent — model-driven, promptable, legitimate.
  - An **approval gate** (human confirms before send) is **NOT** an agent. It is a platform-enforced
    control primitive: an agent's behavior is soft/promptable, but the gate must be *hard* — the `send`
    capability stays blocked until a recorded human approval exists, and no prompt can bypass it.
- **Refinement 2 — "Workflow Engine":** the other review's Phase 2 (agent collaboration) is our known
  gap: today the orchestrator runs single agents; multi-agent delegation (Chief of Staff → Gary/Georgia)
  needs an orchestration plan / workflow layer.

**Approval gate decision (POC):** enforcement is real but the collection mechanism is simple — post a
message to Teams for an approver (who may be the user themselves) to approve; `send` is blocked until
that approval is recorded. It is a system primitive whose *UI* is a Teams notification, not a
configurable/promptable agent.

## 12. Revised roadmap (phased)

Deploy phases sequentially; each builds on the previous.

| Phase | Goal | Scope |
|-------|------|-------|
| **Phase 0** (current) | Prove the governed loop end-to-end | One agent: auth (OBO) → catalog → read-only Graph → memory → result. Writes present but disabled. Deploy to GCC High. |
| **Phase 1** | Dynamic agent creation | Builder UI + `POST /v1/agents`; users compose agents from the catalog subset, no admin, no deploy. |
| **Phase 2** | Agent collaboration (workflow engine) | Chief of Staff delegates to sub-agents (Gary/Georgia); orchestration plan; async/durable monitoring (Georgia watching replies); approval gate primitive. |
| **Phase 3** | Chief-of-Staff templates | Ship starter packages (Chief of Staff, Meeting Prep, Security Review, etc.) as configuration on the platform. |

New capabilities the scenario surfaces (tracked in [`BACKLOG.md`](BACKLOG.md)): `teams.chat.message.read`
(ChatMessage.Read), `teams.message.send` (ChatMessage.Send), plus the already-stubbed `email.draft` /
`email.send`; configurable read window (60 days vs 48h default).

## 13. Decision log

| Date | Decision |
|------|----------|
| 2026-07-05 | Create `chief-of-staff-runtime/` as a self-contained, portable folder; all docs live here; no code coupling to SimpleChat; integration over a network contract only. |
| 2026-07-05 | Hosting = Azure Functions; language = Python; memory = Cosmos DB; catalog = versioned config file in repo; POC slice = one custom agent end-to-end, read-only, writes disabled. |
| 2026-07-06 | Auth = delegated OBO with the runtime as its own confidential client; per-invocation scope subsetting is the least-privilege enforcement point. App registration `cos-runtime-api` created. |
| 2026-07-06 | Adopt Michael's prompt as the canonical end-to-end scenario (§10). |
| 2026-07-06 | Reconciled with second Copilot review: agree on platform framing; flag that self-service agent creation is safe *only* because of the catalog; split HITL into reviewer-agent (soft) vs approval-gate (hard platform primitive). |
| 2026-07-06 | POC sequencing = Phase 0 (governed read-only loop, deploy first) → Phase 1 (dynamic creation) → Phase 2 (collaboration/workflow + approval gate) → Phase 3 (templates). |
| 2026-07-06 | Approval gate for POC = enforcement is a hard primitive; collection mechanism is a Teams approval message (approver may be the user); `send` blocked until approval recorded. |
