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

    function renderBriefing(briefing) {
        el('cos-summary').textContent = briefing.summary || 'No summary available.';
        renderSourceCounts(briefing.source_counts);
        renderActionItems(briefing.action_items || []);
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
