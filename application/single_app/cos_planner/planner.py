# planner.py
# The core planner: turns a natural-language request into a safe, approval-gated plan.
#
# Flow for one turn (see docs/BACKLOG.md "Orchestration/planner IP boundary"):
#   1. Auto-gather READ context by invoking the agent with no proposed actions (reads run; nothing
#      is written).
#   2. Ask the LLM to answer and/or propose WRITE actions, exposing the agent's write capabilities
#      as tools built from their catalog parameter schemas.
#   3. If no write was proposed -> "answered". If a write was proposed and auto_approve is off ->
#      "awaiting_approval" (host previews and later calls execute()). If auto_approve is on ->
#      execute immediately and return "executed".
#
# The runtime remains the hard approval gate: writes are created as PendingActions on invoke and
# only run via approve(). The planner never writes directly to Microsoft Graph.

import json
import logging
from typing import Any, Dict, List, Optional

from .ports import (
    Capability,
    LLMPort,
    PlannerTurn,
    ProposedAction,
    RuntimePort,
    ToolSpec,
)

logger = logging.getLogger(__name__)

# OpenAI-style function names allow [a-zA-Z0-9_-] only, so encode capability ids without dots.
_NAME_SEP = "__"


def _cap_to_tool_name(capability_id: str) -> str:
    return capability_id.replace(".", _NAME_SEP)


def _tool_name_to_cap(tool_name: str) -> str:
    return tool_name.replace(_NAME_SEP, ".")


SYSTEM_PROMPT_TEMPLATE = (
    "You are {agent_name}, a Chief of Staff assistant acting ONLY on the signed-in user's own "
    "data (self-only scope). {agent_instructions}\n\n"
    "You can do two kinds of things:\n"
    "1. Read/summarize the user's data (already gathered for you below when available).\n"
    "2. Propose WRITE/SEND actions (draft an email, send an email, schedule an event, post to "
    "Teams) by calling the matching tool. NEVER claim you have sent, drafted, scheduled, or posted "
    "anything yourself — proposing the tool call is all you do; a human approval step performs the "
    "real action afterwards.\n\n"
    "Rules:\n"
    "- Only call a tool when the user actually asked for that action. For pure questions "
    "(\"what's in my inbox?\"), just answer from the context; do not call a tool.\n"
    "- Fill tool parameters accurately from the user's request and the context. If the user says "
    "\"to myself\" or \"me\", use their own address if it appears in the context; otherwise leave "
    "recipient blank and ask.\n"
    "- When drafting or sending a REPLY or FOLLOW-UP to someone who appears in the gathered "
    "context, default the recipient to that person's sender (\"from\") email address from the "
    "context. Prefer this over asking, as long as a matching sender address is present.\n"
    "- If the relevant message was sent BY the user (the \"from\" is the user themselves), the "
    "other party is instead in that message's recipients (\"toRecipients\"/\"ccRecipients\"); use "
    "the matching recipient address from the context as the target.\n"
    "- If required information is genuinely missing (e.g. no matching \"from\" or recipient "
    "address is in the context), ask a short clarifying question instead of guessing.\n"
    "- Keep replies concise."
)

REVIEWER_SYSTEM_PROMPT_TEMPLATE = (
    "You are {agent_name}, a reviewer in a multi-agent workflow. {agent_instructions}\n\n"
    "Another assistant has already PROPOSED the write/send actions listed below (they are NOT yet "
    "executed — a human still has to approve them). Your job is to review each proposed action and, "
    "where it improves quality or fit with the user's style/intent, REVISE it.\n\n"
    "Rules:\n"
    "- Re-emit EVERY action you want to keep by calling the matching tool again, revising the "
    "parameters as needed (e.g. reword an email body, fix a subject, tighten a Teams message).\n"
    "- To drop an action you disapprove of, simply do NOT call its tool.\n"
    "- You may only call the SAME kinds of tools that were proposed; do not invent new actions.\n"
    "- In your text reply, briefly explain what you changed and why (1-3 sentences)."
)


class CosPlanner:
    """Host-agnostic LLM planner over the Chief of Staff Runtime. Depends only on the ports."""

    def __init__(self, llm: LLMPort, runtime: RuntimePort) -> None:
        self._llm = llm
        self._runtime = runtime

    # -- public API ---------------------------------------------------------

    def plan(
        self,
        agent: Dict[str, Any],
        capabilities: List[Capability],
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
        auto_approve: bool = False,
        reviewer: Optional[Dict[str, Any]] = None,
    ) -> PlannerTurn:
        """Run one planning turn for the given agent and user message.

        reviewer (optional) enables a minimal multi-agent handoff: after the primary agent proposes
        write actions, a second "reviewer" agent inspects and may revise them (e.g. to match the
        user's conversational style) before they are presented for approval. Shape:
            {"agent": {"id"?, "name", "instructions"}}
        The reviewer can only re-emit the SAME action types the primary proposed (no new powers).
        """
        agent_id = agent.get("id")
        if not agent_id:
            return PlannerTurn(status="error", reply="No agent selected.")

        read_caps = [c for c in capabilities if not c.requires_approval]
        write_caps = [c for c in capabilities if c.requires_approval]

        # 1. Auto-gather read context (reads only; no writes possible here).
        context: Dict[str, Any] = {}
        scopes_used: List[str] = []
        notes: List[str] = []
        if read_caps:
            try:
                invoked = self._runtime.invoke(agent_id, user_message)
                context = invoked.get("context", {}) or {}
                scopes_used = invoked.get("scopes_used", []) or []
                notes = invoked.get("notes", []) or []
            except Exception as exc:  # noqa: BLE001 - surface as a note, keep planning
                logger.warning("cos_planner: context gathering failed: %s", exc)
                notes.append(f"context gathering failed: {exc}")

        # 2. Ask the LLM to answer and/or propose write actions.
        messages = self._build_messages(agent, context, history, user_message)
        tools = [self._capability_to_tool(c) for c in write_caps]

        try:
            response = self._llm.complete(messages, tools=tools or None)
        except Exception as exc:  # noqa: BLE001
            logger.exception("cos_planner: LLM call failed")
            return PlannerTurn(
                status="error",
                reply=f"The planner could not reach the language model: {exc}",
                context=context,
                notes=notes,
                scopes_used=scopes_used,
            )

        proposed = self._extract_proposed_actions(response, write_caps)
        reply = (response.text or "").strip()

        # 3a. Nothing to write -> just answer.
        if not proposed:
            if not reply:
                reply = "I couldn't determine an action for that request. Could you rephrase?"
            return PlannerTurn(
                status="answered",
                reply=reply,
                context=context,
                notes=notes,
                scopes_used=scopes_used,
            )

        # 2b. Optional multi-agent handoff: a reviewer agent revises before approval.
        review_info: Optional[Dict[str, Any]] = None
        if reviewer and reviewer.get("agent"):
            proposed, review_info = self._review_actions(
                reviewer_agent=reviewer["agent"],
                write_caps=write_caps,
                user_message=user_message,
                proposed=proposed,
                context=context,
            )

        proposed_dicts = [p.to_dict() for p in proposed]

        # 3b. Auto-approve enabled -> execute now.
        if auto_approve:
            results, exec_notes = self.execute(agent_id, user_message, proposed_dicts)
            if not reply:
                reply = "Done — I completed the requested action(s)."
            return PlannerTurn(
                status="executed",
                reply=reply,
                proposed_actions=proposed_dicts,
                context=context,
                results=results,
                notes=notes + exec_notes,
                scopes_used=scopes_used,
                review=review_info,
            )

        # 3c. Otherwise preview and wait for the host to confirm.
        if not reply:
            reply = "Here's what I'd like to do. Approve to proceed, or reject to cancel."
        return PlannerTurn(
            status="awaiting_approval",
            reply=reply,
            proposed_actions=proposed_dicts,
            context=context,
            notes=notes,
            scopes_used=scopes_used,
            review=review_info,
        )

    def execute(
        self, agent_id: str, task: str, proposed_actions: List[Dict[str, Any]]
    ) -> "tuple[List[Dict[str, Any]], List[str]]":
        """Record the proposed actions as pending on the runtime, then approve each in turn.

        Returns (results, notes). The runtime enforces the approval gate: invoke creates the
        PendingActions; approve executes them with a fresh least-privilege token.
        """
        results: List[Dict[str, Any]] = []
        notes: List[str] = []
        try:
            invoked = self._runtime.invoke(
                agent_id, task, proposed_actions=proposed_actions
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("cos_planner: invoke for execution failed")
            return results, [f"could not record actions for approval: {exc}"]

        notes.extend(invoked.get("notes", []) or [])
        pending = invoked.get("pending_actions", []) or []
        if not pending:
            notes.append("No actions were recorded for approval (they may have been rejected by policy).")
            return results, notes

        for action in pending:
            action_id = action.get("id")
            entry: Dict[str, Any] = {
                "action_id": action_id,
                "capability": action.get("capability_id") or action.get("capability"),
                "parameters": action.get("parameters", {}),
            }
            try:
                approved = self._runtime.approve(action_id)
                entry["status"] = approved.get("status", "unknown")
                entry["result"] = approved.get("result")
                entry["error"] = approved.get("error")
            except Exception as exc:  # noqa: BLE001
                entry["status"] = "error"
                entry["error"] = str(exc)
            results.append(entry)
        return results, notes

    # -- internals ----------------------------------------------------------

    def _build_messages(
        self,
        agent: Dict[str, Any],
        context: Dict[str, Any],
        history: Optional[List[Dict[str, str]]],
        user_message: str,
    ) -> List[Dict[str, str]]:
        system = SYSTEM_PROMPT_TEMPLATE.format(
            agent_name=agent.get("name") or "Assistant",
            agent_instructions=(agent.get("instructions") or "").strip(),
        )
        messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
        if context:
            messages.append(
                {
                    "role": "system",
                    "content": "Context gathered from the user's data (read-only):\n"
                    + json.dumps(context, indent=2, default=str),
                }
            )
        for turn in history or []:
            role = turn.get("role")
            content = turn.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_message})
        return messages

    def _capability_to_tool(self, capability: Capability) -> ToolSpec:
        params = capability.parameters or {"type": "object", "properties": {}}
        description = capability.description or capability.display_name or capability.id
        return ToolSpec(
            name=_cap_to_tool_name(capability.id),
            description=description,
            parameters=params,
        )

    def _extract_proposed_actions(
        self, response, write_caps: List[Capability]
    ) -> List[ProposedAction]:
        allowed = {c.id for c in write_caps}
        proposed: List[ProposedAction] = []
        for call in response.tool_calls or []:
            capability_id = _tool_name_to_cap(call.name)
            if capability_id not in allowed:
                logger.warning("cos_planner: model called unknown/forbidden tool %s", call.name)
                continue
            proposed.append(
                ProposedAction(capability=capability_id, parameters=call.arguments or {})
            )
        return proposed

    def _review_actions(
        self,
        reviewer_agent: Dict[str, Any],
        write_caps: List[Capability],
        user_message: str,
        proposed: List[ProposedAction],
        context: Dict[str, Any],
    ) -> "tuple[List[ProposedAction], Dict[str, Any]]":
        """Minimal multi-agent handoff: a reviewer agent inspects/revises proposed actions.

        Returns (final_actions, review_info). The reviewer can only re-emit the same capability
        types the primary proposed; it cannot introduce new powers. If the reviewer LLM call fails
        or returns no actions, the original proposal is kept unchanged (fail-open on review, since
        the human approval gate still protects execution).
        """
        reviewer_name = reviewer_agent.get("name") or "Reviewer"
        cap_by_id = {c.id: c for c in write_caps}
        # Only expose the capability types actually proposed, so the reviewer stays on task.
        proposed_ids = {p.capability for p in proposed}
        review_caps = [cap_by_id[c] for c in proposed_ids if c in cap_by_id]
        tools = [self._capability_to_tool(c) for c in review_caps]

        system = REVIEWER_SYSTEM_PROMPT_TEMPLATE.format(
            agent_name=reviewer_name,
            agent_instructions=(reviewer_agent.get("instructions") or "").strip(),
        )
        proposed_json = json.dumps(
            [p.to_dict() for p in proposed], indent=2, default=str
        )
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system},
            {
                "role": "system",
                "content": "Original user request:\n" + user_message,
            },
            {
                "role": "system",
                "content": "Proposed actions to review (JSON):\n" + proposed_json,
            },
        ]
        if context:
            messages.append(
                {
                    "role": "system",
                    "content": "Context available (read-only):\n"
                    + json.dumps(context, indent=2, default=str),
                }
            )
        messages.append(
            {
                "role": "user",
                "content": "Review these proposed actions. Re-emit each one you approve (revised as "
                "needed) by calling the matching tool, and briefly explain your changes.",
            }
        )

        review_info: Dict[str, Any] = {
            "reviewer": reviewer_name,
            "reviewer_id": reviewer_agent.get("id"),
            "revised": False,
        }
        try:
            response = self._llm.complete(messages, tools=tools or None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cos_planner: reviewer LLM call failed: %s", exc)
            review_info["comment"] = f"Reviewer unavailable ({exc}); kept original actions."
            return proposed, review_info

        revised = self._extract_proposed_actions(response, review_caps)
        review_info["comment"] = (response.text or "").strip()
        if revised:
            review_info["revised"] = True
            return revised, review_info

        # Reviewer approved without re-emitting actions -> keep the originals.
        if not review_info["comment"]:
            review_info["comment"] = f"{reviewer_name} approved the actions without changes."
        return proposed, review_info
