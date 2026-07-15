# route_backend_cos_agents.py
# Proxy routes that let the SimpleChat browser talk to the external Chief of Staff Runtime.
#
# The browser calls these same-origin SimpleChat endpoints; SimpleChat forwards each call to the
# runtime with a runtime-audience bearer token (minted server-side). This keeps the runtime token
# out of the browser and preserves the "UI is a client" boundary (runtime is a network service).

import logging

from config import *
from functions_authentication import *
from functions_appinsights import log_event
from swagger_wrapper import swagger_route, get_auth_security
from functions_cos_runtime import (
    CosRuntimeError,
    is_runtime_configured,
    get_catalog,
    list_agents,
    get_agent,
    create_agent,
    update_agent,
    delete_agent,
    invoke_agent,
    list_approvals,
    approve_action,
    reject_action,
)
from functions_cos_planner import run_planner_turn, execute_proposed_actions


def _relay(call, *args, **kwargs):
    """Invoke a runtime client function and translate its result into a Flask JSON response."""
    if not is_runtime_configured():
        return jsonify({
            "error": "not_configured",
            "message": "The Chief of Staff Runtime is not configured for this deployment.",
        }), 503
    try:
        status_code, body = call(*args, **kwargs)
    except CosRuntimeError as exc:
        log_event(
            f"Chief of Staff Runtime proxy error: {exc.message}",
            level=logging.WARNING,
            category="COS_RUNTIME",
        )
        return jsonify({"error": "runtime_error", "message": exc.message}), exc.status_code
    if body is None:
        body = {}
    return jsonify(body), status_code


def register_route_backend_cos_agents(bp):

    @bp.route('/api/cos/catalog', methods=['GET'])
    @swagger_route(security=get_auth_security())
    @login_required
    @user_required
    def cos_catalog():
        """Return the runtime's vetted capability catalog for the Agent Builder."""
        return _relay(get_catalog)

    @bp.route('/api/cos/agents', methods=['GET'])
    @swagger_route(security=get_auth_security())
    @login_required
    @user_required
    def cos_list_agents():
        """List the signed-in user's agent definitions."""
        return _relay(list_agents)

    @bp.route('/api/cos/agents', methods=['POST'])
    @swagger_route(security=get_auth_security())
    @login_required
    @user_required
    def cos_create_agent():
        """Create an agent from the catalog subset."""
        payload = request.get_json(silent=True) or {}
        return _relay(create_agent, payload)

    @bp.route('/api/cos/agents/<agent_id>', methods=['GET'])
    @swagger_route(security=get_auth_security())
    @login_required
    @user_required
    def cos_get_agent(agent_id):
        """Fetch a single agent definition."""
        return _relay(get_agent, agent_id)

    @bp.route('/api/cos/agents/<agent_id>', methods=['PUT'])
    @swagger_route(security=get_auth_security())
    @login_required
    @user_required
    def cos_update_agent(agent_id):
        """Update an agent definition (partial; catalog zone re-validated by the runtime)."""
        payload = request.get_json(silent=True) or {}
        return _relay(update_agent, agent_id, payload)

    @bp.route('/api/cos/agents/<agent_id>', methods=['DELETE'])
    @swagger_route(security=get_auth_security())
    @login_required
    @user_required
    def cos_delete_agent(agent_id):
        """Delete an agent definition."""
        return _relay(delete_agent, agent_id)

    @bp.route('/api/cos/agents/<agent_id>/invoke', methods=['POST'])
    @swagger_route(security=get_auth_security())
    @login_required
    @user_required
    def cos_invoke_agent(agent_id):
        """Run an agent against a user task."""
        payload = request.get_json(silent=True) or {}
        task = payload.get('task', '')
        return _relay(invoke_agent, agent_id, task)

    @bp.route('/api/cos/planner/chat', methods=['POST'])
    @swagger_route(security=get_auth_security())
    @login_required
    @user_required
    def cos_planner_chat():
        """Run one planner turn: gather read context, then answer and/or propose write actions.

        Proposed write actions are previewed (never executed) unless auto_approve is set, in which
        case the runtime's approval gate is driven automatically this turn.
        """
        if not is_runtime_configured():
            return jsonify({
                "error": "not_configured",
                "message": "The Chief of Staff Runtime is not configured for this deployment.",
            }), 503
        payload = request.get_json(silent=True) or {}
        agent_id = payload.get('agent_id')
        message = payload.get('message', '')
        history = payload.get('history') or []
        auto_approve = bool(payload.get('auto_approve', False))
        reviewer_agent_id = payload.get('reviewer_agent_id') or None
        if not agent_id or not message.strip():
            return jsonify({
                "error": "bad_request",
                "message": "Both 'agent_id' and a non-empty 'message' are required.",
            }), 400
        try:
            user_id = get_current_user_id()
            result = run_planner_turn(
                agent_id, message, history=history, auto_approve=auto_approve, user_id=user_id,
                reviewer_agent_id=reviewer_agent_id,
            )
        except CosRuntimeError as exc:
            log_event(
                f"Chief of Staff planner error: {exc.message}",
                level=logging.WARNING,
                category="COS_PLANNER",
            )
            return jsonify({"error": "runtime_error", "message": exc.message}), exc.status_code
        return jsonify(result), 200

    @bp.route('/api/cos/planner/execute', methods=['POST'])
    @swagger_route(security=get_auth_security())
    @login_required
    @user_required
    def cos_planner_execute():
        """Approve and execute proposed actions previously previewed by the planner."""
        if not is_runtime_configured():
            return jsonify({
                "error": "not_configured",
                "message": "The Chief of Staff Runtime is not configured for this deployment.",
            }), 503
        payload = request.get_json(silent=True) or {}
        agent_id = payload.get('agent_id')
        task = payload.get('task', '')
        proposed_actions = payload.get('proposed_actions') or []
        if not agent_id or not proposed_actions:
            return jsonify({
                "error": "bad_request",
                "message": "Both 'agent_id' and a non-empty 'proposed_actions' list are required.",
            }), 400
        try:
            user_id = get_current_user_id()
            result = execute_proposed_actions(
                agent_id, task, proposed_actions, user_id=user_id
            )
        except CosRuntimeError as exc:
            log_event(
                f"Chief of Staff planner execute error: {exc.message}",
                level=logging.WARNING,
                category="COS_PLANNER",
            )
            return jsonify({"error": "runtime_error", "message": exc.message}), exc.status_code
        return jsonify(result), 200

    @bp.route('/api/cos/approvals', methods=['GET'])
    @swagger_route(security=get_auth_security())
    @login_required
    @user_required
    def cos_list_approvals():
        """List the signed-in user's pending/approved/rejected actions."""
        status = request.args.get('status')
        return _relay(list_approvals, status)

    @bp.route('/api/cos/approvals/<action_id>/approve', methods=['POST'])
    @swagger_route(security=get_auth_security())
    @login_required
    @user_required
    def cos_approve_action(action_id):
        """Approve and execute a single pending write action."""
        return _relay(approve_action, action_id)

    @bp.route('/api/cos/approvals/<action_id>/reject', methods=['POST'])
    @swagger_route(security=get_auth_security())
    @login_required
    @user_required
    def cos_reject_action(action_id):
        """Reject a single pending write action."""
        return _relay(reject_action, action_id)
