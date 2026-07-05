import React, { useCallback, useEffect, useState } from "react";
import { errorMessage, isAuthError } from "../api/client";
import { getSpread, getState, getVerdict } from "../api/screener";
import { getApiBase, getToken, hasBackend, setApiBase, setToken } from "../config";
import BackendOffline from "../components/BackendOffline.jsx";
import OrderTicketPanel from "../components/OrderTicketPanel.jsx";
import PayoffChart from "../components/PayoffChart.jsx";
import SpreadSummary from "../components/SpreadSummary.jsx";
import SpreadTable from "../components/SpreadTable.jsx";
import VerdictBadge from "../components/VerdictBadge.jsx";
import "../chartjs.js";

const STRATEGY_ID = "vix_hedge";
const REFRESH_MS = 60000;

const fmt = (v, digits = 2) => (v == null ? "—" : Number(v).toFixed(digits));

function Screener() {
  const [connected, setConnected] = useState(hasBackend());
  const [state, setState] = useState(null);
  const [verdict, setVerdict] = useState(null);
  const [spread, setSpread] = useState(null);
  const [contracts, setContracts] = useState(1);
  const [error, setError] = useState(null);
  const [authNeeded, setAuthNeeded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [settingsBase, setSettingsBase] = useState(getApiBase());
  const [settingsToken, setSettingsToken] = useState(getToken());

  const refresh = useCallback(async () => {
    if (!hasBackend()) {
      setConnected(false);
      return;
    }
    setLoading(true);
    setError(null);
    setAuthNeeded(false);
    const results = await Promise.allSettled([
      getState(STRATEGY_ID),
      getVerdict(STRATEGY_ID),
      getSpread(STRATEGY_ID, { contracts }),
    ]);
    const [stateRes, verdictRes, spreadRes] = results;
    if (stateRes.status === "fulfilled") setState(stateRes.value);
    if (verdictRes.status === "fulfilled") setVerdict(verdictRes.value);
    if (spreadRes.status === "fulfilled") setSpread(spreadRes.value);
    const failure = results.find((r) => r.status === "rejected");
    if (failure) {
      if (isAuthError(failure.reason)) setAuthNeeded(true);
      else setError(errorMessage(failure.reason));
    }
    setLoading(false);
  }, [contracts]);

  useEffect(() => {
    if (!connected) return undefined;
    const kickoff = setTimeout(refresh, 0);
    const timer = setInterval(refresh, REFRESH_MS);
    return () => {
      clearTimeout(kickoff);
      clearInterval(timer);
    };
  }, [connected, refresh]);

  if (!connected) {
    return (
      <div className="screener">
        <h1>VIX Screener</h1>
        <BackendOffline onSaved={() => setConnected(hasBackend())} />
      </div>
    );
  }

  const saveSettings = () => {
    setApiBase(settingsBase);
    setToken(settingsToken);
    setShowSettings(false);
    setConnected(hasBackend());
    refresh();
  };

  const opening = state?.openingRange;
  const macd = state?.macd;

  return (
    <div className="screener">
      <div className="screener-header">
        <h1>VIX Screener</h1>
        <div className="screener-header-right">
          {verdict && <VerdictBadge verdict={verdict.verdict} />}
          <button className="ghost" disabled={loading} onClick={refresh}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
          <button className="ghost" onClick={() => setShowSettings(!showSettings)}>
            Settings
          </button>
        </div>
      </div>

      {showSettings && (
        <div className="panel settings-panel">
          <div className="settings-grid">
            <label>
              API base URL
              <input
                value={settingsBase}
                onChange={(e) => setSettingsBase(e.target.value)}
                placeholder="https://vix.yourdomain.com/api/v1"
              />
            </label>
            <label>
              API token
              <input
                type="password"
                value={settingsToken}
                onChange={(e) => setSettingsToken(e.target.value)}
              />
            </label>
            <button onClick={saveSettings}>Save</button>
          </div>
        </div>
      )}

      {authNeeded && (
        <p className="error">
          The backend rejected the API token (401). Open Settings and paste the
          token from your VPS <code>deploy/.env</code>.
        </p>
      )}
      {error && <p className="error">{error}</p>}

      {state && (
        <div className="stats-row">
          <div className="stat">
            <div className="stat-label">VIX</div>
            <div className="stat-value">{fmt(state.spot)}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Prior close</div>
            <div className="stat-value">{fmt(state.priorClose)}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Confirming close</div>
            <div className="stat-value">{fmt(state.confirmingClose)}</div>
          </div>
          <div className="stat">
            <div className="stat-label">
              OR {opening?.windowMin ?? 30}m high
            </div>
            <div className="stat-value">
              {fmt(opening?.high)}
              {opening && !opening.complete ? " (forming)" : ""}
            </div>
          </div>
          <div className="stat">
            <div className="stat-label">MACD hist</div>
            <div className="stat-value">
              {fmt(macd?.hist, 3)}
              {macd?.bottomSignal ? " ⚡" : ""}
            </div>
          </div>
          <div className="stat">
            <div className="stat-label">Data</div>
            <div className="stat-value">{state.marketDataType}</div>
          </div>
        </div>
      )}

      {verdict && (
        <div className="panel">
          <h3>
            Entry checks <span className="muted">— {verdict.reason}</span>
          </h3>
          <ul className="checks">
            {verdict.checks.map((c) => (
              <li key={c.key} className={c.pass ? "check-pass" : "check-fail"}>
                <span className="check-mark">{c.pass ? "✓" : "✗"}</span>
                {c.label}
                {c.detail && <span className="muted"> — {c.detail}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {spread && (
        <div className="panel">
          <div className="panel-title-row">
            <h3>
              {spread.found
                ? "Qualifying spread (equal $100 widths, net debit < $" +
                  Math.round(spread.netDebitCapUsd) +
                  ")"
                : "No qualifying spread — WAIT"}
            </h3>
            <label className="contracts-input">
              Contracts
              <input
                type="number"
                min="1"
                max="100"
                value={contracts}
                onChange={(e) =>
                  setContracts(Math.max(1, Number(e.target.value) || 1))
                }
              />
            </label>
          </div>

          {!spread.found && (
            <p className="warn">
              {spread.reason}
              {spread.closest &&
                ` — closest: net ${spread.closest.net?.perComboUsd >= 0 ? "debit" : "credit"} $${Math.abs(
                  spread.closest.net?.perComboUsd ?? 0
                ).toFixed(0)} per combo`}
            </p>
          )}

          {(spread.found ? spread : spread.closest) && (
            <>
              <SpreadSummary
                spread={spread.found ? spread : { ...spread, ...spread.closest }}
              />
              <div className="spread-body">
                <SpreadTable
                  legs={(spread.found ? spread : spread.closest).legs}
                />
                <PayoffChart
                  payoff={(spread.found ? spread : spread.closest).payoff}
                  breakevens={(spread.found ? spread : spread.closest).breakevens}
                  spot={spread.center}
                  title={`P&L at expiration — ${contracts} combo${contracts > 1 ? "s" : ""}`}
                />
              </div>
            </>
          )}

          {spread.warnings?.length > 0 && (
            <p className="warn">⚠ {spread.warnings.join(" · ")}</p>
          )}

          {spread.found && spread.alternatives?.length > 0 && (
            <p className="muted">
              Alternatives:{" "}
              {spread.alternatives
                .map(
                  (a) =>
                    `${a.callSpread}C + ${a.putSpread}P (net $${a.netUsd.toFixed(0)})`
                )
                .join(" · ")}
            </p>
          )}
        </div>
      )}

      {spread?.found && (
        <OrderTicketPanel
          strategyId={STRATEGY_ID}
          expiryRaw={spread.expiryRaw}
          contracts={contracts}
        />
      )}
    </div>
  );
}

export default Screener;
