# auth.py
# Authentication: incoming token validation + On-Behalf-Of (OBO) exchange for Microsoft Graph.
#
# Flow (see docs/AUTH_FLOW.md, option A):
#   1. SimpleChat calls the runtime with a bearer token whose audience is this runtime's API
#      (api://<client_id>). We validate it against the tenant's JWKS.
#   2. The caller identity (oid/upn) is read from the VALIDATED token claims — never from the body.
#   3. To call Graph on the user's behalf, we exchange that token via OBO for a Graph token that is
#      scoped to only the capabilities the invoked agent uses (per-invocation least privilege).

import logging
from dataclasses import dataclass
from typing import List, Optional

import jwt
import msal
import requests
from jwt import PyJWKClient

from .config import RuntimeConfig

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Raised when a token is missing, malformed, or fails validation."""


@dataclass(frozen=True)
class CallerIdentity:
    """Identity derived from a validated access token. Never populated from request bodies."""

    oid: str  # Entra object id — the stable per-user identifier used for owner scoping.
    upn: str
    name: str
    raw_token: str  # the original assertion, needed for the OBO exchange


def extract_bearer_token(authorization_header: Optional[str]) -> str:
    """Pull the raw JWT out of an 'Authorization: Bearer <token>' header."""
    if not authorization_header:
        raise AuthError("missing Authorization header")
    parts = authorization_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthError("Authorization header must be 'Bearer <token>'")
    token = parts[1].strip()
    if not token:
        raise AuthError("empty bearer token")
    return token


class TokenValidator:
    """Validates incoming access tokens against the tenant JWKS (sovereign-aware)."""

    def __init__(self, config: RuntimeConfig) -> None:
        self._config = config
        # OpenID metadata drives issuer + signing keys; works for sovereign clouds via authority_host.
        self._metadata_url = f"{config.authority}/v2.0/.well-known/openid-configuration"
        self._jwks_client: Optional[PyJWKClient] = None
        self._issuer: Optional[str] = None
        # Accept both the App ID URI and the bare client id as valid audiences.
        self._audiences = [f"api://{config.client_id}", config.client_id]

    def _ensure_metadata(self) -> None:
        if self._jwks_client is not None and self._issuer is not None:
            return
        response = requests.get(self._metadata_url, timeout=10)
        response.raise_for_status()
        metadata = response.json()
        self._issuer = metadata["issuer"]
        self._jwks_client = PyJWKClient(metadata["jwks_uri"])

    def validate(self, token: str) -> CallerIdentity:
        try:
            self._ensure_metadata()
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._audiences,
                issuer=self._issuer,
            )
        except Exception as exc:  # noqa: BLE001 - surface all validation failures as AuthError
            raise AuthError(f"token validation failed: {exc}") from exc

        oid = claims.get("oid")
        if not oid:
            raise AuthError("token missing 'oid' claim")

        return CallerIdentity(
            oid=oid,
            upn=claims.get("upn") or claims.get("preferred_username", ""),
            name=claims.get("name", ""),
            raw_token=token,
        )


class OboTokenExchanger:
    """Exchanges a validated incoming token for a Graph token via the OBO flow."""

    def __init__(self, config: RuntimeConfig) -> None:
        self._config = config
        self._app = msal.ConfidentialClientApplication(
            client_id=config.client_id,
            client_credential=config.client_secret,
            authority=config.authority,
        )

    def acquire_graph_token(self, user_assertion: str, graph_scopes: List[str]) -> str:
        """Acquire a Graph access token on behalf of the user, limited to graph_scopes.

        graph_scopes is the per-invocation subset (least privilege). If empty, no Graph token is
        needed and this should not be called.
        """
        if not graph_scopes:
            raise AuthError("no graph scopes requested for OBO exchange")

        scopes = [self._to_resource_scope(s) for s in graph_scopes]
        result = self._app.acquire_token_on_behalf_of(
            user_assertion=user_assertion,
            scopes=scopes,
        )
        if "access_token" not in result:
            error = result.get("error_description") or result.get("error") or "unknown OBO error"
            raise AuthError(f"OBO exchange failed: {error}")
        return result["access_token"]

    def _to_resource_scope(self, scope: str) -> str:
        """Map a bare Graph permission (e.g. 'Mail.Read') to a fully-qualified resource scope."""
        if "://" in scope or scope.startswith("http"):
            return scope
        base = self._config.graph_base_url.split("/v1.0")[0].rstrip("/")
        return f"{base}/{scope}"
