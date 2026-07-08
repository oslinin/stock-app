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
pytest        # pure-math tests: MACD, signals, payoff, strike selection, order build,
              # strategy spec schema, doc compiler, spec persistence
```

## Strategy library (Phase 1 of the trading-platform plan)

The `/specs` API is the strategy database: every strategy is an
`OptionsStrategySpec` (see `app/specs/schema.py`) stored as versioned JSON.
IB Gateway is NOT required for any of it. A 45-DTE 0.30Δ put credit spread
is seeded automatically on first startup.

```bash
# after "Run locally" above (Gateway optional):
curl -s localhost:8000/api/v1/specs                        # list (filters: ?status=&origin=&category=)
curl -s localhost:8000/api/v1/specs/1                      # record + current spec JSON
curl -s localhost:8000/api/v1/specs/1/doc                  # markdown doc + payoff + section status
curl -s "localhost:8000/api/v1/specs/1/payoff?reference_price=600"
curl -s -X POST localhost:8000/api/v1/specs/1/approve      # 422 while exits are unspecified
```

Rules the source never stated are the explicit sentinel `"unspecified"` —
they render as "⚠ not stated in source" and block approval until a human
resolves them by saving a new version (PUT `/specs/{id}`).

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
