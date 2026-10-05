import frappe
import json
import logging

logger = logging.getLogger("rika_debug")

@frappe.whitelist(allow_guest=True)
def debug_auth():
    """Debug endpoint — traces the auth flow step by step in the LIVE worker."""
    req = frappe.request
    auth_header = (req.headers.get("Authorization") or "").strip()
    token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""
    
    steps = []
    
    # Step 1: What does the worker see at request time?
    steps.append({
        "step": 1,
        "description": "Initial request state",
        "session_user": frappe.session.user,
        "path": req.path,
        "has_auth_header": bool(auth_header),
        "token_length": len(token),
        "token_prefix": token[:20] + "..." if len(token) > 20 else token,
    })
    
    # Step 2: Can we validate the token?
    if token:
        try:
            from hmis.hmis.auth.jwt_auth import validate_access_token
            payload = validate_access_token(token)
            steps.append({
                "step": 2,
                "description": "JWT validation",
                "success": True,
                "jwt_sub": payload.get("sub", "unknown"),
                "jwt_type": payload.get("type", "unknown"),
            })
            
            # Step 3: Can we set the user?
            old_user = frappe.session.user
            frappe.set_user(payload["sub"])
            new_user = frappe.session.user
            steps.append({
                "step": 3,
                "description": "User set after JWT validation",
                "old_user": old_user,
                "new_user": new_user,
                "user_changed": old_user != new_user,
            })
        except Exception as e:
            steps.append({
                "step": 2,
                "description": "JWT validation",
                "success": False,
                "error_type": type(e).__name__,
                "error_message": str(e)[:300],
            })
    else:
        steps.append({
            "step": 2,
            "description": "No token provided",
            "success": False,
        })
    
    return {"steps": steps, "final_session_user": frappe.session.user}
