# AI Chief of Staff — Pluggable Data Sources

> How the Chief of Staff briefing gets its input data.
> Branch: `feature/ai-chief-of-staff-phase1`
> Companion to [README.md](README.md) (POC plan) and [FILES_CHANGED.md](FILES_CHANGED.md).

The briefing logic is decoupled from *where* the emails, meetings, and Teams messages come
from. A single setting selects the active data source, and every downstream step (prompt
building, the LLM call, JSON parsing, the dashboard, and the API) is identical regardless of
source.

---

## 1. The setting

| Setting | Values | Default | Where |
|---|---|---|---|
| `chief_of_staff_data_source` | `sample` \| `graph` | `sample` | `functions_settings.py` (`get_settings()`) |

- `sample` — use the bundled JSON fixtures (the POC default; no configuration required).
- `graph` — pull the signed-in user's live mail, calendar, and Teams chats from Microsoft
  Graph.

The setting is read lazily inside `load_briefing_data()` so the pure data/parsing logic can be
imported and unit-tested without the full Flask/Azure runtime.

---

## 2. Dispatch flow

```
generate_briefing(user_id)
  └─ load_briefing_data(user_id)                 # reads chief_of_staff_data_source
       ├─ 'sample' → load_sample_briefing_data()  # bundled fixtures
       └─ 'graph'  → load_graph_briefing_data(user_id)
                        └─ on any failure, falls back to load_sample_briefing_data()
```

Both providers return the **same dict shape**, so nothing downstream needs to change:

```json
{
  "emails":         [ { "id", "from", "to", "received", "subject", "body" } ],
  "meetings":       [ { "id", "title", "start", "end", "attendees", "notes" } ],
  "teams_messages": [ { "id", "channel", "from", "sent", "message" } ]
}
```

If the setting can't be read, or the Graph fetch raises, the app defaults to sample data so the
dashboard always renders.

---

## 3. Sample provider (`load_sample_briefing_data`)

Reads three JSON fixtures from
`application/single_app/static/chief_of_staff/sample_data/`:

- `emails.json`
- `meetings.json`
- `teams_messages.json`

A missing or malformed fixture logs a warning and yields an empty list for that source rather
than failing the whole briefing.

---

## 4. Microsoft Graph provider (`load_graph_briefing_data`)

> **Status:** implemented, **not yet validated against a live GCC-H mailbox/Teams tenant.**
> The provider reuses SimpleChat's existing `MSGraphPlugin`, which acquires a delegated token
> for the signed-in user from the MSAL session cache and handles pagination and error shaping.

### Sources fetched

| Source | Graph call | Scope | Notes |
|---|---|---|---|
| Emails | `MSGraphPlugin.get_my_messages` → `GET /me/messages` | `Mail.Read` | Newest first; selects `id,subject,from,receivedDateTime,bodyPreview`. |
| Meetings | `MSGraphPlugin.get_my_events` → `GET /me/calendarView` | `Calendars.Read` | Windowed to now ± 48h; selects `id,subject,start,end,attendees,bodyPreview,organizer`. |
| Teams | `GET /me/chats` then per-chat `GET /me/chats/{id}/messages` | `Chat.Read` | Best effort; a few recent chats, a few recent messages each. |

Each source is fetched in its own `try/except`, so one failure (for example, a missing
`Chat.Read` consent) still lets the others populate the briefing. System Teams messages
(membership changes, etc.) and empty-body messages are skipped.

### Windows / limits

Tunable constants at the top of `functions_chief_of_staff.py`:

| Constant | Default | Meaning |
|---|---|---|
| `GRAPH_LOOKBACK_HOURS` | 48 | How far back to scan mail/Teams. |
| `GRAPH_LOOKAHEAD_HOURS` | 48 | How far forward to scan the calendar. |
| `GRAPH_MAX_EMAILS` | 15 | Max messages fetched. |
| `GRAPH_MAX_MEETINGS` | 10 | Max calendar events fetched. |
| `GRAPH_MAX_CHATS` | 5 | Max chats scanned for Teams messages. |
| `GRAPH_MAX_MESSAGES_PER_CHAT` | 5 | Max messages read per chat. |

### Normalization

Pure, unit-tested helpers map Graph JSON into the fixture shape (HTML bodies are stripped to
short plain text):

- `_normalize_graph_emails(value)`
- `_normalize_graph_meetings(value)`
- `_normalize_graph_teams(messages, channel)`

These are covered by `functional_tests/test_chief_of_staff_briefing.py`
(`test_graph_normalizers`).

---

## 5. Enabling the Graph source

1. Ensure the app's Entra registration has delegated consent for `Mail.Read`,
   `Calendars.Read`, and `Chat.Read`, and that the signed-in user's MSAL session holds those
   scopes.
2. Set `chief_of_staff_data_source` to `graph` in settings.
3. Open the Chief of Staff dashboard. On any Graph failure, the app logs a warning and falls
   back to the sample fixtures.

### GCC High note

Per [README.md](README.md) §2, a GCC-H-registered app can only reach mailboxes/Teams in the
**same GCC-H tenant** (sovereign `.us` Graph endpoints). It cannot read commercial
`@microsoft.com` data. The Graph provider itself is cloud-agnostic — it relies on SimpleChat's
existing environment/authority configuration (`AZURE_ENVIRONMENT`, `CUSTOM_GRAPH_URL_VALUE`,
etc.) to target the correct cloud.
