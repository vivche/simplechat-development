#!/usr/bin/env python3
"""
Functional test for the Chief of Staff Runtime skeleton.
Version: chief-of-staff-runtime POC (decoupled component; not tied to SimpleChat config.py VERSION)
Implemented in: initial scaffold

This test ensures the runtime components wire together and enforce the core rules without needing
network access, Graph consent, or a Cosmos DB account:
  - the capability catalog loads and exposes only enabled scopes,
  - agent validation rejects unknown/disabled capabilities,
  - the in-memory Agent Registry enforces per-owner isolation,
  - the Shared Memory Service isolates by owner,
  - the orchestrator computes the least-privilege scope subset for an agent.
"""

import os
import sys

# Import the runtime package from src/.
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, SRC_DIR)

from cos.catalog import load_catalog  # noqa: E402
from cos.memory import InMemoryMemoryService, scope_key_for  # noqa: E402
from cos.registry import InMemoryAgentRegistry  # noqa: E402
from cos.schema import AgentValidationError, build_agent  # noqa: E402


CATALOG_PATH = os.path.join(SRC_DIR, "config", "capability_catalog.v1.json")


def test_catalog_loads_enabled_scopes():
    print("Testing capability catalog...")
    catalog = load_catalog(CATALOG_PATH)
    assert catalog.exists("email.read")
    assert catalog.is_enabled("email.read")
    assert not catalog.is_enabled("email.send")  # write cap disabled in POC
    superset = catalog.superset_scopes()
    assert "Mail.Read" in superset
    assert "Mail.Send" not in superset  # disabled caps excluded from consent superset
    print("  catalog OK")
    return catalog


def test_agent_validation(catalog):
    print("Testing agent validation...")
    good = build_agent(
        owner_id="owner-1",
        payload={"name": "Inbox Triage", "capabilities": ["email.read", "calendar.read"]},
        catalog=catalog,
    )
    assert good.owner_id == "owner-1"
    assert good.capabilities == ["email.read", "calendar.read"]

    for bad_caps, reason in (
        (["does.not.exist"], "unknown capability"),
        (["email.send"], "disabled capability"),
    ):
        try:
            build_agent("owner-1", {"name": "x", "capabilities": bad_caps}, catalog)
            raise AssertionError(f"expected validation failure for {reason}")
        except AgentValidationError:
            pass

    try:
        build_agent("owner-1", {"capabilities": []}, catalog)
        raise AssertionError("expected validation failure for missing name")
    except AgentValidationError:
        pass
    print("  validation OK")
    return good


def test_registry_owner_isolation(agent):
    print("Testing registry owner isolation...")
    registry = InMemoryAgentRegistry()
    registry.create(agent)
    # Same owner can read; different owner cannot.
    assert registry.get("owner-1", agent.id) is not None
    assert registry.get("owner-2", agent.id) is None
    assert len(registry.list_for_owner("owner-1")) == 1
    assert len(registry.list_for_owner("owner-2")) == 0
    assert registry.delete("owner-2", agent.id) is False
    assert registry.delete("owner-1", agent.id) is True
    print("  registry isolation OK")


def test_memory_isolation():
    print("Testing memory isolation...")
    memory = InMemoryMemoryService()
    key = scope_key_for("agent", "agent-123")
    assert key == "agent:agent-123"
    memory.append("owner-1", key, "note")
    assert len(memory.list("owner-1", key)) == 1
    assert len(memory.list("owner-2", key)) == 0
    assert scope_key_for("none", "agent-123") is None
    print("  memory isolation OK")


def test_scope_subset(catalog):
    print("Testing least-privilege scope subset...")
    scopes = catalog.scopes_for(["email.read"])
    assert scopes == ["Mail.Read"]  # only what the agent uses, not the full superset
    print("  scope subset OK")


def main():
    try:
        catalog = test_catalog_loads_enabled_scopes()
        agent = test_agent_validation(catalog)
        test_registry_owner_isolation(agent)
        test_memory_isolation()
        test_scope_subset(catalog)
        print("All tests passed!")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"Test failed: {exc}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
