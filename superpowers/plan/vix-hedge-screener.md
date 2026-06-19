# VIX Options Hedging Screener (AJ Brown strategy) — Implementation Plan

## Context
You want to trade AJ Brown's "VIX hedge for options sellers" — a near‑zero‑cost structure that
breaks even most of the time and pays off in a vol spike. The practical problem is that live VIX
option prices aren't reliably visible (OptionStrat sometimes shows them, sometimes not), and the
entries are rule‑based (a MACD "bottom signal" plus next‑day confirmation "bots"). You have an
Interactive Brokers account and want IBKR as the data source. Goal: a **visual screener** for this
(and later other) strategies, **automated alerts**, and **one‑click order tickets** that you review
and submit in IBKR — surfaced inside the existing `stock-app` UI.

This plan adds a Python backend (IBKR via `ib_insync`) that **you deploy on your persistent VPS**, and
a new React "Screener" page served from GitHub Pages that reads from that VPS over HTTPS. The existing
Alpha Vantage stock‑lookup demo keeps working and keeps deploying to GitHub Pages.

> Note: this implementation will be run by you on your **VPS** (a real, persistent host — not the
> ephemeral cloud container this planning session runs in, which can't host a public service).

## Decisions confirmed with you
- **Data path:** live backend service (FastAPI + `ib_insync` → IB Gateway) hosted on **your VPS**; the
  GitHub Pages frontend reads from it over **HTTPS**.
- **First deliverable:** visual screener **+ alerts + order tickets** (nothing auto‑executes).
- **Entry signal:** MACD "bottom signal" (arming) + next‑day confirmation conditions (below).
- **Instrument:** standard CBOE **VIX index options** (`Option('VIX', …, 'CBOE', multiplier='100')`),
  kept configurable so options‑on‑VIX‑futures can be added later.
- **Default to IBKR paper trading**; live is an explicit opt‑in setting.

## ⭐ Hard requirement: $100‑wide spreads with net debit < $100
The core screening criterion, and what your screenshots highlight:
- VIX options multiplier = **$100/point**, so a **"$100‑wide" vertical = 1 VIX point wide** (max value $100).
- **Pic 1** is the target profile: 1‑pt call debit spread + 1‑pt put credit spread, max gain +$100 /
  max loss −$100, **net debit ≈ $0** (the put credit finances the call debit).
- **Pic 2** (NET DEBIT $2,289 / MAX LOSS $2,389) is the build to **avoid** — too expensive (mismatched
  widths e.g. 14.5/16 = 1.5 pt, longer‑dated less‑liquid strikes quoted at wide mids, and/or more contracts).
- VIX options price off the **expiry's VIX future**, not spot VIX (why pic 1 centered on 19.48 and pic 2
  on 18.48) — the strike search centers on the future, not spot.

**Acceptance criterion the screener enforces:** both legs equal width (default 1.0 pt = $100), and
**net debit per combo < $100** (configurable cap; ranked toward $0). Combos with net debit ≥ cap are
rejected; if none qualify, the verdict is **WAIT** (the normal state when vol isn't cheap).

## Architecture overview
- **Monorepo:** add a `backend/` tree + `deploy/` artifacts to `stock-app`. The Vite/Pages build only
  compiles the frontend, so `backend/` and `deploy/` are ignored by `deploy.yml` (no workflow change).
- **Backend on your VPS:** FastAPI + `ib_insync` runs as a long‑lived service alongside IB Gateway,
  behind a reverse proxy that terminates **HTTPS** (mandatory — a page on `https://oslinin.github.io`
  is blocked by the browser from calling an `http://` API; "mixed content"). Deployed via Docker Compose.
- **Frontend → backend:** the static Pages site reaches the VPS via `VITE_API_BASE`
  (`https://<your-domain>/api/v1`). If unset/unreachable, the Screener page shows a graceful
  "backend offline" state. All backend calls carry an **API token** you enter once in the UI (stored in
  `localStorage`, never baked into the build) — so no secret ships in the public Pages bundle.
- **Frontend** gains its first router (`react-router-dom`, **HashRouter** to avoid Pages deep‑link 404s
  under the `/stock-app/` base) and Screener + Alerts pages.

## Strategy logic
**Structure (two 1‑pt verticals, same monthly VIX expiry, ~15–34 DTE):**
- Call **debit** spread (long‑vol / crash winner): long lower call, short call 1 pt higher.
- Put **credit** spread (financing): short higher put, long put 1 pt lower.
- Strikes chosen so credit ≈ debit → net ≈ $0 (algorithm below).

**Entry — arming (EOD):** MACD (default 12/26/9) on **daily VIX** produces a "bottom signal"
(histogram turning up from a trough and/or MACD line crossing above signal at a relatively low VIX
level). On detection after the close, persist an `ArmedState` (with the "confirming day" close) for the
next session.

**Entry — confirmation (next session, intraday) — all must hold to fire ENTER:**
1. VIX > **previous day's close**, AND
2. VIX > **confirming‑day close** (stored at arming), AND
3. **Opening‑range breakout:** VIX > high of the **first 30 minutes** of the RTH session.

Verdict ∈ `{ NO_DATA, WAIT, ARMED, ENTER }`.

## Spread construction & filtering algorithm
In `backend/app/strategies/vix_hedge.py` (selection) + `spread_math.py` (math). Inputs: live chain with
bid/ask/mid + greeks, the expiry's **future price**, width, DTE window, contracts, debit cap.
1. **Pick expiry:** nearest listed monthly VIX expiry with DTE in `[dteMin, dteMax]`.
2. **Enumerate candidates:** all 1‑pt call verticals and 1‑pt put verticals on the chain.
3. **Price each** from real quotes: call `debit = mid(longC) − mid(shortC)`; put `credit = mid(shortP) − mid(longP)`. Keep bid/ask for slippage.
4. **Combine & filter:** for call+put combinations, `netDebit = debit − credit` per share; require equal
   widths and **`netDebit × 100 < debitCap` (default $100)**. Rank by smallest `netDebit` (toward $0).
   This reproduces pic 1 and rejects pic‑2‑style expensive builds.
5. **Math (per share ×100 ×contracts):** call `maxLoss=debit`, `maxGain=width−debit`; put `maxGain=credit`,
   `maxLoss=width−credit`; total payoff is piecewise‑linear, evaluated at the four strikes + padded
   endpoints to produce `payoff:[{x,y}]`, breakevens (roots of the curve), and worst‑case max loss.
   Report economics in **both points and dollars**, residual net vs $0, and aggregate by `contracts`.
6. **Warnings:** delayed data, wide/no‑bid legs, non‑zero residual net.
Pure functions → unit‑tested with synthetic chains, no IB needed.

## Backend (new `backend/` tree)
```
backend/
  pyproject.toml  .env.example  README.md  Dockerfile
  app/
    main.py            # FastAPI app, CORS, API-token dependency, router mounting, lifespan (IB + scheduler)
    config.py          # pydantic-settings (IBKR, SMTP, API_TOKEN, CORS, strategy defaults, debit cap)
    security.py        # require_token dependency (Authorization: Bearer <API_TOKEN>)
    ibkr/              # ONLY place importing ib_insync
      client.py        # connect/reconnect, reqMarketDataType (delayed default)
      contracts.py     # resolve VIX Index + chain via reqSecDefOptParams, qualifyContracts
      marketdata.py    # spot, intraday bars (opening range, prior close), option quotes+greeks
      orders.py        # build 4-leg BAG combo; whatIf preview; place transmit=False (NEVER True)
    indicators/        # macd.py, signals.py (bottom_signal, confirmation, verdict), opening_range.py
    strategies/        # base.py (ABC), registry.py, vix_hedge.py, spread_math.py
    screener/          # engine.py (orchestrate), schemas.py (pydantic models)
    alerts/            # models.py (SQLite), smtp.py, push.py (optional), dispatcher.py (dedupe)
    scheduler/         # APScheduler: eod_arming_scan, intraday_confirmation_poll (US/Eastern)
    db/                # SQLite session/init (single-user, persisted on a Docker volume)
    api/               # routes_health, routes_strategies, routes_screener, routes_orders, routes_alerts
  tests/               # test_macd, test_signals, test_spread_math, test_vix_hedge, test_orders_build
```
**Key endpoints** (base `/api/v1`, all behind the API token except `/health`; strategy‑generic so a
second strategy needs no new routes):
- `GET /health` (public) and `GET /ibkr/status` → connected, mode (paper/live), marketDataType.
- `GET /strategies`, `GET /strategies/{id}` → registry + param schema.
- `GET /screener/{id}/state` → spot, priorClose, confirmingClose, openingRange, macd.
- `GET /screener/{id}/verdict` → verdict + per‑check pass/fail list.
- `GET /screener/{id}/spread?expiry&width&contracts` → legs (bid/ask/mid/greeks), call/put economics,
  `net` (debit in pts + $), maxLoss, breakevens, `payoff[]`, warnings.
- `POST /orders/preview` → ib_insync `whatIf` (margin/commission only; transmits nothing).
- `POST /orders/ticket` → builds BAG combo, places **`transmit=False`** (staged for review) or returns a
  manual spec if headless. Hard setting `ALLOW_ORDER_STAGING` (default off).
- `GET/POST/PATCH/DELETE /alerts` + `GET /alerts/events`.

**IBKR notes:** single `IB()` instance in FastAPI lifespan (shared asyncio loop with APScheduler);
`Index('VIX','CBOE')`; opening range from `reqHistoricalData` 5‑min RTH bars normalized to US/Eastern;
respect pacing (~50 md lines) when quoting candidate strikes.

## Frontend (under existing `src/`)
- `main.jsx`: wrap in `<HashRouter>`. `App.jsx`: becomes a layout shell with nav + `<Routes>`; move the
  current stock lookup **verbatim** into `src/pages/StockLookup.jsx` (no behavior change).
- `src/api/client.js`: axios instance, `baseURL = import.meta.env.VITE_API_BASE`, attaches
  `Authorization: Bearer <token from localStorage>`. `src/api/screener.js` wraps the endpoints.
- `src/config.js`: `hasBackend = !!VITE_API_BASE`; helpers to get/set the API token in `localStorage`.
- `src/pages/Screener.jsx`: strategy picker, live VIX header, `VerdictBadge` (WAIT/ARMED/ENTER), check
  list, `SpreadTable` (4 legs), `SpreadSummary` (net debit pts+$, max loss, breakevens, DTE),
  `PayoffChart`, `OrderTicketPanel` ("Preview" + "Stage in IBKR", persistent "nothing auto‑executes" copy),
  and a small **Settings** field to paste the API token.
- `src/pages/Alerts.jsx`: CRUD over alert rules + recent events.
- `src/components/PayoffChart.jsx`: **reuse** the Chart.js registration already in `App.jsx`
  (LinearScale/PointElement/LineElement registered), linear‑x P&L‑at‑expiration line, green/red fill via
  `segment`, vertical markers at spot + breakevens, tooltip "VIX x → $y". Add `--green`/`--red` to
  `index.css`. Only new dependency: `react-router-dom`.

## Alerts + scheduler
APScheduler `AsyncIOScheduler` in the lifespan. `eod_arming_scan` after the cash close (writes/refreshes
`ArmedState`, fires `ARMED`); `intraday_confirmation_poll` every ~5 min during RTH only while armed
(fires `ENTER`, embeds the constructed spread). Email via SMTP (Gmail app‑password friendly; default
recipient your address); optional push (ntfy/Pushover) behind the same dispatcher. Dedupe via
`AlertEvent` keyed by `(rule, strategy, verdict, tradingDate, expiry)` → at most once per trading day.

## Order tickets (no auto‑execute, layered safety)
ENTER → "Preview in IBKR" (`whatIf`, margin/commission only) → "Stage in IBKR" (`transmit=False`, order
appears **untransmitted** in TWS; you click Transmit). `transmit=True` never appears in the codebase;
`ALLOW_ORDER_STAGING` defaults false; paper port is the default. Headless Gateway (no GUI to review a
staged order) → returns a manual order spec instead of staging.

## Deployment on your VPS (Docker Compose)
New `deploy/` tree committed to the repo:
```
deploy/
  docker-compose.yml   # 3 services: backend (FastAPI), ib-gateway (headless), caddy (reverse proxy/TLS)
  Caddyfile            # auto-HTTPS for your domain; reverse_proxy /api/* -> backend:8000
  .env.example         # DOMAIN, API_TOKEN, IBKR creds/mode, SMTP, CORS_ORIGINS
  README.md            # step-by-step VPS bring-up
```
- **ib-gateway service:** a headless IB Gateway image (e.g. `ghcr.io/gnzsnz/ib-gateway`) with **IBC**
  auto‑login; exposes API port **only on the internal Docker network** (never published to the host's
  public interface). Backend connects to `ib-gateway:4002` (paper) / `4001` (live).
- **caddy service:** terminates **HTTPS** with a free Let's Encrypt cert for your domain; this is what
  makes `https://oslinin.github.io → https://<your-domain>/api/v1` work without mixed‑content blocking.
- **Persistence:** SQLite + IB settings on named Docker volumes; `restart: unless-stopped` so it survives
  reboots (replaces systemd — none needed).
- **DNS/firewall:** point an A record (`vix.<your-domain>`) at the VPS; open **only 443** (and 80 for ACME)
  publicly; keep IB ports internal. Set `CORS_ORIGINS=https://oslinin.github.io` and a strong `API_TOKEN`.
- Bring‑up: `cd deploy && cp .env.example .env && <edit> && docker compose up -d`.

## Config & secrets
Backend `deploy/.env` / `backend/.env` (gitignored; `.env.example` committed): `DOMAIN`, `API_TOKEN`,
`IBKR_HOST=ib-gateway`, `IBKR_PORT=4002`, `IBKR_MODE=paper`, `IBKR_USE_DELAYED=true`,
`ALLOW_ORDER_STAGING=false`, `SMTP_*`, `DEFAULT_ALERT_EMAIL=oleg.slinin@gmail.com`,
`DB_URL=sqlite:////data/vix_screener.db`, `CORS_ORIGINS=https://oslinin.github.io`, and strategy defaults
incl. `VIX_SPREAD_WIDTH=1.0`, `VIX_NET_DEBIT_CAP_USD=100`, `VIX_DTE_MIN=15`, `VIX_DTE_MAX=34`,
MACD 12/26/9, `VIX_OR_MINUTES=30`.
Frontend build: set `VITE_API_BASE=https://<your-domain>/api/v1` (a non‑secret URL; safe to commit in a
`.env` or to set in the Pages build). The **API token is NOT built in** — you paste it into the Screener
Settings field; it lives in `localStorage`. No IBKR/SMTP secrets ever touch GitHub Actions; `deploy.yml`
is unchanged except optionally injecting `VITE_API_BASE`.

## Generalization
`strategies/registry.py` + a `Strategy` ABC (`metadata`, `params`, `evaluate()`, `build_spread()`) so
"this and other trades" plug in without new endpoints or new React components — the API envelope
(`verdict`, `checks`, `legs`, `net`, `breakevens`, `payoff`) is uniform.

## Strategy docs / Obsidian
I **cannot access `oslinin/second-brain` in this session** (GitHub integration is scoped to `stock-app`),
so I can't write your Obsidian page now. Plan: commit `docs/strategies/vix-hedge.md` into `stock-app`
capturing the rules, parameters, and the $100‑wide/<$100‑debit criterion. Mirror it into Obsidian, or
grant this session access to `second-brain` later and I'll write it there.

## How to run & verify
**On your VPS (production):** `cd deploy && cp .env.example .env && <edit DOMAIN/API_TOKEN/IBKR/SMTP> &&
docker compose up -d`; confirm `https://<your-domain>/api/v1/health` returns ok over HTTPS, and
`GET /ibkr/status` (with `Authorization: Bearer <API_TOKEN>`) shows connected.
**Local dev (optional):** backend `cd backend && python -m venv .venv && . .venv/bin/activate &&
pip install -e . && cp .env.example .env && uvicorn app.main:app --reload --port 8000`; frontend
`pnpm install && pnpm add react-router-dom && echo VITE_API_BASE=http://localhost:8000/api/v1 >> .env && pnpm dev`.
**Tests (no IB):** `cd backend && pytest`; `pnpm lint`.
**End‑to‑end checks:**
1. `GET /ibkr/status` → connected; note marketDataType.
2. `GET /screener/vix_hedge/state` → sane VIX spot (~10–40), opening range populated in RTH, MACD present.
3. `GET /screener/vix_hedge/spread` → both legs 1 pt wide, **net debit < $100**, payoff flat‑up on the
   right / flat‑down on the left; spot‑check the math by hand against the algorithm formulas.
4. Frontend (Pages or `pnpm dev`) `/#/screener` → paste API token, badge/table/summary/payoff render;
   wrong/empty token → clear error; unset `VITE_API_BASE` → offline state.
5. Alerts → create rule, force ARMED (fixture or EOD job) → exactly one email + one `AlertEvent`.
6. Orders → `preview` shows margin; `ticket` in **paper** → staged, **untransmitted** combo in TWS.

## Phased commits (first PR, on branch `claude/relaxed-edison-n8iglq`)
1. Backend skeleton (FastAPI + `/health` + config + API‑token dependency + `.env.example`).
2. Pure indicators + `spread_math` + tests (CI‑safe, no IB).
3. Strategy registry + `vix_hedge` (offline, synthetic chain) + `/strategies`.
4. IBKR integration (`ibkr/*`, `/ibkr/status`, `/screener/*` live).
5. Orders preview + staged (no‑execute) + tests.
6. Persistence + alerts + scheduler.
7. Deployment artifacts (`backend/Dockerfile`, `deploy/docker-compose.yml`, `Caddyfile`, `.env.example`, README).
8. Frontend: HashRouter + move StockLookup + api client (token) + config + offline state (demo still works).
9. Frontend: Screener page + components (incl. PayoffChart) + token Settings.
10. Frontend: Alerts page.
11. Docs (`backend/README.md`, root README backend/VPS split, `docs/strategies/vix-hedge.md`).
(1–3, 8 are mergeable without IB. Frontend deploys to Pages on merge to `main`; backend/deploy never deploy to Pages.)

## Risks & caveats
- **HTTPS is mandatory:** Pages is HTTPS, so the VPS backend must serve HTTPS (Caddy handles this) or the
  browser blocks every call as mixed content. Needs a real **domain + DNS A record** for the cert.
- **Public trading endpoint security:** the backend can place IBKR orders, so it's token‑gated, IB ports
  stay on the internal Docker network (never public), only 443/80 are exposed, and `transmit=True` never
  appears in code. Use a strong `API_TOKEN`; rotate if leaked. Consider IP allowlist as a stretch.
- **IBKR market‑data entitlements:** VIX index + OPRA option data usually need a paid CBOE/OPRA
  subscription; otherwise quotes/greeks are delayed or empty → degraded spread math (surfaced as warnings).
- **VIX option settlement:** AM‑settled, monthly, last trade Tuesday before the Wed expiry, SOQ settlement
  — DTE/expiry logic must account for this; avoid very‑low‑DTE legs near settlement.
- **Liquidity:** wide bid/ask on far/low strikes → mids may misstate net cost; bid/ask shown.
- **Opening‑range timezone:** normalize bars to US/Eastern with DST — the main correctness trap; tested.
- **IB Gateway auto‑login:** headless IBC needs your IBKR credentials in `deploy/.env` (kept off‑repo);
  2FA accounts may need IBKR's "second‑factor" handling — confirm your login type. Headless = no GUI to
  review staged orders, so order tickets fall back to a manual spec (or run TWS instead of Gateway).
- **VPS egress:** ensure the VPS can reach IBKR servers and your SMTP host (this is your VPS, so no
  allowlist — unlike this planning container).
