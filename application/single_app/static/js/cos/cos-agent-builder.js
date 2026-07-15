// cos-agent-builder.js
// Front-end for the Chief of Staff Runtime "Agent Builder".
// Talks only to same-origin SimpleChat proxy routes (/api/cos/*), which forward to the runtime.

(function () {
    'use strict';

    var catalog = [];   // [{id, display_name, description, action, enabled, requires_approval}]
    var agents = [];    // [{id, name, capabilities, ...}]
    var selectedId = null;

    function el(id) { return document.getElementById(id); }

    function showStatus(message, kind) {
        var box = el('cos-status');
        box.className = 'alert alert-' + (kind || 'info');
        box.textContent = message;
        box.classList.remove('d-none');
    }

    function clearStatus() {
        el('cos-status').classList.add('d-none');
    }

    // ---- API helpers -------------------------------------------------------

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
                    if (data && Array.isArray(data.details) && data.details.length) {
                        msg += ': ' + data.details.join('; ');
                    }
                    var err = new Error(msg);
                    err.status = response.status;
                    throw err;
                }
                return data;
            });
        });
    }

    // ---- Rendering ---------------------------------------------------------

    function renderCapabilities(selected) {
        var container = el('cos-capabilities');
        container.textContent = '';
        selected = selected || [];

        if (!catalog.length) {
            container.innerHTML = '<div class="text-muted small">No capabilities available.</div>';
            return;
        }

        catalog.forEach(function (cap) {
            var wrapper = document.createElement('div');
            wrapper.className = 'form-check';

            var input = document.createElement('input');
            input.className = 'form-check-input';
            input.type = 'checkbox';
            input.value = cap.id;
            input.id = 'cap-' + cap.id;
            input.checked = selected.indexOf(cap.id) !== -1;
            input.disabled = !cap.enabled;

            var label = document.createElement('label');
            label.className = 'form-check-label';
            label.htmlFor = input.id;

            var title = document.createElement('span');
            title.textContent = cap.display_name || cap.id;
            label.appendChild(title);

            if (!cap.enabled) {
                var disabledBadge = document.createElement('span');
                disabledBadge.className = 'badge bg-secondary ms-2';
                disabledBadge.textContent = 'disabled';
                label.appendChild(disabledBadge);
            }
            if (cap.requires_approval) {
                var approvalBadge = document.createElement('span');
                approvalBadge.className = 'badge bg-warning text-dark ms-2';
                approvalBadge.textContent = 'approval';
                label.appendChild(approvalBadge);
            }
            if (cap.description) {
                var desc = document.createElement('div');
                desc.className = 'form-text';
                desc.textContent = cap.description;
                label.appendChild(desc);
            }

            wrapper.appendChild(input);
            wrapper.appendChild(label);
            container.appendChild(wrapper);
        });
    }

    function renderAgents() {
        var loading = el('cos-agents-loading');
        var empty = el('cos-agents-empty');
        var list = el('cos-agents-list');

        loading.classList.add('d-none');
        list.textContent = '';

        if (!agents.length) {
            empty.classList.remove('d-none');
            list.classList.add('d-none');
            return;
        }

        empty.classList.add('d-none');
        list.classList.remove('d-none');

        agents.forEach(function (agent) {
            var item = document.createElement('li');
            item.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-start';
            if (agent.id === selectedId) {
                item.classList.add('active');
            }
            item.style.cursor = 'pointer';

            var left = document.createElement('div');
            var name = document.createElement('div');
            name.className = 'fw-semibold';
            name.textContent = agent.name;
            left.appendChild(name);

            var caps = document.createElement('div');
            caps.className = 'small ' + (agent.id === selectedId ? '' : 'text-muted');
            caps.textContent = (agent.capabilities || []).join(', ') || 'no capabilities';
            left.appendChild(caps);

            item.appendChild(left);
            item.addEventListener('click', function () { selectAgent(agent.id); });
            list.appendChild(item);
        });
    }

    // ---- Form state --------------------------------------------------------

    function collectSelectedCapabilities() {
        var checked = [];
        catalog.forEach(function (cap) {
            var input = el('cap-' + cap.id);
            if (input && input.checked) {
                checked.push(cap.id);
            }
        });
        return checked;
    }

    function fillForm(agent) {
        el('cos-agent-id').value = agent ? agent.id : '';
        el('cos-agent-name').value = agent ? (agent.name || '') : '';
        el('cos-agent-description').value = agent ? (agent.description || '') : '';
        el('cos-agent-instructions').value = agent ? (agent.instructions || '') : '';
        el('cos-agent-model').value = agent ? (agent.model || 'gpt-4o') : 'gpt-4o';
        el('cos-agent-memory').value = agent ? (agent.memory_scope || 'agent') : 'agent';
        renderCapabilities(agent ? agent.capabilities : []);

        var isEdit = !!agent;
        el('cos-editor-title').textContent = isEdit ? ('Edit: ' + agent.name) : 'New agent';
        el('cos-delete-btn').classList.toggle('d-none', !isEdit);
        el('cos-cancel-btn').classList.toggle('d-none', !isEdit);
        el('cos-invoke-section').classList.toggle('d-none', !isEdit);
        el('cos-invoke-result').classList.add('d-none');
        el('cos-task-input').value = '';

        // Notify the planner chat panel which agent is active (null when creating a new agent).
        document.dispatchEvent(new CustomEvent('cos-agent-selected', {
            detail: { agent: agent || null }
        }));
    }

    function selectAgent(id) {
        selectedId = id;
        var agent = agents.filter(function (a) { return a.id === id; })[0];
        fillForm(agent || null);
        renderAgents();
    }

    function newAgent() {
        selectedId = null;
        fillForm(null);
        renderAgents();
    }

    // ---- Loaders -----------------------------------------------------------

    function loadCatalog() {
        return api('GET', '/api/cos/catalog').then(function (data) {
            catalog = (data && data.capabilities) || [];
        });
    }

    function loadAgents() {
        el('cos-agents-loading').classList.remove('d-none');
        return api('GET', '/api/cos/agents').then(function (data) {
            agents = (data && data.agents) || [];
            renderAgents();
            // Let the test/chat panel refresh its agent dropdown.
            document.dispatchEvent(new CustomEvent('cos-agents-loaded', {
                detail: { agents: agents }
            }));
        });
    }

    // ---- Actions -----------------------------------------------------------

    function saveAgent(event) {
        event.preventDefault();
        clearStatus();

        var id = el('cos-agent-id').value;
        var payload = {
            name: el('cos-agent-name').value.trim(),
            description: el('cos-agent-description').value.trim(),
            instructions: el('cos-agent-instructions').value.trim(),
            capabilities: collectSelectedCapabilities(),
            data_scope: 'self-only',
            model: el('cos-agent-model').value.trim() || 'gpt-4o',
            memory_scope: el('cos-agent-memory').value
        };

        if (!payload.name) {
            showStatus('Name is required.', 'warning');
            return;
        }

        var request = id
            ? api('PUT', '/api/cos/agents/' + encodeURIComponent(id), payload)
            : api('POST', '/api/cos/agents', payload);

        request.then(function (saved) {
            showStatus(id ? 'Agent updated.' : 'Agent created.', 'success');
            return loadAgents().then(function () {
                selectAgent(saved.id);
            });
        }).catch(function (err) {
            showStatus(err.message, 'danger');
        });
    }

    function deleteAgent() {
        var id = el('cos-agent-id').value;
        if (!id) { return; }
        if (!window.confirm('Delete this agent?')) { return; }
        clearStatus();
        api('DELETE', '/api/cos/agents/' + encodeURIComponent(id)).then(function () {
            showStatus('Agent deleted.', 'success');
            return loadAgents().then(newAgent);
        }).catch(function (err) {
            showStatus(err.message, 'danger');
        });
    }

    function invokeAgent() {
        var id = el('cos-agent-id').value;
        if (!id) { return; }
        var task = el('cos-task-input').value.trim();
        clearStatus();
        el('cos-invoke-btn').disabled = true;
        api('POST', '/api/cos/agents/' + encodeURIComponent(id) + '/invoke', { task: task })
            .then(function (result) {
                el('cos-scopes-used').textContent = (result.scopes_used || []).join(', ') || 'none';
                var output = {
                    context: result.context || {},
                    notes: result.notes || []
                };
                el('cos-invoke-output').textContent = JSON.stringify(output, null, 2);
                el('cos-invoke-result').classList.remove('d-none');
            })
            .catch(function (err) {
                showStatus(err.message, 'danger');
            })
            .then(function () {
                el('cos-invoke-btn').disabled = false;
            });
    }

    // ---- Init --------------------------------------------------------------

    function init() {
        el('cos-agent-form').addEventListener('submit', saveAgent);
        el('cos-new-agent-btn').addEventListener('click', newAgent);
        el('cos-cancel-btn').addEventListener('click', newAgent);
        el('cos-delete-btn').addEventListener('click', deleteAgent);
        el('cos-invoke-btn').addEventListener('click', invokeAgent);
        el('cos-refresh-btn').addEventListener('click', function () {
            loadAgents().catch(function (err) { showStatus(err.message, 'danger'); });
        });

        loadCatalog()
            .then(loadAgents)
            .then(function () { fillForm(null); })
            .catch(function (err) {
                el('cos-agents-loading').classList.add('d-none');
                showStatus(err.message, 'danger');
            });
    }

    document.addEventListener('DOMContentLoaded', init);
})();
