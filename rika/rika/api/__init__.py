# Rika public API - guest-accessible lead endpoint

# Generic error-surfacing: patch frappe.utils.response.report_error so that
# JSON API error responses include the real exception message instead of the
# generic "Validation failed." / "Server Error" string.
from . import error_surfacing  # noqa: F401  (side-effect: applies the patch)
