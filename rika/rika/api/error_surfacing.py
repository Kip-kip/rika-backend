"""
Generic error-surfacing for the Rika app.

Patches ``frappe.utils.response.report_error`` so that JSON API error
responses include the real exception message instead of the generic
"Validation failed." / "Server Error" string.

The original ``report_error`` builds its response from ``frappe.response``
which only carries ``exc_type`` and (in dev) the last traceback line — the
human-readable message from ``frappe.throw("...")`` is lost.

This patch preserves the original behaviour but adds the exception's
``.message`` (or ``str(exc)``) to the JSON body under the ``message`` key
that the Rika frontend's booking.js (and other callers) already read.

Applied on import so any code path that loads this module gets the patch.
"""

import frappe
import frappe.utils.response as _response_mod
import sys

_ORIG_REPORT_ERROR = _response_mod.report_error


def _extract_message(exc) -> str:
    msg = getattr(exc, "message", None)
    if isinstance(msg, str) and msg.strip():
        return msg.strip()
    if exc.args and isinstance(exc.args[0], str) and exc.args[0].strip():
        return exc.args[0].strip()
    text = str(exc).strip()
    return text or "Internal server error"


def report_error(status_code):
    """Patched: same as original, but adds the real message to the JSON body."""
    # Capture the exception BEFORE the original runs (it consumes sys.exc_info())
    _, exc_value, _ = sys.exc_info()
    real_message = _extract_message(exc_value) if exc_value else None

    # Call the original to build the response (handles v1/v2, traceback, etc.)
    response = _ORIG_REPORT_ERROR(status_code)

    if real_message and exc_value:
        import json

        try:
            body = json.loads(response.data) if response.data else {}
        except Exception:
            body = {}

        # v1 shape: {"message": ..., "exc_type": ...}
        # v2 shape: {"errors": [{...}]}
        if "errors" in body and isinstance(body["errors"], list) and body["errors"]:
            body["errors"][0]["message"] = real_message
        else:
            body["message"] = real_message

        response.data = json.dumps(body, separators=(",", ":"))

    return response


def apply():
    """Patch frappe.utils.response.report_error. Idempotent."""
    if getattr(_response_mod, "_rika_error_surfacing_patched", False):
        return
    _response_mod.report_error = report_error
    _response_mod._rika_error_surfacing_patched = True


# Apply immediately on import so any code path that loads this module gets the patch.
apply()
