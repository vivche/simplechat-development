# route_backend_chief_of_staff.py

import logging

from config import *
from functions_authentication import *
from functions_settings import *
from functions_appinsights import log_event
from functions_chief_of_staff import generate_briefing
from swagger_wrapper import swagger_route, get_auth_security


def register_route_backend_chief_of_staff(bp):

    @bp.route('/api/chief-of-staff/briefing', methods=['GET'])
    @swagger_route(security=get_auth_security())
    @login_required
    @user_required
    @enabled_required('enable_chief_of_staff_dashboard')
    def chief_of_staff_briefing():
        """Return the AI Chief of Staff briefing generated from the configured data source."""
        try:
            user_id = get_current_user_id()
            briefing = generate_briefing(user_id=user_id)
            return jsonify({'success': True, 'briefing': briefing})
        except Exception as exc:
            log_event(
                f"Chief of Staff: failed to generate briefing: {exc}",
                level=logging.ERROR,
                category="CHIEF_OF_STAFF",
                exceptionTraceback=True,
            )
            return jsonify({
                'success': False,
                'error': 'Failed to generate the briefing. Please try again later.'
            }), 500
