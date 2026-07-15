#!/usr/bin/env python3
"""
Functional test for the Chief of Staff planner (cos_planner) multi-agent handoff (reviewer).
Version: 0.250.025
Implemented in: 0.250.025

This test ensures that when a reviewer agent is supplied, the planner performs a minimal
multi-agent handoff: after the primary agent proposes a write action, the reviewer agent inspects
and may REVISE it before the approval preview. The reviewer can only re-emit the same capability
types that were proposed (no new powers), and the two-phase approval gate is preserved.

The planner is exercised through its ports with in-memory fakes, so no network, LLM, or runtime
service is required.
"""

import os
import sys

# cos_planner lives in the application root (parent of functional_tests/).
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cos_planner import Capability, CosPlanner, LLMResponse, ToolCall


class ScriptedLLM:
    """Returns different tool calls per call so we can distinguish the primary vs reviewer turn."""

    def __init__(self):
        self.calls = 0
        self.last_tools = None

    def complete(self, messages, tools=None):
        self.last_tools = tools
        self.calls += 1
        if self.calls == 1:
            # Primary agent proposes a rough draft.
            return LLMResponse(
                text="I'll draft that email.",
                tool_calls=[
                    ToolCall(
                        name="email__draft",
                        arguments={"to": "me@example.com", "subject": "hi", "body": "hey"},
                    )
                ],
            )
        # Reviewer revises the draft to match the user's style.
        return LLMResponse(
            text="Polished the greeting and subject to match your professional tone.",
            tool_calls=[
                ToolCall(
                    name="email__draft",
                    arguments={
                        "to": "me@example.com",
                        "subject": "Following up",
                        "body": "Hello,\n\nJust following up. Best regards.",
                    },
                )
            ],
        )


class ApproveOnlyLLM:
    """Primary proposes; reviewer approves without re-emitting any tool call."""

    def __init__(self):
        self.calls = 0

    def complete(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                text="Drafting.",
                tool_calls=[
                    ToolCall(
                        name="email__draft",
                        arguments={"to": "me@example.com", "subject": "hi", "body": "hey"},
                    )
                ],
            )
        return LLMResponse(text="Looks good, no changes needed.", tool_calls=[])


class FakeRuntime:
    """In-memory runtime: records invoke calls, mints pending actions, and approves them."""

    def __init__(self):
        self.invoke_calls = []
        self.approved = []

    def invoke(self, agent_id, task, parameters=None, proposed_actions=None):
        self.invoke_calls.append(
            {"agent_id": agent_id, "task": task, "proposed_actions": proposed_actions}
        )
        pending = []
        for idx, action in enumerate(proposed_actions or []):
            pending.append(
                {
                    "id": f"pa-{idx}",
                    "capability_id": action["capability"],
                    "parameters": action["parameters"],
                }
            )
        return {
            "agent_id": agent_id,
            "context": {"email": {"messages": []}},
            "scopes_used": ["Mail.Read"],
            "notes": [],
            "pending_actions": pending,
        }

    def approve(self, action_id):
        self.approved.append(action_id)
        return {"action_id": action_id, "status": "completed", "result": {"drafted": True}, "error": None}

    def reject(self, action_id):
        return {"action_id": action_id, "status": "rejected"}


def _capabilities():
    return [
        Capability(id="email.read", action="read", requires_approval=False),
        Capability(
            id="email.draft",
            display_name="Email — Draft",
            description="Compose a draft reply.",
            action="write",
            requires_approval=True,
            parameters={
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
        ),
    ]


def _reviewer():
    return {"agent": {"id": "gary-1", "name": "Gary", "instructions": "Match the user's tone."}}


def test_reviewer_revises_proposed_action():
    """The reviewer's revised parameters replace the primary agent's proposal before approval."""
    print("Testing reviewer revises the proposed draft...")
    llm = ScriptedLLM()
    runtime = FakeRuntime()
    planner = CosPlanner(llm=llm, runtime=runtime)

    turn = planner.plan(
        agent={"id": "agent-1", "name": "Draft Writer", "instructions": "Draft emails."},
        capabilities=_capabilities(),
        user_message="draft a follow-up email to myself",
        auto_approve=False,
        reviewer=_reviewer(),
    )

    assert llm.calls == 2, f"expected two LLM calls (primary + reviewer), got {llm.calls}"
    assert turn.status == "awaiting_approval", f"expected awaiting_approval, got {turn.status}"
    assert len(turn.proposed_actions) == 1, "expected one reviewed action"
    # The reviewer's revised values must win.
    params = turn.proposed_actions[0]["parameters"]
    assert params["subject"] == "Following up", f"reviewer subject not applied: {params}"
    assert "Best regards" in params["body"], "reviewer body not applied"
    # Review metadata should be present and marked as revised.
    assert turn.review is not None, "review info should be present"
    assert turn.review["revised"] is True, "review should be marked revised"
    assert turn.review["reviewer"] == "Gary"
    # Approval gate preserved: nothing executed at preview.
    assert runtime.approved == [], "no action should be approved during preview"
    print("Reviewer-revises test passed!")
    return True


def test_reviewer_approves_without_changes():
    """When the reviewer re-emits nothing, the original proposal is kept and marked not revised."""
    print("Testing reviewer approves without changes...")
    llm = ApproveOnlyLLM()
    runtime = FakeRuntime()
    planner = CosPlanner(llm=llm, runtime=runtime)

    turn = planner.plan(
        agent={"id": "agent-1", "name": "Draft Writer", "instructions": "Draft emails."},
        capabilities=_capabilities(),
        user_message="draft a follow-up email to myself",
        auto_approve=False,
        reviewer=_reviewer(),
    )

    assert turn.status == "awaiting_approval", f"expected awaiting_approval, got {turn.status}"
    assert len(turn.proposed_actions) == 1, "original proposal should be kept"
    params = turn.proposed_actions[0]["parameters"]
    assert params["subject"] == "hi", "original proposal should be unchanged"
    assert turn.review is not None and turn.review["revised"] is False, "should be marked not revised"
    print("Reviewer-approves test passed!")
    return True


def test_no_reviewer_is_unchanged_behavior():
    """Without a reviewer, the planner behaves exactly as before (single-agent, no review info)."""
    print("Testing single-agent behavior is unchanged when no reviewer is supplied...")
    llm = ScriptedLLM()
    runtime = FakeRuntime()
    planner = CosPlanner(llm=llm, runtime=runtime)

    turn = planner.plan(
        agent={"id": "agent-1", "name": "Draft Writer", "instructions": "Draft emails."},
        capabilities=_capabilities(),
        user_message="draft a follow-up email to myself",
        auto_approve=False,
    )

    assert llm.calls == 1, f"expected a single LLM call with no reviewer, got {llm.calls}"
    assert turn.status == "awaiting_approval", f"expected awaiting_approval, got {turn.status}"
    assert turn.review is None, "no review info expected without a reviewer"
    # The primary (unrevised) proposal stands.
    assert turn.proposed_actions[0]["parameters"]["subject"] == "hi"
    print("No-reviewer test passed!")
    return True


if __name__ == "__main__":
    tests = [
        test_reviewer_revises_proposed_action,
        test_reviewer_approves_without_changes,
        test_no_reviewer_is_unchanged_behavior,
    ]
    results = []
    for test in tests:
        print(f"\nRunning {test.__name__}...")
        try:
            results.append(test())
        except Exception as exc:  # noqa: BLE001
            print(f"Test failed: {exc}")
            import traceback

            traceback.print_exc()
            results.append(False)

    print(f"\nResults: {sum(1 for r in results if r)}/{len(results)} tests passed")
    sys.exit(0 if all(results) else 1)
