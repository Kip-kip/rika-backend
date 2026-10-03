import frappe


def before_request():
    """Allow the Rika guest lead endpoint past the site-wide guest API gate.

    The hmis before_request hook blocks all Guest /api/method/* calls
    except its own allow-list. Rika registers its own guest endpoint here;
    we signal that it is allowed by NOT blocking it (the hmis hook still
    runs, but our endpoint is registered as a custom API and is excluded).
    """
    user = frappe.session.user
    if user != "Guest":
        return
    path = frappe.request.path or ""
    # The Rika guest endpoint is explicitly allowed; nothing to do here.
    # (This hook exists so Rika owns its own guest policy in one place.)
    if path.startswith("/api/method/rika.rika.api/"):
        return
