# ports.py
# The portability contract for cos_planner. The planner depends ONLY on these interfaces and
# value types — never on any host (SimpleChat) module. A host supplies concrete implementations
# of LLMPort and RuntimePort and passes host data (agent, capabilities) in as plain dataclasses.

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class Capability:
    """A single vetted capability the agent may use (a subset of the runtime catalog).

    parameters is a JSON-schema-style object describing the arguments a write capability takes
    (e.g. {"type": "object", "properties": {...}, "required": [...]}). Read capabilities usually
    have no parameters.
    """

    id: str
    display_name: str = ""
    description: str = ""
    action: str = "read"  # "read" or "write"
    requires_approval: bool = False
    parameters: Optional[Dict[str, Any]] = None


@dataclass
class ToolSpec:
    """A vendor-neutral tool definition the LLM may call. The LLM adapter converts this into the
    concrete provider format (e.g. OpenAI function-tool schema)."""

    name: str
    description: str
    parameters: Dict[str, Any]


@dataclass
class ToolCall:
    """A single tool invocation the model requested."""

    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    """Normalized result of one LLM turn."""

    text: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)


@dataclass
class ProposedAction:
    """A write/send action the planner proposes (never executed until approved)."""

    capability: str
    parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"capability": self.capability, "parameters": self.parameters}


@dataclass
class PlannerTurn:
    """The result of one planner turn returned to the host for rendering."""

    # "answered"          — no write proposed; reply is the answer.
    # "awaiting_approval" — one or more write actions proposed; host must confirm before executing.
    # "executed"          — write actions were auto-approved and executed this turn.
    # "error"             — something failed; reply carries a human-readable message.
    status: str
    reply: str = ""
    proposed_actions: List[Dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    results: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    scopes_used: List[str] = field(default_factory=list)
    # Set when a reviewer agent handed back a verdict on the proposed actions (multi-agent handoff).
    review: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "reply": self.reply,
            "proposed_actions": self.proposed_actions,
            "context": self.context,
            "results": self.results,
            "notes": self.notes,
            "scopes_used": self.scopes_used,
            "review": self.review,
        }


class LLMPort(Protocol):
    """A minimal chat-completion interface with optional tool calling.

    messages: list of {"role": "system"|"user"|"assistant", "content": str}.
    tools: optional list of ToolSpec the model may call.
    Returns an LLMResponse with assistant text and/or requested tool calls.
    """

    def complete(
        self, messages: List[Dict[str, str]], tools: Optional[List[ToolSpec]] = None
    ) -> LLMResponse:
        ...


class RuntimePort(Protocol):
    """The Chief of Staff Runtime seen by the planner: invoke an agent and approve/reject writes.

    Each method returns the runtime's parsed JSON body as a dict. Implementations raise on
    transport/config failure.
    """

    def invoke(
        self,
        agent_id: str,
        task: str,
        parameters: Optional[Dict[str, Any]] = None,
        proposed_actions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        ...

    def approve(self, action_id: str) -> Dict[str, Any]:
        ...

    def reject(self, action_id: str) -> Dict[str, Any]:
        ...
