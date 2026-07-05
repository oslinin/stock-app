# VPS deployment

Three containers via Docker Compose: `ib-gateway` (headless IB Gateway with
auto-login), `backend` (the FastAPI screener), and `caddy` (automatic HTTPS).
Only ports 80/443 are published; the IB API socket never leaves the internal
Docker network.

## Prerequisites

- A VPS with Docker + the compose plugin, and outbound access to IBKR/SMTP.
- A DNS **A record** (e.g. `vix.yourdomain.com`) pointing at the VPS, with
  ports 80 and 443 open. HTTPS is mandatory: the GitHub Pages frontend is
  served over https and browsers block calls to an http API (mixed content).
- IBKR credentials (start with the **paper** account).

## Bring-up

```bash
cd deploy
cp .env.example .env
# edit .env: DOMAIN, TWS_USERID/TWS_PASSWORD, API_TOKEN, SMTP_*
docker compose up -d --build
docker compose logs -f backend   # wait for "connected to IBKR"
```

Verify from anywhere:

```bash
curl https://$DOMAIN/api/v1/health
curl -H "Authorization: Bearer $API_TOKEN" https://$DOMAIN/api/v1/ibkr/status
curl -H "Authorization: Bearer $API_TOKEN" https://$DOMAIN/api/v1/screener/vix_hedge/spread
```

Then open the frontend, go to the Screener page, and paste the API base
(`https://$DOMAIN/api/v1`) and token into its Settings panel once — they are
kept in the browser's localStorage, never in the built site.

## Notes

- **2FA**: with IB mobile-app 2FA the gateway login sits waiting for your
  approval; `TWOFA_TIMEOUT_ACTION=restart` keeps retrying. The gateway also
  restarts nightly (`AUTO_RESTART_TIME`) per IB's session rules.
- **Market data**: without a CBOE (VIX index) + OPRA (options) subscription
  quotes are delayed or empty; the API surfaces this in `warnings` and
  `marketDataType`. Keep `IBKR_USE_DELAYED=true` until subscribed.
- **Order staging**: `ALLOW_ORDER_STAGING=false` means `/orders/ticket`
  returns a manual order spec only. When enabled, orders are placed with
  `transmit=false` — they appear in TWS as untransmitted orders for you to
  review; the backend never transmits. A headless gateway has no UI to show
  staged orders, so either keep the manual flow or run TWS instead.
- **Persistence**: SQLite (alert rules/events, armed state) lives on the
  `backend-data` volume; IB Gateway settings on `ib-settings`.
- **Updates**: `git pull && docker compose up -d --build`.
