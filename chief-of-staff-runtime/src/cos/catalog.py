# catalog.py
# Tool Registry / Capability Catalog loader.
# The catalog is the security-reviewed set of capabilities (Tier 1, platform owner). Each capability
# maps a tool to its MAXIMUM delegated Graph scope. Agents may only reference and use a SUBSET.

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Capability:
    """A single vetted capability: a tool bound to its maximum Graph scope."""

    id: str
    display_name: str
    description: str
    graph_scope: str
    tool: str
    action: str  # "read" or "write"
    enabled: bool
    requires_approval: bool


class CapabilityCatalog:
    """In-memory view of the vetted capability catalog."""

    def __init__(self, version: str, data_scope: str, capabilities: List[Capability]):
        self.version = version
        self.data_scope = data_scope
        self._by_id: Dict[str, Capability] = {c.id: c for c in capabilities}

    @property
    def capabilities(self) -> List[Capability]:
        return list(self._by_id.values())

    def get(self, capability_id: str) -> Optional[Capability]:
        return self._by_id.get(capability_id)

    def exists(self, capability_id: str) -> bool:
        return capability_id in self._by_id

    def is_enabled(self, capability_id: str) -> bool:
        cap = self._by_id.get(capability_id)
        return bool(cap and cap.enabled)

    def scopes_for(self, capability_ids: List[str]) -> List[str]:
        """Return the delegated Graph scopes required by the given capabilities (deduplicated)."""
        scopes: List[str] = []
        for cid in capability_ids:
            cap = self._by_id.get(cid)
            if cap and cap.graph_scope and cap.graph_scope not in scopes:
                scopes.append(cap.graph_scope)
        return scopes

    def superset_scopes(self) -> List[str]:
        """All distinct Graph scopes across enabled capabilities (the consent superset)."""
        scopes: List[str] = []
        for cap in self._by_id.values():
            if cap.enabled and cap.graph_scope and cap.graph_scope not in scopes:
                scopes.append(cap.graph_scope)
        return scopes

    def public_view(self) -> dict:
        """Serializable catalog for the Builder UI (via GET /v1/catalog)."""
        return {
            "version": self.version,
            "data_scope": self.data_scope,
            "capabilities": [
                {
                    "id": c.id,
                    "display_name": c.display_name,
                    "description": c.description,
                    "graph_scope": c.graph_scope,
                    "action": c.action,
                    "enabled": c.enabled,
                    "requires_approval": c.requires_approval,
                }
                for c in self._by_id.values()
            ],
        }


def load_catalog(path: str) -> CapabilityCatalog:
    """Load the capability catalog from a JSON file relative to the app root."""
    resolved = path
    if not os.path.isabs(resolved):
        # Resolve relative to the src/ directory (parent of this package).
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        resolved = os.path.join(base_dir, path)

    with open(resolved, "r", encoding="utf-8") as handle:
        raw = json.load(handle)

    capabilities = [
        Capability(
            id=item["id"],
            display_name=item.get("display_name", item["id"]),
            description=item.get("description", ""),
            graph_scope=item.get("graph_scope", ""),
            tool=item.get("tool", ""),
            action=item.get("action", "read"),
            enabled=bool(item.get("enabled", False)),
            requires_approval=bool(item.get("requires_approval", False)),
        )
        for item in raw.get("capabilities", [])
    ]

    return CapabilityCatalog(
        version=str(raw.get("version", "0")),
        data_scope=raw.get("data_scope", "self-only"),
        capabilities=capabilities,
    )
