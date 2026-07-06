# function_app.py
# Azure Functions app (Python v2 programming model) — HTTP API for the Chief of Staff Runtime.
# All routes are under the /v1/ prefix (see docs/INTEGRATION.md). This is the ONLY integration
# surface: SimpleChat talks to the runtime over HTTP, never by importing it.

import json
import logging

import azure.functions as func

from cos.auth import AuthError, extract_bearer_token
from cos.container import get_container
from cos.orchestrator import OrchestratorError
from cos.schema import AgentValidationError, build_agent

logger = logging.getLogger(__name__)

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


def _json(body: dict, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(body), status_code=status, mimetype="application/json"
    )


def _authenticate(req: func.HttpRequest):
    """Validate the incoming bearer token and return the caller identity."""
    token = extract_bearer_token(req.headers.get("Authorization"))
    return get_container().token_validator.validate(token)


@app.route(route="v1/health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    return _json({"status": "ok"})


@app.route(route="v1/catalog", methods=["GET"])
def get_catalog(req: func.HttpRequest) -> func.HttpResponse:
    try:
        _authenticate(req)
    except AuthError as exc:
        return _json({"error": str(exc)}, status=401)
    return _json(get_container().catalog.public_view())


@app.route(route="v1/agents", methods=["GET", "POST"])
def agents(req: func.HttpRequest) -> func.HttpResponse:
    container = get_container()
    try:
        caller = _authenticate(req)
    except AuthError as exc:
        return _json({"error": str(exc)}, status=401)

    if req.method == "GET":
        items = [a.to_dict() for a in container.registry.list_for_owner(caller.oid)]
        return _json({"agents": items})

    # POST: create an agent. owner_id comes from the token, never from the body.
    try:
        payload = req.get_json()
    except ValueError:
        return _json({"error": "invalid JSON body"}, status=400)

    try:
        agent = build_agent(caller.oid, payload, container.catalog)
    except AgentValidationError as exc:
        return _json({"error": "validation failed", "details": exc.errors}, status=400)

    container.registry.create(agent)
    return _json(agent.to_dict(), status=201)


@app.route(route="v1/agents/{agent_id}", methods=["GET", "DELETE"])
def agent_by_id(req: func.HttpRequest) -> func.HttpResponse:
    container = get_container()
    try:
        caller = _authenticate(req)
    except AuthError as exc:
        return _json({"error": str(exc)}, status=401)

    agent_id = req.route_params.get("agent_id")

    if req.method == "DELETE":
        deleted = container.registry.delete(caller.oid, agent_id)
        if not deleted:
            return _json({"error": "agent not found"}, status=404)
        return _json({"deleted": True})

    agent = container.registry.get(caller.oid, agent_id)
    if agent is None:
        return _json({"error": "agent not found"}, status=404)
    return _json(agent.to_dict())


@app.route(route="v1/agents/{agent_id}/invoke", methods=["POST"])
def invoke_agent(req: func.HttpRequest) -> func.HttpResponse:
    container = get_container()
    try:
        caller = _authenticate(req)
    except AuthError as exc:
        return _json({"error": str(exc)}, status=401)

    agent_id = req.route_params.get("agent_id")
    try:
        payload = req.get_json()
    except ValueError:
        payload = {}
    task = (payload or {}).get("task", "")

    try:
        result = container.orchestrator.invoke(caller, agent_id, task)
    except OrchestratorError as exc:
        return _json({"error": str(exc)}, status=400)
    except AuthError as exc:
        return _json({"error": str(exc)}, status=403)

    return _json(
        {
            "agent_id": result.agent_id,
            "agent_name": result.agent_name,
            "scopes_used": result.scopes_used,
            "context": result.context,
            "notes": result.notes,
        }
    )
