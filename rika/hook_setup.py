import frappe


def before_request():
    """Rika request hook.

    Validates the Bearer JWT early so frappe.session.user is set BEFORE
    the hmis guest-gate and Frappe's core validate_auth run. This is
    required because the hmis JWT auth_hook runs inside validate_auth,
    which is too late — the hmis before_request gate 401s Guest requests
    to /api/method/* before validate_auth ever runs.
    """
    try:
        req = frappe.local.request
        if not req or not req.path.startswith("/api/method/rika."):
            return
        hdr = req.headers.get("Authorization", "")
        if not hdr.startswith("Bearer "):
            return
        token = hdr[7:]
        if not token or len(token) < 50:
            return
        from hmis.hmis.auth.jwt_auth import validate_and_set_user
        validate_and_set_user(token)
    except frappe.AuthenticationError:
        raise
    except Exception:
        pass  # let Frappe's own auth chain handle it
