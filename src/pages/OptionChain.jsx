import React, { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage } from "../api/client";
import { getChain, getExpiries, getProviders } from "../api/marketdata";
import { hasBackend } from "../config";
import BackendOffline from "../components/BackendOffline.jsx";
import ProvenanceBadge from "../components/ProvenanceBadge.jsx";

const fmt = (v, digits = 2) =>
  v === null || v === undefined ? "–" : Number(v).toFixed(digits);

// rows arrive flat (one per contract); the classic chain view is one row
// per strike with call columns on the left, put columns on the right
function byStrike(rows) {
  const strikes = new Map();
  for (const r of rows) {
    const entry = strikes.get(r.strike) || { strike: r.strike };
    entry[r.right === "C" ? "call" : "put"] = r;
    strikes.set(r.strike, entry);
  }
  return [...strikes.values()].sort((a, b) => a.strike - b.strike);
}

// nearest listed strike to spot — strikes rarely land on the exact spot
// price, so "at the money" has to mean closest, not equal
function nearestStrike(rows, spot) {
  if (spot == null || rows.length === 0) return null;
  return rows.reduce((best, r) =>
    Math.abs(r.strike - spot) < Math.abs(best.strike - spot) ? r : best
  ).strike;
}

function Side({ leg, greeksFirst }) {
  const cells = [
    <td key="iv">{leg?.iv != null ? (leg.iv * 100).toFixed(1) + "%" : "–"}</td>,
    <td key="delta">{fmt(leg?.delta, 3)}</td>,
    <td key="bid">{fmt(leg?.bid)}</td>,
    <td key="ask">{fmt(leg?.ask)}</td>,
    <td key="oi">{leg?.openInterest != null ? leg.openInterest : "–"}</td>,
  ];
  return greeksFirst ? cells : cells.reverse();
}

function OptionChain() {
  const [connected, setConnected] = useState(hasBackend());
  const [symbol, setSymbol] = useState("SPY");
  const [pending, setPending] = useState("SPY");
  const [source, setSource] = useState("");
  const [providers, setProviders] = useState([]);
  const [expiries, setExpiries] = useState([]);
  const [expiry, setExpiry] = useState("");
  const [chain, setChain] = useState(null);
  const [provenance, setProvenance] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const scrollRef = useRef(null);
  const atmCellRef = useRef(null);

  useEffect(() => {
    if (!connected) return;
    getProviders()
      .then((list) => setProviders(list.filter((p) => p.capabilities.includes("chain"))))
      .catch(() => setProviders([]));
  }, [connected]);

  const loadExpiries = useCallback(async () => {
    if (!hasBackend() || !symbol) return;
    setError(null);
    try {
      const res = await getExpiries(symbol, source || undefined);
      setExpiries(res.data);
      setExpiry((prev) => (res.data.includes(prev) ? prev : res.data[0] || ""));
    } catch (err) {
      setExpiries([]);
      setChain(null);
      setError(errorMessage(err));
    }
  }, [symbol, source]);

  useEffect(() => {
    if (!connected) return undefined;
    const kickoff = setTimeout(loadExpiries, 0);
    return () => clearTimeout(kickoff);
  }, [connected, loadExpiries]);

  const loadChain = useCallback(async () => {
    if (!hasBackend() || !symbol || !expiry) return;
    setLoading(true);
    setError(null);
    try {
      const res = await getChain(symbol, { expiry, source: source || undefined });
      setChain(res.data);
      setProvenance(res.provenance);
    } catch (err) {
      setChain(null);
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [symbol, expiry, source]);

  useEffect(() => {
    if (!connected || !expiry) return undefined;
    const kickoff = setTimeout(loadChain, 0);
    return () => clearTimeout(kickoff);
  }, [connected, expiry, loadChain]);

  const rows = chain ? byStrike(chain.rows) : [];
  const spot = chain?.spot;
  const atmStrike = nearestStrike(rows, spot);

  const jumpToAtm = useCallback((behavior = "auto") => {
    const container = scrollRef.current;
    const cell = atmCellRef.current;
    if (!container || !cell) return;
    container.scrollTo({
      top: Math.max(0, cell.offsetTop - container.clientHeight / 2 + cell.clientHeight / 2),
      left: Math.max(0, cell.offsetLeft - container.clientWidth / 2 + cell.clientWidth / 2),
      behavior,
    });
  }, []);

  // center the strike ladder on the ATM row/column as soon as a chain loads
  // — without this the table opens at its lowest strike, often far from spot
  useEffect(() => {
    if (!chain) return;
    const raf = requestAnimationFrame(() => jumpToAtm("auto"));
    return () => cancelAnimationFrame(raf);
  }, [chain, jumpToAtm]);

  if (!connected) {
    return (
      <div className="screener">
        <h1>Option Chain</h1>
        <BackendOffline onSaved={() => setConnected(hasBackend())} />
      </div>
    );
  }

  return (
    <div className="screener chain-page">
      <div className="screener-header">
        <h1>Option Chain</h1>
        {provenance && <ProvenanceBadge provenance={provenance} />}
      </div>
      {error && <p className="error">{error}</p>}
      <div className="panel">
        <form
          className="filter-row"
          onSubmit={(e) => {
            e.preventDefault();
            setSymbol(pending.trim().toUpperCase());
          }}
        >
          <label>
            symbol
            <input
              value={pending}
              onChange={(e) => setPending(e.target.value)}
              size={6}
            />
          </label>
          <label>
            source
            <select value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="">auto</option>
              {providers.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name} ({p.latency})
                </option>
              ))}
            </select>
          </label>
          <label>
            expiry
            <select value={expiry} onChange={(e) => setExpiry(e.target.value)}>
              {expiries.map((e) => (
                <option key={e} value={e}>
                  {e}
                </option>
              ))}
            </select>
          </label>
          <button type="submit">Load</button>
          {spot != null && (
            <span className="chain-spot">
              {chain.symbol} <strong>{fmt(spot)}</strong>
            </span>
          )}
          {atmStrike != null && (
            <button type="button" className="ghost" onClick={() => jumpToAtm("smooth")}>
              ↕ jump to ATM
            </button>
          )}
        </form>
        {loading && <p className="muted">loading chain…</p>}
        {!loading && rows.length > 0 && (
          <>
            <p className="chain-hint muted">
              scroll to see more strikes and the full calls/puts spread — the
              row highlighted in the ATM color is the strike nearest spot
            </p>
            <div className="chain-scroll" ref={scrollRef}>
              <table className="chain-table">
                <thead>
                  <tr>
                    <th colSpan={5} className="side-label side-label-calls">
                      Calls
                    </th>
                    <th className="strike-header">Strike</th>
                    <th colSpan={5} className="side-label side-label-puts">
                      Puts
                    </th>
                  </tr>
                  <tr>
                    <th>OI</th>
                    <th>Ask</th>
                    <th>Bid</th>
                    <th>Δ</th>
                    <th>IV</th>
                    <th />
                    <th>IV</th>
                    <th>Δ</th>
                    <th>Bid</th>
                    <th>Ask</th>
                    <th>OI</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const isAtm = r.strike === atmStrike;
                    return (
                      <tr key={r.strike} className={isAtm ? "atm-row" : ""}>
                        <Side leg={r.call} greeksFirst={false} />
                        <td
                          className="strike-cell"
                          ref={isAtm ? atmCellRef : null}
                        >
                          {r.strike}
                          {isAtm && <span className="atm-tag">ATM</span>}
                        </td>
                        <Side leg={r.put} greeksFirst={true} />
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
        {!loading && chain && rows.length === 0 && (
          <p className="muted">Empty chain for {expiry}.</p>
        )}
      </div>
    </div>
  );
}

export default OptionChain;
