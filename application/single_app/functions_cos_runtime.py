# functions_cos_runtime.py
# Thin client for the external Chief of Staff Runtime (a separate Azure Function service).
#
# SimpleChat is a *client* of the runtime — there is no in-process coupling. This module:
#   1. Mints a runtime-audience access token for the signed-in user (delegated, via MSAL silent
#      acquisition against the runtime's exposed scope), and
#   2. Forwards Agent Builder / catalog / invoke calls to the runtime over HTTPS, returning the
#      runtime's JSON response.
#
# The runtime validates the token audience/scope, derives the user identity from the token, and
# performs least-privilege On-Behalf-Of Graph calls per invocation. See the runtime's docs/AUTH_FLOW.md.

import logging

import requests

from config import (
    COS_RUNTIME_BASE_URL,
    COS_RUNTIME_SCOPE,
    COS_RUNTIME_TIMEOUT_SECONDS,
)
from functions_authentication import get_valid_access_token
from functions_appinsights import log_event


class CosRuntimeError(Exception):
    """Raised when a call to the Chief of Staff Runtime fails.

    status_code carries the HTTP status to surface to the caller (proxy route). A status of 0
    indicates a client-side/config/network failure before a response was received.
    """

    def __init__(self, message, status_code=502, details=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details


def is_runtime_configured():
    """Return True when the runtime base URL and scope are both configured."""
    return bool(COS_RUNTIME_BASE_URL) and bool(COS_RUNTIME_SCOPE)


def get_cos_runtime_token():
    """Acquire a runtime-audience access token for the current user.

    Uses MSAL silent acquisition (cache + refresh token) for the runtime's exposed scope. Returns
    the token string. Raises CosRuntimeError(401) when the user is not signed in or consent for the
    runtime API has not been granted (silent acquisition returns None).
    """
    if not COS_RUNTIME_SCOPE:
        raise CosRuntimeError(
            "Chief of Staff Runtime scope is not configured (COS_RUNTIME_SCOPE).",
            status_code=503,
        )

    token = get_valid_access_token(scopes=[COS_RUNTIME_SCOPE])
    if not token:
        raise CosRuntimeError(
            "Could not acquire a token for the Chief of Staff Runtime. Sign in again or grant "
            "consent for the runtime API.",
            status_code=401,
        )
    return token


def _request(method, path, json_body=None):
    """Call the runtime and return (status_code, parsed_json_or_none).

    Raises CosRuntimeError for configuration/network failures. HTTP error statuses from the runtime
    are returned to the caller so the proxy can pass them through unchanged.
    """
    if not COS_RUNTIME_BASE_URL:
        raise CosRuntimeError(
            "Chief of Staff Runtime base URL is not configured (COS_RUNTIME_BASE_URL).",
            status_code=503,
        )

    token = get_cos_runtime_token()
    url = f"{COS_RUNTIME_BASE_URL}/{path.lstrip('/')}"
    headers = {"Authorization": f"Bearer {token}"}
    if json_body is not None:
        headers["Content-Type"] = "application/json"

    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            json=json_body,
            timeout=COS_RUNTIME_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        log_event(
            f"Chief of Staff Runtime request failed: {method} {path}: {exc}",
            level=logging.ERROR,
            category="COS_RUNTIME",
        )
        raise CosRuntimeError(
            "Could not reach the Chief of Staff Runtime.", status_code=502
        ) from exc

    try:
        body = response.json() if response.content else None
    except ValueError:
        body = None

    return response.status_code, body


def get_catalog():
    """GET /v1/catalog — the vetted capability catalog for the Builder UI."""
    return _request("GET", "v1/catalog")


def list_agents():
    """GET /v1/agents — the caller's agent definitions."""
    return _request("GET", "v1/agents")


def get_agent(agent_id):
    """GET /v1/agents/{id}."""
    return _request("GET", f"v1/agents/{agent_id}")


def create_agent(payload):
    """POST /v1/agents — create an agent from the catalog subset. owner_id is derived server-side."""
    return _request("POST", "v1/agents", json_body=payload)


def update_agent(agent_id, payload):
    """PUT /v1/agents/{id} — partial update; the catalog-constrained zone is re-validated."""
    return _request("PUT", f"v1/agents/{agent_id}", json_body=payload)


def delete_agent(agent_id):
    """DELETE /v1/agents/{id}."""
    return _request("DELETE", f"v1/agents/{agent_id}")


def invoke_agent(agent_id, task, parameters=None, proposed_actions=None):
    """POST /v1/agents/{id}/invoke — run an agent against a user task.

    Read capabilities auto-run and return data under 'context'. Any 'proposed_actions'
    (write/send capabilities) are recorded as pending approvals and are NEVER executed here;
    they run only after an explicit approve_action() call.
    """
    body = {"task": task}
    if parameters:
        body["parameters"] = parameters
    if proposed_actions:
        body["proposed_actions"] = proposed_actions
    return _request("POST", f"v1/agents/{agent_id}/invoke", json_body=body)


def list_approvals(status=None):
    """GET /v1/approvals — the caller's pending/approved/rejected actions (owner-scoped)."""
    path = "v1/approvals"
    if status:
        path += f"?status={status}"
    return _request("GET", path)


def approve_action(action_id):
    """POST /v1/approvals/{id}/approve — execute a pending write action (fresh least-privilege OBO)."""
    return _request("POST", f"v1/approvals/{action_id}/approve")


def reject_action(action_id):
    """POST /v1/approvals/{id}/reject — reject a pending write action; the tool never runs."""
    return _request("POST", f"v1/approvals/{action_id}/reject")
