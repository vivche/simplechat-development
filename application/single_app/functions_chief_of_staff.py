# functions_chief_of_staff.py

import os
import re
import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

# Note: functions_settings and functions_appinsights are imported lazily inside the
# functions that need them, so the pure data/parsing logic in this module can be
# loaded and tested without the full Flask/Azure runtime. The Microsoft Graph plugin
# is likewise imported lazily inside load_graph_briefing_data because it pulls in the
# semantic-kernel runtime.

# Directory holding the POC sample data fixtures (emails, meetings, Teams messages).
SAMPLE_DATA_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'static', 'chief_of_staff', 'sample_data'
)


def _log(message, level=logging.INFO):
    """Log via App Insights when available, otherwise fall back to stdlib logging."""
    try:
        from functions_appinsights import log_event
        log_event(message, level=level, category="CHIEF_OF_STAFF")
    except Exception:
        logging.getLogger(__name__).log(level, message)


# Setting key that selects where briefing input comes from. 'sample' uses the bundled
# POC fixtures; 'graph' pulls the signed-in user's live mail/calendar/Teams via Microsoft
# Graph (Phase 2). Defaults to 'sample' so the POC keeps working with no configuration.
DATA_SOURCE_SETTING = 'chief_of_staff_data_source'
DEFAULT_DATA_SOURCE = 'sample'


def load_sample_briefing_data():
    """Load the POC fixture data for emails, meetings, and Teams messages.

    Returns a dict with keys: emails, meetings, teams_messages.
    """
    sources = {
        'emails': 'emails.json',
        'meetings': 'meetings.json',
        'teams_messages': 'teams_messages.json',
    }
    data = {}
    for key, filename in sources.items():
        path = os.path.join(SAMPLE_DATA_DIR, filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data[key] = json.load(f)
        except (OSError, ValueError) as exc:
            _log(
                f"Chief of Staff: failed to load sample data '{filename}': {exc}",
                level=logging.WARNING,
            )
            data[key] = []
    return data


# How far back to look for recent mail/Teams activity, and how far forward to scan the
# calendar for meetings that still need preparation.
GRAPH_LOOKBACK_HOURS = 48
GRAPH_LOOKAHEAD_HOURS = 48
GRAPH_MAX_EMAILS = 15
GRAPH_MAX_MEETINGS = 10
GRAPH_MAX_CHATS = 5
GRAPH_MAX_MESSAGES_PER_CHAT = 5


def _strip_html(value):
    """Collapse a Graph HTML/text body into a short plain-text string for the prompt."""
    text = str(value or '')
    if not text:
        return ''
    # Drop tags, unescape the few entities Graph commonly emits, and squeeze whitespace.
    text = re.sub(r'<[^>]+>', ' ', text)
    text = (
        text.replace('&nbsp;', ' ')
        .replace('&amp;', '&')
        .replace('&lt;', '<')
        .replace('&gt;', '>')
        .replace('&quot;', '"')
        .replace('&#39;', "'")
    )
    return re.sub(r'\s+', ' ', text).strip()


def _format_graph_sender(address_holder):
    """Turn a Graph 'from'/'organizer' object into a 'Name <email>' string."""
    email_address = (address_holder or {}).get('emailAddress', {}) or {}
    name = str(email_address.get('name') or '').strip()
    address = str(email_address.get('address') or '').strip()
    if name and address:
        return f"{name} <{address}>"
    return name or address


def _normalize_graph_emails(value):
    """Normalize Graph message objects into the sample email fixture shape."""
    emails = []
    for message in value or []:
        if not isinstance(message, dict):
            continue
        emails.append({
            'id': message.get('id', ''),
            'from': _format_graph_sender(message.get('from')),
            'to': 'You',
            'received': message.get('receivedDateTime', ''),
            'subject': message.get('subject', ''),
            'body': _strip_html(message.get('bodyPreview')),
        })
    return emails


def _normalize_graph_meetings(value):
    """Normalize Graph calendar event objects into the sample meeting fixture shape."""
    meetings = []
    for event in value or []:
        if not isinstance(event, dict):
            continue
        attendees = []
        for attendee in event.get('attendees', []) or []:
            if not isinstance(attendee, dict):
                continue
            attendee_email = attendee.get('emailAddress', {}) or {}
            attendee_name = str(attendee_email.get('name') or attendee_email.get('address') or '').strip()
            if attendee_name:
                attendees.append(attendee_name)
        meetings.append({
            'id': event.get('id', ''),
            'title': event.get('subject', ''),
            'start': (event.get('start', {}) or {}).get('dateTime', ''),
            'end': (event.get('end', {}) or {}).get('dateTime', ''),
            'attendees': attendees,
            'notes': _strip_html(event.get('bodyPreview')),
        })
    return meetings


def _normalize_graph_teams(messages, channel=''):
    """Normalize Graph chat message objects into the sample Teams fixture shape."""
    teams_messages = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        # Skip system messages (membership changes, etc.) that carry no user body.
        if str(message.get('messageType') or 'message').lower() != 'message':
            continue
        sender_user = ((message.get('from') or {}).get('user') or {})
        sender = str(sender_user.get('displayName') or '').strip()
        body_text = _strip_html((message.get('body') or {}).get('content'))
        if not body_text:
            continue
        teams_messages.append({
            'id': message.get('id', ''),
            'channel': channel or 'Teams chat',
            'from': sender,
            'sent': message.get('createdDateTime', ''),
            'message': body_text,
        })
    return teams_messages


def _graph_value(result):
    """Return the list under a Graph plugin result's 'value', or [] on error/empty."""
    if isinstance(result, dict) and not result.get('error'):
        value = result.get('value')
        if isinstance(value, list):
            return value
    if isinstance(result, dict) and result.get('error'):
        _log(
            f"Chief of Staff: Graph request '{result.get('operation')}' failed: "
            f"{result.get('error')} - {result.get('message')}",
            level=logging.WARNING,
        )
    return []


def _load_graph_teams_messages(plugin):
    """Best-effort fetch of the user's recent Teams chat messages via the Graph plugin."""
    teams_messages = []
    chats_result = plugin._perform_graph_request(
        'cos_list_chats',
        'GET',
        '/v1.0/me/chats',
        ['Chat.Read'],
        params={'$top': GRAPH_MAX_CHATS, '$select': 'id,topic,chatType'},
        paginate=True,
        max_items=GRAPH_MAX_CHATS,
    )
    for chat in _graph_value(chats_result):
        if not isinstance(chat, dict):
            continue
        chat_id = str(chat.get('id') or '').strip()
        if not chat_id:
            continue
        chat_topic = str(chat.get('topic') or '').strip() or 'Teams chat'
        messages_result = plugin._perform_graph_request(
            'cos_chat_messages',
            'GET',
            f"/v1.0/me/chats/{quote(chat_id, safe='')}/messages",
            ['Chat.Read'],
            params={'$top': GRAPH_MAX_MESSAGES_PER_CHAT},
            paginate=False,
            max_items=GRAPH_MAX_MESSAGES_PER_CHAT,
        )
        teams_messages.extend(
            _normalize_graph_teams(_graph_value(messages_result), channel=chat_topic)
        )
    return teams_messages


def load_graph_briefing_data(user_id):
    """Load live briefing input for a user from Microsoft Graph.

    Returns the same dict shape as load_sample_briefing_data():
    {'emails': [...], 'meetings': [...], 'teams_messages': [...]}.

    Reuses SimpleChat's existing MSGraphPlugin, which acquires a delegated token for the
    signed-in user (via the MSAL session cache) and handles pagination and error shaping.
    Each source is fetched independently so a failure in one (for example, a missing
    Chat.Read consent) still lets the others populate the briefing.
    """
    # Imported lazily: MSGraphPlugin pulls in the semantic-kernel runtime, which we do not
    # want to require for the pure data/parsing paths in this module.
    from semantic_kernel_plugins.msgraph_plugin import MSGraphPlugin

    plugin = MSGraphPlugin()

    now = datetime.now(timezone.utc)
    window_start = (now - timedelta(hours=GRAPH_LOOKBACK_HOURS)).strftime('%Y-%m-%dT%H:%M:%SZ')
    window_end = (now + timedelta(hours=GRAPH_LOOKAHEAD_HOURS)).strftime('%Y-%m-%dT%H:%M:%SZ')

    data = {'emails': [], 'meetings': [], 'teams_messages': []}

    # Recent mail (newest first).
    try:
        messages_result = plugin.get_my_messages(
            top=GRAPH_MAX_EMAILS,
            select_fields='id,subject,from,receivedDateTime,bodyPreview',
        )
        data['emails'] = _normalize_graph_emails(_graph_value(messages_result))
    except Exception as exc:
        _log(f"Chief of Staff: Graph mail fetch failed: {exc}", level=logging.WARNING)

    # Calendar events in the today +/- window that may still need preparation.
    try:
        events_result = plugin.get_my_events(
            top=GRAPH_MAX_MEETINGS,
            start_datetime=window_start,
            end_datetime=window_end,
            select_fields='id,subject,start,end,attendees,bodyPreview,organizer',
        )
        data['meetings'] = _normalize_graph_meetings(_graph_value(events_result))
    except Exception as exc:
        _log(f"Chief of Staff: Graph calendar fetch failed: {exc}", level=logging.WARNING)

    # Recent Teams chat messages (best effort).
    try:
        data['teams_messages'] = _load_graph_teams_messages(plugin)
    except Exception as exc:
        _log(f"Chief of Staff: Graph Teams fetch failed: {exc}", level=logging.WARNING)

    _log(
        "Chief of Staff: loaded Graph briefing data "
        f"(emails={len(data['emails'])}, meetings={len(data['meetings'])}, "
        f"teams={len(data['teams_messages'])})."
    )
    return data


def load_briefing_data(user_id=None):
    """Resolve the configured data source and return the day's input data.

    Reads the 'chief_of_staff_data_source' setting: 'sample' (default) uses the bundled
    POC fixtures; 'graph' pulls the signed-in user's live data. If the live source is
    selected but unavailable, falls back to sample data so the dashboard still renders.
    """
    source = DEFAULT_DATA_SOURCE
    try:
        from functions_settings import get_settings
        settings = get_settings()
        source = (settings.get(DATA_SOURCE_SETTING) or DEFAULT_DATA_SOURCE).lower()
    except Exception as exc:
        _log(
            f"Chief of Staff: could not read data-source setting, defaulting to sample: {exc}",
            level=logging.WARNING,
        )

    if source == 'graph':
        try:
            return load_graph_briefing_data(user_id)
        except Exception as exc:
            _log(
                f"Chief of Staff: Graph data source unavailable, falling back to sample: {exc}",
                level=logging.WARNING,
            )
            return load_sample_briefing_data()

    return load_sample_briefing_data()


def _build_briefing_prompt(data):
    """Build the user prompt text from the loaded source data."""
    return (
        "Here is today's raw input from three sources. Produce the briefing.\n\n"
        f"EMAILS:\n{json.dumps(data.get('emails', []), indent=2)}\n\n"
        f"MEETINGS:\n{json.dumps(data.get('meetings', []), indent=2)}\n\n"
        f"TEAMS MESSAGES:\n{json.dumps(data.get('teams_messages', []), indent=2)}"
    )


BRIEFING_SYSTEM_PROMPT = (
    "You are an AI Chief of Staff for a delivery team lead. "
    "You are given the day's emails, meeting notes/calendar, and Teams messages. "
    "Review all three sources and produce a single briefing that helps the user stay on "
    "top of their work. Return ONLY valid JSON (no markdown, no code fences) with this "
    "exact shape:\n"
    "{\n"
    '  "summary": "a short 2-4 sentence overview of what needs attention today",\n'
    '  "priorities": [\n'
    '    {"rank": 1, "title": "the single most important thing to do", '
    '"why": "one short sentence on why it matters most now"}\n'
    "  ],\n"
    '  "action_items": [\n'
    '    {"title": "short imperative task", "owner": "who is responsible or \'You\'", '
    '"due": "a due date or timeframe if mentioned, else empty string", '
    '"source": "email|meeting|teams", "priority": "high|medium|low"}\n'
    "  ],\n"
    '  "commitments": [\n'
    '    {"commitment": "something YOU promised or agreed to do", '
    '"to_whom": "the person or group you owe it to", '
    '"due": "a due date or timeframe if mentioned, else empty string", '
    '"source": "email|meeting|teams"}\n'
    "  ],\n"
    '  "meeting_briefings": [\n'
    '    {"meeting": "meeting title", "when": "start time or timeframe", '
    '"objective": "the goal / why this meeting matters", '
    '"prep": ["a short prep bullet the user should do or bring"], '
    '"attendees": "comma-separated key attendees"}\n'
    "  ],\n"
    '  "follow_ups": [\n'
    '    {"item": "an open item awaiting a response or still unresolved", '
    '"waiting_on": "who owes the response, or \'You\'", '
    '"age": "how long it has been open or since when, if known, else empty string", '
    '"suggested_nudge": "a short suggested next step to move it forward"}\n'
    "  ]\n"
    "}\n"
    "Guidance: 'priorities' should rank the 2-4 highest-impact items across everything, "
    "ordered by rank (1 = do first). 'commitments' are things the USER personally said they "
    "would do (look for phrases like 'You agreed', 'You to', 'I'll', 'I will'). "
    "'meeting_briefings' should cover upcoming or same-day meetings that need preparation. "
    "'follow_ups' are open loops: questions asked but unanswered, approvals pending, or items "
    "waiting on someone. Be factual and only include items genuinely implied by the input. "
    "If a section has nothing, return an empty array for it."
)


def generate_briefing(user_id=None):
    """Generate the Chief of Staff briefing using the configured data source and LLM.

    The input data comes from load_briefing_data() (sample fixtures or live Microsoft
    Graph, per the 'chief_of_staff_data_source' setting). Returns a dict with keys:
    summary, priorities, action_items, commitments, meeting_briefings, follow_ups,
    source_counts.
    """
    data = load_briefing_data(user_id)
    source_counts = {
        'emails': len(data.get('emails', [])),
        'meetings': len(data.get('meetings', [])),
        'teams_messages': len(data.get('teams_messages', [])),
    }

    from functions_settings import get_settings
    settings = get_settings()

    # Reuse SimpleChat's existing GPT client resolution (APIM / managed identity /
    # key / GCC clouds all handled) rather than constructing a new client here.
    from route_backend_conversation_export import _initialize_gpt_client
    gpt_client, gpt_model = _initialize_gpt_client(settings)

    model_lower = (gpt_model or '').lower()
    is_reasoning_model = (
        'o1' in model_lower or 'o3' in model_lower or 'gpt-5' in model_lower
    )
    instruction_role = 'developer' if is_reasoning_model else 'system'

    response = gpt_client.chat.completions.create(
        model=gpt_model,
        messages=[
            {'role': instruction_role, 'content': BRIEFING_SYSTEM_PROMPT},
            {'role': 'user', 'content': _build_briefing_prompt(data)},
        ],
    )

    content = ''
    if response.choices:
        content = (response.choices[0].message.content or '').strip()

    briefing = _parse_briefing_json(content)
    briefing['source_counts'] = source_counts
    return briefing


def _parse_briefing_json(content):
    """Parse the model response into a briefing dict, tolerating stray formatting."""
    text = content.strip()
    # Strip a fenced code block if the model added one despite instructions.
    if text.startswith('```'):
        text = text.strip('`')
        if text.lower().startswith('json'):
            text = text[4:]
        text = text.strip()

    try:
        parsed = json.loads(text)
    except ValueError:
        _log(
            "Chief of Staff: model returned non-JSON briefing; returning raw text.",
            level=logging.WARNING,
        )
        return {
            'summary': content,
            'priorities': [],
            'action_items': [],
            'commitments': [],
            'meeting_briefings': [],
            'follow_ups': [],
        }

    return {
        'summary': parsed.get('summary', ''),
        'priorities': parsed.get('priorities', []) or [],
        'action_items': parsed.get('action_items', []) or [],
        'commitments': parsed.get('commitments', []) or [],
        'meeting_briefings': parsed.get('meeting_briefings', []) or [],
        'follow_ups': parsed.get('follow_ups', []) or [],
    }
