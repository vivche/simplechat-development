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
    "You are given the day's emails, meeting notes, and Teams messages. "
    "Produce a concise executive briefing and extract concrete action items. "
    "Return ONLY valid JSON (no markdown, no code fences) with this exact shape:\n"
    "{\n"
    '  "summary": "a short 2-4 sentence overview of what needs attention today",\n'
    '  "action_items": [\n'
    '    {"title": "short imperative task", "owner": "who is responsible or \'You\'", '
    '"due": "a due date or timeframe if mentioned, else empty string", '
    '"source": "email|meeting|teams", "priority": "high|medium|low"}\n'
    "  ]\n"
    "}\n"
    "Be factual and only include action items that are genuinely implied by the input."
)


def generate_briefing():
    """Generate the Chief of Staff briefing from sample data using the configured LLM.

    Returns a dict: {'summary': str, 'action_items': list, 'source_counts': dict}.
    """
    data = load_sample_briefing_data()
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
        return {'summary': content, 'action_items': []}

    return {
        'summary': parsed.get('summary', ''),
        'action_items': parsed.get('action_items', []) or [],
    }
