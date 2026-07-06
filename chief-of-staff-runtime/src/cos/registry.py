# registry.py
# Agent Registry: persistence for agent definitions, isolated per owner.
# Two backends behind one interface: an in-memory store (POC/local) and a Cosmos DB store
# (production-ready). Backend is selected by config; callers use the same API.
#
# Access-control rule: every read/update/delete is scoped by owner_id. The owner_id comes from the
# caller's validated token, never from client input, so one user can never touch another's agents.

import logging
import threading
from typing import Dict, List, Optional

from .config import RuntimeConfig
from .schema import AgentDefinition

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Interface for agent persistence. Implementations must enforce owner scoping."""

    def create(self, agent: AgentDefinition) -> AgentDefinition:
        raise NotImplementedError

    def get(self, owner_id: str, agent_id: str) -> Optional[AgentDefinition]:
        raise NotImplementedError

    def list_for_owner(self, owner_id: str) -> List[AgentDefinition]:
        raise NotImplementedError

    def delete(self, owner_id: str, agent_id: str) -> bool:
        raise NotImplementedError


class InMemoryAgentRegistry(AgentRegistry):
    """Thread-safe in-memory registry for local development and the POC."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._agents: Dict[str, AgentDefinition] = {}

    def create(self, agent: AgentDefinition) -> AgentDefinition:
        with self._lock:
            self._agents[agent.id] = agent
        return agent

    def get(self, owner_id: str, agent_id: str) -> Optional[AgentDefinition]:
        with self._lock:
            agent = self._agents.get(agent_id)
        if agent is None or agent.owner_id != owner_id:
            return None
        return agent

    def list_for_owner(self, owner_id: str) -> List[AgentDefinition]:
        with self._lock:
            return [a for a in self._agents.values() if a.owner_id == owner_id]

    def delete(self, owner_id: str, agent_id: str) -> bool:
        with self._lock:
            agent = self._agents.get(agent_id)
            if agent is None or agent.owner_id != owner_id:
                return False
            del self._agents[agent_id]
            return True


class CosmosAgentRegistry(AgentRegistry):
    """Cosmos DB registry. Partitioned by owner_id for per-user isolation and efficient queries."""

    CONTAINER = "agents"
    PARTITION_KEY = "/owner_id"

    def __init__(self, config: RuntimeConfig) -> None:
        # Import here so the azure-cosmos dependency is only required when this backend is used.
        from azure.cosmos import CosmosClient, PartitionKey

        self._client = CosmosClient(config.cosmos_endpoint, credential=config.cosmos_key)
        database = self._client.create_database_if_not_exists(config.cosmos_database)
        self._container = database.create_container_if_not_exists(
            id=self.CONTAINER,
            partition_key=PartitionKey(path=self.PARTITION_KEY),
        )

    def create(self, agent: AgentDefinition) -> AgentDefinition:
        self._container.upsert_item(agent.to_dict())
        return agent

    def get(self, owner_id: str, agent_id: str) -> Optional[AgentDefinition]:
        from azure.cosmos import exceptions

        try:
            item = self._container.read_item(item=agent_id, partition_key=owner_id)
        except exceptions.CosmosResourceNotFoundError:
            return None
        return AgentDefinition.from_dict(item)

    def list_for_owner(self, owner_id: str) -> List[AgentDefinition]:
        items = self._container.query_items(
            query="SELECT * FROM c WHERE c.owner_id = @owner",
            parameters=[{"name": "@owner", "value": owner_id}],
            partition_key=owner_id,
        )
        return [AgentDefinition.from_dict(item) for item in items]

    def delete(self, owner_id: str, agent_id: str) -> bool:
        from azure.cosmos import exceptions

        try:
            self._container.delete_item(item=agent_id, partition_key=owner_id)
            return True
        except exceptions.CosmosResourceNotFoundError:
            return False


def build_agent_registry(config: RuntimeConfig) -> AgentRegistry:
    """Factory: pick the backend based on configuration."""
    if config.use_in_memory_stores or not config.cosmos_endpoint:
        logger.info("Using in-memory agent registry")
        return InMemoryAgentRegistry()
    logger.info("Using Cosmos DB agent registry")
    return CosmosAgentRegistry(config)
