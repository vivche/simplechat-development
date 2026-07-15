# __init__.py
# cos_planner — a headless, host-agnostic LLM planner/orchestrator for the Chief of Staff Runtime.
#
# PORTABILITY BOUNDARY (see chief-of-staff-runtime/docs/BACKLOG.md "Orchestration/planner IP
# boundary"): this package has NO dependency on SimpleChat. It talks to the outside world ONLY
# through the ports defined in ports.py (LLMPort, RuntimePort). A host (SimpleChat today, any other
# app later) supplies concrete adapters for those ports and drives the planner. The UI is a host
# concern and lives entirely outside this package.

from .ports import (
    Capability,
    LLMPort,
    LLMResponse,
    PlannerTurn,
    ProposedAction,
    RuntimePort,
    ToolCall,
    ToolSpec,
)
from .planner import CosPlanner

__all__ = [
    "Capability",
    "CosPlanner",
    "LLMPort",
    "LLMResponse",
    "PlannerTurn",
    "ProposedAction",
    "RuntimePort",
    "ToolCall",
    "ToolSpec",
]
