from __future__ import annotations

import logging
import urllib.request

from ..config import Settings

log = logging.getLogger(__name__)


def send_push(settings: Settings, title: str, body: str) -> bool:
    """Optional push channel via an ntfy topic URL. Blocking — run in a thread."""
    if not settings.ntfy_url:
        return False
    try:
        req = urllib.request.Request(
            settings.ntfy_url,
            data=body.encode(),
            headers={"Title": title},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15):
            return True
    except Exception:  # noqa: BLE001
        log.exception("failed to send push notification")
        return False
