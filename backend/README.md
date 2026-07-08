# VIX Screener Backend

FastAPI service that screens AJ Brown's VIX hedge (call debit spread below
the VIX future + put credit spread above it, equal $100 widths, net debit
under $100), computes MACD-arming / opening-range-confirmation verdicts,
sends alerts, and builds IBKR order tickets that never auto-execute.
Strategy rules: `../docs/strategies/vix-hedge.md`.

## Run locally

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) and
Python 3.11+ (uv installs the interpreter for you if it's missing), plus an
IB Gateway or TWS session (paper: Gateway port 4002 / TWS 7497) with API
connections enabled.

```bash
cd backend
uv sync --extra dev           # creates .venv, installs from uv.lock (~10s)
cp .env.example .env          # edit IBKR_PORT etc.
uv run uvicorn app.main:app --reload --port 8000 --loop asyncio
```

`--loop asyncio` matters: ib_async, APScheduler and FastAPI share one plain
asyncio event loop. `uv run` picks up `.venv` automatically — no
`source .venv/bin/activate` needed (though it still works if you prefer it).

Added a dependency to `pyproject.toml`? Run `uv lock` to update `uv.lock`,
then `uv sync --extra dev` — commit both files together.

Then point the frontend at it: `echo "VITE_API_BASE=http://localhost:8000/api/v1" >> ../.env && pnpm dev`
(or enter the URL in the Screener page's Settings panel).

## Tests

```bash
uv run pytest   # pure-math tests: MACD, signals, payoff, strike selection, order build,
                # strategy spec schema, doc compiler, spec persistence,
                # provider routing/provenance/budget guard, BS greeks/IV,
                # IV rank, optionlab glue, indicators, iv_snapshot job
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
| `GET /marketdata/providers` | registered sources + capabilities + latency |
| `GET /marketdata/quote?symbol&source` | provenance-labeled quote |
| `GET /marketdata/bars?symbol&period&interval&source` | OHLCV bars |
| `GET /marketdata/expiries?symbol&source` | option expiries |
| `GET /marketdata/chain?symbol&expiry&source&greeks` | chain rows + mid-IV + BS greeks |
| `GET /marketdata/indicators?symbol&set=macd,rsi,bbands,sma20,atr` | indicator series over bars |
| `GET /marketdata/ivrank?symbol` | IV rank/percentile over iv_history |
| `POST /analytics/structure` | optionlab PoP / expected profit / P&L for arbitrary legs |

## Market data layer (Phase 2 of the trading-platform plan)

Every `/marketdata` response is a provenance envelope —
`{data, provenance: {source, asof, latency}}` — so the UI can never show
an unlabeled number. Providers (registration order = default routing):

- **yfinance** (default; free, delayed, no gateway needed): quotes, bars,
  chains (Yahoo's own per-contract IV, re-enriched with vollib greeks).
- **ibkr** (`?source=ibkr`; needs the gateway): quotes, bars, chains with
  IBKR model greeks, and the **IV index history** that feeds IV rank
  (the only IV-history source — free daily ATM-IV series, ~1y deep).
- **alphavantage** (registers only when `ALPHAVANTAGE_API_KEY` is set;
  free key at alphavantage.co, 25 req/day): `HISTORICAL_OPTIONS` EOD
  chains. A persistent budget guard refuses call 26 (HTTP 429) instead of
  silently burning the quota.

New `.env` keys (see `.env.example`): `ALPHAVANTAGE_API_KEY`,
`ALPHAVANTAGE_DAILY_BUDGET`, `IV_SNAPSHOT_SYMBOLS`,
`ANALYTICS_RISK_FREE_RATE`.

Smoke test (backend running; IB Gateway optional):

```bash
curl -s localhost:8000/api/v1/marketdata/providers | python3 -m json.tool
curl -s "localhost:8000/api/v1/marketdata/quote?symbol=SPY" | python3 -m json.tool
curl -s "localhost:8000/api/v1/marketdata/chain?symbol=SPY" | python3 -m json.tool | head -40
curl -s "localhost:8000/api/v1/marketdata/chain?symbol=SPY&source=ibkr" \
  | python3 -m json.tool | head -20     # provenance.source flips to ibkr
curl -s -X POST localhost:8000/api/v1/analytics/structure \
  -H 'content-type: application/json' \
  -d '{"legs":[{"right":"P","action":"sell","strike":95,"premium":2.0},
               {"right":"P","action":"buy","strike":90,"premium":1.1}],
       "spot":100,"volatility":0.25,"daysToTarget":45}'
curl -s "localhost:8000/api/v1/marketdata/ivrank?symbol=SPY"   # 404 until iv_history has rows
```

## Scheduler

- `eod_arming_scan` — 16:20 ET weekdays: detects the MACD bottom signal,
  persists the armed state (with the confirming close), fires ARMED alerts.
- `intraday_confirmation_poll` — every 5 min, 09:35–16:00 ET, only while
  armed: fires ENTER alerts (with the constructed spread) once per day.
- `iv_snapshot` — 16:45 ET weekdays: syncs daily ATM-IV history per
  `IV_SNAPSHOT_SYMBOLS` into `iv_history` from IBKR's IV index
  (whatToShow `OPTION_IMPLIED_VOLATILITY`). The first run backfills
  ~1 year, so `/marketdata/ivrank` works immediately; later runs top up
  missing days (a night with the gateway down is backfilled by the next
  successful sync). Idempotent per symbol/day; skips with a log line
  when no IV-history-capable provider is registered.

## Safety

- `transmit=True` appears nowhere in this codebase; tickets stage only.
- `ALLOW_ORDER_STAGING` defaults to false → manual order spec instead.
- Empty `API_TOKEN` disables auth for local dev; production always sets one
  (see `../deploy/.env.example`).

## Deployment

See `../deploy/README.md` for the VPS stack (backend + headless IB Gateway +
Caddy HTTPS via Docker Compose).
