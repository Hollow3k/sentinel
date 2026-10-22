# app/auth.py
import os
import secrets

from fastapi import Header, HTTPException


def require_role(*allowed):
    def dep(x_api_key: str | None = Header(default=None)):
        keys = {"admin": os.getenv("ADMIN_API_KEY"), "analyst": os.getenv("ANALYST_API_KEY")}
        role = next((r for r, k in keys.items()
                     if k and x_api_key and secrets.compare_digest(k, x_api_key)), None)
        if role is None:
            raise HTTPException(401, "invalid or missing API key")
        if role not in allowed:
            raise HTTPException(403, "insufficient role")
        return role
    return dep