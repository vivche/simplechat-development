// dashboard.js

(function () {
    'use strict';

    const priorityBadgeClass = {
        high: 'bg-danger',
        medium: 'bg-warning text-dark',
        low: 'bg-secondary'
    };

    const sourceIcon = {
        email: 'bi-envelope',
        meeting: 'bi-calendar-event',
        teams: 'bi-chat-dots'
    };

    function el(id) {
        return document.getElementById(id);
    }

    function showLoading() {
        el('cos-loading').classList.remove('d-none');
        el('cos-content').classList.add('d-none');
        el('cos-error').classList.add('d-none');
    }

    function showError(message) {
        el('cos-loading').classList.add('d-none');
        el('cos-content').classList.add('d-none');
        const errorBox = el('cos-error');
        el('cos-error-text').textContent = message;
        errorBox.classList.remove('d-none');
    }

    function renderSourceCounts(counts) {
        const container = el('cos-source-counts');
        container.textContent = '';
        if (!counts) {
            return;
        }
        const labels = {
            emails: 'emails',
            meetings: 'meetings',
            teams_messages: 'Teams messages'
        };
        Object.keys(labels).forEach(function (key) {
            const span = document.createElement('span');
            span.className = 'badge bg-light text-dark border';
            span.textContent = (counts[key] || 0) + ' ' + labels[key];
            container.appendChild(span);
        });
    }

    function renderActionItems(items) {
        const list = el('cos-action-list');
        list.textContent = '';
        el('cos-action-count').textContent = String(items.length);

        if (!items.length) {
            const li = document.createElement('li');
            li.className = 'list-group-item text-muted';
            li.textContent = 'No action items were identified.';
            list.appendChild(li);
            return;
        }

        items.forEach(function (item) {
            const li = document.createElement('li');
            li.className = 'list-group-item';

            const topRow = document.createElement('div');
            topRow.className = 'd-flex align-items-start justify-content-between';

            const titleWrap = document.createElement('div');
            const icon = document.createElement('i');
            icon.className = 'bi ' + (sourceIcon[item.source] || 'bi-dot') + ' me-2 text-muted';
            titleWrap.appendChild(icon);
            const titleSpan = document.createElement('span');
            titleSpan.className = 'fw-semibold';
            titleSpan.textContent = item.title || '(untitled task)';
            titleWrap.appendChild(titleSpan);
            topRow.appendChild(titleWrap);

            const priority = (item.priority || 'low').toLowerCase();
            const badge = document.createElement('span');
            badge.className = 'badge ' + (priorityBadgeClass[priority] || 'bg-secondary');
            badge.textContent = priority;
            topRow.appendChild(badge);

            li.appendChild(topRow);

            const meta = document.createElement('div');
            meta.className = 'small text-muted mt-1';
            const parts = [];
            if (item.owner) {
                parts.push('Owner: ' + item.owner);
            }
            if (item.due) {
                parts.push('Due: ' + item.due);
            }
            meta.textContent = parts.join('  \u2022  ');
            li.appendChild(meta);

            list.appendChild(li);
        });
    }

    function emptyListItem(list, message) {
        const li = document.createElement('li');
        li.className = 'list-group-item text-muted';
        li.textContent = message;
        list.appendChild(li);
    }

    function renderPriorities(items) {
        const list = el('cos-priority-list');
        list.textContent = '';
        el('cos-priority-count').textContent = String(items.length);
        if (!items.length) {
            emptyListItem(list, 'No priorities were identified.');
            return;
        }
        items.forEach(function (item) {
            const li = document.createElement('li');
            li.className = 'list-group-item d-flex justify-content-between align-items-start';
            const wrap = document.createElement('div');
            wrap.className = 'ms-2 me-auto';
            const title = document.createElement('div');
            title.className = 'fw-semibold';
            title.textContent = item.title || '(untitled)';
            wrap.appendChild(title);
            if (item.why) {
                const why = document.createElement('div');
                why.className = 'small text-muted';
                why.textContent = item.why;
                wrap.appendChild(why);
            }
            li.appendChild(wrap);
            list.appendChild(li);
        });
    }

    function renderCommitments(items) {
        const list = el('cos-commitment-list');
        list.textContent = '';
        el('cos-commitment-count').textContent = String(items.length);
        if (!items.length) {
            emptyListItem(list, 'No personal commitments were detected.');
            return;
        }
        items.forEach(function (item) {
            const li = document.createElement('li');
            li.className = 'list-group-item';
            const title = document.createElement('div');
            title.className = 'fw-semibold';
            const icon = document.createElement('i');
            icon.className = 'bi ' + (sourceIcon[item.source] || 'bi-dot') + ' me-2 text-muted';
            title.appendChild(icon);
            const text = document.createElement('span');
            text.textContent = item.commitment || '(unspecified commitment)';
            title.appendChild(text);
            li.appendChild(title);

            const meta = document.createElement('div');
            meta.className = 'small text-muted mt-1';
            const parts = [];
            if (item.to_whom) {
                parts.push('To: ' + item.to_whom);
            }
            if (item.due) {
                parts.push('Due: ' + item.due);
            }
            meta.textContent = parts.join('  \u2022  ');
            li.appendChild(meta);
            list.appendChild(li);
        });
    }

    function renderMeetingBriefings(items) {
        const list = el('cos-meeting-list');
        list.textContent = '';
        el('cos-meeting-count').textContent = String(items.length);
        if (!items.length) {
            const div = document.createElement('div');
            div.className = 'list-group-item text-muted';
            div.textContent = 'No meetings need preparation.';
            list.appendChild(div);
            return;
        }
        items.forEach(function (item) {
            const div = document.createElement('div');
            div.className = 'list-group-item';

            const topRow = document.createElement('div');
            topRow.className = 'd-flex align-items-start justify-content-between';
            const title = document.createElement('span');
            title.className = 'fw-semibold';
            title.textContent = item.meeting || '(untitled meeting)';
            topRow.appendChild(title);
            if (item.when) {
                const when = document.createElement('span');
                when.className = 'badge bg-light text-dark border';
                when.textContent = item.when;
                topRow.appendChild(when);
            }
            div.appendChild(topRow);

            if (item.objective) {
                const obj = document.createElement('div');
                obj.className = 'small text-muted mt-1';
                obj.textContent = item.objective;
                div.appendChild(obj);
            }

            if (Array.isArray(item.prep) && item.prep.length) {
                const ul = document.createElement('ul');
                ul.className = 'small mb-1 mt-2';
                item.prep.forEach(function (point) {
                    const li = document.createElement('li');
                    li.textContent = point;
                    ul.appendChild(li);
                });
                div.appendChild(ul);
            }

            if (item.attendees) {
                const att = document.createElement('div');
                att.className = 'small text-muted';
                att.textContent = 'Attendees: ' + item.attendees;
                div.appendChild(att);
            }

            list.appendChild(div);
        });
    }

    function renderFollowUps(items) {
        const list = el('cos-followup-list');
        list.textContent = '';
        el('cos-followup-count').textContent = String(items.length);
        if (!items.length) {
            emptyListItem(list, 'No open items to follow up on.');
            return;
        }
        items.forEach(function (item) {
            const li = document.createElement('li');
            li.className = 'list-group-item';
            const title = document.createElement('div');
            title.className = 'fw-semibold';
            title.textContent = item.item || '(unspecified item)';
            li.appendChild(title);

            const meta = document.createElement('div');
            meta.className = 'small text-muted mt-1';
            const parts = [];
            if (item.waiting_on) {
                parts.push('Waiting on: ' + item.waiting_on);
            }
            if (item.age) {
                parts.push('Open: ' + item.age);
            }
            meta.textContent = parts.join('  \u2022  ');
            li.appendChild(meta);

            if (item.suggested_nudge) {
                const nudge = document.createElement('div');
                nudge.className = 'small mt-1';
                const icon = document.createElement('i');
                icon.className = 'bi bi-lightbulb me-1 text-warning';
                nudge.appendChild(icon);
                const text = document.createElement('span');
                text.textContent = item.suggested_nudge;
                nudge.appendChild(text);
                li.appendChild(nudge);
            }

            list.appendChild(li);
        });
    }

    function renderBriefing(briefing) {
        el('cos-summary').textContent = briefing.summary || 'No summary available.';
        renderSourceCounts(briefing.source_counts);
        renderPriorities(briefing.priorities || []);
        renderActionItems(briefing.action_items || []);
        renderCommitments(briefing.commitments || []);
        renderMeetingBriefings(briefing.meeting_briefings || []);
        renderFollowUps(briefing.follow_ups || []);
        el('cos-loading').classList.add('d-none');
        el('cos-error').classList.add('d-none');
        el('cos-content').classList.remove('d-none');
    }

    function loadBriefing() {
        showLoading();
        fetch('/api/chief-of-staff/briefing', {
            headers: { 'Accept': 'application/json' }
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return { ok: response.ok, data: data };
                });
            })
            .then(function (result) {
                if (!result.ok || !result.data.success) {
                    showError(result.data.error || 'Failed to load the briefing.');
                    return;
                }
                renderBriefing(result.data.briefing);
            })
            .catch(function () {
                showError('Could not reach the briefing service. Please try again.');
            });
    }

    document.addEventListener('DOMContentLoaded', function () {
        const refreshBtn = el('cos-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', loadBriefing);
        }
        loadBriefing();
    });
})();
