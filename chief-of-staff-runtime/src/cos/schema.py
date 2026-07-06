# schema.py
# Agent Definition Schema.
# An agent definition has two zones (see docs/ARCHITECTURE.md):
#   - Free-form zone: name, description, instructions, examples, output_format, memory_scope.
#     Anything the author wants; the differentiator that lets users create agents dynamically.
#   - Catalog-constrained zone: capabilities[], data_scope, model.
#     Validated against the vetted capability catalog. This is the least-privilege boundary.

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .catalog import CapabilityCatalog


class AgentValidationError(ValueError):
    """Raised when an agent definition violates the catalog-constrained zone rules."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentDefinition:
    """A user- or admin-authored agent. Persisted per-owner in the Agent Registry."""

    # Identity
    id: str
    owner_id: str  # Entra object id (oid) of the owner — never client-supplied at invoke time.

    # Free-form zone
    name: str
    description: str = ""
    instructions: str = ""
    examples: List[str] = field(default_factory=list)
    output_format: str = "markdown"
    memory_scope: str = "agent"  # "agent" | "user" | "none"

    # Catalog-constrained zone
    capabilities: List[str] = field(default_factory=list)
    data_scope: str = "self-only"
    model: str = "gpt-4o"

    # Metadata
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "name": self.name,
            "description": self.description,
            "instructions": self.instructions,
            "examples": list(self.examples),
            "output_format": self.output_format,
            "memory_scope": self.memory_scope,
            "capabilities": list(self.capabilities),
            "data_scope": self.data_scope,
            "model": self.model,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "AgentDefinition":
        return cls(
            id=data.get("id") or str(uuid.uuid4()),
            owner_id=data["owner_id"],
            name=data["name"],
            description=data.get("description", ""),
            instructions=data.get("instructions", ""),
            examples=list(data.get("examples", [])),
            output_format=data.get("output_format", "markdown"),
            memory_scope=data.get("memory_scope", "agent"),
            capabilities=list(data.get("capabilities", [])),
            data_scope=data.get("data_scope", "self-only"),
            model=data.get("model", "gpt-4o"),
            created_at=data.get("created_at", _utc_now_iso()),
            updated_at=data.get("updated_at", _utc_now_iso()),
        )


def build_agent(owner_id: str, payload: Dict, catalog: CapabilityCatalog) -> AgentDefinition:
    """Construct and validate an AgentDefinition from a request payload.

    Raises AgentValidationError if the catalog-constrained zone is invalid.
    """
    if not owner_id:
        raise AgentValidationError(["owner_id is required and is derived from the caller's token"])

    name = (payload.get("name") or "").strip()
    errors: List[str] = []
    if not name:
        errors.append("name is required")

    memory_scope = payload.get("memory_scope", "agent")
    if memory_scope not in ("agent", "user", "none"):
        errors.append("memory_scope must be one of: agent, user, none")

    data_scope = payload.get("data_scope", "self-only")
    if data_scope != "self-only":
        errors.append("data_scope must be 'self-only' in this runtime")

    capabilities = list(payload.get("capabilities", []))
    for cap_id in capabilities:
        if not catalog.exists(cap_id):
            errors.append(f"unknown capability: {cap_id}")
        elif not catalog.is_enabled(cap_id):
            errors.append(f"capability not enabled: {cap_id}")

    if errors:
        raise AgentValidationError(errors)

    return AgentDefinition(
        id=str(uuid.uuid4()),
        owner_id=owner_id,
        name=name,
        description=payload.get("description", ""),
        instructions=payload.get("instructions", ""),
        examples=list(payload.get("examples", [])),
        output_format=payload.get("output_format", "markdown"),
        memory_scope=memory_scope,
        capabilities=capabilities,
        data_scope=data_scope,
        model=payload.get("model", "gpt-4o"),
    )
