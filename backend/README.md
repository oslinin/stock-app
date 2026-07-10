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
                # IV rank, optionlab glue, indicators, iv_snapshot job,
                # condition interpreter, spec strategy registry, screeners,
                # watchlist scan job, Fidelity CSV parser, beta extraction,
                # beta-weighted delta, forward-looking CVaR, bot state
                # machine, risk gate, bot lifecycle/compile_bot, safety
                # invariants (transmit=True gating), compile_backtest,
                # backtest job queue, OO CSV import, metrics, robustness
                # (MCPT/bootstrap/walk-forward), data loaders/validators,
                # AGPL boundary (optopsy import forbidden in app/)
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
| `GET /specs/{id}/verdict` | live entry-condition verdict (ENTER/WAIT) for an **approved** spec |
| `GET/POST/DELETE /watchlist` | watched symbols |
| `GET /watchlist/screeners` | screener registry (id/name/description) |
| `POST /watchlist/screeners/{id}/run` | rank the latest `symbol_metrics` scan through a screener |
| `GET /portfolio/positions?group_by=account\|underlying` | IBKR live + latest Fidelity CSV positions, merged |
| `GET /portfolio/summary` | aggregate greeks + beta-weighted delta, per-account net liq/BP |
| `GET /portfolio/risk?lookback_days` | forward-looking 1-day CVaR (95%/99%) by historical simulation |
| `POST /portfolio/fidelity/upload` | parse + snapshot a Fidelity Positions CSV export |
| `GET /portfolio/beta?symbol` | cached beta from IB Gateway's fundamental-ratios feed (weekly `beta_refresh` job) |
| `GET/POST /bots`, `GET /bots/{id}` | bot CRUD — creation blocked by `compile_bot()` unless the spec is fully runtime-executable |
| `GET /bots/{id}/runs` | per-tick audit trail (position_state, action, detail) |
| `POST /bots/{id}/start\|pause\|kill`, `POST /bots/kill-all` | lifecycle + kill switch (cancels a pending order, never flattens an open position) |
| `GET /backtests/compile-preview?spec_id` | compile_backtest() preview — optopsy strategy/kwargs, OO setup sheet, unsupported[] |
| `POST /backtests` | queue a job (`engine: optopsy`) — 422 with `unsupported[]` if the spec's structure isn't mapped |
| `GET /backtests/{id}`, `/equity`, `/trades.csv` | run status/metrics, equity curve, trade list CSV |
| `GET /backtests/{id}/setup-sheet` | Option Omega manual-bridge fields + Custom-Signals CSV |
| `POST /backtests/import/oo?spec_id` | import an OO trade-log CSV export → `backtest_run(engine=oo_manual)` + result |
| `POST/GET /backtests/{id}/robustness` | run/list MCPT permutation, bootstrap, or walk-forward on a completed run |
| `POST /backtests/jobs/claim\|{id}/result\|{id}/fail` | optopsy worker's job-queue protocol (`WORKER_TOKEN` bearer, not `API_TOKEN`) |

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

## Spec interpreter (Phase 3 of the trading-platform plan)

An **approved** spec now runs as a real strategy: `app/specs/spec_strategy.py`
wraps it to the existing `Strategy` ABC, so it appears in `/strategies`
(and the StrategyDetail page) with no new plumbing — the registry just
grows an entry with id `spec:<slug>`. `app/specs/interpreter.py` evaluates
its `entry` conditions (AND semantics) against a `MarketContext` built
from Phase 2's dataproviders + `iv_history` — the same layers
`/marketdata` uses. Ten condition kinds are wired so far (`iv_rank_gte`,
`iv_rank_lte`, `dte_between`, `delta_between`, `vix_below`, `vix_above`,
`price_above_sma`, `price_below_sma`, `day_of_week_in`,
`credit_min_pct_width`); the rest (`funding_rate_*`, `edge_score_gte`,
`cot_zscore_gte`, `gex_regime_is`, `no_earnings_within_days`) need data
sources later phases haven't built yet (crypto funding, edge scoring,
COT, GEX, an earnings calendar) — an unimplemented kind fails closed
(counts as not-passed) rather than being silently skipped or crashing.

The registry is built once at startup; approving or editing a spec
refreshes it immediately (`POST /specs/{id}/approve`, `PUT /specs/{id}`),
so a newly-approved spec's verdict is queryable right away — no restart
needed.

Smoke test (backend running):

```bash
curl -s -X POST localhost:8000/api/v1/specs -H 'content-type: application/json' -d '{
  "spec": {
    "meta": {"name": "IV rank demo", "category": "options", "origin": "manual"},
    "universe": {"underlyings": ["SPY"], "sec_type": "option"},
    "structure": [],
    "entry": [{"kind": "iv_rank_gte", "params": {"value": 20}}],
    "exit": {"profit_target_pct_credit": 50.0, "stop_loss_x_credit": 2.0, "time_exit_dte": 21}
  }
}'                                                       # note the returned id
curl -s -X POST localhost:8000/api/v1/specs/<id>/approve
curl -s localhost:8000/api/v1/strategies                # spec:iv-rank-demo now listed
curl -s localhost:8000/api/v1/specs/<id>/verdict         # {verdict, checks:[{kind,pass,observed,detail}]}
```

## Watchlist + screeners (Phase 4 of the trading-platform plan)

`app/watchlist/` is a separate package from the VIX-specific
`app/screener/` (per the plan's module tree) — a symbol's watchlist
membership and daily chain sample have nothing to do with the VIX hedge
strategy engine. Each night, `watchlist_scan` samples one representative
strike (nearest spot) from each watched symbol's chain at the nearest
listed expiry and writes a `symbol_metrics` row (idempotent per
symbol/day; a provider error skips that symbol without crashing the
job, same discipline as `iv_snapshot`). Screeners
(`app/watchlist/screeners.py`) are pure functions over that table — no
live chain fetch at request time — so `POST /watchlist/screeners/{id}/run`
answers instantly: `expensive_premium` (highest premium/day-of-notional),
`high_ivr` (IV rank ≥ threshold, default 50), `delta_dte_candidates`
(0.16–0.30Δ, 21–45 DTE band). All three respect optional
`min_open_interest`/`max_spread_pct` liquidity params. `no_earnings_within_days`
from the plan's screener list is deferred — no earnings-calendar data
source exists yet (same rationale as Phase 3's deferred spec conditions).

The Watchlist page has no payoff-builder yet, so a screener row's "open
chain" link deep-links to `/chain?symbol=<sym>` (Option Chain, pre-filled)
instead — a scoping decision, not the plan's "opens pre-filled payoff."

Smoke test (backend running):

```bash
curl -s -X POST localhost:8000/api/v1/watchlist -H 'content-type: application/json' -d '{"symbol":"SPY"}'
curl -s localhost:8000/api/v1/watchlist
curl -s localhost:8000/api/v1/watchlist/screeners
curl -s -X POST localhost:8000/api/v1/watchlist/screeners/high_ivr/run -H 'content-type: application/json' -d '{}'
# empty [] until the nightly scan (or a manual `watchlist_scan()` call) has written today's symbol_metrics
```

## Portfolio (Phase 5 of the trading-platform plan)

`app/portfolio/` merges two position sources with different freshness:
IBKR positions are fetched **live** via `ib_async`'s `portfolio()`/`accountSummary()`
every `/portfolio/*` call (and persisted as a `position_snapshot` row each
time, for a provenance trail); Fidelity has no live feed, so its
positions are a **versioned CSV upload** — `POST /portfolio/fidelity/upload`
parses and snapshots one `position_snapshot` per upload, and `/positions`
always reads the *latest* Fidelity snapshot per account.

- `fidelity_csv.py`: ~60-line parser for Fidelity's Positions.csv export
  (options symbol format `-AAPL250117C150`, `$`/`,`/`%`/`()` quirks,
  disclaimer/footer rows dropped by requiring a parseable symbol+quantity).
- `beta.py` + the weekly `beta_refresh` job: pulls each watchlist symbol's
  beta straight from IB Gateway's fundamental-ratios feed (generic tick
  258) — never computed in-process. No Reuters Fundamentals entitlement
  on the account means IB just never populates the ratio; the symbol is
  skipped, not estimated with our own regression.
- `bwdelta.py`: tastytrade's published beta-weighted-delta formula
  (`delta * beta * underlying/benchmark price ratio`, ×100×contracts for
  options) — see `tests/test_bwdelta.py` for the hand-worked numbers.
- `risk.py`: forward-looking 1-day CVaR by historical simulation — full
  Black-Scholes repricing per option position (IV held constant —
  "sticky-IV"; a beta-scaled vol shock is a documented upgrade, not built
  this phase), linear repricing for stock. `GET /portfolio/risk` fetches
  each position's spot (`QUOTE`) and, for options, a matching chain row's
  IV (`CHAIN`) — reusing the Phase 2 provider layer exactly like
  `build_market_context` (Phase 3) and `watchlist_scan` (Phase 4) do.
  Non-priceable positions (no quote, no matching chain row, insufficient
  price history) are excluded from the simulation and listed with a reason.
- **Deferred**: IBKR model-greek enrichment (positions show quantity/price
  correctly; delta/theta/vega need a second `reqMktData` greeks round trip
  per contract, the same enrichment `ibkr_provider.py` already does for
  chains — not built this phase, so `/portfolio/summary`'s aggregate
  greeks read `null` for IBKR positions until that follow-up lands).
  `group_by=campaign|strategy` (needs journal linkage / manual tags — no
  journal exists yet). Realized equity-curve CVaR (needs journal history).

Smoke test (backend running):

```bash
curl -s -F "file=@positions.csv" -F "account_label=main" \
  localhost:8000/api/v1/portfolio/fidelity/upload
curl -s localhost:8000/api/v1/portfolio/positions
curl -s "localhost:8000/api/v1/portfolio/positions?group_by=underlying"
curl -s localhost:8000/api/v1/portfolio/summary
curl -s localhost:8000/api/v1/portfolio/risk   # cvar95/cvar99, or excluded[] reasons without live data
curl -s "localhost:8000/api/v1/portfolio/beta?symbol=SPY"   # 404 until beta_refresh has run
```

## Paper bot (Phase 6 of the trading-platform plan)

`app/brokers/` (the `BrokerAdapter` protocol + `IBKRAdapter`) and
`app/bots/` (state machine, risk gate, leg resolver, compile_bot, sim
broker) together let an **approved spec run itself**: FLAT → entry
conditions + gates pass → `ENTRY_SIGNALED` → risk gate → `ORDER_PENDING`
→ fill → `IN_POSITION`. `bot_tick` (RTH, 1 min) drives every `running`
bot's tick, reusing `build_market_context` (Phase 3) and the `CHAIN`
provider (Phase 2) — same layers every other job builds on.

**Safety** (`test_safety_invariants.py` enforces this, not just docs):
`transmit=True` may appear in exactly one place in the entire codebase —
`brokers/ibkr_adapter.py`'s auto-transmit branch, and even there it
requires three independent conditions at once: `ibkr_mode == "paper"`,
`PAPER_AUTO_TRANSMIT=true`, and the gateway actually pointed at a
recognized paper port (4002/7497). A live bot (`mode="live"`) never
auto-transmits this phase — live warm-up/per-order approval isn't built
yet, so a live order always stages with `transmit=False`, same as the
existing `/orders/ticket` path, and `mode="live"` bots are refused
outright unless `ALLOW_LIVE_TRADING=true`.

`compile_bot()` is the strictest of the plan's three spec compilers: a
bot can't be created (or started) from a spec with unspecified exits, an
unsupported condition kind, an unsupported strike rule, or **any**
adjustment/roll rule — since exit/adjustment monitoring (`MANAGING`)
isn't built this phase, a bot must never open a position it can't safely
manage the exit of. `POST /bots` returns the exact blocker list.

New `.env` keys (see `.env.example`): `ALLOW_LIVE_TRADING` (default
false), `PAPER_AUTO_TRANSMIT` (default false), `BOT_MAX_BP_PCT`,
`BOT_MAX_CONCURRENT_GLOBAL`, `BOT_DAILY_LOSS_HALT_USD`.

**Deferred this phase** (documented, not silently missing):
exit/adjustment monitoring (`MANAGING` state — rolls, profit-target/
stop-loss exits); portfolio-level risk caps (max beta-weighted delta,
net short vega, correlated-exposure) — the risk gate covers BP%,
concurrency, and daily-loss halt only; `bot_tick`'s risk inputs use a
placeholder NetLiq (100k) and zero realized P&L today until
`portfolio/ibkr_positions.py`'s `accountSummary()` and journal history
are wired in; ntfy action buttons; the watchdog/heartbeat job; the Bots
frontend page's start/pause/kill controls beyond a basic list+create.

Smoke test (backend running, a spec approved with `curl` per the specs
section above — needs fully-specified exits, no adjustments):

```bash
curl -s -X POST localhost:8000/api/v1/bots -H 'content-type: application/json' \
  -d '{"specId": <id>, "mode": "paper", "bpPct": 0.1, "fixedContracts": 1}'
curl -s -X POST localhost:8000/api/v1/bots/<bot id>/start
curl -s localhost:8000/api/v1/bots/<bot id>/runs
curl -s -X POST localhost:8000/api/v1/bots/<bot id>/kill
```

## Backtesting (Phase 10 of the trading-platform plan)

Two engines behind one `backtest_run` job-queue table: **optopsy**
(local, free, AGPL — runs in a separate `optopsy-worker` process/
container with its own `pyproject.toml` and no shared imports/DB file
with this backend — `test_agpl_boundary.py` enforces the isolation) and
**Option Omega** via a manual bridge (no automation by design — user
decision, brittle + ToS risk). `compile_backtest()` maps a spec's
structure to an optopsy strategy function + kwargs (single legs and
2-leg same-right verticals only — `short_puts`/`long_puts`/
`short_calls`/`long_calls`/`{short,long}_{put,call}_spread`; anything
else, plus P&L-triggered exits (optopsy has no native PT/SL, only a
calendar `exit_dte`), lands in `unsupported[]` — "backtest ignores: X",
never silently dropped) and to an OO setup sheet + Custom-Signals CSV.

- `backtests/service.py`: the job queue — `enqueue`/`claim`/
  `record_result`/`record_failure`, a pure DB state machine (a job is
  claimed once; a result can't be recorded twice; a completed run can't
  be failed after the fact).
- `backtests/oo_import.py`: OO trade-log CSV parser. OO's export-schema
  docs page 403s from this sandbox, so it matches columns by
  normalized-alias (`Date Opened`/`Opened`/`Entry Date`/...) rather than
  one exact header string, and rejects a CSV missing a required column
  with a clear error.
- `backtests/metrics.py`: CAGR/win rate/expectancy/max drawdown/Sharpe/
  trade count from a trade list + equity curve — engine-agnostic.
- `backtests/robustness.py`: MCPT permutation test (cheaper variant —
  random-entry-timing against the real underlying return series, not a
  full bar-shuffle re-run of the engine), Monte Carlo bootstrap (trade
  resampling → equity-curve percentile bands, drawdown distribution,
  risk of ruin, losing-streak distribution), and walk-forward window
  math (the actual per-window re-optimization runs in the optopsy
  worker — it owns the data).
- `backtests/data.py`: parquet cache + sanity validators (missing
  columns, negative bid/ask, ask < bid, non-positive strikes, duplicate
  rows, expiration before quote date) over historical chain data.
  `fetch_dolthub_chain()` is **unverified against DoltHub's live
  schema** — this sandbox has no outbound network to check table/column
  names against the real `post-no-preference/options` repo; verify the
  SQL before trusting a real run.
- `optopsy-worker/worker.py`: polls `POST /backtests/jobs/claim`, runs
  the compiled optopsy strategy against the cached parquet chain,
  normalizes optopsy's raw trade-level output (`entry`/`exit`/
  `pct_change` for single legs, `total_entry_cost`/`total_exit_proceeds`
  for spreads — verified against a real local optopsy install, column
  names confirmed even though a fully populated non-empty result needs
  real historical data this sandbox doesn't have), posts the result
  back. **Not verified end-to-end against real DoltHub data or a running
  Docker Compose stack** — verify on your VPS before trusting it.

Smoke test (backend running):

```bash
curl -s "localhost:8000/api/v1/backtests/compile-preview?spec_id=<id>" | python3 -m json.tool
curl -s -X POST localhost:8000/api/v1/backtests -H 'content-type: application/json' \
  -d '{"specId": <id>, "engine": "optopsy"}'                    # queues a job
curl -s -X POST "localhost:8000/api/v1/backtests/jobs/claim?engine=optopsy"  # what the worker calls
curl -s -X POST localhost:8000/api/v1/backtests/jobs/<run id>/result -H 'content-type: application/json' \
  -d '{"metrics": {}, "trades": [{"entryDate":"2024-01-01","exitDate":"2024-02-01","pnl":100}], "equityCurve": [10000, 10100], "engineRaw": {}}'
curl -s -X POST localhost:8000/api/v1/backtests/<run id>/robustness -H 'content-type: application/json' \
  -d '{"kind": "bootstrap", "params": {"n": 2000}}'
curl -s -F "file=@trade_log.csv" "localhost:8000/api/v1/backtests/import/oo?spec_id=<id>"
```

Running the optopsy worker locally (separate venv, AGPL isolation):

```bash
cd backend/optopsy-worker
uv sync                                # its own pyproject.toml/uv.lock, optopsy included
BACKEND_URL=http://localhost:8000/api/v1 WORKER_TOKEN= uv run python worker.py
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
- `watchlist_scan` — 17:00 ET weekdays: samples each watched symbol's
  chain into `symbol_metrics` for the screener registry. Skips with a
  log line when no chain-capable provider is registered.
- `beta_refresh` — 08:00 ET Saturdays: pulls each watchlist symbol's beta
  from IB Gateway's fundamental-ratios feed, cached in `beta_cache`.
  Weekly because a broker-reported beta barely moves day to day, and
  running off-market on a non-trading day keeps it off the weekday jobs'
  provider-pacing budget.
- `bot_tick` — every minute, 09:00–16:00 ET weekdays: ticks every
  `running` bot's state machine once. A bot-level exception is caught
  and logged; one bot's failure never stops the rest from ticking.

## PWA + mobile push (Phase 18 of the trading-platform plan)

The frontend is installable (`vite-plugin-pwa`: manifest + service
worker, `registerType: "autoUpdate"`) — on Android, Chrome's "Add to
Home screen" installs it as a standalone app. All pages are responsive
(off-canvas drawer nav below 720px; tables scroll horizontally inside
their own container rather than the page; `.filter-row` controls shrink
instead of forcing viewport overflow — a real bug on the Backtests page
found via a 390px-width horizontal-overflow sweep across every page,
fixed by adding `min-width: 0`/`max-width: 100%` to `.filter-row
select`, a classic flexbox shrink gotcha).

Push notifications go through **ntfy** (`app/alerts/push.py`, already
wired into the alert dispatcher — no code changes this phase):

1. Pick a private topic name (treat it like a password — anyone who
   knows it can read your notifications): e.g. `stockapp-yourname-8f2c`.
2. Set `NTFY_URL=https://ntfy.sh/<your-topic>` in the backend's `.env`
   (or deploy `.env` — see `../deploy/.env.example`).
3. Install the [ntfy Android app](https://ntfy.sh/) (or iOS/desktop) and
   subscribe to the same topic.
4. Any alert rule with `push` in its channels (`POST /alerts` /
   `PATCH /alerts/{id}`) now delivers to your phone.

**Deferred this phase**: ntfy action buttons (approve/kill directly from
the notification — the plan's "approve/kill works from phone via ntfy
buttons" acceptance line is not met; ntfy supports this via an `Actions`
header calling back to an authenticated endpoint, but wiring that up
needs a token-scoped callback URL per bot/rule, not built here); a
Journal page (doesn't exist yet — phases 12–13) so the ✅ line's
"Bots/Portfolio/Journal usable at 390px" only covers Bots/Portfolio (and
every other page, checked broadly, not narrowly to those two); Lighthouse
PWA-installable was not run (no Lighthouse CLI in this sandbox) — the
underlying criteria (valid manifest fetched over HTTP, service worker
registered with the correct scope, icons present) were verified directly
via a real Playwright browser session against a production build served
from the correct `/stock-app/` subpath, which is what Lighthouse itself
checks under the hood.

## Safety

- `transmit=True` appears nowhere in this codebase; tickets stage only.
- `ALLOW_ORDER_STAGING` defaults to false → manual order spec instead.
- Empty `API_TOKEN` disables auth for local dev; production always sets one
  (see `../deploy/.env.example`).

## Deployment

See `../deploy/README.md` for the VPS stack (backend + headless IB Gateway +
Caddy HTTPS via Docker Compose).
