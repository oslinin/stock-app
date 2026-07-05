from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from ..config import Settings
from .errors import IBKRUnavailable
from .ib_lib import IB

log = logging.getLogger(__name__)

RECONNECT_SECONDS = 15


class IBClient:
    """Owns the single IB() instance for the process.

    ib_async, APScheduler and FastAPI must all share one asyncio loop; this
    client is created inside the FastAPI lifespan so everything runs on the
    uvicorn loop (start uvicorn with --loop asyncio).
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.ib = IB()
        self._stopping = False
        self._task: asyncio.Task | None = None

    @property
    def connected(self) -> bool:
        return self.ib.isConnected()

    @property
    def market_data_type(self) -> str:
        return "delayed" if self.settings.ibkr_use_delayed else "realtime"

    def start(self) -> None:
        if self.settings.ibkr_enabled:
            self._task = asyncio.create_task(self._run(), name="ibkr-connect-loop")

    async def _run(self) -> None:
        while not self._stopping:
            if not self.connected:
                try:
                    await self.ib.connectAsync(
                        self.settings.ibkr_host,
                        self.settings.ibkr_port,
                        clientId=self.settings.ibkr_client_id,
                        timeout=10,
                    )
                    # 1 = live, 3 = delayed (free); delayed is the safe default
                    self.ib.reqMarketDataType(3 if self.settings.ibkr_use_delayed else 1)
                    log.info(
                        "connected to IBKR at %s:%s (clientId=%s, %s data)",
                        self.settings.ibkr_host,
                        self.settings.ibkr_port,
                        self.settings.ibkr_client_id,
                        self.market_data_type,
                    )
                except Exception as exc:  # noqa: BLE001 - keep retrying
                    log.warning("IBKR connect failed: %s (retry in %ss)", exc, RECONNECT_SECONDS)
            await asyncio.sleep(RECONNECT_SECONDS)

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self.connected:
            self.ib.disconnect()

    def require(self) -> IB:
        if not self.settings.ibkr_enabled:
            raise IBKRUnavailable("IBKR is disabled (IBKR_ENABLED=false)")
        if not self.connected:
            raise IBKRUnavailable(
                f"not connected to IB Gateway/TWS at "
                f"{self.settings.ibkr_host}:{self.settings.ibkr_port}"
            )
        return self.ib

    def status(self) -> dict:
        return {
            "enabled": self.settings.ibkr_enabled,
            "connected": self.connected,
            "host": self.settings.ibkr_host,
            "port": self.settings.ibkr_port,
            "clientId": self.settings.ibkr_client_id,
            "mode": self.settings.ibkr_mode,
            "marketDataType": self.market_data_type,
            "serverTime": datetime.now(timezone.utc).isoformat(),
        }
