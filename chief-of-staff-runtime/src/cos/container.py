# container.py
# Composition root: builds and caches the runtime's component graph once per process.
# Keeping wiring here keeps function_app.py thin and makes the components easy to unit-test.

import logging
from functools import lru_cache

from .auth import OboTokenExchanger, TokenValidator
from .catalog import CapabilityCatalog, load_catalog
from .config import RuntimeConfig, load_config
from .graph_tools import GraphClient
from .memory import build_memory_service
from .orchestrator import Orchestrator
from .registry import build_agent_registry

logger = logging.getLogger(__name__)


class Container:
    """Holds singleton instances of the runtime components."""

    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self.catalog: CapabilityCatalog = load_catalog(config.capability_catalog_path)
        self.registry = build_agent_registry(config)
        self.memory = build_memory_service(config)
        self.graph_client = GraphClient(config)
        self.token_validator = TokenValidator(config)
        self.obo = self._build_obo(config)
        self.orchestrator = Orchestrator(
            catalog=self.catalog,
            registry=self.registry,
            memory=self.memory,
            graph_client=self.graph_client,
            obo=self.obo,
        )

    @staticmethod
    def _build_obo(config: RuntimeConfig):
        if config.client_secret and not config.client_secret.startswith("<"):
            return OboTokenExchanger(config)
        logger.warning("No client secret configured; OBO disabled (Graph calls will not work)")
        return None


@lru_cache(maxsize=1)
def get_container() -> Container:
    """Return the process-wide Container, built lazily on first use."""
    return Container(load_config())
