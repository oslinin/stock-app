import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { errorMessage } from "../api/client";
import {
  addWatchlistSymbol,
  listScreeners,
  listWatchlist,
  removeWatchlistSymbol,
  runScreener,
} from "../api/watchlist";
import { hasBackend } from "../config";
import BackendOffline from "../components/BackendOffline.jsx";

const fmt = (v, digits = 2) =>
  v === null || v === undefined ? "–" : Number(v).toFixed(digits);
const pct = (v, digits = 1) =>
  v === null || v === undefined ? "–" : `${(Number(v) * 100).toFixed(digits)}%`;

function Watchlist() {
  const [connected, setConnected] = useState(hasBackend());
  const [items, setItems] = useState([]);
  const [symbolInput, setSymbolInput] = useState("");
  const [screeners, setScreeners] = useState([]);
  const [screenerId, setScreenerId] = useState("");
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(false);

  const refresh = useCallback(async () => {
    if (!hasBackend()) return;
    setError(null);
    try {
      const [watchlist, screenerList] = await Promise.all([
        listWatchlist(),
        listScreeners(),
      ]);
      setItems(watchlist);
      setScreeners(screenerList);
      setScreenerId((prev) => prev || screenerList[0]?.id || "");
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    if (!connected) return undefined;
    const kickoff = setTimeout(refresh, 0);
    return () => clearTimeout(kickoff);
  }, [connected, refresh]);

  if (!connected) {
    return (
      <div className="screener">
        <h1>Watchlist &amp; Screeners</h1>
        <BackendOffline onSaved={() => setConnected(hasBackend())} />
      </div>
    );
  }

  const addSymbol = async (e) => {
    e.preventDefault();
    const symbol = symbolInput.trim().toUpperCase();
    if (!symbol) return;
    try {
      await addWatchlistSymbol({ symbol });
      setSymbolInput("");
      refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const removeSymbol = async (symbol) => {
    try {
      await removeWatchlistSymbol(symbol);
      refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const run = async () => {
    if (!screenerId) return;
    setRunning(true);
    setError(null);
    try {
      setResults(await runScreener(screenerId));
    } catch (err) {
      setError(errorMessage(err));
      setResults(null);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="screener">
      <h1>Watchlist &amp; Screeners</h1>
      {error && <p className="error">{error}</p>}

      <div className="panel">
        <h3>Watchlist</h3>
        <form className="filter-row" onSubmit={addSymbol}>
          <input
            value={symbolInput}
            onChange={(e) => setSymbolInput(e.target.value)}
            placeholder="symbol, e.g. AAPL"
            size={10}
          />
          <button type="submit">Add</button>
        </form>
        {items.length === 0 && <p className="muted">No symbols yet.</p>}
        {items.length > 0 && (
          <div className="watchlist-chips">
            {items.map((item) => (
              <span key={item.symbol} className="watchlist-chip">
                {item.symbol}
                <button
                  type="button"
                  className="ghost"
                  onClick={() => removeSymbol(item.symbol)}
                  aria-label={`Remove ${item.symbol}`}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
        <p className="muted">
          A nightly scan samples each symbol's chain into symbol_metrics; screeners
          below rank the most recent scan.
        </p>
      </div>

      <div className="panel">
        <h3>Screeners</h3>
        <div className="filter-row">
          <label>
            screener
            <select value={screenerId} onChange={(e) => setScreenerId(e.target.value)}>
              {screeners.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <button type="button" onClick={run} disabled={running || !screenerId}>
            {running ? "running…" : "Run"}
          </button>
        </div>
        {screeners.find((s) => s.id === screenerId) && (
          <p className="muted">{screeners.find((s) => s.id === screenerId).description}</p>
        )}

        {results && results.length === 0 && (
          <p className="muted">
            No matches yet — the nightly scan may not have run, or no watchlist
            symbol clears this screener's bar.
          </p>
        )}
        {results && results.length > 0 && (
          <table className="legs-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Px</th>
                <th>IV rank</th>
                <th>Premium yield</th>
                <th>Δ</th>
                <th>DTE</th>
                <th>OI</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={r.symbol}>
                  <td>{r.symbol}</td>
                  <td>{fmt(r.underlying_px)}</td>
                  <td>{r.iv_rank != null ? r.iv_rank.toFixed(0) : "–"}</td>
                  <td>{pct(r.premium_yield, 3)}</td>
                  <td>{fmt(r.sampled_delta, 3)}</td>
                  <td>{r.sampled_dte ?? "–"}</td>
                  <td>{r.open_interest ?? "–"}</td>
                  <td>
                    <Link className="ghost" to={`/chain?symbol=${r.symbol}`}>
                      open chain
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default Watchlist;
