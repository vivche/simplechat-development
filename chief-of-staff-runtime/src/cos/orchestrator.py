# orchestrator.py
# Chief-of-Staff Orchestrator: the invocation engine that ties the components together.
#
# On invoke(caller, agent_id, task):
#   1. Load the agent (owner-scoped) from the registry.
#   2. Compute the least-privilege Graph scope subset from the agent's capabilities.
#   3. OBO-exchange the caller's token for a Graph token limited to that subset.
#   4. Dispatch each capability's read-only tool and collect context.
#   5. (POC) return the gathered context; a model-backed synthesis step is a later step.
#   6. Optionally persist a memory note for the agent/user scope.
#
# The orchestrator NEVER trusts a client-supplied identity: owner scoping uses caller.oid only.

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from .auth import CallerIdentity, OboTokenExchanger
from .catalog import CapabilityCatalog
from .graph_tools import GraphClient, build_tool_dispatch
from .memory import MemoryService, scope_key_for
from .registry import AgentRegistry
from .schema import AgentDefinition

logger = logging.getLogger(__name__)


class OrchestratorError(Exception):
    """Raised for invocation failures (agent not found, capability disabled, tool error)."""


@dataclass
class InvocationResult:
    agent_id: str
    agent_name: str
    scopes_used: List[str]
    context: Dict[str, list]
    notes: List[str]


class Orchestrator:
    def __init__(
        self,
        catalog: CapabilityCatalog,
        registry: AgentRegistry,
        memory: MemoryService,
        graph_client: GraphClient,
        obo: Optional[OboTokenExchanger],
    ) -> None:
        self._catalog = catalog
        self._registry = registry
        self._memory = memory
        self._graph_client = graph_client
        self._dispatch = build_tool_dispatch(graph_client)
        self._obo = obo

    def invoke(self, caller: CallerIdentity, agent_id: str, task: str) -> InvocationResult:
        agent = self._registry.get(caller.oid, agent_id)
        if agent is None:
            raise OrchestratorError("agent not found")

        # Enforce: only enabled catalog capabilities are honored at invoke time.
        active_caps = [c for c in agent.capabilities if self._catalog.is_enabled(c)]
        scopes = self._catalog.scopes_for(active_caps)

        context: Dict[str, list] = {}
        notes: List[str] = []

        if scopes:
            if self._obo is None:
                raise OrchestratorError(
                    "OBO exchanger not configured; cannot acquire Graph token for capabilities"
                )
            graph_token = self._obo.acquire_graph_token(caller.raw_token, scopes)
            for cap_id in active_caps:
                capability = self._catalog.get(cap_id)
                if capability is None:
                    continue
                tool = self._dispatch.get(capability.tool)
                if tool is None:
                    logger.warning("No tool bound for capability %s (tool=%s)", cap_id, capability.tool)
                    continue
                try:
                    context[capability.tool] = tool(graph_token)
                except Exception as exc:  # noqa: BLE001 - report per-tool failures without aborting all
                    logger.error("Tool %s failed: %s", capability.tool, exc)
                    context[capability.tool] = []
                    notes.append(f"{capability.tool} failed: {exc}")

        # Persist a lightweight memory note if the agent uses memory.
        memory_key = scope_key_for(agent.memory_scope, agent.id)
        if memory_key:
            self._memory.append(caller.oid, memory_key, f"invoked with task: {task}")

        return InvocationResult(
            agent_id=agent.id,
            agent_name=agent.name,
            scopes_used=scopes,
            context=context,
            notes=notes,
        )
