# VIX Screener Backend

FastAPI service that screens AJ Brown's VIX hedge (call debit spread below
the VIX future + put credit spread above it, equal $100 widths, net debit
under $100), computes MACD-arming / opening-range-confirmation verdicts,
sends alerts, and builds IBKR order tickets that never auto-execute.
Strategy rules: `../docs/strategies/vix-hedge.md`.

## Run locally

Requires Python 3.11+ and an IB Gateway or TWS session (paper: Gateway port
4002 / TWS 7497) with API connections enabled.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # edit IBKR_PORT etc.
uvicorn app.main:app --reload --port 8000 --loop asyncio
```

`--loop asyncio` matters: ib_async, APScheduler and FastAPI share one plain
asyncio event loop.

Then point the frontend at it: `echo "VITE_API_BASE=http://localhost:8000/api/v1" >> ../.env && pnpm dev`
(or enter the URL in the Screener page's Settings panel).

## Tests

```bash
pytest        # pure-math tests: MACD, signals, payoff, strike selection, order build
```

## API (prefix `/api/v1`, Bearer token except `/health`)

| Endpoint | Purpose |
|---|---|
| `GET /health` | liveness (public) |
| `GET /ibkr/status` | gateway connection + market-data mode |
| `GET /strategies`, `GET /strategies/{id}` | strategy registry + params |
| `GET /screener/{id}/state` | spot, prior/confirming close, opening range, MACD |
| `GET /screener/{id}/verdict` | WAIT / ARMED / ENTER + per-check details |
| `GET /screener/{id}/spread?expiry&width&contracts` | best qualifying combo, legs, payoff, breakevens |
| `POST /orders/preview` | IBKR whatIf (margin/commission) — places nothing |
| `POST /orders/ticket` | staged `transmit=false` combo (gated by `ALLOW_ORDER_STAGING`) or manual spec |
| `GET/POST/PATCH/DELETE /alerts`, `GET /alerts/events` | alert rules + fired events |

## Scheduler

- `eod_arming_scan` — 16:20 ET weekdays: detects the MACD bottom signal,
  persists the armed state (with the confirming close), fires ARMED alerts.
- `intraday_confirmation_poll` — every 5 min, 09:35–16:00 ET, only while
  armed: fires ENTER alerts (with the constructed spread) once per day.

## Safety

- `transmit=True` appears nowhere in this codebase; tickets stage only.
- `ALLOW_ORDER_STAGING` defaults to false → manual order spec instead.
- Empty `API_TOKEN` disables auth for local dev; production always sets one
  (see `../deploy/.env.example`).

## Deployment

See `../deploy/README.md` for the VPS stack (backend + headless IB Gateway +
Caddy HTTPS via Docker Compose).
