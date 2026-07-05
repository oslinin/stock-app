import secrets

from fastapi import HTTPException, Request


def require_token(request: Request) -> None:
    """Bearer-token gate for every endpoint except /health.

    An empty API_TOKEN disables auth (local development). In production the
    deploy/.env sets a long random token and the frontend sends it as
    `Authorization: Bearer <token>`.
    """
    settings = request.app.state.settings
    if not settings.api_token:
        return
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing API token")
    supplied = auth[7:].strip()
    if not secrets.compare_digest(supplied, settings.api_token):
        raise HTTPException(status_code=401, detail="Invalid API token")
