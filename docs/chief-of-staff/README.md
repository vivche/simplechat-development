# AI Chief of Staff for Delivery Teams — POC Plan & Recommendations

> Reference document for the "AI Chief of Staff" proof of concept built on SimpleChat.
> Branch: `feature/ai-chief-of-staff-phase1`
> Status: Implemented (POC). Sample data is the default; a Microsoft Graph data source is
> implemented behind the `chief_of_staff_data_source` setting (see
> [DATA_SOURCES.md](DATA_SOURCES.md)).

---

## 1. POC Goal

An "AI Chief of Staff for Delivery Teams" that helps a user stay on top of their work by:

1. **Summarizing** emails, Teams messages, and meetings.
2. **Identifying and tracking action items**.

Target experience (inspired by Microsoft Scout): open the app and immediately see a
"What's on deck?" dashboard with live briefing tiles + action cards — no typing required.

### Phase 1 capabilities (implemented on sample data)

The single briefing call now covers all of the following, rendered as cards on the dashboard:

| Capability | Where it shows |
|---|---|
| Reviews emails | Source input + summary |
| Reviews Teams messages | Source input + summary |
| Reviews calendar / meetings | Source input + summary |
| Prioritizes work | **Top Priorities** (ranked) |
| Tracks action items | **Action Items** (owner, due, source, priority) |
| Notices commitments you made | **Your Commitments** (what you promised, to whom, due) |
| Prepares meeting briefings | **Meeting Briefings** (objective, prep bullets, attendees) |
| Follows up on open items | **Follow-ups & Open Items** (waiting-on, age, suggested nudge) |

All six sections come from one LLM call that returns a structured JSON briefing; the parser
returns every section as a safe default (empty list) when the model output is missing or
malformed.

**Layout:** Today's Summary and Top Priorities stay visible at the top for an at-a-glance
view; Action Items, Your Commitments, Meeting Briefings, and Follow-ups are grouped into
Bootstrap tabs (each with a live count badge) to keep the page compact.

---

## 2. GCC High (GCC-H) Reality — READ FIRST

The POC runs in **GCC High**, a sovereign/isolated Microsoft cloud.

### What works
- SimpleChat **already supports GCC-H**. Relevant config in `application/single_app/config.py`:
  - `AZURE_ENVIRONMENT=usgovernment` (values: `public`, `usgovernment`, `custom`)
  - `CUSTOM_GRAPH_URL_VALUE`, `CUSTOM_GRAPH_AUTHORITY_URL_VALUE`
  - Auth/Graph paths switch to `.us` sovereign endpoints (`graph.microsoft.us`, `login.microsoftonline.us`).
- Reading mail/calendar via **delegated Microsoft Graph** works in GCC-H.

### The hard boundary
- A GCC-H-registered app can **only** access mailboxes/Teams that live in the **same GCC-H tenant**.
- It **cannot** reach commercial-cloud (`@microsoft.com`) mail or Teams — the clouds are
  cross-tenant isolated (different Graph endpoints, no cross-cloud delegated tokens).

### Implication for testing
- ✅ Test against a **GCC-H tenant mailbox/Teams** (a GCC-H test account, or seeded test data).
- ❌ Do **not** expect a GCC-H app to read your corporate commercial `@microsoft.com` data.
- If a commercial-data demo is required, that needs a **separate app registration in the
  commercial cloud** — a different deployment, not the GCC-H one.

**Action:** provision one or more GCC-H test users with sample emails/meetings for the POC.

---

## 2.5 DECISION: Mock Data for the POC (no mailbox available)

**Confirmed constraint:** the current GCC-H environment has **no Teams or Outlook mailbox**
available, and there is **no other cloud** to test against.

**Decision:** the POC will run on **mock / sample data** until a suitable environment (a
GCC-H test mailbox, or a commercial-cloud deployment) becomes available.

### The abstraction that makes this safe
Build the Chief of Staff against a **`BriefingSource` interface** so the data source is
pluggable. Real Graph drops in later with no rework of the agent, dashboard, or action-item
tracking.

```
BriefingSource (interface)
 ├── SampleBriefingSource   → JSON fixtures / seeded Cosmos items   (NOW - POC)
 └── GraphBriefingSource    → delegated Microsoft Graph             (LATER - when mailbox exists)
```

- Selection driven by a setting, e.g. `chief_of_staff_data_source` = `sample` | `graph`.
- `SampleBriefingSource` reads realistic fake emails / meetings / Teams messages from bundled
  JSON fixtures (and optionally supports upload/paste of user-provided sample content).
- The agent, summarization, action-item extraction, dashboard, and Cosmos storage are all
  **identical** regardless of source.

### POC data approach
- **Fixtures only.** Bundled JSON fixtures of realistic emails, meetings, and Teams messages
  so the dashboard auto-populates instantly on load — no typing, no upload, fully automated
  (matches Scout's "it's already done for you" experience).
- No upload/paste for the POC (deliberately kept out to preserve the pure-automation demo).

### Switch-over path (implemented)
The `GraphBriefingSource` is now implemented (`load_graph_briefing_data()` in
`functions_chief_of_staff.py`) using the existing `MSGraphPlugin`. Set
`chief_of_staff_data_source = graph` to activate it — no UI or agent changes required. It has
not yet been validated against a live GCC-H mailbox; if the live fetch fails the app falls back
to sample data so the dashboard still renders. See [DATA_SOURCES.md](DATA_SOURCES.md) for the
full design, scopes, and normalization details.

---

## 3. The Key Architecture Decision: what "automatic" means

Two flavors of "automatically obtain data," with very different cost/risk:

| Mode | How it works | Auth needed | POC fit |
|---|---|---|---|
| **In-session auto-fetch** (recommended) | On dashboard open, the app immediately calls Graph with the user's delegated token and shows summaries — feels automatic, no typing. | Existing delegated OAuth (already wired) | ✅ Low risk |
| **True background ingestion** | A timer/worker pulls mail/Teams even when the user is offline, pre-computes briefings. | `offline_access` refresh tokens stored securely, OR application permissions (admin consent, reads all mailboxes — large security surface) | ⚠️ Defer past POC |

**Recommendation:** build **in-session auto-fetch** first. It delivers the Scout experience
using the delegated token flow that already exists, with none of the app-level-permission or
token-storage risk. True background pre-computation is a phase-2 enhancement.

---

## 4. What Already Exists vs. What to Build

### Already there (reuse)
- `semantic_kernel_plugins/msgraph_plugin.py` (`MSGraphPlugin`) — read mail, read/create
  calendar events, send mail (with a draft/approve "pending actions" flow) under delegated auth.
- Graph capability definitions: `functions_msgraph_operations.py`
  (`MSGRAPH_CAPABILITY_DEFINITIONS`): get_my_profile, get_my_timezone, get_my_events,
  create_calendar_invite, get_my_messages, mark_message_as_read, send_mail, search_users,
  get_user_by_email, list_drive_items, get_my_security_alerts.
- Pending actions (draft/approve/send): `functions_msgraph_pending_actions.py` +
  Cosmos `msgraph_pending_actions` container + `route_backend_msgraph_pending_actions.py`.
- Agent + plugin loading: `semantic_kernel_loader.py`
  (`initialize_semantic_kernel`, `load_single_agent_for_kernel`, `load_agent_specific_plugins`).
- Agents directory UI ("Find your next AI partner"): `route_frontend_agents.py`,
  `templates/agents.html`, `static/js/agents_catalog.js`.
- Deep-link pattern `chatWithAgent()` → `POST /api/user/settings/selected_agent` → `/chats`.
- Feature-flag + nav pattern: `@enabled_required('...')`, `templates/_sidebar_nav.html`,
  flags in `functions_settings.py` `get_settings()`.

### Gaps to build (POC = mock data)
1. **`BriefingSource` abstraction** with `SampleBriefingSource` (fixtures) now and
   `GraphBriefingSource` (delegated Graph) later. Selected via `chief_of_staff_data_source`.
2. **Sample data fixtures** — realistic fake emails / meetings / Teams messages (JSON).
3. **Chief of Staff global agent** (template) with a new action-item plugin (Graph plugin added
   later when the source switches to `graph`).
4. **Chief of Staff dashboard** page (route + template + JS + feature flag).
5. **Briefing API** — on dashboard load, read from the active `BriefingSource` (sample now) and
   return summarized cards.
6. **Action-item plugin + Cosmos `action_items` container** — the "track" half of goal #2.
7. **`GraphBriefingSource` + Teams messages** — real mail/calendar via `MSGraphPlugin`;
   Teams messages read via `/me/chats` + per-chat `/messages` (best effort). Implemented
   behind the `chief_of_staff_data_source = graph` setting; see
   [DATA_SOURCES.md](DATA_SOURCES.md). Live GCC-H validation still pending.

---

## 5. Recommended Build Order (mock-first)

```
1. BriefingSource interface + SampleBriefingSource + JSON fixtures      [done]
2. Briefing API                          (GET /api/chief-of-staff/briefing)   [done]
3. Chief of Staff global agent template  (action-item plugin wired)     [partial]
4. Dashboard page                        (Scout-style cards + live tiles)     [done]
5. Action-item plugin + Cosmos container (extract / store / list / update)    [deferred]
--- live data ---
6. GraphBriefingSource                    (delegated Graph; flip chief_of_staff_data_source)  [done, untested live]
7. Teams messages                         (Chat.Read scope + new operations)  [done, untested live]
```

Items 1–4 delivered the demoable "open → auto-summary" loop on mock data. Items 6–7 add the
live Microsoft Graph data source behind the `chief_of_staff_data_source` setting and require no
UI/agent rework. Item 5 (persistent action-item tracking in Cosmos) remains deferred.

---

## 6. UI Proposal — Scout-style Chief of Staff Dashboard

New sidebar item **"Chief of Staff"** (below Agents), gated by `enable_chief_of_staff_dashboard`.

### Layer 1 — Action cards (deep-link launchers)
Mirror the existing `chatWithAgent()` pattern: each card sets the Chief-of-Staff agent as
selected, stashes a preset prompt, and redirects to `/chats` to auto-send. Example cards:
- 📧 Summarize unread emails
- 🎯 What should I focus on?
- 📅 Prep me for my next meeting
- ✅ Show my open action items

> Note: the chat view has **no** preset-prompt param today. Add a `sessionStorage` handoff read
> by `static/js/chat/chat-global.js` on load (minimal change).

### Layer 2 — Live briefing panel (the "automatic" part)
Above the cards, call the briefing API on load and render live tiles
("3 urgent emails", "Next: Standup in 40 min", "2 commitments due today"). This is what makes
it feel like a Chief of Staff rather than a prompt menu.

---

## 7. Files to Create / Modify

See [FILES_CHANGED.md](FILES_CHANGED.md) for the authoritative, as-built list of every file
added and modified for this POC. The table below is the original plan for reference.

| File | Action | Purpose |
|---|---|---|
| `application/single_app/functions_chief_of_staff.py` | **new** | `BriefingSource` interface + `SampleBriefingSource` (+ `GraphBriefingSource` later) |
| `application/single_app/static/chief_of_staff/sample_data/*.json` | **new** | Mock emails / meetings / Teams fixtures |
| `application/single_app/route_frontend_chief_of_staff.py` | **new** | `/chief-of-staff` page route |
| `application/single_app/templates/chief_of_staff_dashboard.html` | **new** | Dashboard template (extends `base.html`) |
| `application/single_app/static/js/chief_of_staff/dashboard.js` | **new** | Card handlers + briefing render |
| `application/single_app/route_backend_chief_of_staff.py` | **new** | `GET /api/chief-of-staff/briefing` |
| `application/single_app/semantic_kernel_plugins/action_item_plugin.py` | **new** | Extract/track action items |
| `application/single_app/functions_settings.py` | modify | Add `enable_chief_of_staff_dashboard` + `chief_of_staff_data_source` (`sample`/`graph`) |
| `application/single_app/templates/_sidebar_nav.html` | modify | Add nav link (flag-gated) |
| `application/single_app/templates/admin_settings.html` | modify | Add admin toggle + data-source selector |
| `application/single_app/config.py` | modify | Bump `VERSION`; add `action_items` container |
| `application/single_app/static/js/chat/chat-global.js` | modify | Read `sessionStorage` preset prompt on load |

---

## 8. Conventions to Follow (from CLAUDE.md / repo instructions)

- Every Flask route: `@swagger_route(security=get_auth_security())` after `@app.route`,
  before auth decorators. Decorator order:
  `@bp.route` → `@swagger_route` → `@login_required` → `@user_required`/`@admin_required` →
  `@enabled_required('flag')`.
- Frontend routes: **always** `sanitize_settings_for_user()` before `render_template`/`jsonify`
  (EXCEPT admin routes).
- Files start with a filename comment; use `log_event` (not `print`); 4-space indent.
- Frontend JS must be **local static assets** (no CDN, no dynamic imports). Use Bootstrap
  `d-none` (not `display:none`) and Bootstrap alerts (not `alert()`).
- Version: bump 3rd segment of `VERSION` in `config.py` on code changes.
- Functional tests in `functional_tests/` with version headers.
- Feature docs in `docs/explanation/features/`; fixes in `docs/explanation/fixes/`;
  release notes in `docs/explanation/release_notes.md`.

---

## 9. Decisions Made / Still Open

**Decided:**
- ✅ **Data source:** pluggable via `chief_of_staff_data_source` (`sample` | `graph`). Sample
  fixtures are the default for the POC; the live `GraphBriefingSource` is implemented and
  activates when the setting is `graph` (live GCC-H validation still pending).
- ✅ **Dashboard placement:** dedicated "Chief of Staff" page (Scout-style).
- ✅ **Agent model:** single Chief of Staff agent (no multi-agent orchestration for phase 1).

- ✅ **Mock content:** **fixtures only** (no upload/paste) — preserves the pure-automation,
  "open and it's ready" Scout experience.
- ✅ **First-demo scope:** fixtures cover **all three sources** (emails, meetings, Teams
  messages) so the automated briefing is complete from day one.

*(No open decisions remaining — cleared to build.)*

---

## 10. Deferred / Out of Scope for Phase 1

- Multi-agent orchestration mesh (`agent_orchestrator_groupchat.py`,
  `agent_orchestrator_magnetic.py`) — scaffolding exists but is **disabled**; a single Chief of
  Staff agent is sufficient and simpler for the POC.
- True unattended background ingestion (offline_access refresh tokens / app permissions).
- Persistent action-item tracking in a Cosmos `action_items` container (extract/store/list/
  update). The briefing surfaces action items per run, but they are not yet persisted.
- Cross-cloud (commercial `@microsoft.com`) access from the GCC-H app (not possible).
- Live validation of the Microsoft Graph data source against a GCC-H mailbox/Teams tenant
  (implemented but untested — see [DATA_SOURCES.md](DATA_SOURCES.md)).
