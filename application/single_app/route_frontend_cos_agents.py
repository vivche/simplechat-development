# route_frontend_cos_agents.py
# Renders the Chief of Staff Runtime "Agent Builder" page. All data is loaded client-side from the
# same-origin proxy routes in route_backend_cos_agents.py.

from config import *
from functions_authentication import *
from functions_settings import *
from swagger_wrapper import swagger_route, get_auth_security


def register_route_frontend_cos_agents(bp):

    @bp.route('/cos-agents')
    @swagger_route(security=get_auth_security())
    @login_required
    @user_required
    def cos_agent_builder():
        """Render the Agent Builder UI (composes agents from the runtime catalog)."""
        settings = get_settings()
        public_settings = sanitize_settings_for_user(settings)
        return render_template(
            'cos_agent_builder.html',
            app_settings=public_settings,
            settings=public_settings,
        )
