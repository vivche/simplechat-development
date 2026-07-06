# memory.py
# Shared Memory Service: durable notes/context keyed by (owner_id, scope_key).
# Memory is always partitioned by owner_id — an agent can never read another user's memory.
# scope_key encodes the memory_scope from the agent definition:
#   - "agent" -> scope_key = f"agent:{agent_id}"  (private to that agent)
#   - "user"  -> scope_key = "user"               (shared across the owner's agents)
#   - "none"  -> memory disabled for that agent
#
# Two backends behind one interface: in-memory (POC) and Cosmos DB (production-ready).

import logging
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .config import RuntimeConfig

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryService:
    """Interface for shared memory. Implementations must enforce owner scoping."""

    def append(self, owner_id: str, scope_key: str, content: str) -> dict:
        raise NotImplementedError

    def list(self, owner_id: str, scope_key: str, limit: int = 50) -> List[dict]:
        raise NotImplementedError


class InMemoryMemoryService(MemoryService):
    """Thread-safe in-memory memory store for local development and the POC."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # keyed by (owner_id, scope_key) -> list of entries
        self._store: Dict[tuple, List[dict]] = {}

    def append(self, owner_id: str, scope_key: str, content: str) -> dict:
        entry = {"content": content, "created_at": _utc_now_iso()}
        with self._lock:
            self._store.setdefault((owner_id, scope_key), []).append(entry)
        return entry

    def list(self, owner_id: str, scope_key: str, limit: int = 50) -> List[dict]:
        with self._lock:
            entries = list(self._store.get((owner_id, scope_key), []))
        return entries[-limit:]


class CosmosMemoryService(MemoryService):
    """Cosmos DB memory store. Partitioned by owner_id for per-user isolation."""

    CONTAINER = "memory"
    PARTITION_KEY = "/owner_id"

    def __init__(self, config: RuntimeConfig) -> None:
        from azure.cosmos import CosmosClient, PartitionKey

        self._client = CosmosClient(config.cosmos_endpoint, credential=config.cosmos_key)
        database = self._client.create_database_if_not_exists(config.cosmos_database)
        self._container = database.create_container_if_not_exists(
            id=self.CONTAINER,
            partition_key=PartitionKey(path=self.PARTITION_KEY),
        )

    def append(self, owner_id: str, scope_key: str, content: str) -> dict:
        import uuid

        entry = {
            "id": str(uuid.uuid4()),
            "owner_id": owner_id,
            "scope_key": scope_key,
            "content": content,
            "created_at": _utc_now_iso(),
        }
        self._container.upsert_item(entry)
        return entry

    def list(self, owner_id: str, scope_key: str, limit: int = 50) -> List[dict]:
        items = self._container.query_items(
            query=(
                "SELECT * FROM c WHERE c.owner_id = @owner AND c.scope_key = @scope "
                "ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit"
            ),
            parameters=[
                {"name": "@owner", "value": owner_id},
                {"name": "@scope", "value": scope_key},
                {"name": "@limit", "value": limit},
            ],
            partition_key=owner_id,
        )
        return list(items)


def scope_key_for(memory_scope: str, agent_id: str) -> Optional[str]:
    """Translate an agent's memory_scope into a storage scope key. None means memory disabled."""
    if memory_scope == "agent":
        return f"agent:{agent_id}"
    if memory_scope == "user":
        return "user"
    return None


def build_memory_service(config: RuntimeConfig) -> MemoryService:
    """Factory: pick the backend based on configuration."""
    if config.use_in_memory_stores or not config.cosmos_endpoint:
        logger.info("Using in-memory memory service")
        return InMemoryMemoryService()
    logger.info("Using Cosmos DB memory service")
    return CosmosMemoryService(config)
