# VIX Hedge for Options Sellers (AJ Brown)

A near-zero-cost VIX options structure that breaks even most of the time and
pays off in a volatility spike. Source: AJ Brown via thetaprofits.com,
"A VIX hedge for options sellers that breaks even most of the time" and the
companion video "This VIX Trade Breaks Even Most of the Time — And Wins Big
in Crashes".

## Structure

Two vertical spreads on the **same monthly VIX expiration** (~15–34 DTE),
both **1.0 point wide** (VIX options have a $100/point multiplier, so each
vertical is "$100 wide"):

| Leg | Role |
|---|---|
| BUY call, strike below the VIX future | call debit spread — the crash winner |
| SELL call, 1 point higher | |
| SELL put, strike above the VIX future | put credit spread — finances the call spread |
| BUY put, 1 point lower | |

Reference example (VIX future ≈ 19.5): long 14.5C / short 15.5C, short 21P /
long 20P. Payoff at expiration: **−$100** if VIX settles below the call
spread, **≈ $0** in the middle band, **+$100** if VIX settles above the put
spread — and the position costs ≈ nothing to open.

## Hard screening requirement

- Both verticals **equal width** (default 1.0 pt).
- **Net debit per combo < $100** (call-spread debit − put-spread credit,
  × $100 multiplier), ranked toward $0.
- Strike search is centered on the **expiry's VIX future** (VIX options
  price off the future, not spot).
- Expensive builds — mismatched widths (e.g. a 1.5-pt call spread), wide
  long-dated quotes, multi-thousand-dollar net debits — are rejected. When
  nothing qualifies the screener reports **WAIT**; that is the normal state
  when volatility is not cheap.

## Entry rules

**Arming (evening, after the close)** — a MACD bottom signal on the daily
VIX chart (defaults 12/26/9): MACD line crossing above its signal line
and/or the histogram turning up from a trough, while VIX is relatively low
(bottom 40% of its trailing 120-day range, or under an absolute floor of 20).

**Confirmation (next session) — all three must hold, checked intraday:**

1. VIX is higher than the **previous day's close**;
2. VIX is higher than the **confirming-day close** (the close of the day the
   signal fired, in case that differs from the previous day);
3. VIX trades above the **opening range** — the high of the first 30 minutes
   of the session.

When all hold, the verdict flips to **ENTER** and the screener constructs the
cheapest qualifying combo. From the transcript: *"in the evening, if we
identify that there's been one of these bottom signals found, we'll go ahead
and program our bots that evening to trade the next day, assuming some simple
conditions are met… it's higher than the previous day close, it's higher than
the confirming day close… if it's trading above the open range."*

## Management

- The structure is designed to be held; most cycles it expires in the
  flat/break-even band.
- In a volatility spike each combo approaches its ~$100 max value — the
  hedge pays exactly when short-premium portfolios hurt.
- VIX options are European, cash-settled, **AM-settled** monthlies: last
  trading day is the Tuesday before the Wednesday expiration; settlement is
  the SOQ, not the Wednesday open print.

## Implementation in this repo

- Backend strategy: `backend/app/strategies/vix_hedge.py` (selection +
  filters), signals in `backend/app/indicators/`.
- Verdicts/spread API: `/api/v1/screener/vix_hedge/{state,verdict,spread}`.
- Alerts fire on ARMED (evening) and ENTER (intraday confirmation), deduped
  per trading day; order tickets are whatIf previews or `transmit=false`
  staged combos — nothing auto-executes.
- All parameters (MACD, opening-range window, width, debit cap, DTE window)
  are configurable via environment variables (see `backend/.env.example`).
