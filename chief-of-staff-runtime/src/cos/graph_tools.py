# graph_tools.py
# Read-only Microsoft Graph tool implementations (sovereign-aware).
# Each tool corresponds to a capability in the catalog and maps 1:1 to its 'tool' field:
#   get_my_messages -> email.read      (Mail.Read)
#   get_my_events   -> calendar.read   (Calendars.Read)
#   get_my_chats    -> teams.chat.read (Chat.Read)
#
# These call Graph with a token acquired via OBO (see auth.py). They require admin consent to be
# live-callable. Until consent is granted they will return a 403 from Graph, which is expected.

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List

import requests

from .config import RuntimeConfig

logger = logging.getLogger(__name__)


class GraphClient:
    """Thin read-only Graph client. All calls use a delegated (OBO) token for the signed-in user."""

    def __init__(self, config: RuntimeConfig) -> None:
        self._base_url = config.graph_base_url.rstrip("/")
        self._lookback_hours = config.graph_lookback_hours
        self._lookahead_hours = config.graph_lookahead_hours

    def _get(self, access_token: str, path: str, params: Dict) -> dict:
        response = requests.get(
            f"{self._base_url}{path}",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def get_my_messages(self, access_token: str, top: int = 10) -> List[dict]:
        """Recent inbox messages (Mail.Read)."""
        data = self._get(
            access_token,
            "/me/messages",
            {
                "$top": top,
                "$select": "subject,from,receivedDateTime,bodyPreview,isRead,importance",
                "$orderby": "receivedDateTime DESC",
            },
        )
        return data.get("value", [])

    def get_my_events(self, access_token: str, top: int = 25) -> List[dict]:
        """Calendar events within the configured look-back/look-ahead window (Calendars.Read)."""
        now = datetime.now(timezone.utc)
        start = (now - timedelta(hours=self._lookback_hours)).isoformat()
        end = (now + timedelta(hours=self._lookahead_hours)).isoformat()
        data = self._get(
            access_token,
            "/me/calendarView",
            {
                "startDateTime": start,
                "endDateTime": end,
                "$top": top,
                "$select": "subject,organizer,start,end,location,isAllDay,attendees",
                "$orderby": "start/dateTime",
            },
        )
        return data.get("value", [])

    def get_my_chats(self, access_token: str, top: int = 10) -> List[dict]:
        """Recent Teams chats (Chat.Read)."""
        data = self._get(
            access_token,
            "/me/chats",
            {
                "$top": top,
                "$select": "id,topic,chatType,lastUpdatedDateTime",
                "$orderby": "lastUpdatedDateTime DESC",
            },
        )
        return data.get("value", [])


# Tool name -> bound method resolver. The orchestrator uses this to dispatch a capability's tool.
def build_tool_dispatch(client: GraphClient) -> Dict[str, Callable[[str], List[dict]]]:
    return {
        "get_my_messages": lambda token: client.get_my_messages(token),
        "get_my_events": lambda token: client.get_my_events(token),
        "get_my_chats": lambda token: client.get_my_chats(token),
    }
