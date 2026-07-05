# route_frontend_chief_of_staff.py

from config import *
from functions_authentication import *
from functions_settings import *
from swagger_wrapper import swagger_route, get_auth_security


def register_route_frontend_chief_of_staff(bp):

    @bp.route('/chief-of-staff')
    @swagger_route(security=get_auth_security())
    @login_required
    @user_required
    @enabled_required('enable_chief_of_staff_dashboard')
    def chief_of_staff_dashboard():
        """Render the AI Chief of Staff dashboard (POC)."""
        settings = get_settings()
        public_settings = sanitize_settings_for_user(settings)
        return render_template(
            'chief_of_staff_dashboard.html',
            app_settings=public_settings,
            settings=public_settings,
        )
