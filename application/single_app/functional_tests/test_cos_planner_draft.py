#!/usr/bin/env python3
"""
Functional test for the Chief of Staff planner (cos_planner) Draft Writer scenario.
Version: 0.250.023
Implemented in: 0.250.023

This test ensures that when the user asks in natural language to draft an email, the headless
planner turns the request into an approval-gated `email.draft` proposed action (two-phase preview),
and that when auto-approve is enabled the action is executed through the runtime approval gate.

The planner is exercised through its ports with in-memory fakes, so no network, LLM, or runtime
service is required.
"""

import os
import sys

# cos_planner lives in the application root (parent of functional_tests/).
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cos_planner import Capability, CosPlanner, LLMResponse, ToolCall


class FakeLLM:
    """Returns a single email.draft tool call, mimicking a model that decided to draft an email."""

    def __init__(self):
        self.last_tools = None

    def complete(self, messages, tools=None):
        self.last_tools = tools
        return LLMResponse(
            text="I'll draft that email for you.",
            tool_calls=[
                ToolCall(
                    name="email__draft",
                    arguments={
                        "to": "me@example.com",
                        "subject": "COS test",
                        "body": "hello",
                    },
                )
            ],
        )


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


def test_preview_proposes_draft():
    """Without auto-approve, the planner previews an email.draft action and does not execute it."""
    print("Testing planner preview (awaiting_approval) for a draft request...")
    llm = FakeLLM()
    runtime = FakeRuntime()
    planner = CosPlanner(llm=llm, runtime=runtime)

    turn = planner.plan(
        agent={"id": "agent-1", "name": "Draft Writer", "instructions": "Draft emails."},
        capabilities=_capabilities(),
        user_message="draft an email to myself titled COS test saying hello",
        auto_approve=False,
    )

    assert turn.status == "awaiting_approval", f"expected awaiting_approval, got {turn.status}"
    assert len(turn.proposed_actions) == 1, "expected exactly one proposed action"
    action = turn.proposed_actions[0]
    assert action["capability"] == "email.draft", f"expected email.draft, got {action['capability']}"
    assert action["parameters"]["subject"] == "COS test"
    # The write tool schema must have been offered to the LLM; the read capability must not be a tool.
    tool_names = {t.name for t in (llm.last_tools or [])}
    assert tool_names == {"email__draft"}, f"unexpected tools offered: {tool_names}"
    # No execution must have happened at preview time (approval gate preserved).
    assert runtime.approved == [], "no action should be approved during preview"
    print("Preview test passed!")
    return True


def test_auto_approve_executes_draft():
    """With auto-approve on, the planner records and approves the draft through the runtime."""
    print("Testing planner auto-approve (executed) for a draft request...")
    llm = FakeLLM()
    runtime = FakeRuntime()
    planner = CosPlanner(llm=llm, runtime=runtime)

    turn = planner.plan(
        agent={"id": "agent-1", "name": "Draft Writer", "instructions": "Draft emails."},
        capabilities=_capabilities(),
        user_message="draft an email to myself titled COS test saying hello",
        auto_approve=True,
    )

    assert turn.status == "executed", f"expected executed, got {turn.status}"
    assert len(turn.results) == 1, "expected one execution result"
    assert turn.results[0]["status"] == "completed", "action should be completed"
    assert runtime.approved == ["pa-0"], f"expected pa-0 approved, got {runtime.approved}"
    print("Auto-approve test passed!")
    return True


def test_question_is_answered_without_action():
    """A pure question yields an answer with no proposed actions."""
    print("Testing planner answers a question without proposing an action...")

    class AnswerOnlyLLM:
        def complete(self, messages, tools=None):
            return LLMResponse(text="You have 3 unread emails.", tool_calls=[])

    runtime = FakeRuntime()
    planner = CosPlanner(llm=AnswerOnlyLLM(), runtime=runtime)

    turn = planner.plan(
        agent={"id": "agent-1", "name": "Assistant", "instructions": ""},
        capabilities=_capabilities(),
        user_message="what's in my inbox?",
        auto_approve=False,
    )

    assert turn.status == "answered", f"expected answered, got {turn.status}"
    assert not turn.proposed_actions, "no actions expected for a pure question"
    assert runtime.approved == [], "nothing should be approved"
    print("Answer-only test passed!")
    return True


if __name__ == "__main__":
    tests = [
        test_preview_proposes_draft,
        test_auto_approve_executes_draft,
        test_question_is_answered_without_action,
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
