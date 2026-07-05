#!/usr/bin/env python3
"""
Functional test for the AI Chief of Staff POC dashboard.
Version: 0.250.022
Implemented in: 0.250.015

This test ensures that:
  - The bundled sample fixtures (emails, meetings, Teams messages) load correctly.
  - The briefing prompt builder includes all three sources.
  - The model-response JSON parser tolerates fenced code blocks and malformed output.
  - The parser exposes all briefing sections (priorities, action items,
    commitments, meeting briefings, follow-ups).
  - The Microsoft Graph normalizers map Graph JSON into the sample fixture shape
    (added in 0.250.019 with the Graph data source).
"""

import sys
import os
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

APP_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'application', 'single_app')
)
sys.path.insert(0, APP_DIR)


def test_load_sample_data():
    """Sample fixtures should load and contain all three source types."""
    print("Testing sample data loading...")
    try:
        from functions_chief_of_staff import load_sample_briefing_data

        data = load_sample_briefing_data()
        assert isinstance(data, dict), "Expected a dict of sources"
        for key in ('emails', 'meetings', 'teams_messages'):
            assert key in data, f"Missing source '{key}'"
            assert isinstance(data[key], list), f"Source '{key}' should be a list"
            assert len(data[key]) > 0, f"Source '{key}' should not be empty"

        print("Sample data loading passed!")
        return True
    except Exception as e:
        print(f"Sample data loading failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_prompt_includes_all_sources():
    """The prompt builder should reference all three source blocks."""
    print("Testing briefing prompt builder...")
    try:
        from functions_chief_of_staff import _build_briefing_prompt, load_sample_briefing_data

        prompt = _build_briefing_prompt(load_sample_briefing_data())
        assert 'EMAILS:' in prompt
        assert 'MEETINGS:' in prompt
        assert 'TEAMS MESSAGES:' in prompt

        print("Prompt builder passed!")
        return True
    except Exception as e:
        print(f"Prompt builder failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_parse_briefing_json():
    """The parser should handle clean JSON, fenced JSON, and malformed text."""
    print("Testing briefing JSON parser...")
    try:
        from functions_chief_of_staff import _parse_briefing_json

        section_keys = (
            'priorities', 'action_items', 'commitments',
            'meeting_briefings', 'follow_ups',
        )

        clean = json.dumps({
            'summary': 'Hi',
            'priorities': [{'rank': 1, 'title': 'Top thing', 'why': 'Urgent'}],
            'action_items': [{'title': 'Do X'}],
            'commitments': [{'commitment': 'Send report', 'to_whom': 'Priya'}],
            'meeting_briefings': [{'meeting': 'Go/No-Go', 'prep': ['bring risks']}],
            'follow_ups': [{'item': 'Ticket number', 'waiting_on': 'Marcus'}],
        })
        result = _parse_briefing_json(clean)
        assert result['summary'] == 'Hi'
        assert len(result['action_items']) == 1
        assert len(result['priorities']) == 1
        assert len(result['commitments']) == 1
        assert len(result['meeting_briefings']) == 1
        assert len(result['follow_ups']) == 1

        fenced = "```json\n" + clean + "\n```"
        result = _parse_briefing_json(fenced)
        assert result['summary'] == 'Hi'

        # Malformed output should still return every section key as a safe default.
        bad = "not json at all"
        result = _parse_briefing_json(bad)
        assert result['summary'] == bad
        for key in section_keys:
            assert result[key] == [], f"Expected empty list for '{key}' on bad input"

        print("JSON parser passed!")
        return True
    except Exception as e:
        print(f"JSON parser failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_graph_normalizers():
    """Graph JSON should normalize into the same shape as the sample fixtures."""
    print("Testing Microsoft Graph normalizers...")
    try:
        from functions_chief_of_staff import (
            _normalize_graph_emails,
            _normalize_graph_meetings,
            _normalize_graph_teams,
        )

        emails = _normalize_graph_emails([
            {
                'id': 'AAMk',
                'subject': 'Release decision',
                'from': {'emailAddress': {'name': 'Priya Nair', 'address': 'priya@contoso.gov'}},
                'receivedDateTime': '2025-06-09T08:12:00Z',
                'bodyPreview': 'Need a <b>decision</b> by Wednesday.&nbsp;Thanks',
            }
        ])
        assert len(emails) == 1
        email = emails[0]
        assert email['from'] == 'Priya Nair <priya@contoso.gov>'
        assert email['to'] == 'You'
        assert email['received'] == '2025-06-09T08:12:00Z'
        assert email['subject'] == 'Release decision'
        assert '<b>' not in email['body'] and 'decision by Wednesday' in email['body']

        meetings = _normalize_graph_meetings([
            {
                'id': 'evt1',
                'subject': 'Go/No-Go',
                'start': {'dateTime': '2025-06-11T13:00:00Z', 'timeZone': 'UTC'},
                'end': {'dateTime': '2025-06-11T13:30:00Z', 'timeZone': 'UTC'},
                'attendees': [
                    {'emailAddress': {'name': 'Marcus Webb', 'address': 'marcus@contoso.gov'}},
                    {'emailAddress': {'address': 'dana@contoso.gov'}},
                ],
                'bodyPreview': 'Bring the risk summary.',
            }
        ])
        assert len(meetings) == 1
        meeting = meetings[0]
        assert meeting['title'] == 'Go/No-Go'
        assert meeting['start'] == '2025-06-11T13:00:00Z'
        assert meeting['end'] == '2025-06-11T13:30:00Z'
        assert meeting['attendees'] == ['Marcus Webb', 'dana@contoso.gov']
        assert meeting['notes'] == 'Bring the risk summary.'

        teams = _normalize_graph_teams(
            [
                {
                    'id': 'msg1',
                    'messageType': 'message',
                    'from': {'user': {'displayName': 'Marcus Webb'}},
                    'createdDateTime': '2025-06-09T10:05:00Z',
                    'body': {'contentType': 'html', 'content': '<p>Staging is down again.</p>'},
                },
                {
                    'id': 'sys1',
                    'messageType': 'systemEventMessage',
                    'from': None,
                    'body': {'content': ''},
                },
            ],
            channel='Delivery Team',
        )
        assert len(teams) == 1, "System/empty messages should be skipped"
        message = teams[0]
        assert message['channel'] == 'Delivery Team'
        assert message['from'] == 'Marcus Webb'
        assert message['sent'] == '2025-06-09T10:05:00Z'
        assert message['message'] == 'Staging is down again.'

        # Empty / None inputs should return empty lists, not raise.
        assert _normalize_graph_emails(None) == []
        assert _normalize_graph_meetings([]) == []
        assert _normalize_graph_teams(None) == []

        print("Graph normalizers passed!")
        return True
    except Exception as e:
        print(f"Graph normalizers failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    tests = [
        test_load_sample_data,
        test_prompt_includes_all_sources,
        test_parse_briefing_json,
        test_graph_normalizers,
    ]
    results = []
    for test in tests:
        print(f"\nRunning {test.__name__}...")
        results.append(test())

    success = all(results)
    print(f"\nResults: {sum(results)}/{len(results)} tests passed")
    sys.exit(0 if success else 1)
