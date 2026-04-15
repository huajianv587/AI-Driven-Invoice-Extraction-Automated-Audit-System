from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from src.api.security import decode_access_token
from src.api.services import get_user_by_id, log_security_event, parse_old_secrets, public_user
from src.config import load_flat_config
from src.db.mysql_client import MySQLClient


def get_cfg() -> dict:
    return load_flat_config()


def get_db(cfg: dict = Depends(get_cfg)):
    db = MySQLClient(
        host=cfg["mysql_host"],
        port=int(cfg["mysql_port"]),
        user=cfg["mysql_user"],
        password=cfg["mysql_password"],
        db=cfg["mysql_db"],
        connect_timeout=10,
        autocommit=True,
    )
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    request: Request,
    db: MySQLClient = Depends(get_db),
    cfg: dict = Depends(get_cfg),
) -> dict:
    request_id = getattr(request.state, "request_id", "")
    ip_address = request.client.host if request.client else ""
    user_agent = request.headers.get("user-agent", "")
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        log_security_event(
            db,
            event_type="auth.missing_bearer",
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            outcome="denied",
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(
        token,
        str(cfg["AUTH_JWT_SECRET"]),
        parse_old_secrets(cfg.get("AUTH_JWT_OLD_SECRETS")),
    )
    if not payload:
        log_security_event(
            db,
            event_type="auth.invalid_access_token",
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            outcome="denied",
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired access token.")
    user = get_user_by_id(db, int(payload["sub"]))
    if not user or int(user.get("is_active") or 0) != 1:
        log_security_event(
            db,
            event_type="auth.inactive_user",
            user_id=int(payload["sub"]),
            email=str(payload.get("email") or ""),
            role=str(payload.get("role") or ""),
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            outcome="denied",
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is not active.")
    return public_user(user)


def require_roles(*allowed_roles: str):
    allowed = {role for role in allowed_roles if role}

    def dependency(
        request: Request,
        user: dict = Depends(get_current_user),
        db: MySQLClient = Depends(get_db),
    ) -> dict:
        if allowed and user["role"] not in allowed:
            log_security_event(
                db,
                event_type="rbac.denied",
                user_id=int(user["id"]),
                email=str(user.get("email") or ""),
                role=str(user.get("role") or ""),
                request_id=getattr(request.state, "request_id", ""),
                ip_address=request.client.host if request.client else "",
                user_agent=request.headers.get("user-agent", ""),
                outcome="denied",
                metadata={"allowed_roles": sorted(allowed), "path": request.url.path},
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this resource.")
        return user

    return dependency
