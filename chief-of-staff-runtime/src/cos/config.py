# config.py
# Environment-based configuration for the Chief of Staff Runtime.
# All configuration comes from environment variables (COS_* prefix) so the service stays portable
# and can be hosted on any platform without shared config files.

import os
from dataclasses import dataclass


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _get_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class RuntimeConfig:
    """Immutable snapshot of runtime configuration read from the environment."""

    tenant_id: str
    client_id: str
    client_secret: str
    api_scope: str

    graph_base_url: str
    authority_host: str

    cosmos_endpoint: str
    cosmos_key: str
    cosmos_database: str
    use_in_memory_stores: bool

    capability_catalog_path: str

    graph_lookback_hours: int
    graph_lookahead_hours: int

    @property
    def authority(self) -> str:
        """Full Entra authority URL for this tenant (sovereign-aware)."""
        return f"{self.authority_host.rstrip('/')}/{self.tenant_id}"


def load_config() -> RuntimeConfig:
    """Build a RuntimeConfig from the current environment."""
    return RuntimeConfig(
        tenant_id=os.environ.get("COS_TENANT_ID", ""),
        client_id=os.environ.get("COS_CLIENT_ID", ""),
        client_secret=os.environ.get("COS_CLIENT_SECRET", ""),
        api_scope=os.environ.get("COS_API_SCOPE", ""),
        graph_base_url=os.environ.get("COS_GRAPH_BASE_URL", "https://graph.microsoft.us/v1.0"),
        authority_host=os.environ.get("COS_AUTHORITY_HOST", "https://login.microsoftonline.us"),
        cosmos_endpoint=os.environ.get("COS_COSMOS_ENDPOINT", ""),
        cosmos_key=os.environ.get("COS_COSMOS_KEY", ""),
        cosmos_database=os.environ.get("COS_COSMOS_DATABASE", "chief_of_staff"),
        use_in_memory_stores=_get_bool("COS_USE_IN_MEMORY_STORES", True),
        capability_catalog_path=os.environ.get(
            "COS_CAPABILITY_CATALOG_PATH", "config/capability_catalog.v1.json"
        ),
        graph_lookback_hours=_get_int("COS_GRAPH_LOOKBACK_HOURS", 48),
        graph_lookahead_hours=_get_int("COS_GRAPH_LOOKAHEAD_HOURS", 48),
    )
