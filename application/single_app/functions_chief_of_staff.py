# functions_chief_of_staff.py

import os
import json
import logging

# Note: functions_settings and functions_appinsights are imported lazily inside the
# functions that need them, so the pure data/parsing logic in this module can be
# loaded and tested without the full Flask/Azure runtime.

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


def load_graph_briefing_data(user_id):
    """Load live briefing input for a user from Microsoft Graph (Phase 2).

    Should return the same dict shape as load_sample_briefing_data():
    {'emails': [...], 'meetings': [...], 'teams_messages': [...]}.

    Implementation plan (Phase 2):
      - Acquire a delegated Graph token for the signed-in user (on-behalf-of),
        with scopes Mail.Read, Calendars.Read, Chat.Read.
      - GET /me/messages (recent/unread, windowed to the last 24-48h).
      - GET /me/calendarView (today + upcoming) for meetings.
      - GET /me/chats/.../messages for Teams.
      - Normalize each source into the same lightweight fields the sample fixtures use
        so _build_briefing_prompt and the LLM prompt need no changes.
    """
    raise NotImplementedError(
        "Microsoft Graph data source for Chief of Staff is not implemented yet (Phase 2)."
    )


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
