# functions_cos_planner.py
# SimpleChat host binding for the headless cos_planner package.
#
# This is the ONLY place the portable planner touches SimpleChat. It supplies concrete
# implementations of the planner's ports:
#   - _GptLLMAdapter  -> LLMPort    (uses SimpleChat's Azure OpenAI client + tool calling)
#   - _RuntimeAdapter -> RuntimePort (uses functions_cos_runtime.py)
# and resolves the agent's capabilities (with a built-in parameter-schema fallback so the POC
# works even before the runtime is redeployed with per-capability parameter schemas).

import json
import logging

from config import *
from functions_settings import get_settings
from functions_appinsights import log_event

from functions_cos_runtime import (
    CosRuntimeError,
    get_agent,
    get_catalog,
    invoke_agent,
    approve_action,
    reject_action,
)
from cos_planner import Capability, CosPlanner, LLMResponse, ToolCall

# Fallback parameter schemas keyed by capability id. Preferred source is the runtime catalog's
# per-capability "parameters"; this map keeps the planner working when the deployed runtime's
# /v1/catalog does not yet return parameter schemas (i.e. before it is redeployed).
DEFAULT_PARAM_SCHEMAS = {
    "email.draft": {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient email address."},
            "subject": {"type": "string", "description": "Subject line of the draft."},
            "body": {"type": "string", "description": "Plain-text body of the draft."},
        },
        "required": ["to", "subject", "body"],
    },
    "email.send": {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient email address."},
            "subject": {"type": "string", "description": "Subject line of the email."},
            "body": {"type": "string", "description": "Plain-text body of the email."},
        },
        "required": ["to", "subject", "body"],
    },
    "calendar.schedule": {
        "type": "object",
        "properties": {
            "subject": {"type": "string", "description": "Title of the calendar event."},
            "start": {"type": "string", "description": "Start date-time in ISO 8601."},
            "end": {"type": "string", "description": "End date-time in ISO 8601."},
            "time_zone": {"type": "string", "description": "Time zone for start/end. Defaults to UTC."},
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional attendee email addresses.",
            },
            "location": {"type": "string", "description": "Optional meeting location."},
            "body": {"type": "string", "description": "Optional plain-text agenda."},
        },
        "required": ["subject", "start", "end"],
    },
    "teams.message.send": {
        "type": "object",
        "properties": {
            "chat_id": {"type": "string", "description": "The Teams chat id to post into."},
            "content": {"type": "string", "description": "The message text to post."},
        },
        "required": ["chat_id", "content"],
    },
}


class _RuntimeAdapter:
    """Adapts functions_cos_runtime.py (which returns (status, body) and raises CosRuntimeError)
    to the planner's RuntimePort (returns a body dict, raises on failure)."""

    @staticmethod
    def _unwrap(status, body, what):
        if status is None or status >= 400:
            message = None
            if isinstance(body, dict):
                message = body.get("error")
            raise CosRuntimeError(
                message or f"Runtime {what} failed (HTTP {status}).",
                status_code=status or 502,
                details=body,
            )
        return body or {}

    def invoke(self, agent_id, task, parameters=None, proposed_actions=None):
        status, body = invoke_agent(
            agent_id, task, parameters=parameters, proposed_actions=proposed_actions
        )
        return self._unwrap(status, body, "invoke")

    def approve(self, action_id):
        status, body = approve_action(action_id)
        return self._unwrap(status, body, "approve")

    def reject(self, action_id):
        status, body = reject_action(action_id)
        return self._unwrap(status, body, "reject")


class _GptLLMAdapter:
    """Adapts SimpleChat's Azure OpenAI client to the planner's LLMPort, translating ToolSpec into
    OpenAI function-tool schema and parsing tool calls back into the neutral LLMResponse shape."""

    def __init__(self, client, model):
        self._client = client
        self._model = model

    def complete(self, messages, tools=None):
        kwargs = {"model": self._model, "messages": messages}
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
            kwargs["tool_choice"] = "auto"

        completion = self._client.chat.completions.create(**kwargs)
        message = completion.choices[0].message
        text = message.content or ""
        tool_calls = []
        for call in getattr(message, "tool_calls", None) or []:
            raw_args = getattr(call.function, "arguments", "") or "{}"
            try:
                args = json.loads(raw_args)
            except (ValueError, TypeError):
                args = {}
            tool_calls.append(ToolCall(name=call.function.name, arguments=args))
        return LLMResponse(text=text, tool_calls=tool_calls)


def _get_llm_adapter(settings, user_id=None):
    # Imported lazily to avoid a circular import at module load time.
    from route_backend_conversation_export import _initialize_gpt_client

    client, model = _initialize_gpt_client(settings, user_id=user_id)
    return _GptLLMAdapter(client, model)


def _load_agent_capabilities(agent):
    """Resolve the agent's selected capabilities into planner Capability objects, merging the
    runtime catalog's parameter schemas with the built-in fallback map."""
    selected = list(agent.get("capabilities", []) or [])
    if not selected:
        return []

    catalog_by_id = {}
    try:
        status, body = get_catalog()
        if status and status < 400 and isinstance(body, dict):
            for entry in body.get("capabilities", []) or []:
                catalog_by_id[entry.get("id")] = entry
    except CosRuntimeError as exc:
        log_event(
            f"cos_planner: could not load catalog, using fallback schemas: {exc.message}",
            level=logging.WARNING,
            category="COS_PLANNER",
        )

    capabilities = []
    for cap_id in selected:
        entry = catalog_by_id.get(cap_id, {})
        requires_approval = bool(entry.get("requires_approval", cap_id in DEFAULT_PARAM_SCHEMAS))
        parameters = entry.get("parameters") or None
        if not parameters and requires_approval:
            parameters = DEFAULT_PARAM_SCHEMAS.get(cap_id)
        capabilities.append(
            Capability(
                id=cap_id,
                display_name=entry.get("display_name", cap_id),
                description=entry.get("description", ""),
                action=entry.get("action", "write" if requires_approval else "read"),
                requires_approval=requires_approval,
                parameters=parameters,
            )
        )
    return capabilities


def _build_planner(settings, user_id=None):
    return CosPlanner(
        llm=_get_llm_adapter(settings, user_id=user_id),
        runtime=_RuntimeAdapter(),
    )


def run_planner_turn(agent_id, message, history=None, auto_approve=False, user_id=None,
                     reviewer_agent_id=None):
    """Run one planner turn for the given agent. Returns a plain dict (PlannerTurn.to_dict()).

    reviewer_agent_id (optional) enables a minimal multi-agent handoff: after the primary agent
    proposes write actions, that second agent reviews/revises them before the approval preview.
    """
    settings = get_settings()
    status, agent = get_agent(agent_id)
    if status is None or status >= 400 or not isinstance(agent, dict):
        raise CosRuntimeError(
            (agent or {}).get("error", f"Could not load agent {agent_id}.")
            if isinstance(agent, dict)
            else f"Could not load agent {agent_id}.",
            status_code=status or 502,
        )

    reviewer = None
    if reviewer_agent_id and reviewer_agent_id != agent_id:
        r_status, r_agent = get_agent(reviewer_agent_id)
        if r_status is not None and r_status < 400 and isinstance(r_agent, dict):
            reviewer = {
                "agent": {
                    "id": reviewer_agent_id,
                    "name": r_agent.get("name", "Reviewer"),
                    "instructions": r_agent.get("instructions", ""),
                }
            }

    capabilities = _load_agent_capabilities(agent)
    planner = _build_planner(settings, user_id=user_id)
    turn = planner.plan(
        agent={
            "id": agent_id,
            "name": agent.get("name", "Assistant"),
            "instructions": agent.get("instructions", ""),
        },
        capabilities=capabilities,
        user_message=message,
        history=history,
        auto_approve=auto_approve,
        reviewer=reviewer,
    )
    return turn.to_dict()


def execute_proposed_actions(agent_id, task, proposed_actions, user_id=None):
    """Approve and execute previously previewed proposed actions. Returns a dict with results."""
    settings = get_settings()
    planner = _build_planner(settings, user_id=user_id)
    results, notes = planner.execute(agent_id, task, proposed_actions)
    return {
        "status": "executed",
        "results": results,
        "notes": notes,
    }
