# AI Chief of Staff (POC) — Files Changed / Added

> As-built inventory of every file created or modified to deliver the AI Chief of Staff POC.
> Branch: `feature/ai-chief-of-staff-phase1`
> Companion to [README.md](README.md) (the POC plan & design).

All changes are additive and gated behind the `enable_chief_of_staff_dashboard` setting
(off by default), so the feature has no effect until an admin turns it on.

---

## New files added

### Backend logic
| File | Purpose |
|---|---|
| `application/single_app/functions_chief_of_staff.py` | Core module: loads bundled sample data, builds the LLM prompt, calls the configured Azure OpenAI model, and parses the JSON briefing. Exposes `generate_briefing()`. The prompt/parser produce six sections: summary, priorities, action items, commitments, meeting briefings, follow-ups. |
| `application/single_app/route_backend_chief_of_staff.py` | Backend API route returning the generated briefing JSON. Gated by `@enabled_required('enable_chief_of_staff_dashboard')`. |
| `application/single_app/route_frontend_chief_of_staff.py` | Frontend route that renders the dashboard page. Gated by the same feature flag. |

### Frontend
| File | Purpose |
|---|---|
| `application/single_app/templates/chief_of_staff_dashboard.html` | Dashboard page — Today's Summary and Top Priorities at the top; Action Items, Your Commitments, Meeting Briefings, and Follow-ups grouped into Bootstrap tabs (with live count badges); plus a "Refresh briefing" button. |
| `application/single_app/static/js/chief_of_staff/dashboard.js` | Fetches the briefing from the backend endpoint and renders all six sections (summary, priorities, action items, commitments, meeting briefings, follow-ups) using XSS-safe DOM construction. |

### Sample data (the POC's mock mailbox / calendar / Teams)
| File | Purpose |
|---|---|
| `application/single_app/static/chief_of_staff/sample_data/emails.json` | Realistic fake emails. |
| `application/single_app/static/chief_of_staff/sample_data/meetings.json` | Realistic fake meetings. |
| `application/single_app/static/chief_of_staff/sample_data/teams_messages.json` | Realistic fake Teams messages. |

### Tests & documentation
| File | Purpose |
|---|---|
| `functional_tests/test_chief_of_staff_briefing.py` | Validates sample-data loading, prompt inclusion of all sources, and JSON parsing across all six briefing sections. |
| `docs/chief-of-staff/README.md` | POC plan, GCC-H constraints, architecture, and design decisions. |
| `docs/chief-of-staff/FILES_CHANGED.md` | This file — as-built inventory of changed/added files. |

---

## Modified files (wiring only)

| File | Change |
|---|---|
| `application/single_app/app.py` | Imports and registers the frontend + backend Chief of Staff blueprints under `user_required`. |
| `application/single_app/functions_settings.py` | Adds the default setting `enable_chief_of_staff_dashboard: False`. |
| `application/single_app/route_frontend_admin_settings.py` | Reads the admin checkbox from the settings form and persists it. |
| `application/single_app/templates/admin_settings.html` | Adds the "AI Chief of Staff (POC)" toggle card in the General tab. |
| `application/single_app/templates/_sidebar_nav.html` | Adds the sidebar "Chief of Staff" link, shown only when the flag is on. |
| `application/single_app/config.py` | Version bump. |

---

## How the pieces connect

```
Admin toggle (admin_settings.html)
   └─ enable_chief_of_staff_dashboard (functions_settings.py)
        └─ Sidebar link (_sidebar_nav.html)
             └─ Frontend route (route_frontend_chief_of_staff.py)
                  └─ dashboard.html + dashboard.js
                       └─ fetch briefing → Backend route (route_backend_chief_of_staff.py)
                            └─ generate_briefing() (functions_chief_of_staff.py)
                                 ├─ sample_data/*.json
                                 └─ Azure OpenAI model
```

---

## Notes

- **Prerequisite:** Azure OpenAI must be configured for the briefing to generate. In a
  `managed_identity` tenant, the identity needs the `Cognitive Services OpenAI User` data-plane
  role on the OpenAI resource.
- **Not part of this feature:** any change to `application/single_app/static/images/custom_logo.png`
  appears unrelated to the Chief of Staff work and should be reviewed separately before committing.
