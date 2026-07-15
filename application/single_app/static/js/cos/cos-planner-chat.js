// cos-planner-chat.js
// Front-end for the Chief of Staff planner chat panel (the "Test / Chat" tab on Agent Builder).
//
// Sends a natural-language request to the same-origin planner route (/api/cos/planner/chat).
// The planner gathers read context, then either answers or proposes write actions. Proposed
// actions are previewed with Approve/Reject buttons unless "Auto-approve" is on, in which case
// the planner executes them immediately and this panel just reports the result.

(function () {
    'use strict';

    var agentsById = {};       // id -> agent object, kept in sync with the Build tab
    var currentAgent = null;   // {id, name, ...} the agent chosen in the Test tab dropdown
    var history = [];          // [{role, content}] running transcript for the LLM
    var busy = false;
    var activeTurn = null;     // the DOM container for the in-progress conversation turn
    var turnCount = 0;

    // Friendly labels + icons for each capability, used in action cards.
    var CAP_META = {
        'email.draft': { label: 'Email — Draft', icon: 'bi-envelope', tone: 'primary' },
        'email.send': { label: 'Email — Send', icon: 'bi-send', tone: 'danger' },
        'calendar.schedule': { label: 'Calendar — Schedule', icon: 'bi-calendar-event', tone: 'info' },
        'teams.message.send': { label: 'Teams — Message', icon: 'bi-chat-dots', tone: 'warning' }
    };

    function el(id) { return document.getElementById(id); }

    function api(method, path, body) {
        var opts = {
            method: method,
            headers: { 'Accept': 'application/json' },
            credentials: 'same-origin'
        };
        if (body !== undefined) {
            opts.headers['Content-Type'] = 'application/json';
            opts.body = JSON.stringify(body);
        }
        return fetch(path, opts).then(function (response) {
            return response.json().catch(function () { return {}; }).then(function (data) {
                if (!response.ok) {
                    var msg = (data && (data.message || data.error)) || ('Request failed (' + response.status + ')');
                    var err = new Error(msg);
                    err.status = response.status;
                    throw err;
                }
                return data;
            });
        });
    }

    // ---- Turn + rendering --------------------------------------------------

    function clearPlaceholder() {
        var placeholder = el('cos-chat-placeholder');
        if (placeholder) {
            placeholder.remove();
        }
    }

    function scrollToBottom() {
        var log = el('cos-chat-log');
        log.scrollTop = log.scrollHeight;
    }

    // Begin a new conversation turn: a clearly divided block containing the user's prompt and
    // everything the agent produced in response.
    function startTurn(userMessage) {
        clearPlaceholder();
        turnCount += 1;

        var turn = document.createElement('div');
        turn.className = 'cos-turn';
        if (turnCount > 1) {
            turn.classList.add('border-top', 'pt-3', 'mt-1');
        }

        var meta = document.createElement('div');
        meta.className = 'text-muted small mb-2';
        meta.innerHTML = '<i class="bi bi-arrow-return-right me-1"></i>Turn ' + turnCount;
        turn.appendChild(meta);

        el('cos-chat-log').appendChild(turn);
        activeTurn = turn;
        addBubble('user', userMessage);
    }

    function targetEl() {
        return activeTurn || el('cos-chat-log');
    }

    function addBubble(role, text) {
        var wrapper = document.createElement('div');
        var isUser = role === 'user';
        wrapper.className = 'd-flex mb-2 ' + (isUser ? 'justify-content-end' : 'justify-content-start');

        var bubble = document.createElement('div');
        bubble.className = 'p-2 rounded ' + (isUser ? 'bg-primary text-white' : 'bg-body-secondary');
        bubble.style.maxWidth = '85%';
        bubble.style.whiteSpace = 'pre-wrap';
        bubble.textContent = text;

        wrapper.appendChild(bubble);
        targetEl().appendChild(wrapper);
        scrollToBottom();
        return bubble;
    }

    function addNote(text, kind) {
        var note = document.createElement('div');
        note.className = 'alert alert-' + (kind || 'secondary') + ' py-1 px-2 small mb-2';
        note.textContent = text;
        targetEl().appendChild(note);
        scrollToBottom();
    }

    // Build the parameter view for an action, formatting long text fields (body/content) as a
    // bordered block and short fields as a compact label/value list.
    function renderParams(params) {
        var wrap = document.createElement('div');
        params = params || {};
        Object.keys(params).forEach(function (key) {
            var value = params[key];
            if (Array.isArray(value)) { value = value.join(', '); }
            if (value === null || value === undefined) { value = ''; }
            value = String(value);

            var isLong = value.length > 60 || value.indexOf('\n') !== -1;
            var row = document.createElement('div');
            row.className = 'mb-1';

            var label = document.createElement('span');
            label.className = 'fw-semibold text-capitalize me-1';
            label.textContent = key.replace(/_/g, ' ') + ':';
            row.appendChild(label);

            if (isLong) {
                var block = document.createElement('div');
                block.className = 'border rounded bg-body-tertiary p-2 mt-1 small';
                block.style.whiteSpace = 'pre-wrap';
                block.textContent = value;
                row.appendChild(block);
            } else {
                var span = document.createElement('span');
                span.textContent = value;
                row.appendChild(span);
            }
            wrap.appendChild(row);
        });
        return wrap;
    }

    function renderActionCard(action) {
        var meta = CAP_META[action.capability] || { label: action.capability, icon: 'bi-gear', tone: 'secondary' };

        var card = document.createElement('div');
        card.className = 'card border-' + meta.tone + ' mb-2';

        var header = document.createElement('div');
        header.className = 'card-header bg-' + meta.tone + '-subtle py-1 small fw-semibold';
        header.innerHTML = '<i class="bi ' + meta.icon + ' me-1"></i>' + meta.label;
        card.appendChild(header);

        var body = document.createElement('div');
        body.className = 'card-body py-2 small';
        body.appendChild(renderParams(action.parameters));
        card.appendChild(body);
        return card;
    }

    // Show the reviewer agent's verdict (multi-agent handoff) when present.
    function renderReview(review) {
        if (!review) { return; }
        var box = document.createElement('div');
        var tone = review.revised ? 'info' : 'secondary';
        box.className = 'alert alert-' + tone + ' py-1 px-2 small mb-2';
        var name = review.reviewer || 'Reviewer';
        var verb = review.revised ? 'revised' : 'reviewed';
        var head = document.createElement('div');
        head.className = 'fw-semibold';
        head.innerHTML = '<i class="bi bi-people me-1"></i>' + name + ' ' + verb + ' the proposed action(s)';
        box.appendChild(head);
        if (review.comment) {
            var comment = document.createElement('div');
            comment.textContent = review.comment;
            box.appendChild(comment);
        }
        targetEl().appendChild(box);
    }

    function renderPreview(turn, task) {
        renderReview(turn.review);

        var panel = document.createElement('div');
        panel.className = 'border border-warning rounded p-2 mb-2';

        var title = document.createElement('div');
        title.className = 'small fw-semibold text-warning-emphasis mb-2';
        title.innerHTML = '<i class="bi bi-shield-exclamation me-1"></i>Approval required — review the '
            + turn.proposed_actions.length + ' proposed action(s) below';
        panel.appendChild(title);

        turn.proposed_actions.forEach(function (action) {
            panel.appendChild(renderActionCard(action));
        });

        var btnRow = document.createElement('div');
        btnRow.className = 'd-flex gap-2 mt-1';

        var approveBtn = document.createElement('button');
        approveBtn.type = 'button';
        approveBtn.className = 'btn btn-sm btn-success';
        approveBtn.innerHTML = '<i class="bi bi-check-lg me-1"></i>Approve';

        var rejectBtn = document.createElement('button');
        rejectBtn.type = 'button';
        rejectBtn.className = 'btn btn-sm btn-outline-danger';
        rejectBtn.innerHTML = '<i class="bi bi-x-lg me-1"></i>Reject';

        approveBtn.addEventListener('click', function () {
            approveBtn.disabled = true;
            rejectBtn.disabled = true;
            executeActions(task, turn.proposed_actions);
        });
        rejectBtn.addEventListener('click', function () {
            approveBtn.disabled = true;
            rejectBtn.disabled = true;
            addNote('Rejected. No actions were taken.', 'secondary');
        });

        btnRow.appendChild(approveBtn);
        btnRow.appendChild(rejectBtn);
        panel.appendChild(btnRow);

        targetEl().appendChild(panel);
        scrollToBottom();
    }

    function renderResults(results) {
        (results || []).forEach(function (r) {
            var ok = r.status && r.status !== 'error' && !r.error;
            var cap = r.capability || 'action';
            var meta = CAP_META[cap] || { label: cap, icon: 'bi-gear' };

            var row = document.createElement('div');
            row.className = 'alert alert-' + (ok ? 'success' : 'danger')
                + ' py-1 px-2 small mb-2 d-flex align-items-center';
            var statusIcon = ok ? 'bi-check-circle' : 'bi-exclamation-triangle';
            var text = meta.label + ' — ' + (r.status || 'unknown');
            if (r.error) { text += ': ' + r.error; }
            row.innerHTML = '<i class="bi ' + statusIcon + ' me-2"></i>';
            var span = document.createElement('span');
            span.textContent = text;
            row.appendChild(span);
            targetEl().appendChild(row);
        });
        scrollToBottom();
    }

    // ---- Actions -----------------------------------------------------------

    function setBusy(state) {
        busy = state;
        el('cos-chat-input').disabled = state || !currentAgent;
        el('cos-chat-send').disabled = state || !currentAgent;
    }

    function sendMessage() {
        if (busy || !currentAgent) { return; }
        var input = el('cos-chat-input');
        var message = (input.value || '').trim();
        if (!message) { return; }

        startTurn(message);
        history.push({ role: 'user', content: message });
        input.value = '';
        setBusy(true);

        var autoApprove = el('cos-auto-approve').checked;
        var reviewerSelect = el('cos-chat-reviewer-select');
        var reviewerId = reviewerSelect ? (reviewerSelect.value || null) : null;
        api('POST', '/api/cos/planner/chat', {
            agent_id: currentAgent.id,
            message: message,
            history: history.slice(0, -1),
            auto_approve: autoApprove,
            reviewer_agent_id: reviewerId
        }).then(function (turn) {
            if (turn.reply) {
                addBubble('assistant', turn.reply);
                history.push({ role: 'assistant', content: turn.reply });
            }
            (turn.notes || []).forEach(function (note) { addNote(note, 'info'); });

            if (turn.status === 'awaiting_approval') {
                renderPreview(turn, message);
            } else if (turn.status === 'executed') {
                renderReview(turn.review);
                renderResults(turn.results);
            } else if (turn.status === 'error') {
                addNote(turn.reply || 'The planner reported an error.', 'danger');
            }
        }).catch(function (err) {
            addNote(err.message || 'The request failed.', 'danger');
        }).then(function () {
            setBusy(false);
            el('cos-chat-input').focus();
        });
    }

    function executeActions(task, proposedActions) {
        setBusy(true);
        addNote('Approved — executing...', 'secondary');
        api('POST', '/api/cos/planner/execute', {
            agent_id: currentAgent.id,
            task: task,
            proposed_actions: proposedActions
        }).then(function (data) {
            (data.notes || []).forEach(function (note) { addNote(note, 'info'); });
            renderResults(data.results);
        }).catch(function (err) {
            addNote(err.message || 'Execution failed.', 'danger');
        }).then(function () {
            setBusy(false);
        });
    }

    function clearChat() {
        history = [];
        activeTurn = null;
        turnCount = 0;
        var log = el('cos-chat-log');
        log.textContent = '';
        var placeholder = document.createElement('div');
        placeholder.className = 'text-muted small';
        placeholder.id = 'cos-chat-placeholder';
        placeholder.innerHTML = 'Select an agent above, then ask it to do something — for example '
            + '<em>"draft an email to myself titled COS test saying hello"</em>.';
        log.appendChild(placeholder);
    }

    // ---- Agent selection ---------------------------------------------------

    function setCurrentAgent(agent) {
        currentAgent = agent || null;
        history = [];
        activeTurn = null;
        setBusy(false);
    }

    function populateDropdown(agents) {
        var select = el('cos-chat-agent-select');
        if (!select) { return; }
        var previous = select.value;
        select.textContent = '';

        var placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = 'Select an agent…';
        select.appendChild(placeholder);

        agentsById = {};
        agents.forEach(function (agent) {
            agentsById[agent.id] = agent;
            var opt = document.createElement('option');
            opt.value = agent.id;
            opt.textContent = agent.name || agent.id;
            select.appendChild(opt);
        });

        // Preserve the current selection if it still exists.
        if (previous && agentsById[previous]) {
            select.value = previous;
        }

        populateReviewerDropdown(agents);
    }

    function populateReviewerDropdown(agents) {
        var select = el('cos-chat-reviewer-select');
        if (!select) { return; }
        var previous = select.value;
        select.textContent = '';

        var none = document.createElement('option');
        none.value = '';
        none.textContent = 'None';
        select.appendChild(none);

        agents.forEach(function (agent) {
            var opt = document.createElement('option');
            opt.value = agent.id;
            opt.textContent = agent.name || agent.id;
            select.appendChild(opt);
        });

        if (previous && agentsById[previous]) {
            select.value = previous;
        }
    }

    // The Build tab loaded/refreshed the agent list.
    function onAgentsLoaded(event) {
        var agents = (event.detail && event.detail.agents) || [];
        populateDropdown(agents);
    }

    // The Build tab selected an agent — sync the dropdown so the two tabs agree.
    function onAgentSelectedInBuilder(event) {
        var agent = event.detail && event.detail.agent;
        if (!agent) { return; }
        var select = el('cos-chat-agent-select');
        if (select && agentsById[agent.id]) {
            select.value = agent.id;
            setCurrentAgent(agentsById[agent.id]);
        }
    }

    function onDropdownChange() {
        var id = el('cos-chat-agent-select').value;
        setCurrentAgent(id ? agentsById[id] : null);
    }

    // ---- Wiring ------------------------------------------------------------

    function init() {
        el('cos-chat-send').addEventListener('click', sendMessage);
        el('cos-chat-input').addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                sendMessage();
            }
        });
        el('cos-chat-agent-select').addEventListener('change', onDropdownChange);
        el('cos-chat-clear').addEventListener('click', clearChat);

        document.addEventListener('cos-agents-loaded', onAgentsLoaded);
        document.addEventListener('cos-agent-selected', onAgentSelectedInBuilder);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
