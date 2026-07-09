# Stock App → Personal Trading Platform

A React frontend (GitHub Pages) + FastAPI/`ib_async` backend (your machine or
a VPS, next to IB Gateway) that is growing, phase by phase, into a personal
options/crypto trading platform: strategy database, provider-labeled market
data, backtesting, bots, journal, portfolio. The living plan is
[`superpowers/plan/trading-platform.md`](superpowers/plan/trading-platform.md).

**Live frontend:** https://oslinin.github.io/stock-app/ — the backend never
runs on Pages; you point the static frontend at your own backend URL.

---

## What works today

| Feature | Status | How to try it |
|---|---|---|
| Stock lookup (quotes + 30-day chart) | ✅ live | `#/` on the demo, or `pnpm dev` (needs `VITE_API_KEY`) |
| VIX hedge screener + alerts + order tickets | ✅ needs backend + IB Gateway | `#/screener`, `#/alerts` |
| Strategy library (spec DB + doc/payoff pages) | ✅ Phase 1, needs backend | `#/strategies` — a seeded 45-DTE put credit spread appears; view its doc + payoff, edit it, approve it |
| Provider-labeled market data + option analytics | ✅ Phase 2, needs backend | `#/chain` — option chain with a source switcher (yfinance free / IBKR), IV + greeks, provenance badge; `POST /analytics/structure` gives PoP/expected profit; nightly job syncs ATM-IV history from IBKR's IV index for `/marketdata/ivrank` |
| Spec interpreter — approved specs run as real strategies | ✅ Phase 3, needs backend | `#/strategies/{id}` — approve a spec and it appears in the registry (`spec:<slug>`); the Entry rules table gains a live ENTER/WAIT verdict with per-condition observed values, refreshed on every page load |
| Watchlist + screeners | ✅ Phase 4, needs backend | `#/watchlist` — add symbols, run a screener (expensive premium / high IV rank / Δ-DTE candidates) over the nightly `symbol_metrics` scan, open a result in the Option Chain page |
| Portfolio view | ✅ Phase 5, needs backend | `#/portfolio` — IBKR live positions + Fidelity CSV upload, merged; grouping toggle, aggregate greeks + beta-weighted delta, forward-looking CVaR risk tiles |
| Backtesting, bots, journal… | 🔜 phases 6–18 | see the plan |

---

## Run it locally

### Prerequisites

- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** for the
  backend (Python 3.11+ — uv installs the interpreter for you if needed)
  and **Node 20+ with pnpm** (`corepack enable`) for the frontend
- **IB Gateway or TWS** (optional) — only needed for the VIX screener,
  order tickets, `?source=ibkr` market data, and IV-rank history. The
  strategy library, yfinance market data, and option analytics work
  without it. Paper defaults: Gateway port 4002 / TWS 7497, with API
  connections enabled.

### 1. Backend

```bash
cd backend
uv sync --extra dev         # creates .venv, installs from uv.lock (~10s)
cp .env.example .env        # then edit — see below
uv run uvicorn app.main:app --reload --port 8000 --loop asyncio
```

`--loop asyncio` matters: ib_async, APScheduler and FastAPI must share one
plain asyncio event loop. `uv run` uses `.venv` automatically, no manual
activation needed.

The `.env` defaults are fine for a first run without IB. Keys you may want
to set (all documented in `backend/.env.example`):

| Key | When you need it |
|---|---|
| `API_TOKEN` | empty = no auth (local dev); always set in production |
| `IBKR_ENABLED` / `IBKR_PORT` | `false` to silence connect retries without a gateway; port 4002 gateway-paper, 7497 TWS-paper |
| `ALPHAVANTAGE_API_KEY` | optional; registers the Alpha Vantage provider (free key, 25 req/day, guarded) |
| `IV_SNAPSHOT_SYMBOLS` | symbols the nightly job keeps IV-rank history for (needs IB) |
| `SMTP_*` / `NTFY_URL` | alert delivery |

First startup creates `vix_screener.db` (SQLite, WAL) and seeds one example
strategy spec.

### 2. Frontend

```bash
# repo root, second terminal
pnpm install
echo "VITE_API_BASE=http://localhost:8000/api/v1" >> .env
pnpm dev                    # open the printed URL
```

Optional, only for the stock-lookup page: add `VITE_API_KEY=<alpha vantage key>`
to the same `.env`.

Instead of `VITE_API_BASE` you can also set the backend URL (and bearer
token) at runtime in the Screener page's settings panel — that's how the
deployed Pages build connects to your backend.

### 3. Check it works

Sidebar pages: **Stock Lookup**, **VIX Screener**, **Strategies**,
**Option Chain**, **Watchlist**, **Portfolio**, **Alerts**. Or without the UI:

```bash
curl -s localhost:8000/api/v1/health                                 # liveness
curl -s localhost:8000/api/v1/specs | python3 -m json.tool           # seeded strategy (Phase 1)
curl -s "localhost:8000/api/v1/marketdata/quote?symbol=SPY"          # {data, provenance} (Phase 2)
curl -s "localhost:8000/api/v1/marketdata/chain?symbol=SPY" | head   # chain + IV + greeks
curl -s -X POST localhost:8000/api/v1/analytics/structure \
  -H 'content-type: application/json' \
  -d '{"legs":[{"right":"P","action":"sell","strike":95,"premium":2.0},
               {"right":"P","action":"buy","strike":90,"premium":1.1}],
       "spot":100,"volatility":0.25,"daysToTarget":45}'              # PoP, max P/L
```

More per-feature smoke tests: [`backend/README.md`](backend/README.md).

### 4. Tests

```bash
cd backend && uv run pytest   # pure-logic suite, no network/IB required
pnpm run lint && pnpm run build
```

---

## Deployment

- **Frontend (production)**: pushes to `main` auto-deploy to
  `https://oslinin.github.io/stock-app/` via `.github/workflows/deploy.yml`
  (set the `VITE_API_KEY` repo secret for the stock-lookup page).
- **Frontend (PR previews)**: pushes to any other branch auto-deploy to
  `https://oslinin.github.io/stock-app/preview/<branch>/` via
  `.github/workflows/deploy-preview.yml` — production is never touched;
  the preview is removed automatically when its PR closes or merges. Also
  runnable on demand from the Actions tab (`workflow_dispatch`).
- **Backend + IB Gateway on a VPS**: Docker Compose stack (backend +
  headless gateway + Caddy TLS) in [`deploy/`](deploy/README.md).

---

## Repo layout

| Path | Contents |
|---|---|
| `src/` | React frontend (Vite, React Router, Chart.js) |
| `backend/` | FastAPI app: `app/specs` (strategy DB), `app/dataproviders` + `app/analytics` (market data, greeks), `app/ibkr` (gateway client), `app/screener`, `app/alerts`, `app/scheduler`; tests in `backend/tests/` |
| `deploy/` | VPS Docker Compose stack + Caddy |
| `docs/` | strategy rule write-ups + reference PDFs |
| `superpowers/plan/` | implementation plans; `trading-platform.md` is the source of truth for phases 1–18 |

## History

Started from the Medium article
[Build & Publish Your First Stock App (for FREE!)](https://medium.com/@wl8380/build-publish-your-first-stock-app-for-free-df59820998aa)
(the `#/` stock-lookup page), swapped CRA/npm for Vite/pnpm and manual
deploys for GitHub Actions, then grew the VIX hedge screener and the
trading-platform phases on top. The AJ Brown VIX hedge strategy rules live
in [`docs/strategies/vix-hedge.md`](docs/strategies/vix-hedge.md).
