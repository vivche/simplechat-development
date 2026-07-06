# Chief of Staff Runtime — `src/`

Azure Functions (Python v2) app implementing the runtime. Decoupled from SimpleChat: nothing here
imports SimpleChat; integration is HTTP-only over the `/v1/*` API.

## Layout

```
src/
  function_app.py                 # HTTP API routes (/v1/*)
  host.json                       # Functions host config
  requirements.txt                # runtime dependencies (self-contained)
  local.settings.json.example     # copy to local.settings.json and fill in
  config/
    capability_catalog.v1.json    # vetted capability catalog (Tool Registry data, git-versioned)
  cos/
    config.py                     # env-based RuntimeConfig
    catalog.py                    # capability catalog loader (Tool Registry)
    schema.py                     # Agent Definition Schema + validation
    registry.py                   # Agent Registry (in-memory + Cosmos backends)
    memory.py                     # Shared Memory Service (in-memory + Cosmos backends)
    auth.py                       # token validation + OBO exchange
    graph_tools.py                # read-only Graph tools
    orchestrator.py               # Chief-of-Staff invocation engine
    container.py                  # composition root (singletons)
```

## API surface (`/v1/*`)

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/v1/health` | Liveness (no auth) |
| GET | `/v1/catalog` | The capability catalog for the Builder UI |
| GET | `/v1/agents` | List the caller's agents |
| POST | `/v1/agents` | Create an agent (owner from token) |
| GET | `/v1/agents/{id}` | Get one of the caller's agents |
| DELETE | `/v1/agents/{id}` | Delete one of the caller's agents |
| POST | `/v1/agents/{id}/invoke` | Run an agent (OBO → Graph) |

All routes except `/v1/health` require `Authorization: Bearer <token>` where the token audience is
`api://<client_id>`. The caller identity (`oid`) is read from the validated token and used for owner
scoping — it is never taken from the request body.

## Run locally

Prerequisites: Python 3.11+, [Azure Functions Core Tools v4](https://learn.microsoft.com/azure/azure-functions/functions-run-local).

```powershell
cd chief-of-staff-runtime/src
Copy-Item local.settings.json.example local.settings.json
# Fill COS_CLIENT_SECRET (from Key Vault) — required for OBO/Graph calls.

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

func start
```

Notes for the POC:
- `COS_USE_IN_MEMORY_STORES=true` keeps agents/memory in-process — no Cosmos needed to try the API.
- Graph tools require **admin consent** on the `cos-runtime-api` app registration to return data.
  Until then, `/v1/agents/{id}/invoke` will surface a 403 from Graph in the `notes` field, which is
  expected. Agent CRUD and `/v1/catalog` work without consent.

## Tests

```powershell
cd chief-of-staff-runtime/src
pip install -r requirements.txt
python -m pytest ../tests -q
```
